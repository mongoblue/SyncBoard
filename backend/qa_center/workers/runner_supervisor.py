"""
Runner Supervisor — 在 Django 进程中启动 runner_worker 子进程并流式读事件。

全局注册表 _RUNNERS（task_id → subprocess.Popen），用于 abort 端点终结子进程。
_EVENTS 注册表用于前端 WS 连上时回放历史事件（保留 60 秒）。
_ABORTED 标记用于区分用户中止与真实 WORKER_CRASHED。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid as _uuid
from typing import Callable, Optional

from django.conf import settings

logger = logging.getLogger("qa_center.runner")

# task_id → subprocess.Popen 的注册表，用于 abort 端点
_RUNNERS: dict[str, "subprocess.Popen"] = {}
_RUNNERS_LOCK = threading.Lock()

# task_id → 已发出事件列表，用于前端 WS 连上时回放历史
_EVENTS: dict[str, list[dict]] = {}
_EVENTS_LOCK = threading.Lock()

# task_id → 是否被用户 abort
_ABORTED: dict[str, bool] = {}
_ABORTED_LOCK = threading.Lock()

# 历史事件保留时间（秒）
_EVENTS_TTL = 60.0

# 并发限流（进程内）
_CONCURRENCY_LOCK = threading.Lock()
_ACTIVE_RUNNERS = 0


def _max_concurrent() -> int:
    try:
        value = int(getattr(settings, "UI_TEST_MAX_CONCURRENT_RUNNERS", 3) or 3)
    except (TypeError, ValueError):
        value = 3
    return max(1, value)


def _acquire_runner_slot() -> int:
    """占用一个并发槽位；失败抛 UiConcurrencyLimitError。"""
    global _ACTIVE_RUNNERS
    from qa_center.ui_execution import UiConcurrencyLimitError

    with _CONCURRENCY_LOCK:
        limit = _max_concurrent()
        if _ACTIVE_RUNNERS >= limit:
            raise UiConcurrencyLimitError(
                f"UI 测试并发已达上限 ({limit})，请稍后重试",
                max_concurrent=limit,
            )
        _ACTIVE_RUNNERS += 1
        return _ACTIVE_RUNNERS


def _release_runner_slot() -> None:
    global _ACTIVE_RUNNERS
    with _CONCURRENCY_LOCK:
        _ACTIVE_RUNNERS = max(0, _ACTIVE_RUNNERS - 1)


def active_runner_count() -> int:
    with _CONCURRENCY_LOCK:
        return _ACTIVE_RUNNERS


def register_runner(task_id: str, proc: "subprocess.Popen") -> None:
    with _RUNNERS_LOCK:
        _RUNNERS[task_id] = proc


def unregister_runner(task_id: str) -> None:
    with _RUNNERS_LOCK:
        _RUNNERS.pop(task_id, None)


def mark_aborted(task_id: str) -> None:
    with _ABORTED_LOCK:
        _ABORTED[task_id] = True


def is_aborted(task_id: str) -> bool:
    with _ABORTED_LOCK:
        return bool(_ABORTED.get(task_id))


def clear_aborted(task_id: str) -> None:
    with _ABORTED_LOCK:
        _ABORTED.pop(task_id, None)


def abort_runner(task_id: str) -> bool:
    """终止指定 task_id 的 worker 子进程。返回是否成功找到并发送了 terminate。"""
    with _RUNNERS_LOCK:
        proc: Optional[subprocess.Popen] = _RUNNERS.get(task_id)
    if proc is None:
        return False
    mark_aborted(task_id)
    try:
        if proc.poll() is None:
            proc.terminate()
        return True
    except Exception:
        logger.exception("abort_runner 失败: %s", task_id)
        return False


def is_runner_alive(task_id: str) -> bool:
    with _RUNNERS_LOCK:
        proc: Optional[subprocess.Popen] = _RUNNERS.get(task_id)
    if proc is None:
        return False
    return proc.poll() is None


def record_event(task_id: str, event: dict) -> None:
    """记录一条事件到缓存，供前端 WS 连上后回放。"""
    stamped = dict(event)
    stamped.setdefault("_ts", time.time())
    with _EVENTS_LOCK:
        bucket = _EVENTS.setdefault(task_id, [])
        bucket.append(stamped)


def get_events(task_id: str) -> list[dict]:
    """读取并清空 task_id 的事件缓存。一次性消费，避免重复回放。"""
    with _EVENTS_LOCK:
        return _EVENTS.pop(task_id, [])


def peek_events(task_id: str) -> list[dict]:
    """只读不消费。用于调试/扩展与晚连接 WS 回放。"""
    with _EVENTS_LOCK:
        return list(_EVENTS.get(task_id, []))


def cleanup_expired_events(now: float | None = None) -> int:
    """清理超过 TTL 的历史事件缓存。返回清理条数。"""
    now = now if now is not None else time.time()
    with _EVENTS_LOCK:
        expired = [
            tid
            for tid, evs in _EVENTS.items()
            if not evs or (now - evs[-1].get("_ts", now)) > _EVENTS_TTL
        ]
        for tid in expired:
            _EVENTS.pop(tid, None)
        return len(expired)


def _worker_entry() -> list:
    """返回启动 worker 的命令行（python -m 模式）"""
    return [sys.executable, "-m", "qa_center.workers.runner_worker"]


def _publish_run_event(task_id: str, event: dict) -> None:
    """双写：事件缓存 + Channels 组推送。"""
    record_event(task_id, event)
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"ui_run_{task_id}",
            {"type": "run_event", "data": {"type": "run_event", "data": event}},
        )
    except Exception:
        logger.exception("推送 UI run 事件失败: %s", task_id)


def execute_ui_case(
    case_data: dict,
    on_event: Callable[[dict], None],
    timeout_seconds: int = 300,
    task_id: str | None = None,
) -> dict:
    """
    阻塞执行单个 UI 用例。
    case_data: {"case_id": int|None, "url": "...", "steps": [...]}
    on_event: 每收到一行事件就调用一次。
    task_id: 可选；如传入则使用调用方提供的 id（用于 abort 端点路由），否则内部生成。
    返回最终 finished 事件 dict。
    """
    if task_id is None:
        task_id = _uuid.uuid4().hex

    _acquire_runner_slot()
    clear_aborted(task_id)

    backend_dir = str(settings.BASE_DIR)
    try:
        proc = subprocess.Popen(
            _worker_entry(),
            cwd=backend_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except Exception:
        _release_runner_slot()
        clear_aborted(task_id)
        raise

    register_runner(task_id, proc)

    DEBUG = os.environ.get("UI_TEST_DEBUG", "").lower() in ("1", "true", "yes")
    io_log = None
    if DEBUG:
        debug_dir = os.path.join(settings.BASE_DIR, ".playwright-temp")
        os.makedirs(debug_dir, exist_ok=True)
        log_path = os.path.join(debug_dir, f"io_{task_id}.log")
        io_log = open(log_path, "w", encoding="utf-8")
        logger.info("UI_TEST_DEBUG 开启，事件流写入 %s", log_path)

    final_result = {
        "type": "finished",
        "success": False,
        "summary": {"passed": 0, "failed": 0, "total": 0},
        "task_id": task_id,
        "aborted": False,
    }

    def _emit(event: dict) -> None:
        payload = dict(event)
        payload.setdefault("task_id", task_id)
        try:
            on_event(payload)
        except Exception:
            logger.exception("on_event 回调异常")
        try:
            _publish_run_event(task_id, payload)
        except Exception:
            logger.exception("record/publish 事件失败")
        if io_log is not None:
            try:
                io_log.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
                io_log.flush()
            except Exception:
                logger.exception("写入 io_log 失败")

    try:
        _emit({"type": "supervisor_meta", "task_id": task_id, "worker_pid": proc.pid})

        try:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(case_data, ensure_ascii=False, default=str) + "\n")
            proc.stdin.flush()
            proc.stdin.close()
        except Exception:
            logger.exception("写入 worker stdin 失败")

        stderr_buf: list = []

        def _drain_stderr():
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_buf.append(line)
                logger.info("[worker:%s] %s", proc.pid, line.rstrip())

        t = threading.Thread(target=_drain_stderr, daemon=True)
        t.start()

        timed_out = {"flag": False}

        def _on_timeout():
            timed_out["flag"] = True
            logger.warning("worker 运行超时 (%ss)，触发 terminate", timeout_seconds)
            try:
                proc.terminate()
            except Exception:
                logger.exception("terminate worker 失败")

        watchdog = threading.Timer(timeout_seconds, _on_timeout)
        watchdog.daemon = True
        watchdog.start()

        try:
            try:
                if proc.stdout is not None:
                    for line in proc.stdout:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("非 JSON 输出: %s", line)
                            continue
                        _emit(event)
                        if event.get("type") == "finished":
                            final_result = dict(event)
                            final_result["task_id"] = task_id
            except Exception:
                logger.exception("读 worker stdout 异常")
        finally:
            watchdog.cancel()
            if io_log is not None:
                try:
                    io_log.close()
                except Exception:
                    pass

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                proc.terminate()
            except Exception:
                logger.exception("terminate worker 失败")
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    logger.exception("kill worker 失败")
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.error("worker 在 kill 后仍未退出")

        t.join(timeout=5)

        aborted = is_aborted(task_id)
        if timed_out["flag"]:
            _emit({
                "type": "error",
                "code": "STEP_TIMEOUT",
                "message": f"运行超时 ({timeout_seconds}s)，已强制终止 worker",
            })
            final_result = {
                "type": "finished",
                "success": False,
                "summary": final_result.get("summary") or {"passed": 0, "failed": 0, "total": 0},
                "task_id": task_id,
                "aborted": False,
                "timed_out": True,
            }
        elif aborted:
            _emit({
                "type": "error",
                "code": "ABORTED",
                "message": "用户中止执行",
            })
            final_result = {
                "type": "finished",
                "success": False,
                "summary": final_result.get("summary") or {"passed": 0, "failed": 0, "total": 0},
                "task_id": task_id,
                "aborted": True,
            }
            _emit(final_result)
        elif (
            proc.returncode not in (0, None)
            and final_result.get("type") != "finished"
        ):
            crash_msg = "".join(stderr_buf[-20:])
            _emit({
                "type": "error",
                "code": "WORKER_CRASHED",
                "message": f"worker 退出码 {proc.returncode}",
                "traceback": crash_msg,
            })
            final_result = {
                "type": "finished",
                "success": False,
                "summary": {"passed": 0, "failed": 1, "total": 1},
                "task_id": task_id,
                "aborted": False,
            }
            _emit(final_result)
    finally:
        unregister_runner(task_id)
        clear_aborted(task_id)
        _release_runner_slot()

    final_result.setdefault("task_id", task_id)
    return final_result
