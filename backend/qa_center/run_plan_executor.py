"""
批量执行计划（TestRunPlan）执行器。

特性：

特性：
- 串行 / 并发（ThreadPoolExecutor）
- 所有用例共享一个 requests.Session（cookie/连接复用）
- 每完成一条用例通过 WebSocket 推送进度到项目作用域 group `qa_dashboard_<project_id>`
- 支持 stop_on_failure：遇到失败立刻取消后续未开始的任务
- 单用例独立 timeout（用例级 timeout_seconds，可被 plan.case_timeout_seconds 覆盖）

不直接复用 ApiAutoTestExecutor 是因为后者绑定 suite_id 概念，且使用模块级 requests.request（无 Session）。
本执行器与之共存，未来 M3 可以把两者合并。
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from threading import Event, Lock
from typing import Any, Dict, Optional, List

import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.utils import timezone

from .api_auto_executor import AssertionExecutor
from .bug_utils import create_bug_from_test_failure
from .models import (
    ApiAutoTestCase,
    ApiAutoTestResult,
    ApiAutoTestCaseResult,
    ApiAutoTestSuite,
    TestRunPlan,
)
from . import unified_assertions as ua
from . import template_engine as te
from . import extractors as ex_engine
from . import request_builder as rb

logger = logging.getLogger(__name__)


def _broadcast(event: dict, *, project_id: int) -> None:
    """向项目作用域 QA dashboard 组广播一条进度事件。channels 不可用时静默忽略。"""
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(f'qa_dashboard_{project_id}', event)
    except Exception as e:  # pragma: no cover
        logger.debug('[RunPlan] broadcast failed: %s', e)


def _get_or_create_plan_suite(plan: TestRunPlan) -> ApiAutoTestSuite:
    """ApiAutoTestResult.suite 是 NOT NULL 外键，给每个 plan 准备一个占位 suite。

    我们用 name='__run_plan__#<plan_id>' 标识，避免和真实套件混淆。"""
    suite, _ = ApiAutoTestSuite.objects.get_or_create(
        project=plan.project,
        name=f'__run_plan__#{plan.id}',
        defaults={
            'description': f'TestRunPlan #{plan.id} 占位套件，请勿手工修改',
            'is_active': False,
            'created_by': plan.created_by,
        },
    )
    return suite


class TestRunPlanExecutor:
    def __init__(
        self,
        plan: TestRunPlan,
        user: Optional[User] = None,
        *,
        parallel: Optional[bool] = None,
        max_workers: Optional[int] = None,
        stop_on_failure: Optional[bool] = None,
        environment_id: Optional[int] = None,
    ):
        self.plan = plan
        self.user = user
        self.parallel = parallel if parallel is not None else plan.parallel
        self.max_workers = max(1, min(32, max_workers if max_workers is not None else plan.max_workers))
        self.stop_on_failure = stop_on_failure if stop_on_failure is not None else plan.stop_on_failure
        self.timeout = plan.case_timeout_seconds

        # M3.2: 解析运行环境 + 全局变量，预先合并成变量池
        env = te.resolve_project_environment(
            plan.project,
            env_id=environment_id if environment_id is not None else (plan.environment_id if plan.environment_id else None),
        )
        globals_ = te.load_project_globals(plan.project)
        self._variables = te.build_variable_pool(environment=env, global_vars=globals_)
        self._environment = env

        # M3.3: 用例间抽取变量。串行下逐条注入；并行下保留抽取但日志警告"不会传递"
        self._extracted: Dict[str, Any] = {}
        self._extracted_lock = Lock()

        self.test_result: Optional[ApiAutoTestResult] = None
        self._session: Optional[requests.Session] = None
        self._stop_event = Event()
        self._counter_lock = Lock()
        self._completed = 0
        self._passed = 0
        self._failed = 0
        self._error = 0

    # ---------- public ----------

    def execute(self) -> ApiAutoTestResult:
        cases = self._load_cases()
        total = len(cases)

        suite = _get_or_create_plan_suite(self.plan)
        execution_name = f'{self.plan.name}_{timezone.now().strftime("%Y%m%d_%H%M%S")}'
        self.test_result = ApiAutoTestResult.objects.create(
            suite=suite,
            name=execution_name,
            status='running',
            total_cases=total,
            executed_by=self.user,
            started_at=timezone.now(),
        )

        _broadcast({
            'type': 'run_plan_progress',
            'plan_id': self.plan.id,
            'result_id': self.test_result.id,
            'phase': 'started',
            'total': total,
            'completed': 0,
            'passed': 0,
            'failed': 0,
            'error': 0,
        }, project_id=self.plan.project_id)

        self._session = requests.Session()
        try:
            if self.parallel and total > 1:
                # M3.3: 并行模式下后续 case 拿不到前 case 的抽取值（无确定执行顺序）
                if any(c.extractors.filter(is_active=True).exists() for c in cases):
                    logger.warning(
                        '[RunPlan #%s] 并发模式下变量抽取仅本地记录，不会注入到后续用例。'
                        '如需链式传递请改用串行执行。',
                        self.plan.id,
                    )
                self._run_parallel(cases)
            else:
                self._run_serial(cases)
        finally:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

        self._finalize()
        self._auto_create_bugs()
        return self.test_result

    # ---------- runners ----------

    def _run_serial(self, cases: List[ApiAutoTestCase]) -> None:
        for case in cases:
            if self._stop_event.is_set():
                break
            self._execute_one(case)

    def _run_parallel(self, cases: List[ApiAutoTestCase]) -> None:
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix='runplan') as pool:
            futures: List[Future] = [pool.submit(self._execute_one, case) for case in cases]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:  # pragma: no cover - _execute_one 已自己吞异常
                    logger.exception('[RunPlan] case future raised: %s', e)
                if self._stop_event.is_set():
                    # 取消尚未开始的任务
                    for f in futures:
                        if not f.done() and not f.running():
                            f.cancel()

    # ---------- core ----------

    def _execute_one(self, case: ApiAutoTestCase) -> None:
        if self._stop_event.is_set():
            return

        response_body = ''
        response_headers: dict = {}
        status_code = 0
        response_time_ms = 0
        passed = False
        assertion_details: list = []
        error_message = ''
        extracted_now: Dict[str, Any] = {}

        timeout = case.timeout_seconds or self.timeout
        try:
            headers = dict(case.headers or {})
            if case.content_type and 'Content-Type' not in headers:
                headers['Content-Type'] = case.content_type

            # M3.2 + M3.3: 渲染时合并基础变量池与之前 case 抽取出的变量
            with self._extracted_lock:
                render_pool = dict(self._variables)
                render_pool.update(self._extracted)

            url = te.resolve_url(case.url, render_pool)
            headers = te.render_value(headers, render_pool)
            raw_body = te.render_string(case.body or '', render_pool)

            # M3.4: query 参数 + 文件上传
            params = rb.normalize_query_params(case.query_params, render_pool)
            files = rb.build_file_tuples(case.form_files, render_pool)

            body_json = None
            body_data = None
            if raw_body and case.method in ('POST', 'PUT', 'PATCH'):
                if case.content_type == 'application/json':
                    try:
                        body_json = json.loads(raw_body)
                    except json.JSONDecodeError:
                        body_data = raw_body
                else:
                    body_data = raw_body

            # M3.4: 上传文件时去掉用户写死的 Content-Type，让 requests 自己生成 multipart boundary
            if files:
                headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}
                # multipart 与 json 互斥；body 作为表单数据合并到 data=
                if body_json is not None:
                    body_data = body_json if isinstance(body_json, dict) else None
                    body_json = None

            # M3.4: 是否复用计划级 Session
            transport = self._session if case.enable_cookie_session else requests
            start = time.time()
            response = transport.request(
                method=case.method,
                url=url,
                headers=headers,
                params=params,
                json=body_json,
                data=body_data,
                files=files,
                timeout=timeout,
            )
            response_time_ms = int((time.time() - start) * 1000)
            status_code = response.status_code

            try:
                response_body = response.text
                response_data = response.json() if response.text else {}
            except (json.JSONDecodeError, ValueError):
                response_data = {'raw': response.text}

            response_headers = dict(response.headers)

            active_assertions = list(case.assertions.filter(is_active=True).order_by('sort_order', 'id'))
            ctx = ua.ResponseContext.from_raw(
                status_code=status_code,
                response_body=response_body,
                response_headers=response_headers,
                response_time_ms=response_time_ms,
            )
            assertion_details = ua.run_assertions(active_assertions, ctx)
            all_passed = all(r.get('passed') for r in assertion_details) if assertion_details else True

            has_status_code_assertion = any(
                getattr(a, 'assertion_type', None) == 'status_code' for a in active_assertions
            )
            if not has_status_code_assertion and case.expected_status and status_code != case.expected_status:
                all_passed = False
                assertion_details.insert(0, {
                    'assertion_type': 'status_code',
                    'expected_value': case.expected_status,
                    'actual_value': status_code,
                    'passed': False,
                    'error_message': f'Expected status {case.expected_status}, got {status_code}',
                })

            passed = all_passed

            # M3.3: 执行变量抽取。
            # 优先用 ctx.response_json（已经做过 JSON 解析），失败时退到 response_data。
            json_for_extract = ctx.response_json if ctx.response_json is not None else (
                response_data if isinstance(response_data, (dict, list)) else None
            )
            active_extractors = list(case.extractors.filter(is_active=True).order_by('sort_order', 'id'))
            if active_extractors:
                extracted_now = ex_engine.run_extractors(
                    active_extractors,
                    response_json=json_for_extract,
                    response_headers=response_headers,
                    status_code=status_code,
                    cookies=dict(response.cookies) if hasattr(response, 'cookies') else {},
                    response_time_ms=response_time_ms,
                )
                # 串行：合并到 _extracted；并行：抽取了但不传递（已在 execute() 入口告警）
                if not self.parallel:
                    with self._extracted_lock:
                        self._extracted.update(extracted_now)

        except requests.exceptions.Timeout:
            error_message = f'Request timeout after {timeout}s'
        except requests.exceptions.ConnectionError as e:
            error_message = f'Connection error: {e}'
        except Exception as e:
            error_message = f'Request execution error: {e}'

        ApiAutoTestCaseResult.objects.create(
            test_result=self.test_result,
            case=case,
            status_code=status_code,
            response_body=response_body[:10000],
            response_headers=response_headers,
            response_time_ms=response_time_ms,
            passed=passed,
            assertion_details=assertion_details,
            error_message=error_message,
        )

        self._bump_counters(passed=passed, has_error=bool(error_message))
        self._broadcast_progress(
            case=case, passed=passed, error_message=error_message,
            extracted=extracted_now,
        )

        if not passed and self.stop_on_failure:
            self._stop_event.set()

    # ---------- helpers ----------

    def _load_cases(self) -> List[ApiAutoTestCase]:
        ids = list(self.plan.case_ids or [])
        if not ids:
            return []
        # 保持用户给的顺序
        cases_by_id = {
            c.id: c
            for c in ApiAutoTestCase.objects
            .filter(id__in=ids, is_active=True)
            .prefetch_related('assertions', 'extractors')
        }
        return [cases_by_id[i] for i in ids if i in cases_by_id]

    def _bump_counters(self, *, passed: bool, has_error: bool) -> None:
        with self._counter_lock:
            self._completed += 1
            if passed:
                self._passed += 1
            elif has_error:
                self._error += 1
            else:
                self._failed += 1

    def _broadcast_progress(self, *, case: ApiAutoTestCase, passed: bool, error_message: str,
                            extracted: Optional[Dict[str, Any]] = None) -> None:
        with self._counter_lock:
            snapshot = {
                'completed': self._completed,
                'passed': self._passed,
                'failed': self._failed,
                'error': self._error,
            }
        event = {
            'type': 'run_plan_progress',
            'plan_id': self.plan.id,
            'result_id': self.test_result.id if self.test_result else None,
            'phase': 'case_done',
            'total': self.test_result.total_cases if self.test_result else 0,
            'case_id': case.id,
            'case_name': case.name,
            'case_passed': passed,
            'case_error': error_message[:300] if error_message else '',
            'passed': snapshot['passed'],
            'failed': snapshot['failed'],
            'error': snapshot['error'],
            'completed': snapshot['completed'],
            'last_error': error_message[:300] if error_message else '',
        }
        if extracted:
            event['extracted'] = ex_engine.summarize_extractions(extracted)
        _broadcast(event, project_id=self.plan.project_id)

    def _finalize(self) -> None:
        assert self.test_result is not None
        duration = int((timezone.now() - self.test_result.started_at).total_seconds() * 1000)
        if self._error > 0:
            final = 'error'
        elif self._failed > 0:
            final = 'failed'
        else:
            final = 'passed'

        self.test_result.passed_cases = self._passed
        self.test_result.failed_cases = self._failed
        self.test_result.error_cases = self._error
        self.test_result.duration_ms = duration
        self.test_result.status = final
        self.test_result.completed_at = timezone.now()
        if self._stop_event.is_set():
            self.test_result.error_message = '遇到失败已中止后续用例'
        self.test_result.save()

        _broadcast({
            'type': 'run_plan_progress',
            'plan_id': self.plan.id,
            'result_id': self.test_result.id,
            'phase': 'finished',
            'status': final,
            'total': self.test_result.total_cases,
            'completed': self._completed,
            'passed': self._passed,
            'failed': self._failed,
            'error': self._error,
            'duration_ms': duration,
        }, project_id=self.plan.project_id)

    def _auto_create_bugs(self) -> None:
        if not self.test_result or self.test_result.status not in ('failed', 'error'):
            return
        failed = ApiAutoTestCaseResult.objects.filter(
            test_result=self.test_result, passed=False,
        ).select_related('case__suite__project')
        for fr in failed:
            try:
                create_bug_from_test_failure(fr.case, self.test_result, error_message=fr.error_message or '')
            except Exception as bug_err:  # pragma: no cover
                logger.warning('[RunPlan][AutoBug] %s', bug_err)


def run_plan(
    plan_id: int,
    user: Optional[User] = None,
    *,
    parallel: Optional[bool] = None,
    max_workers: Optional[int] = None,
    stop_on_failure: Optional[bool] = None,
    environment_id: Optional[int] = None,
) -> ApiAutoTestResult:
    plan = TestRunPlan.objects.select_related('project', 'created_by').get(id=plan_id)
    executor = TestRunPlanExecutor(
        plan, user,
        parallel=parallel,
        max_workers=max_workers,
        stop_on_failure=stop_on_failure,
        environment_id=environment_id,
    )
    return executor.execute()
