"""
Runner Worker — 子进程执行 UI 测试用例。
stdin 读 1 行 JSON 输入，stdout 流式输出事件 (JSON Lines)。
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
        format="[runner] %(levelname)s %(message)s",
        stream=sys.stderr,
    )


logger = logging.getLogger("runner_worker")


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def read_input() -> dict:
    line = sys.stdin.readline()
    if not line:
        raise EOFError("stdin closed")
    return json.loads(line)


def setup_temp_dir() -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", ".playwright-temp"
    )
    base = os.path.abspath(base)
    os.makedirs(base, exist_ok=True)
    td = tempfile.mkdtemp(prefix="run_", dir=base)
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
        inp = read_input()
        temp_dir = setup_temp_dir()
        emit({"type": "started", "temp_dir": temp_dir})
        for i, step in enumerate(inp.get("steps", [])):
            emit({"type": "step_start", "index": i, "action": step.get("action"), "desc": step.get("desc", "")})
            emit({"type": "step_log", "index": i, "message": f"模拟执行步骤 {i}"})
            emit({"type": "step_done", "index": i, "success": True, "duration_ms": 1})
        total = len(inp.get("steps", []))
        emit({"type": "finished", "success": True, "summary": {"passed": total, "failed": 0, "total": total}})
    except Exception as e:
        emit({"type": "error", "code": "INTERNAL", "message": str(e), "traceback": traceback.format_exc()})
        emit({"type": "finished", "success": False, "summary": {"passed": 0, "failed": 1, "total": 1}})
    finally:
        if temp_dir:
            cleanup_temp_dir(temp_dir)


if __name__ == "__main__":
    main()
