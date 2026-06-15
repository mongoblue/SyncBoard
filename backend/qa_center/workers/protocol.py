"""
Worker 通信协议定义
所有 stdout 事件和 stdin 命令统一为 JSON Lines（每行一个完整 JSON）。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json


@dataclass
class RunnerInput:
    case_id: Optional[int] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)
    url: str = ""
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    timeout_ms: int = 30000


@dataclass
class RecorderCommand:
    cmd: str  # start | stop | pause | resume | run_step
    url: Optional[str] = None
    viewport: Optional[Dict[str, int]] = None
    step: Optional[Dict[str, Any]] = None


def emit(stream, event: dict) -> None:
    """向给定流写一行 JSON 事件并立即 flush。"""
    line = json.dumps(event, ensure_ascii=False, default=str)
    stream.write(line + "\n")
    stream.flush()


ERROR_CODES = {
    "BROWSER_NOT_INSTALLED": "Chromium 浏览器未安装",
    "LAUNCH_FAILED": "浏览器启动失败",
    "NAVIGATION_FAILED": "页面导航失败",
    "SELECTOR_NOT_FOUND": "找不到页面元素",
    "ASSERTION_FAILED": "断言不通过",
    "STEP_TIMEOUT": "步骤执行超时",
    "UNSUPPORTED_ACTION": "不支持的步骤操作类型",
    "WORKER_CRASHED": "子进程异常退出",
    "ABORTED": "用户中止执行",
    "INTERNAL": "内部错误",
}


def make_error(code: str, message: str, traceback_str: str = "",
               step_index: Optional[int] = None,
               screenshot_path: Optional[str] = None) -> Dict[str, Any]:
    return {
        "type": "error",
        "code": code,
        "message": message,
        "traceback": traceback_str,
        "step_index": step_index,
        "screenshot_path": screenshot_path,
    }
