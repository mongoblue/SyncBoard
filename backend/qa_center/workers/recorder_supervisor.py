"""
Recorder Supervisor — 在 Django 进程中管理 recorder_worker 子进程，
通过 stdin 发送命令、stdout 异步读取事件。
"""
import subprocess
import sys
import os
import json
import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger("qa_center.recorder")


def _worker_entry():
    return [sys.executable, "-m", "qa_center.workers.recorder_worker"]


class RecorderSession:
    def __init__(self, on_event: Callable[[dict], None]):
        self.on_event = on_event
        self.proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stopped = False

    @property
    def pid(self) -> Optional[int]:
        return self.proc.pid if self.proc else None

    def start(self):
        if self.proc:
            return
        backend_dir = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", ".."
        ))
        self.proc = subprocess.Popen(
            _worker_entry(),
            cwd=backend_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def send(self, cmd: dict):
        with self._lock:
            if not self.proc or self.proc.stdin.closed:
                return
            try:
                self.proc.stdin.write(json.dumps(cmd, ensure_ascii=False, default=str) + "\n")
                self.proc.stdin.flush()
            except Exception:
                logger.exception("send 命令失败")

    def stop(self, timeout: int = 10):
        if self._stopped:
            return
        self._stopped = True
        try:
            self.send({"cmd": "stop"})
        except Exception:
            pass
        if self.proc:
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()

    def is_alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def _read_stdout(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("recorder 非 JSON 输出: %s", line)
                    continue
                try:
                    self.on_event(ev)
                except Exception:
                    logger.exception("recorder on_event 异常")
        except Exception:
            logger.exception("读 recorder stdout 异常")
        finally:
            # 兜底：进程退出但未发 stopped
            if self.proc and self.proc.poll() not in (0, None):
                self.on_event({
                    "type": "error", "code": "WORKER_CRASHED",
                    "message": f"recorder 退出码 {self.proc.returncode}",
                })

    def _drain_stderr(self):
        try:
            for line in self.proc.stderr:
                logger.info("[recorder:%s] %s", self.proc.pid, line.rstrip())
        except Exception:
            pass
