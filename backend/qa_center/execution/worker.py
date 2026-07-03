"""
ExecutionWorker — 管理单次压力测试的完整生命周期。

职责：
    - 持有 LocustRunner（底层适配器，唯一持有者）
    - 驱动 Lifecycle 状态机（pending → preparing → probing → ... → terminal）
    - URL 连通性预检（probing）
    - 启动子进程 + 轮询指标 + 检测停止/超时信号
    - 收集最终结果

LocustRunner 为纯适配器（无回调 / 无业务逻辑），
本 Worker 负责所有编排逻辑和生命周期管理。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple, TYPE_CHECKING

import requests
from django.conf import settings

from .job import TestJob
from .lifecycle import (
    Lifecycle,
    LifecycleState,
    is_active,
    is_pre_metrics,
    LIFECYCLE_LABELS,
)
from .probe import TargetProbeService, ProbeResult
from .runner import BaseRunner, create_runner
from .constants import (
    LOCUST_NOT_STARTED,
    LOCUST_RUNNING_NO_REQUESTS,
    LOCUST_RUNNING_WITH_REQUESTS,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── 配置常量 ────────────────────────────────────────────────────

# Locust 运行中但无请求超过此时间 → 推送 warning（秒）
NO_REQUESTS_WARNING_DELAY = 5.0

# 超过此最大运行时间的 1.5 倍强制终止（秒）
TIMEOUT_MULTIPLIER = 1.5

# RPS > 0 且连续 N 次采样认为进入 running（不再处于 ramping）
RAMPING_TO_RUNNING_SAMPLES = 3

# 轮询间隔（秒）
POLL_INTERVAL = 0.5


class WorkerError(Exception):
    """Worker 可恢复/不可恢复错误，携带 lifecycle_state 用于诊断。"""

    def __init__(self, message: str, lifecycle_state: LifecycleState, reason: str = ""):
        super().__init__(message)
        self.lifecycle_state = lifecycle_state
        self.reason = reason


class ExecutionWorker:
    """单次性能测试的生命周期管理器。

    使用方式::

        worker = ExecutionWorker(job, on_metrics=ws_callback, on_lifecycle=persist_callback)
        stats, payload, stopped_by_user = worker.run()
    """

    def __init__(
        self,
        job: TestJob,
        on_metrics: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_lifecycle: Optional[Callable[[LifecycleState, str], None]] = None,
    ):
        self.job = job
        self._on_metrics = on_metrics
        self._on_lifecycle = on_lifecycle

        self._runner: Optional[BaseRunner] = None
        self._stopped_by_user = False
        self._start_time: Optional[float] = None
        self._no_requests_warned = False
        self._ramping_stable_count = 0
        self._max_runtime_seconds: Optional[float] = None
        self._probe_result: Optional[Dict[str, Any]] = None

        # ── 生命周期状态机 ──────────────────────────────────────
        self.lifecycle = Lifecycle()

    # ── 公共入口 ──────────────────────────────────────────────────

    def run(self) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
        """同步执行完整测试流程。

        Returns:
            (final_stats, full_payload, stopped_by_user)

        Raises:
            WorkerError: 不可恢复的生命周期错误（preparing/probing/starting 阶段）
        """
        try:
            self._prepare()
            self._probe()
            self._start()
            self._wait()
            self._collect()
        except WorkerError:
            # _prepare / _probe / _start 的 WorkerError 向上传播给 Engine
            raise
        except Exception as exc:
            self._transition(
                LifecycleState.ERROR,
                reason='worker_exception',
                error_message=str(exc),
            )
            raise WorkerError(str(exc), LifecycleState.ERROR, 'worker_exception') from exc

        return self._gather_results()

    @property
    def is_running(self) -> bool:
        return self._runner is not None and self._runner.is_running()

    # ── 阶段：准备 ────────────────────────────────────────────────

    def _prepare(self) -> None:
        """生成 locustfile 并校验参数。"""
        self._transition(LifecycleState.PREPARING)

        execution_id = self.job.execution_id or 0
        self._runner = create_runner(execution_id=execution_id)

        # 预生成 locustfile，提前发现语法/参数问题
        try:
            # 使用临时 metrics 路径；start_test 会重新生成正确的
            import os, tempfile
            base_temp = os.path.join(tempfile.gettempdir(), 'syncboard-locust')
            os.makedirs(base_temp, exist_ok=True)
            tmp_metrics = os.path.join(base_temp, f'locust_metrics_prepare_{execution_id}.json')
            self._runner.generate_locustfile(self.job.test_case, tmp_metrics)
            logger.info("locustfile 已生成 (execution_id=%s)", execution_id)
        except Exception as exc:
            self._transition(
                LifecycleState.ERROR,
                reason='locustfile_generation_failed',
                error_message=str(exc),
            )
            raise WorkerError(
                f"locustfile 生成失败: {exc}",
                LifecycleState.ERROR,
                'locustfile_generation_failed',
            ) from exc

    # ── 阶段：连通性预检 ──────────────────────────────────────────

    def _probe(self) -> None:
        """使用 TargetProbeService 对目标 URL 做全面预检。

        检查内容：
        - URL scheme 合法性
        - DNS 解析 + IP 分类（localhost/内网/公网/云 metadata）
        - SSRF 策略拦截
        - TCP 端口连通性
        - HTTP 请求 + TLS 证书
        - 安全策略（PERF_ALLOW_LOCALHOST / PERF_ALLOWED_HOSTS 等）

        预检失败 → ERROR（不启动 Locust）
        预检成功 → 进入 STARTING
        """
        self._transition(LifecycleState.PROBING)

        probe_service = TargetProbeService()
        result = probe_service.probe(
            url=self.job.test_case.url,
            method=self.job.test_case.method or 'GET',
        )

        self._probe_result = result.to_dict()

        if not result.ok:
            failure_reason = result.failure_reason or 'probe_failed'
            self._transition(
                LifecycleState.ERROR,
                reason=failure_reason,
                error_message=result.error_summary,
            )
            raise WorkerError(
                result.error_summary or '目标 URL 预检失败',
                LifecycleState.ERROR,
                failure_reason,
            )

        logger.info(
            "URL probing 成功: %s %s → HTTP %s (%.0fms) DNS=%s TCP=%.0fms",
            result.method, result.url,
            result.http_status_code, result.http_duration_ms,
            result.resolved_ips, result.tcp_connect_ms,
        )

    # ── 阶段：启动 Locust ─────────────────────────────────────────

    def _start(self) -> None:
        """启动 Locust 子进程。"""
        self._transition(LifecycleState.STARTING)

        ok = self._runner.start_test(
            test_case=self.job.test_case,
            host=self.job.host,
            users=self.job.users,
            spawn_rate=self.job.spawn_rate,
            run_time=self.job.run_time,
        )

        self._start_time = time.time()

        if not ok:
            stderr_tail = self._runner.read_stderr_tail(50) if self._runner else ""
            self._transition(
                LifecycleState.ERROR,
                reason='locust_start_failed',
                error_message=f'Locust 子进程启动失败。stderr: {stderr_tail[:500]}',
            )
            raise WorkerError(
                "Locust 子进程启动失败",
                LifecycleState.ERROR,
                'locust_start_failed',
            )

        # 计算最大运行时间（用于超时检测）
        run_time_str = self.job.run_time or '60s'
        rt = run_time_str.lower().rstrip('s')
        try:
            run_time_seconds = float(rt)
        except (ValueError, TypeError):
            run_time_seconds = 60.0

        ramp_up = getattr(self.job.test_case, 'ramp_up_seconds', 10) or 10
        extra = getattr(settings, 'PERF_EXTRA_TIMEOUT_SECONDS', 30)
        self._max_runtime_seconds = run_time_seconds + ramp_up + extra

        # ── 启动硬超时看门狗 ──────────────────────────────────
        def _on_hard_timeout():
            self._transition(
                LifecycleState.TIMEOUT,
                reason='hard_timeout',
                error_message=f'硬超时: {self._max_runtime_seconds:.0f}s',
            )

        self._runner.start_watchdog(
            max_runtime=self._max_runtime_seconds,
            on_timeout=_on_hard_timeout,
        )

        diagnostic = self._runner.get_diagnostic_info()
        logger.info(
            "Locust 已启动: execution_id=%s pid=%s users=%s spawn_rate=%s host=%s target=%s",
            self.job.execution_id,
            diagnostic.get('pid'),
            self.job.users,
            self.job.spawn_rate,
            self.job.host,
            diagnostic.get('target_path'),
        )

        # 推送启动诊断信息
        self._push_metrics(self._runner.read_stats())

    # ── 阶段：等待并轮询 ──────────────────────────────────────────

    def _wait(self) -> None:
        """轮询等待直到 Locust 完成、用户停止、超时或异常。"""
        while self._runner is not None and self._runner.is_running():
            # ── 读取实时指标（统一 schema） ──────────────────────
            result = self._runner.read_stats()
            stats = result.get('stats', {})
            total_requests = stats.get('total_requests', 0)
            rps = stats.get('current_rps', stats.get('throughput', 0))

            # ── 生命周期状态推导 ────────────────────────────────
            if total_requests > 0:
                if self.lifecycle.current == LifecycleState.STARTING:
                    # 首次出现请求 → 进入 ramping
                    self._transition(LifecycleState.RAMPING)
                elif self.lifecycle.current == LifecycleState.RAMPING:
                    # 连续 N 次有 RPS → 进入 running
                    if rps > 0:
                        self._ramping_stable_count += 1
                        if self._ramping_stable_count >= RAMPING_TO_RUNNING_SAMPLES:
                            self._transition(LifecycleState.RUNNING)
                    else:
                        self._ramping_stable_count = 0

            # ── 推送指标 ────────────────────────────────────────
            self._push_metrics(result)

            # ── 5 秒无请求 warning ──────────────────────────────
            if (
                not self._no_requests_warned
                and self._start_time is not None
                and (time.time() - self._start_time) >= NO_REQUESTS_WARNING_DELAY
                and total_requests == 0
                and self._runner.is_running()
            ):
                self._no_requests_warned = True
                self._push_metrics(result, extra={
                    'warning': 'no_requests_after_5s',
                    'diagnostic_message': (
                        'Locust is running but no requests have been recorded. '
                        'Please check generated task, target URL reachability, '
                        'host/path split, request body, or Locust logs.'
                    ),
                })
                logger.warning(
                    "execution_id=%s: 运行 %.0fs 但 total_requests 仍为 0",
                    self.job.execution_id, time.time() - (self._start_time or 0),
                )

            # ── 超时检测 ────────────────────────────────────────
            if (
                self._start_time is not None
                and self._max_runtime_seconds is not None
                and (time.time() - self._start_time) > self._max_runtime_seconds
            ):
                self._transition(
                    LifecycleState.TIMEOUT,
                    reason='max_runtime_exceeded',
                    error_message=(
                        f'运行时间超过最大限制 '
                        f'({self._max_runtime_seconds:.0f}s > {self._max_runtime_seconds / TIMEOUT_MULTIPLIER:.0f}s 的 {TIMEOUT_MULTIPLIER}x)'
                    ),
                )
                self._runner.stop_test()
                break

            # ── 用户停止信号 ────────────────────────────────────
            if self._check_should_stop():
                self._transition(LifecycleState.STOPPING, reason='user_requested')
                self._push_metrics(self._runner.read_stats())
                self._runner.cancel_watchdog()
                self._runner.stop_test()
                self._stopped_by_user = True
                # 记录资源使用
                self._runner.get_resource_usage()
                self._transition(LifecycleState.STOPPED, reason='user_requested')
                break

            time.sleep(POLL_INTERVAL)

        # 循环退出后取消看门狗
        if self._runner:
            self._runner.cancel_watchdog()
            self._runner.get_resource_usage()

        # 循环退出但非用户停止/超时 → Locust 自然结束 → collecting
        if (
            self.lifecycle.current not in (
                LifecycleState.STOPPED,
                LifecycleState.STOPPING,
                LifecycleState.TIMEOUT,
                LifecycleState.ERROR,
            )
        ):
            self._transition(LifecycleState.COLLECTING)

    # ── 阶段：收集结果 ────────────────────────────────────────────

    def _collect(self) -> None:
        """收集 Locust 最终指标并确定最终状态。"""
        if self._runner is None:
            return

        result = self._runner.read_stats() or {}
        stats = result.get('stats', {})

        if self.lifecycle.current in (LifecycleState.STOPPED,):
            return
        if self.lifecycle.current == LifecycleState.TIMEOUT:
            return
        if self.lifecycle.current == LifecycleState.ERROR:
            return

        # 根据业务判定进入 passed / failed
        total_requests = stats.get('total_requests', 0)
        error_rate = stats.get('error_rate', 0) or 0

        # 零请求保护：Locust 启动失败或未产生任何请求时进入 error
        if total_requests == 0 and not self._stopped_by_user:
            self._transition(
                LifecycleState.ERROR,
                reason='no_requests_produced',
                error_message='Locust 未产生任何请求，可能目标 URL 不可达或 locustfile 有误',
            )
            return

        if self._stopped_by_user:
            pass
        elif error_rate < self.job.expected_error_rate:
            self._transition(LifecycleState.PASSED)
        else:
            self._transition(
                LifecycleState.FAILED,
                reason=f'error_rate_{error_rate:.1f}_exceeds_{self.job.expected_error_rate:.1f}',
            )

    def _gather_results(self) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
        """收集并返回最终结果。"""
        if self._runner is None:
            return {}, {}, self._stopped_by_user
        payload = self._runner.read_full_payload()
        stats = self._runner.read_stats()
        return stats, payload, self._stopped_by_user

    # ── 生命周期辅助 ──────────────────────────────────────────────

    def _transition(
        self,
        to_state: LifecycleState,
        reason: str = "",
        error_message: str = "",
    ) -> None:
        """执行生命周期状态转换并通知 Engine 持久化。"""
        try:
            snapshot = self.lifecycle.transition(
                to_state,
                reason=reason,
                error_message=error_message,
            )
            logger.info(
                "Lifecycle: %s → %s (reason=%s)",
                snapshot.previous_state.value if snapshot.previous_state else 'initial',
                to_state.value,
                reason or '-',
            )
        except ValueError as exc:
            logger.warning("Lifecycle 转换被拒绝: %s", exc)
            return

        # ── 回调 Engine 持久化 lifecycle_state ──────────────────
        if self._on_lifecycle is not None:
            try:
                self._on_lifecycle(to_state, reason)
            except Exception as exc:
                logger.debug("on_lifecycle 回调异常: %s", exc)

    # ── 停止信号 ──────────────────────────────────────────────────

    def _check_should_stop(self) -> bool:
        """读取 TestResult.aborted 标记。"""
        from qa_center.models import TestResult
        execution_id = self.job.execution_id or 0
        try:
            return TestResult.objects.filter(id=execution_id, aborted=True).exists()
        except Exception:
            return False

    # ── WebSocket 推送 ────────────────────────────────────────────

    def _build_payload(
        self,
        result: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建标准 WebSocket 推送 payload，处理统一 schema。

        result 来自 LocustRunner.read_stats()，schema:
            {ok, runner_status, metrics_status, stats: {...}, diagnostics: {...}}
        """
        # 提取嵌套字段
        ok = result.get('ok', False)
        runner_status = result.get('runner_status', LOCUST_NOT_STARTED)
        metrics_status = result.get('metrics_status', '')
        stats = result.get('stats', {})
        diagnostics = result.get('diagnostics', {})

        # 补充 diagnostic info
        if not diagnostics and self._runner is not None:
            try:
                diagnostics = self._runner.get_diagnostic_info()
            except Exception:
                diagnostics = {}

        payload: Dict[str, Any] = {
            # ── 生命周期信息 ──────────────────────────────────
            **self.lifecycle.to_dict(),
            # ── 统一 schema 字段 ───────────────────────────────
            'execution_id': self.job.execution_id,
            'ok': ok,
            'runner_status': runner_status,
            'metrics_status': metrics_status,
            # ── 核心指标 ──────────────────────────────────────
            'total_requests': stats.get('total_requests', 0),
            'failed_requests': stats.get('failed_requests', 0),
            'rps': stats.get('current_rps', stats.get('throughput', 0)),
            'avg_response_time': stats.get('avg_response_time', 0),
            'error_rate': stats.get('error_rate', 0),
            'last_metrics_at': diagnostics.get('last_metrics_at'),
            'diagnostic_message': diagnostics.get('message', ''),
            # ── 透传原始字段 ──────────────────────────────────
            'state': stats.get('state', result.get('runner_status', 'unknown')),
            'successful_requests': stats.get('successful_requests', 0),
            'min_response_time': stats.get('min_response_time', 0),
            'max_response_time': stats.get('max_response_time', 0),
            'p50_response_time': stats.get('p50_response_time', 0),
            'p90_response_time': stats.get('p90_response_time', 0),
            'p95_response_time': stats.get('p95_response_time', 0),
            'p99_response_time': stats.get('p99_response_time', 0),
            'errors': stats.get('errors', []),
            'per_endpoint': stats.get('per_endpoint', {}),
            'throughput_over_time': stats.get('throughput_over_time', []),
            'response_time_over_time': stats.get('response_time_over_time', []),
            'error_rate_over_time': stats.get('error_rate_over_time', []),
            'response_time_distribution': stats.get('response_time_distribution', {}),
            'timestamp': stats.get('timestamp', time.time()),
            'diagnostic': diagnostics,
            'locust_exit_code': diagnostics.get('locust_exit_code'),
            'artifact_dir': diagnostics.get('artifact_dir'),
            'probe_result': self._probe_result,
        }

        if extra:
            payload.update(extra)

        return payload

    def _push_metrics(
        self,
        result: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """通过回调推送增强后的指标 payload。"""
        if self._on_metrics is None:
            return
        payload = self._build_payload(result, extra=extra)
        self._on_metrics(payload)

    # ── 便捷方法 ──────────────────────────────────────────────────

    def force_stop(self) -> None:
        """强制终止子进程（用于异常恢复）。"""
        if self._runner is not None:
            try:
                self._runner.stop_test()
            except Exception as exc:
                logger.warning("force_stop 失败: %s", exc)
            self._runner = None
