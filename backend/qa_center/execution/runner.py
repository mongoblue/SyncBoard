"""
BaseRunner — 压力测试执行器抽象接口 (v2 架构)。

当前 v1 实现:
    LocalLocustRunner (qa_center.locust_runner.LocustRunner)
    — 在本机 subprocess 中运行 Locust

计划 v1.5:
    DockerLocustRunner
    — 在本地 Docker 容器中运行 Locust

计划 v2:
    K8sJobLocustRunner
    — 在 Kubernetes 集群中以 Job 形式运行 Locust

架构目标:
    Engine → Worker → BaseRunner (抽象)
                          ├── LocalLocustRunner   (v1, 当前)
                          ├── DockerLocustRunner  (v1.5)
                          └── K8sJobLocustRunner  (v2)

    Worker 只依赖 BaseRunner 接口，不感知具体实现。
    通过 PERF_RUNNER_BACKEND 配置切换后端。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

# 从 constants 导入（避免循环导入）
from .constants import (
    LOCUST_NOT_STARTED,
    METRICS_NOT_CREATED,
    METRICS_EMPTY,
    METRICS_PARSE_ERROR,
    LOCUST_PROCESS_EXITED,
    LOCUST_RUNNING_NO_REQUESTS,
    LOCUST_RUNNING_WITH_REQUESTS,
    METRICS_FILE_CREATION_TIMEOUT,
)


class BaseRunner(ABC):
    """压力测试执行器抽象基类。

    所有 runner 实现必须提供以下接口。
    Engine/Worker 只依赖此接口，不感知具体实现。
    """

    # ── 生命周期 ──────────────────────────────────────────────

    @abstractmethod
    def start_test(self, test_case, host: str, users: int = 10,
                   spawn_rate: int = 1, run_time: str = "60s",
                   use_web_ui: bool = False) -> bool:
        """启动压力测试。

        Returns:
            True if test started successfully, False otherwise.
        """
        ...

    @abstractmethod
    def stop_test(self) -> bool:
        """停止压力测试（graceful terminate → kill）。"""
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """检查测试是否仍在运行。"""
        ...

    # ── 指标读取 ──────────────────────────────────────────────

    @abstractmethod
    def read_stats(self) -> Dict[str, Any]:
        """读取当前性能指标快照。

        统一 schema:
            {ok, runner_status, metrics_status, stats: {...}, diagnostics: {...}}
        """
        ...

    @abstractmethod
    def read_full_payload(self) -> Dict[str, Any]:
        """读取完整指标（含时间序列、per-endpoint、诊断信息）。"""
        ...

    # ── 诊断与日志 ────────────────────────────────────────────

    @abstractmethod
    def get_diagnostic_info(self) -> Dict[str, Any]:
        """返回当前执行诊断信息（host/users/pid/日志路径等）。"""
        ...

    @abstractmethod
    def read_stderr_tail(self, lines: int = 50) -> str:
        """读取 stderr 的最后 N 行。"""
        ...

    @abstractmethod
    def read_stdout_tail(self, lines: int = 50) -> str:
        """读取 stdout 的最后 N 行。"""
        ...

    # ── 产物管理 ──────────────────────────────────────────────

    @abstractmethod
    def list_artifacts(self) -> Dict[str, Optional[str]]:
        """列出所有产物文件及其路径。

        Returns:
            {metrics_json: path, stdout_log: path, stderr_log: path,
             report_html: path, stats_csv: path, failures_csv: path,
             metadata_json: path, artifact_dir: path}
        """
        ...

    @property
    @abstractmethod
    def artifact_dir(self) -> str:
        """产物目录路径。"""
        ...

    # ── 资源管理 ──────────────────────────────────────────────

    @abstractmethod
    def get_resource_usage(self) -> Dict[str, Any]:
        """获取当前资源使用快照 {cpu_percent, memory_mb, runtime_seconds}。"""
        ...

    @abstractmethod
    def start_watchdog(self, max_runtime: float, on_timeout: callable = None) -> None:
        """启动硬超时看门狗。"""
        ...

    @abstractmethod
    def cancel_watchdog(self) -> None:
        """取消看门狗。"""
        ...

    # ── locustfile 生成 ───────────────────────────────────────

    @abstractmethod
    def generate_locustfile(self, test_case, metrics_file: str) -> str:
        """生成 Locust 测试文件，返回文件路径。"""
        ...


# ── Runner Factory ───────────────────────────────────────────


def create_runner(execution_id: Optional[int] = None, **kwargs) -> BaseRunner:
    """根据 PERF_RUNNER_BACKEND 配置创建对应的 runner 实例。

    PERF_RUNNER_BACKEND 可选值:
        - 'local' (默认): LocalLocustRunner — 本地 subprocess
        - 'docker':       DockerLocustRunner — Docker 容器（未实现）
        - 'k8s':          K8sJobLocustRunner — Kubernetes Job（未实现）

    用法:
        runner = create_runner(execution_id=42)
        runner.generate_locustfile(test_case, '/tmp/metrics.json')
        runner.start_test(test_case, host, users=10, ...)
    """
    from django.conf import settings
    backend = getattr(settings, 'PERF_RUNNER_BACKEND', 'local')

    if backend == 'local':
        from qa_center.locust_runner import LocustRunner
        return LocustRunner(execution_id=execution_id, **kwargs)
    elif backend == 'docker':
        raise NotImplementedError(
            "DockerLocustRunner 尚未实现。"
            "计划在 v1.5 中通过 docker-py 启动容器。"
        )
    elif backend == 'k8s':
        raise NotImplementedError(
            "K8sJobLocustRunner 尚未实现。"
            "计划在 v2 中通过 kubernetes-client 创建 Job。"
        )
    else:
        raise ValueError(f"未知的 PERF_RUNNER_BACKEND: {backend}")
