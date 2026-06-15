"""
Runner Supervisor — 在 Django 进程中启动 runner_worker 子进程并流式读事件。
"""
import subprocess
import sys
import os
import json
import threading
import logging
from typing import Callable

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
            if event.get("type") == "finished":
                final_result = event
    except Exception:
        logger.exception("读 worker stdout 异常")

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()

    t.join(timeout=5)

    if proc.returncode not in (0, None) and final_result.get("type") != "finished":
        crash_msg = "".join(stderr_buf[-20:])
        on_event({
            "type": "error",
            "code": "WORKER_CRASHED",
            "message": f"worker 退出码 {proc.returncode}",
            "traceback": crash_msg,
        })

    return final_result
