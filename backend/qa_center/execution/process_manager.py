"""
ProcessManager — 生产级子进程管理器。

职责：
    - 以独立进程组启动子进程（setsid / CREATE_NEW_PROCESS_GROUP）
    - Graceful terminate → kill process group
    - Hard timeout watchdog（超时强制 kill）
    - 资源使用记录（CPU / memory / runtime）
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── 平台检测 ──────────────────────────────────────────────────

_IS_WINDOWS = sys.platform == 'win32'


def _start_process_group(cmd: list, cwd: str, stdout_f, stderr_f) -> subprocess.Popen:
    """以独立进程组启动子进程。

    - Linux/macOS: os.setsid (start_new_session=True)
    - Windows: CREATE_NEW_PROCESS_GROUP
    """
    if _IS_WINDOWS:
        return subprocess.Popen(
            cmd,
            stdout=stdout_f,
            stderr=stderr_f,
            text=True,
            cwd=cwd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        return subprocess.Popen(
            cmd,
            stdout=stdout_f,
            stderr=stderr_f,
            text=True,
            cwd=cwd,
            start_new_session=True,  # os.setsid
        )


def _terminate_process_group(process: subprocess.Popen, timeout: float = 5.0) -> bool:
    """Graceful terminate → force kill process group。

    Returns:
        True if process exited cleanly, False if force-killed.
    """
    if process is None or process.poll() is not None:
        return True

    pid = process.pid
    logger.info("Terminating process group (pid=%s)...", pid)

    # ── 1. Graceful terminate ─────────────────────────────────
    try:
        if _IS_WINDOWS:
            # Windows: send Ctrl+C to process group
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            # Unix: SIGTERM to process group
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, OSError) as exc:
        logger.debug("SIGTERM failed (process may already be dead): %s", exc)

    # ── 2. Wait for graceful exit ─────────────────────────────
    try:
        process.wait(timeout=timeout)
        logger.info("Process %s exited gracefully after terminate.", pid)
        return True
    except subprocess.TimeoutExpired:
        logger.warning("Process %s did not exit after terminate, force-killing...", pid)

    # ── 3. Force kill process group ───────────────────────────
    try:
        if _IS_WINDOWS:
            process.kill()  # TerminateProcess
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        process.wait(timeout=5)
        logger.info("Process group %s force-killed.", pid)
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired) as exc:
        logger.error("Failed to kill process group %s: %s", pid, exc)

    return False


def _get_resource_usage(pid: int) -> Dict[str, Any]:
    """获取进程资源使用信息（跨平台）。"""
    usage: Dict[str, Any] = {
        'pid': pid,
        'cpu_percent': None,
        'memory_mb': None,
        'runtime_seconds': None,
    }
    try:
        import psutil
        proc = psutil.Process(pid)
        usage['cpu_percent'] = round(proc.cpu_percent(interval=0.1), 1)
        mem = proc.memory_info()
        usage['memory_mb'] = round(mem.rss / (1024 * 1024), 1)
        usage['runtime_seconds'] = round(time.time() - proc.create_time(), 1)
    except ImportError:
        pass  # psutil not installed
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return usage


# ── Watchdog ──────────────────────────────────────────────────


class HardTimeoutWatchdog:
    """硬超时看门狗：超时后强制 kill 进程组。

    用法::

        watchdog = HardTimeoutWatchdog(process, max_runtime=120)
        watchdog.start()
        # ... 主循环 ...
        watchdog.cancel()  # 正常结束时取消
    """

    def __init__(
        self,
        process: subprocess.Popen,
        max_runtime: float,
        execution_id: int = 0,
        on_timeout: Optional[callable] = None,
    ):
        self.process = process
        self.max_runtime = max_runtime
        self.execution_id = execution_id
        self.on_timeout = on_timeout
        self._timer: Optional[threading.Timer] = None
        self._triggered = False

    def start(self) -> None:
        """启动看门狗定时器。"""
        self._timer = threading.Timer(self.max_runtime, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()
        logger.info(
            "Watchdog started: execution_id=%s max_runtime=%.0fs pid=%s",
            self.execution_id, self.max_runtime, self.process.pid,
        )

    def cancel(self) -> None:
        """取消看门狗（正常完成时调用）。"""
        if self._timer:
            self._timer.cancel()
            self._timer = None
            logger.debug("Watchdog cancelled: execution_id=%s", self.execution_id)

    def _on_timeout(self) -> None:
        """超时回调：强制 kill 进程组。"""
        self._triggered = True
        logger.error(
            "WATCHDOG TIMEOUT: execution_id=%s max_runtime=%.0fs — force killing pid=%s",
            self.execution_id, self.max_runtime, self.process.pid,
        )
        _terminate_process_group(self.process, timeout=2.0)
        if self.on_timeout:
            try:
                self.on_timeout()
            except Exception as exc:
                logger.error("on_timeout callback failed: %s", exc)

    @property
    def triggered(self) -> bool:
        return self._triggered
