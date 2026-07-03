"""
ExecutionEngine — 压力测试统一执行入口（编排层）。

三层架构中的顶层：
    Engine  →  创建 Job + 调度 Worker + 持久化结果
    Worker  →  管理单次测试生命周期（prepare / probe / start / poll / stop / collect）
    Runner  →  底层 Locust 子进程适配器（LocustRunner，仅为 Worker 内部实现）

Engine 不再直接接触 LocustRunner。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from .job import TestJob, ExecutionResult
from .worker import ExecutionWorker, WorkerError
from .lifecycle import LifecycleState, is_terminal, LIFECYCLE_LABELS
from qa_center.result_sink import sync_performance_run_from_test_result
from qa_center import audit

if TYPE_CHECKING:
    from celery.result import AsyncResult

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """压力测试统一编排引擎。

    职责：
        - 接收 TestJob
        - 并发控制（PerfSemaphore）
        - 创建 ExecutionWorker 并驱动其 run()
        - 将 Worker 返回的指标持久化到 TestResult / PerformanceTestResult
        - WebSocket 实时推送（通过 Worker 的 on_metrics 回调）
    """

    def __init__(self):
        self._log = logger

    # ── 公共入口 ──────────────────────────────────────────────────────

    def submit(self, job: TestJob):
        """提交一个压测任务。

        Returns:
            - async_mode=True  → celery.result.AsyncResult
            - async_mode=False → ExecutionResult
        """
        if job.async_mode:
            return self._submit_async(job)
        else:
            return self._execute_sync(job)

    # ── 异步分发（Celery） ────────────────────────────────────────────

    def _submit_async(self, job: TestJob):
        """创建 TestResult 并投递 Celery 任务。"""
        from qa_center.tasks import run_performance_test

        execution_id = self._resolve_execution_id(job)
        return run_performance_test.delay(
            execution_id=execution_id,
            test_case_id=job.case_id,
            host=job.host,
            users=job.users,
            spawn_rate=job.spawn_rate,
            run_time=job.run_time,
        )

    # ── 同步执行核心（Celery worker 与 DevOps 路径共享） ──────────────

    def _execute_sync(self, job: TestJob) -> ExecutionResult:
        """编排一次同步压测：信号量 → Worker.run() → 持久化。"""
        from qa_center.models import PerformanceTestCase, TestResult
        from qa_center.semaphore import PerfSemaphore

        # ── 1. 并发控制 ───────────────────────────────────────────────
        semaphore = PerfSemaphore()
        acquired = semaphore.acquire(job.execution_id or 0)
        if not acquired:
            self._log.warning(
                "并发上限已达 (max=%d), 拒绝 execution_id=%s",
                semaphore.max_concurrent, job.execution_id,
            )
            return ExecutionResult(
                ok=False, status='error',
                execution_id=job.execution_id or 0,
                error=f"并发性能测试已达上限 ({semaphore.max_concurrent})，请稍后重试",
            )

        worker = None
        try:
            # ── 2. 确保 TestResult + TestCase 存在 ────────────────────
            execution_id = job.execution_id
            if execution_id is None:
                execution_id = self._resolve_execution_id(job)

            try:
                test_result = TestResult.objects.get(id=execution_id)
                test_case = PerformanceTestCase.objects.get(id=job.case_id)
            except (TestResult.DoesNotExist, PerformanceTestCase.DoesNotExist) as exc:
                return ExecutionResult(
                    ok=False, status='error', execution_id=execution_id,
                    error=f"数据库记录缺失: {exc}",
                )

            # ── 审计：启动 ────────────────────────────────────
            audit.log_test_started(
                execution_id=execution_id,
                user=str(test_result.executed_by) if test_result.executed_by else 'unknown',
                project_id=test_result.project_id,
                case_name=test_case.name,
                target_url=test_case.url,
                users=job.users,
                duration=int(job.run_time.rstrip('s')) if job.run_time else 0,
            )

            # ── 3. 创建 Worker，注入 WS 回调和生命周期持久化 ──────
            def _on_metrics(stats: Dict[str, Any]) -> None:
                """Worker → Engine → WebSocket 的指标转发回调。"""
                self._ws_send(execution_id, stats)

            def _on_lifecycle(state: LifecycleState, reason: str) -> None:
                """Worker 每次状态转换时回调，持久化 lifecycle_state 到 DB。"""
                try:
                    test_result.lifecycle_state = state.value
                    test_result.lifecycle_reason = reason or ""
                    if is_terminal(state):
                        test_result.completed_at = timezone.now()
                    test_result.save(update_fields=['lifecycle_state', 'lifecycle_reason', 'completed_at'])
                except Exception as exc:
                    logger.warning("持久化 lifecycle_state 失败: %s", exc)

            worker = ExecutionWorker(
                job=job,
                on_metrics=_on_metrics,
                on_lifecycle=_on_lifecycle,
            )

            # ── 4. 驱动 Worker 执行 ───────────────────────────────────
            try:
                final_stats, payload, stopped_by_user = worker.run()
            except WorkerError as exc:
                # Worker 在 preparing / probing / starting 阶段失败
                # lifecycle_state 已由 Worker 的 _transition 设置
                test_result.status = 'error'
                test_result.error_message = str(exc)
                test_result.error_code = exc.reason or ''
                test_result.completed_at = timezone.now()
                test_result.lifecycle_state = exc.lifecycle_state.value
                test_result.lifecycle_reason = exc.reason or ''
                test_result.save()

                # 构建错误 payload，含 stderr
                error_payload = {
                    'state': 'error',
                    'execution_id': execution_id,
                    'lifecycle_state': exc.lifecycle_state.value,
                    'lifecycle_reason': exc.reason,
                    'lifecycle_label': LIFECYCLE_LABELS.get(exc.lifecycle_state, exc.lifecycle_state.value),
                    'lifecycle_is_terminal': True,
                    'error': str(exc),
                    'runner_status': 'locust_not_started',
                    'total_requests': 0,
                    'failed_requests': 0,
                    'rps': 0,
                    'avg_response_time': 0,
                    'error_rate': 0,
                    'diagnostic_message': str(exc),
                }
                if hasattr(worker, '_runner') and worker._runner is not None:
                    try:
                        stderr_tail = worker._runner.read_stderr_tail(50)
                        if stderr_tail:
                            error_payload['stderr_tail'] = stderr_tail
                    except Exception:
                        pass
                    try:
                        error_payload['diagnostic'] = worker._runner.get_diagnostic_info()
                    except Exception:
                        pass
                if hasattr(worker, '_probe_result') and worker._probe_result:
                    error_payload['probe_result'] = worker._probe_result
                    # 将 probe failure_reason 作为 lifecycle_reason
                    probe_failure = worker._probe_result.get('failure_reason', '')
                    if probe_failure:
                        error_payload['lifecycle_reason'] = probe_failure
                self._ws_send(execution_id, error_payload)

                audit.log_test_failed(
                    execution_id=execution_id,
                    reason=exc.reason or 'startup_error',
                    error_message=str(exc),
                    lifecycle_state=exc.lifecycle_state.value,
                )

                return ExecutionResult(
                    ok=False, status='error', execution_id=execution_id,
                    error=str(exc),
                )

            # ── 5. 持久化结果 ─────────────────────────────────────────
            result = self._persist_results(
                job=job,
                test_result=test_result,
                test_case=test_case,
                final_stats=final_stats,
                payload=payload,
                stopped_by_user=stopped_by_user,
            )

            # ── 6. 推送最终态 ─────────────────────────────────────────
            _stats = self._extract_stats(final_stats)
            final_payload = dict(_stats)
            final_payload['state'] = result.status
            final_payload['execution_id'] = execution_id
            final_payload['lifecycle_state'] = getattr(test_result, 'lifecycle_state', result.status) or result.status
            final_payload['lifecycle_is_terminal'] = True
            final_payload['lifecycle_label'] = (
                LIFECYCLE_LABELS.get(LifecycleState(result.status), result.status)
                if result.status in LifecycleState.__members__
                else result.status
            )
            final_payload['error'] = result.error
            # 附加 stderr 摘要
            if result.status in ('error', 'failed'):
                try:
                    if hasattr(worker, '_runner') and worker._runner is not None:
                        stderr_tail = worker._runner.read_stderr_tail(50)
                        if stderr_tail:
                            final_payload['stderr_tail'] = stderr_tail
                except Exception:
                    pass
            self._ws_send(execution_id, final_payload)

            audit.log_test_completed(
                execution_id=execution_id,
                total_requests=_stats.get('total_requests', 0),
                error_rate=_stats.get('error_rate', 0),
                avg_response_time=_stats.get('avg_response_time', 0),
                status=result.status,
            )

            return result

        except Exception as exc:
            self._log.exception("_execute_sync 异常: %s", exc)
            # 确保 TestResult 不永久停留在 'running'
            try:
                test_result.status = 'error'
                test_result.error_message = str(exc)[:500]
                test_result.lifecycle_state = 'error'
                test_result.completed_at = timezone.now()
                test_result.save()
            except Exception:
                pass
            return ExecutionResult(
                ok=False, status='error',
                execution_id=job.execution_id or 0,
                error=str(exc),
            )
        finally:
            # ── 7. 释放并发槽位 ───────────────────────────────────────
            if acquired:
                try:
                    semaphore.release(job.execution_id or 0)
                except Exception as exc:
                    self._log.error("释放信号量失败: %s", exc)

    # ── 辅助：解析 execution_id ───────────────────────────────────────

    def _resolve_execution_id(self, job: TestJob) -> int:
        """若 job 未带 execution_id，自动创建 TestResult 并返回 id。"""
        if job.execution_id is not None:
            return job.execution_id

        from qa_center.models import TestResult

        test_result = TestResult.objects.create(
            test_type='performance',
            name=job.test_case.name,
            project=job.project or getattr(job.test_case, 'project', None),
            status='running',
            executed_by=job.user,
            started_at=timezone.now(),
            source=job.source if job.source in ('single', 'devops') else 'single',
            task_id=job.task_id or '',
            concurrent_users=job.users,
            test_params={
                'test_case_id': job.case_id,
                'users': job.users,
                'spawn_rate': job.spawn_rate,
                'run_time': job.run_time,
                'url': job.test_case.url,
                'method': job.test_case.method,
            },
        )
        return test_result.id

    # ── 持久化 ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_stats(unified: Dict[str, Any]) -> Dict[str, Any]:
        """从统一 schema 中提取 stats 子 dict。

        兼容旧格式（扁平 dict）和新格式（{ok, stats: {...}}）。
        """
        if 'stats' in unified and isinstance(unified.get('stats'), dict):
            return unified['stats']
        # 兼容：旧格式可能直接是扁平指标
        return unified

    def _persist_results(
        self,
        job: TestJob,
        test_result,
        test_case,
        final_stats: Dict[str, Any],
        payload: Dict[str, Any],
        stopped_by_user: bool,
    ) -> ExecutionResult:
        """将 Worker 返回的指标写入 TestResult + PerformanceTestResult。"""
        from qa_center.models import PerformanceTestResult

        # 提取实际指标数据（兼容新旧格式）
        _stats = self._extract_stats(final_stats)
        _payload_stats = self._extract_stats(payload)

        completed_at = timezone.now()
        duration_ms: Optional[int] = None
        if test_result.started_at:
            duration_ms = int(
                (completed_at - test_result.started_at).total_seconds() * 1000
            )

        error_rate = _stats.get('error_rate', 0) or 0

        if stopped_by_user:
            final_status = 'error'
        elif error_rate < job.expected_error_rate:
            final_status = 'passed'
        else:
            final_status = 'failed'

        # ── 更新 TestResult ───────────────────────────────────────────
        test_result.status = final_status
        test_result.response_time_ms = int(_stats.get('avg_response_time', 0) or 0)
        test_result.throughput = _stats.get('current_rps', _stats.get('throughput', 0)) or 0
        test_result.error_rate = error_rate
        if stopped_by_user:
            test_result.aborted = True
            test_result.error_message = '用户停止性能测试'
            test_result.error_code = 'USER_STOPPED'
        test_result.completed_at = completed_at
        if duration_ms is not None:
            test_result.duration_ms = duration_ms

        execution_log = {
            'summary': {
                'total': 1,
                'passed': 1 if final_status == 'passed' else 0,
                'failed': 0 if final_status == 'passed' else 1,
                'pass_rate': 100 if final_status == 'passed' else 0,
            },
            'results': [{
                'case_id': job.case_id,
                'case_name': test_case.name,
                'type': 'performance',
                'passed': final_status == 'passed',
                'response_time_ms': _stats.get('avg_response_time', 0),
                'message': (
                    f"RPS: {_stats.get('current_rps', _stats.get('throughput', 0)):.1f}, "
                    f"平均响应时间: {_stats.get('avg_response_time', 0):.0f}ms, "
                    f"错误率: {error_rate:.2f}%"
                ),
                'request': {
                    'method': test_case.method,
                    'url': test_case.url,
                    'headers': test_case.headers,
                    'body': test_case.body,
                },
                'state': final_status,
                'start_time': final_stats.get('start_time'),
            }],
        }
        test_result.test_log = json.dumps(execution_log, ensure_ascii=False)
        # 生命周期状态由 Worker 的 on_lifecycle 回调实时持久化；
        # 此处确保终态落盘（万一回调未触发）
        if test_result.lifecycle_state and test_result.lifecycle_state not in ('passed', 'failed', 'error', 'stopped', 'timeout'):
            test_result.lifecycle_state = final_status
        test_result.save()

        # ── 写入 PerformanceTestResult ─────────────────────────────────
        perf_result_id: Optional[int] = None
        try:
            with transaction.atomic():
                perf_result = PerformanceTestResult.objects.create(
                    test_case=test_case,
                    test_result=test_result,
                    executed_by=test_result.executed_by,
                    total_requests=_stats.get('total_requests', 0),
                    successful_requests=_stats.get('successful_requests', 0),
                    failed_requests=_stats.get('failed_requests', 0),
                    avg_response_time_ms=_stats.get('avg_response_time', 0) or 0,
                    min_response_time_ms=_stats.get('min_response_time', 0) or 0,
                    max_response_time_ms=_stats.get('max_response_time', 0) or 0,
                    p50_response_time_ms=_stats.get('p50_response_time', 0) or 0,
                    p90_response_time_ms=_stats.get('p90_response_time', 0) or 0,
                    p95_response_time_ms=_stats.get('p95_response_time', 0) or 0,
                    p99_response_time_ms=_stats.get('p99_response_time', 0) or 0,
                    throughput=_stats.get('current_rps', _stats.get('throughput', 0)) or 0,
                    error_rate=error_rate,
                    response_time_distribution=_payload_stats.get('response_time_distribution', {}) or {},
                    throughput_over_time=_payload_stats.get('throughput_over_time', []) or [],
                    response_time_over_time=_payload_stats.get('response_time_over_time', []) or [],
                    error_details=_stats.get('errors', []) or [],
                )
                perf_result_id = perf_result.id
                sync_performance_run_from_test_result(
                    test_result=test_result,
                    performance_result=perf_result,
                )
        except Exception as exc:
            self._log.warning("PerformanceTestResult 持久化失败（TestResult 已保存）: %s", exc)

        return ExecutionResult(
            ok=True,
            status=final_status,
            execution_id=test_result.id,
            stats=dict(_stats),
            payload=dict(_payload_stats),
            test_result_id=test_result.id,
            perf_result_id=perf_result_id,
            stopped_by_user=stopped_by_user,
        )

    # ── WebSocket 推送 ────────────────────────────────────────────────

    @staticmethod
    def _ws_send(execution_id: int, payload: dict) -> None:
        """向 Channels group 推送实时指标。"""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            if channel_layer is None:
                return
            async_to_sync(channel_layer.group_send)(
                f"performance_test_{execution_id}",
                {"type": "test_update", "data": payload},
            )
        except Exception as exc:
            logger.debug("WS push 失败 (execution_id=%s): %s", execution_id, exc)
