"""
Recorder Worker — 子进程运行录制会话。
stdin 持续读命令 (JSON Lines)，stdout 推事件。
"""
import sys
import json
import os
import tempfile
import traceback
import logging


def _setup_io_logging():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="[recorder] %(levelname)s %(message)s",
        stream=sys.stderr,
    )


logger = logging.getLogger("recorder_worker")


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def read_command() -> dict:
    line = sys.stdin.readline()
    if not line:
        raise EOFError("stdin closed")
    return json.loads(line)


def setup_temp_dir() -> str:
    base = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", ".playwright-temp"
    ))
    os.makedirs(base, exist_ok=True)
    td = tempfile.mkdtemp(prefix="rec_", dir=base)
    os.environ["TEMP"] = td
    os.environ["TMP"] = td
    os.environ["PLAYWRIGHT_TEMP_DIR"] = td
    return td


def cleanup_temp_dir(td: str) -> None:
    import shutil
    if td and os.path.exists(td):
        shutil.rmtree(td, ignore_errors=True)


def main():
    _setup_io_logging()
    temp_dir = None
    try:
        temp_dir = setup_temp_dir()
        emit({"type": "ready", "success": True, "temp_dir": temp_dir})
        running = True
        while running:
            try:
                cmd = read_command()
            except json.JSONDecodeError as je:
                emit({"type": "error", "code": "INTERNAL", "message": f"无效 JSON: {je}"})
                continue
            action = cmd.get("cmd")
            if action == "start":
                url = cmd.get("url", "")
                emit({"type": "record_event", "data": {"action": "navigated", "url": url}})
            elif action == "pause":
                emit({"type": "paused"})
            elif action == "resume":
                emit({"type": "resumed"})
            elif action == "run_step":
                emit({"type": "step_run_done", "success": True})
            elif action == "stop":
                emit({"type": "stopped", "success": True})
                running = False
            else:
                emit({"type": "error", "code": "INTERNAL", "message": f"未知命令: {action}"})
    except EOFError:
        logger.info("stdin closed, exiting")
    except Exception as e:
        emit({"type": "error", "code": "INTERNAL", "message": str(e), "traceback": traceback.format_exc()})
    finally:
        if temp_dir:
            cleanup_temp_dir(temp_dir)


if __name__ == "__main__":
    main()
