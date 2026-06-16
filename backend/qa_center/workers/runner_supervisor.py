"""
Runner Supervisor — 在 Django 进程中启动 runner_worker 子进程并流式读事件。
"""
import subprocess
import sys
import os
import json
import threading
import logging
import uuid as _uuid
from typing import Callable

from django.conf import settings

logger = logging.getLogger("qa_center.runner")


def _worker_entry() -> list:
    """返回启动 worker 的命令行（python -m 模式）"""
    return [sys.executable, "-m", "qa_center.workers.runner_worker"]


def execute_ui_case(case_data: dict,
                    on_event: Callable[[dict], None],
                    timeout_seconds: int = 300) -> dict:
    """
    阻塞执行单个 UI 用例。
    case_data: {"case_id": int|None, "url": "...", "steps": [...]}
    on_event: 每收到一行事件就调用一次。
    返回最终 finished 事件 dict。
    """
    backend_dir = os.path.abspath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".."
    ))
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

    task_id = _uuid.uuid4().hex

    # DEBUG 模式：把所有事件额外落盘到 .playwright-temp/io_<task_id>.log
    DEBUG = os.environ.get("UI_TEST_DEBUG", "").lower() in ("1", "true", "yes")
    io_log = None
    if DEBUG:
        debug_dir = os.path.join(settings.BASE_DIR, ".playwright-temp")
        os.makedirs(debug_dir, exist_ok=True)
        log_path = os.path.join(debug_dir, f"io_{task_id}.log")
        io_log = open(log_path, "w", encoding="utf-8")
        logger.info("UI_TEST_DEBUG 开启，事件流写入 %s", log_path)

    try:
        on_event({"type": "supervisor_meta", "task_id": task_id, "worker_pid": proc.pid})
    except Exception:
        logger.exception("emit supervisor_meta 失败")

    final_result = {"type": "finished", "success": False,
                    "summary": {"passed": 0, "failed": 0, "total": 0}}

    try:
        proc.stdin.write(json.dumps(case_data, ensure_ascii=False, default=str) + "\n")
        proc.stdin.flush()
        proc.stdin.close()
    except Exception:
        logger.exception("写入 worker stdin 失败")

    stderr_buf: list = []

    def _drain_stderr():
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
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("非 JSON 输出: %s", line)
                    continue
                try:
                    on_event(event)
                except Exception:
                    logger.exception("on_event 回调异常")
                if io_log is not None:
                    try:
                        io_log.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
                        io_log.flush()
                    except Exception:
                        logger.exception("写入 io_log 失败")
                if event.get("type") == "finished":
                    final_result = event
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

    if timed_out["flag"]:
        on_event({
            "type": "error",
            "code": "STEP_TIMEOUT",
            "message": f"运行超时 ({timeout_seconds}s)，已强制终止 worker",
        })

    if (proc.returncode not in (0, None)
            and final_result.get("type") != "finished"
            and not timed_out["flag"]):
        crash_msg = "".join(stderr_buf[-20:])
        on_event({
            "type": "error",
            "code": "WORKER_CRASHED",
            "message": f"worker 退出码 {proc.returncode}",
            "traceback": crash_msg,
        })

    return final_result
