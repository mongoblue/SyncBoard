"""TestExecutionService — orchestrates real test execution for DevOps tasks.

Phase 2B enhancements:
- Performance runner (Locust) integration
- Scheduled task registration via Celery beat
- Cooperative cancellation with cancellation flag
- Standardised structured logs with event schema
- Unified runner-unavailable error format
- Execution context for future Pipeline→TestTask integration
"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db.models.functions import Coalesce
from django.utils import timezone

from qa_center.api_execution.runtime_guard import RuntimeGuard
from qa_center.models import (
    ApiAutoTestCase, ApiAutoTestResult, TestResult, TestTask, UiTestCase,
)

logger = logging.getLogger(__name__)

# ── Sensitive-key redaction ─────────────────────────────────────────────

_SENSITIVE_KEYS = frozenset({
    'token', 'secret', 'authorization', 'cookie', 'set_cookie',
    'api_token', 'ci_token', 'password', 'access_key', 'private_key',
    'api_key', 'auth', 'credential',
})

# ── Runner-unavailable error format ─────────────────────────────────────

def runner_unavailable_error(runner_type: str) -> dict:
    """Standardised error dict when a runner is not configured or available."""
    return {
        'status': 'failed',
        'error_code': f'{runner_type}_runner_unavailable',
        'error_message': f'{runner_type} 测试执行器未配置或不可用',
        'runner_type': runner_type,
        'data_quality': 'unavailable',
    }


# ── Structured log builder ──────────────────────────────────────────────

def _build_log_event(*, timestamp: str = '', level: str = 'info',
                     phase: str = '', runner_type: str = '',
                     message: str = '', case_id: Any = None,
                     status: str = '', duration_ms: int = 0,
                     error_type: str = '', error_message: str = '',
                     **extra) -> dict:
    """Build a single structured log event."""
    event = {
        'timestamp': timestamp or timezone.now().isoformat(),
        'level': level,
        'phase': phase,
        'runner_type': runner_type,
        'message': message,
    }
    if case_id is not None:
        event['case_id'] = case_id
    if status:
        event['status'] = status
    if duration_ms:
        event['duration_ms'] = duration_ms
    if error_type:
        event['error_type'] = error_type
    if error_message:
        event['error_message'] = error_message[:300]
    event.update({k: v for k, v in extra.items() if v is not None})
    return event


def _sanitize_dict(d: dict) -> dict:
    """Return a shallow copy with sensitive keys redacted."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if isinstance(k, str):
            normalized = k.lower().replace('-', '_')
            if normalized in _SENSITIVE_KEYS:
                out[k] = '[redacted]'
                continue
        if isinstance(v, dict):
            out[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_dict(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def _build_structured_log(results: List[dict], summary: dict,
                          events: Optional[List[dict]] = None) -> str:
    """Build a JSON structured log, sanitised."""
    payload = {
        'summary': summary,
        'results': results,
    }
    if events:
        payload['events'] = events
    sanitised = _sanitize_dict(payload)
    return json.dumps(sanitised, ensure_ascii=False, indent=2)


def _error_message_safe(exc: Exception) -> str:
    """Return exc message without traceback or sensitive data."""
    msg = str(exc)
    if len(msg) > 500:
        msg = msg[:497] + '...'
    return msg


# ── Cron validation ─────────────────────────────────────────────────────

_CRON_RE = re.compile(
    r'^(\*|(\d+(-\d+)?(/\d+)?)|\*/\d+)( (\*|(\d+(-\d+)?(/\d+)?)|\*/\d+)){4}$'
)


def validate_cron_expression(cron_expr: str) -> bool:
    """Return True if expr looks like a valid 5-field cron string."""
    if not cron_expr or not isinstance(cron_expr, str):
        return False
    return bool(_CRON_RE.match(cron_expr.strip()))


class TaskCancelled(Exception):
    """协作取消信号：执行过程中检测到取消请求。"""


# ── Service ─────────────────────────────────────────────────────────────

class TestExecutionService:
    """Stateless service for executing DevOps test tasks and QuickTests."""

    def __init__(self):
        self._guard = RuntimeGuard()

    # ── Execution context (reserved for future Pipeline integration) ────

    def _build_context(self, *, task=None, user=None,
                       pipeline_run=None, commit_sha='', branch='',
                       trigger_source='manual', **extra) -> dict:
        """Build an execution context dict for tracing and future integration."""
        ctx = {
            'trigger_source': trigger_source,
            'runner_mode': 'celery' if getattr(settings, 'USE_CELERY_TASKS', False) else 'thread',
        }
        if pipeline_run is not None:
            ctx['pipeline_run_id'] = getattr(pipeline_run, 'id', None)
        if commit_sha:
            ctx['commit_sha'] = commit_sha
        if branch:
            ctx['branch'] = branch
        if task:
            ctx['task_id'] = task.id
        if user:
            ctx['executed_by'] = user.id
        ctx.update(extra)
        return ctx

    # ── QuickTest ───────────────────────────────────────────────────────

    def execute_quick_test(self, *, test_type: str, case_ids: List[int],
                           project_id, user) -> TestResult:
        """Execute a QuickTest and return the TestResult."""
        from room.models import Project
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise RuntimeError('项目不存在')

        test_result = TestResult.objects.create(
            test_type=test_type,
            name='QuickTest',
            source='devops',
            project=project,
            status='running',
            test_params={'type': test_type, 'case_ids': case_ids},
            executed_by=user,
            started_at=timezone.now(),
        )

        events: List[dict] = []
        ctx = self._build_context(user=user, trigger_source='quick_test')

        try:
            if test_type == 'api':
                all_results, passed, failed = self._run_api_cases(
                    case_ids, project, user, task_id='', events=events, ctx=ctx,
                )
            elif test_type == 'ui':
                all_results, passed, failed = self._run_ui_cases(case_ids)
            elif test_type == 'performance':
                all_results, passed, failed = self._run_performance_cases(
                    case_ids, project, user, events=events, task_id='',
                )
            elif test_type == 'regression':
                return self._fail_test(
                    test_result,
                    runner_unavailable_error('regression'),
                    events=events,
                )
            else:
                return self._fail_test(
                    test_result,
                    {'error_message': f'不支持的测试类型: {test_type}'},
                    events=events,
                )

            total = passed + failed
            pass_rate = round((passed / total * 100), 2) if total > 0 else 0
            execution_report = _build_structured_log(all_results, {
                'total': total, 'passed': passed, 'failed': failed,
                'pass_rate': pass_rate,
            }, events=events)

            test_result.status = 'passed' if failed == 0 else 'failed'
            test_result.completed_at = timezone.now()
            test_result.duration_ms = int(
                (test_result.completed_at - test_result.started_at).total_seconds() * 1000
            )
            test_result.test_log = execution_report
            test_result.actual_result = (
                f'通过: {passed}, 失败: {failed}, 通过率: {pass_rate}%'
            )
            test_result.save()
            return test_result

        except Exception as exc:
            return self._fail_test(
                test_result,
                {'error_message': _error_message_safe(exc)},
                events=events,
            )

    # ── TestTask orchestration ──────────────────────────────────────────

    def _check_cancelled(self, test_result: TestResult) -> None:
        """协作取消检查点：检测到取消请求（TestResult.aborted）则抛 TaskCancelled。

        执行器在每组用例之间调用；运行中的性能用例由 ExecutionWorker 自身
        轮询 aborted 标记停止。
        """
        test_result.refresh_from_db(fields=['aborted'])
        if test_result.aborted:
            raise TaskCancelled()

    def execute_test_task(self, task: TestTask, test_result: TestResult) -> None:
        """Execute all cases configured in a TestTask."""
        test_config = task.test_config or {}
        api_case_ids = test_config.get('api_cases', [])
        ui_case_ids = test_config.get('ui_cases', [])
        perf_case_ids = test_config.get('performance_cases', [])

        all_results: List[dict] = []
        passed_count = 0
        failed_count = 0
        events: List[dict] = []
        ctx = self._build_context(task=task, user=task.created_by,
                                   trigger_source='task_execution')

        try:
            self._check_cancelled(test_result)

            if api_case_ids:
                # 创建父级 ApiAutoTestResult，统一收纳所有 case 结果
                parent_auto_result = None
                try:
                    from qa_center.models import ApiAutoTestResult as AATR
                    parent_auto_result = AATR.objects.create(
                        suite=None,
                        project=task.project,
                        name=f"{task.name} - 执行 #{task.execution_count}",
                        status='running',
                        total_cases=len(api_case_ids),
                        executed_by=task.created_by,
                        started_at=timezone.now(),
                    )
                except Exception:
                    logger.exception("创建父级 ApiAutoTestResult 失败")

                api_results, api_passed, api_failed = self._run_api_cases(
                    api_case_ids, task.project, task.created_by,
                    task_id=str(task.id), events=events, ctx=ctx,
                    parent_result=parent_auto_result,
                )
                all_results.extend(api_results)
                passed_count += api_passed
                failed_count += api_failed

                # 将父级结果关联到 DevOps 任务记录
                if parent_auto_result is not None:
                    test_result.api_auto_result = parent_auto_result

            self._check_cancelled(test_result)

            if ui_case_ids:
                ui_results, ui_passed, ui_failed = self._run_ui_cases(ui_case_ids)
                all_results.extend(ui_results)
                passed_count += ui_passed
                failed_count += ui_failed

            self._check_cancelled(test_result)

            if perf_case_ids:
                perf_results, perf_passed, perf_failed = self._run_performance_cases(
                    perf_case_ids, task.project, task.created_by, events=events,
                    task_id=str(task.id),
                )
                all_results.extend(perf_results)
                passed_count += perf_passed
                failed_count += perf_failed
        except TaskCancelled:
            # 协作取消：停止执行，标记任务与结果为已取消
            test_result.status = 'cancelled'
            test_result.completed_at = timezone.now()
            test_result.error_message = '任务被手动取消'
            test_result.test_log = _build_structured_log(all_results, {
                'total': passed_count + failed_count,
                'passed': passed_count,
                'failed': failed_count,
                'pass_rate': round((passed_count / (passed_count + failed_count) * 100), 2)
                if (passed_count + failed_count) > 0 else 0,
            }, events=events)
            test_result.save()
            task.status = 'cancelled'
            task.save()
            return

        total = passed_count + failed_count
        pass_rate = round((passed_count / total * 100), 2) if total > 0 else 0
        execution_report = _build_structured_log(all_results, {
            'total': total, 'passed': passed_count, 'failed': failed_count,
            'pass_rate': pass_rate,
        }, events=events)

        test_result.status = 'passed' if failed_count == 0 else 'failed'
        test_result.completed_at = timezone.now()
        test_result.duration_ms = int(
            (test_result.completed_at - test_result.started_at).total_seconds() * 1000
        )
        test_result.test_log = execution_report
        test_result.actual_result = (
            f'通过: {passed_count}, 失败: {failed_count}, 通过率: {pass_rate}%'
        )
        test_result.save()

        from qa_center.result_sink import _select_preferred_mirror

        task_result_id = str(task.id)
        linked_result = _select_preferred_mirror(
            auto_result=test_result.api_auto_result,
            task_id=task_result_id,
            exclude_id=test_result.id,
        ) if test_result.api_auto_result_id else None
        if linked_result is None:
            linked_candidates = TestResult.objects.filter(
                project=task.project,
                created_at__gte=test_result.started_at,
            ).exclude(id=test_result.id)
            linked_result = linked_candidates.filter(task_id=task_result_id).order_by(
                Coalesce('started_at', 'created_at').desc(),
                '-created_at',
                '-id',
            ).first()
            if linked_result is None:
                linked_result = linked_candidates.filter(task_id='').order_by(
                    Coalesce('started_at', 'created_at').desc(),
                    '-created_at',
                    '-id',
                ).first()

        if linked_result is not None and linked_result.task_id != task_result_id and linked_result.task_id == '':
            linked_result.task_id = task_result_id
            linked_result.save(update_fields=['task_id'])

        task.status = 'completed' if failed_count == 0 else 'failed'
        task.last_result = linked_result or test_result
        task.save()

    # ── Internal runners ─────────────────────────────────────────────────

    def _run_api_cases(self, case_ids, project, user, task_id='',
                       events=None, ctx=None, parent_result=None):
        from qa_center.views_devops import _execute_api_cases_via_unified

        results = []; passed = 0; failed = 0
        api_results = _execute_api_cases_via_unified(
            case_ids, task_id=task_id, parent_result=parent_result,
        )
        for r in api_results:
            if 'case_name' not in r:
                r['case_name'] = f"用例 #{r.get('case_id', '?')}"
            results.append(r)
            if r.get('passed'): passed += 1
            else: failed += 1
        return results, passed, failed

    def _run_ui_cases(self, case_ids):
        from qa_center.views_devops import _execute_ui_cases_safe
        return _execute_ui_cases_safe(case_ids)

    def _run_performance_cases(self, case_ids, project, user,
                                events=None, task_id='') -> Tuple[List[dict], int, int]:
        """通过统一执行引擎同步执行性能测试用例。

        所有用例顺序执行，每个用例独立通过 ExecutionEngine.submit(async_mode=False)
        执行并收集结果。不直接接触 LocustRunner。

        Args:
            case_ids: 性能用例 ID 列表。
            project: 所属项目（用于权限校验）。
            user: 执行者。
            events: 结构化日志事件列表（原地追加）。
            task_id: DevOps 任务 ID（用于结果追踪）。

        Returns:
            (results, passed_count, failed_count)
        """
        from urllib.parse import urlparse
        from qa_center.models import PerformanceTestCase
        from qa_center.execution.job import TestJob, ExecutionResult
        from qa_center.execution.engine import ExecutionEngine

        results: List[dict] = []
        passed = 0
        failed = 0
        if events is None:
            events = []

        case_count = len(case_ids)
        for idx, cid in enumerate(case_ids):
            case_label = f"[{idx + 1}/{case_count}] 性能用例 #{cid}"

            # ── 加载用例 ──────────────────────────────────────────────
            try:
                perf_case = PerformanceTestCase.objects.get(
                    id=cid, project=project, is_active=True,
                )
            except PerformanceTestCase.DoesNotExist:
                logger.warning("%s 不存在或不属于本项目", case_label)
                results.append({
                    'case_id': cid, 'case_name': f'性能用例 #{cid}',
                    'passed': False,
                    'error_message': '性能测试用例不存在或不属于本项目',
                    'failure_type': 'config_error',
                    'error_code': 'CASE_NOT_FOUND',
                })
                failed += 1
                events.append(_build_log_event(
                    phase='performance_validation', runner_type='locust',
                    level='warning', message=f'{case_label} 不存在或不属于本项目',
                    case_id=cid, error_type='config_error',
                ))
                continue

            # ── 构建 TestJob ──────────────────────────────────────────
            parsed = urlparse(perf_case.url)
            host = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else perf_case.url

            job = TestJob.from_test_case(
                perf_case,
                host=host,
                async_mode=False,
                project=project,
                user=user,
                source='devops',
                task_id=task_id,
            )

            # ── 执行 ──────────────────────────────────────────────────
            t_start = timezone.now()
            engine = ExecutionEngine()
            try:
                exec_result = engine.submit(job)
            except Exception as exc:
                logger.exception("%s ExecutionEngine.submit 异常", case_label)
                results.append({
                    'case_id': cid, 'case_name': perf_case.name,
                    'passed': False,
                    'error_message': _error_message_safe(exc),
                    'failure_type': 'engine_error',
                    'error_code': 'ENGINE_EXCEPTION',
                })
                failed += 1
                events.append(_build_log_event(
                    phase='performance_complete', runner_type='locust',
                    level='error', message=f'{case_label} 引擎异常: {_error_message_safe(exc)}',
                    case_id=cid, error_type='engine_error',
                ))
                continue

            t_elapsed = int((timezone.now() - t_start).total_seconds() * 1000)

            # ── 类型守卫：确保拿到的是 ExecutionResult ─────────────────
            if not isinstance(exec_result, ExecutionResult):
                logger.error(
                    "%s submit() 返回非预期类型 %s（预期 ExecutionResult）",
                    case_label, type(exec_result).__name__,
                )
                results.append({
                    'case_id': cid, 'case_name': perf_case.name,
                    'passed': False,
                    'error_message': '执行引擎返回非预期结果类型',
                    'failure_type': 'engine_error',
                    'error_code': 'UNEXPECTED_RESULT_TYPE',
                })
                failed += 1
                continue

            # ── 结果判定 ──────────────────────────────────────────────
            if not exec_result.ok:
                logger.warning(
                    "%s 执行失败: %s (status=%s, duration=%dms)",
                    case_label, exec_result.error, exec_result.status, t_elapsed,
                )
                results.append({
                    'case_id': cid, 'case_name': perf_case.name,
                    'passed': False,
                    'error_message': exec_result.error or '执行引擎返回失败',
                    'failure_type': (
                        'semaphore_rejected' if '上限' in (exec_result.error or '')
                        else 'engine_error'
                    ),
                    'error_code': 'ENGINE_FAILED',
                })
                failed += 1
                events.append(_build_log_event(
                    phase='performance_complete', runner_type='locust',
                    level='error', message=f'{case_label} 引擎返回失败: {exec_result.error}',
                    case_id=cid, error_type='engine_error',
                ))
                continue

            stats = exec_result.stats
            if stats.get('total_requests', 0) == 0:
                logger.warning("%s 未收集到有效请求指标", case_label)
                results.append({
                    'case_id': cid, 'case_name': perf_case.name,
                    'passed': False,
                    'error_message': '性能测试未收集到有效指标（0 请求）',
                    'failure_type': 'no_metrics',
                    'error_code': 'ZERO_REQUESTS',
                })
                failed += 1
                events.append(_build_log_event(
                    phase='performance_complete', runner_type='locust',
                    level='warning', message=f'{case_label} 未收集到有效指标',
                    case_id=cid, error_type='no_metrics',
                ))
                continue

            # ── 成功路径 ──────────────────────────────────────────────
            avg_rt = stats.get('avg_response_time', 0) or 0
            p95 = stats.get('p95_response_time', 0) or 0
            throughput = stats.get('throughput', 0) or 0
            error_rate = stats.get('error_rate', 0) or 0
            total_req = stats.get('total_requests', 0)
            failed_req = stats.get('failed_requests', 0)
            passed_threshold = exec_result.status == 'passed'

            logger.info(
                "%s 完成: passed=%s rps=%.1f avg_rt=%.0fms p95=%.0fms err=%.2f%% "
                "total_req=%d failed_req=%d duration=%dms",
                case_label, passed_threshold, throughput, avg_rt, p95, error_rate,
                total_req, failed_req, t_elapsed,
            )

            results.append({
                'case_id': cid,
                'case_name': perf_case.name,
                'passed': passed_threshold,
                'status': exec_result.status,
                'metrics': stats,
                'request_count': total_req,
                'failure_count': failed_req,
                'avg_response_time': avg_rt,
                'p95_response_time': p95,
                'throughput': throughput,
                'error_rate': error_rate,
                'duration_ms': t_elapsed,
                'test_result_id': exec_result.test_result_id,
                'perf_result_id': exec_result.perf_result_id,
            })

            if passed_threshold:
                passed += 1
            else:
                failed += 1

            events.append(_build_log_event(
                phase='performance_complete', runner_type='locust',
                level='info',
                message=(
                    f'{case_label} 完成: '
                    f'rps={throughput:.1f} avg_rt={avg_rt:.0f}ms err={error_rate:.2f}%'
                ),
                case_id=cid,
                status='passed' if passed_threshold else 'failed',
                duration_ms=t_elapsed,
            ))

        return results, passed, failed

    # ── Test failure helper ──────────────────────────────────────────────

    def _fail_test(self, test_result: TestResult, error_info: dict,
                   events: Optional[List[dict]] = None) -> TestResult:
        test_result.status = 'failed'
        test_result.completed_at = timezone.now()
        test_result.error_message = error_info.get('error_message', '执行失败')
        log_payload = dict(error_info)
        if events:
            log_payload['events'] = events
        test_result.test_log = json.dumps(log_payload, ensure_ascii=False)
        test_result.save()
        return test_result

    # ── Validation ───────────────────────────────────────────────────────

    def validate_cases_for_project(self, case_ids: List[int], project_id,
                                     test_type: str = 'api') -> None:
        if not case_ids:
            return
        if test_type == 'ui':
            model = UiTestCase
        elif test_type == 'performance':
            from qa_center.models import PerformanceTestCase
            model = PerformanceTestCase
        else:
            model = ApiAutoTestCase
        matching = model.objects.filter(
            id__in=case_ids, project_id=project_id,
        ).values('id').distinct().count()
        if matching != len(set(int(c) for c in case_ids)):
            raise ValueError('部分测试用例不存在或不属于本项目')

    # ── Scheduled tasks (django-celery-beat backed) ──────────────────────

    _SCHEDULE_NAME_PREFIX = "qa_center.test_task"

    def check_scheduled_task_viability(self, task: TestTask) -> Optional[str]:
        if not validate_cron_expression(task.cron_expression or ''):
            return '无效的 Cron 表达式'
        return None  # DB-backed scheduling via django-celery-beat

    def _celery_beat_available(self) -> bool:
        try:
            import django_celery_beat  # noqa: F401
            return True
        except ImportError:
            return False

    def _periodic_task_name(self, task: TestTask) -> str:
        return f"{self._SCHEDULE_NAME_PREFIX}.{task.id}"

    def register_scheduled_task(self, task: TestTask) -> Optional[str]:
        """Register (or update) a DB-backed PeriodicTask via django-celery-beat.

        Returns an error message string on failure, or None on success.
        """
        if not validate_cron_expression(task.cron_expression or ''):
            return '无效的 Cron 表达式'

        if not self._celery_beat_available():
            if self._guard.is_strict():
                return 'django-celery-beat 未安装，无法注册定时任务'
            return None

        try:
            from django_celery_beat.models import CrontabSchedule, PeriodicTask

            cron_parts = task.cron_expression.strip().split()
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day_of_month=cron_parts[2],
                month_of_year=cron_parts[3],
                day_of_week=cron_parts[4],
            )

            defaults = {
                'crontab': schedule,
                'task': 'qa_center.execute_test_task',
                'args': json.dumps([task.id]),
                'enabled': task.is_active,
                'description': f'Scheduled TestTask: {task.name}',
            }

            pt, created = PeriodicTask.objects.update_or_create(
                name=self._periodic_task_name(task),
                defaults=defaults,
            )
            logger.info(
                'PeriodicTask %s (id=%s) for TestTask %s',
                'created' if created else 'updated', pt.id, task.id,
            )
            return None

        except Exception as exc:
            logger.warning('Failed to register scheduled task %s: %s', task.id, exc)
            return f'注册定时任务失败: {exc}'

    def unregister_scheduled_task(self, task: TestTask) -> None:
        """Remove the PeriodicTask for a TestTask."""
        try:
            from django_celery_beat.models import PeriodicTask
            PeriodicTask.objects.filter(name=self._periodic_task_name(task)).delete()
        except Exception:
            pass

    def sync_scheduled_task_enabled(self, task: TestTask) -> None:
        """Sync TestTask.is_active to the matching PeriodicTask.enabled."""
        try:
            from django_celery_beat.models import PeriodicTask
            PeriodicTask.objects.filter(name=self._periodic_task_name(task)).update(
                enabled=task.is_active,
            )
        except Exception:
            pass

    # ── Task result resolution ───────────────────────────────────────────

    def _resolve_task_result(self, task: TestTask) -> Optional[TestResult]:
        task_result_id = str(task.id)
        linked = TestResult.objects.filter(
            project=task.project,
            task_id=task_result_id,
        ).order_by(
            Coalesce('started_at', 'created_at').desc(),
            '-created_at',
            '-id',
        ).first()
        if linked is not None:
            return linked
        fallback = task.last_result
        if fallback is None:
            return None
        if fallback.project_id != task.project_id:
            return None
        if fallback.api_auto_result_id and fallback.task_id not in {'', task_result_id}:
            return None
        return fallback

    # ── Cancel ────────────────────────────────────────────────────────────

    def cancel_task(self, task: TestTask) -> dict:
        """Cancel a running task. Returns status info dict.

        协作取消：置取消信号（TestResult.aborted）+ 标记任务/结果为已取消。
        - 运行中的性能用例：ExecutionWorker 轮询 aborted 自动停止
        - API/UI 批次：execute_test_task 的批次间检查点停止后续用例
        """
        if task.status != 'running':
            return {
                'cancelled': False,
                'cancel_mode': 'rejected',
                'reason': '只能取消正在执行中的任务',
            }

        # 置取消信号并标记所有运行中结果
        task.status = 'cancelled'
        task.save(update_fields=['status'])

        cancelled_count = 0

        def _mark_cancelled(active: TestResult) -> None:
            nonlocal cancelled_count
            active.aborted = True
            active.status = 'cancelled'
            active.error_message = '任务被手动取消'
            active.completed_at = timezone.now()
            active.save(update_fields=[
                'aborted', 'status', 'error_message', 'completed_at',
            ])
            cancelled_count += 1

        for active in TestResult.objects.filter(
            task_id=str(task.id), status='running',
        ):
            _mark_cancelled(active)

        # 兼容老数据：last_result 链路的结果可能未带 task_id
        fallback = self._resolve_task_result(task)
        if fallback is not None and fallback.status == 'running' and not fallback.aborted:
            _mark_cancelled(fallback)

        return {
            'cancelled': True,
            'cancel_mode': 'cooperative',
            'cancelled_results': cancelled_count,
            'message': '已发送取消信号，运行中的用例将尽快停止',
        }

    # ── Logs ──────────────────────────────────────────────────────────────

    def get_task_logs(self, task: TestTask) -> Optional[dict]:
        last = self._resolve_task_result(task)
        if not last or not last.test_log:
            if last:
                return {
                    'task_id': task.id,
                    'status': task.status,
                    'execution_count': task.execution_count,
                    'last_result_id': last.id,
                    'last_result_status': last.status,
                    'error_message': last.error_message or '',
                    'logs': [],
                }
            return None

        try:
            parsed = json.loads(last.test_log)
        except (json.JSONDecodeError, TypeError):
            parsed = {'raw': str(last.test_log)[:2000]}

        return {
            'task_id': task.id,
            'status': task.status,
            'execution_count': task.execution_count,
            'last_result_id': last.id,
            'last_result_status': last.status,
            'error_message': last.error_message or '',
            'logs': _sanitize_dict(parsed) if isinstance(parsed, dict) else parsed,
        }
