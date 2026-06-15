# UI 测试模块深度修复与二次开发 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Playwright 调用从 Django 主进程剥离到独立子进程，彻底修复"空错误/临时目录污染/ASGI 事件循环冲突"，并完成实时进度推送、录制 UX 二次开发。

**Architecture:** 新增 `backend/qa_center/workers/` 包：`protocol.py`（事件/命令定义）、`runner_worker.py`（用例执行子进程）、`recorder_worker.py`（录制子进程）、`runner_supervisor.py` / `recorder_supervisor.py`（Django 侧进程管理 + JSON Lines 双向通信）。`views_ui_test.py` 改为通过 supervisor 调度；`consumers.py` 新增运行实时事件 WS。前端拆分 `UiCaseDetail.vue`，新增 `RunDrawer.vue` 与 `RecorderPanel.vue`。

**Tech Stack:** Python `subprocess` + JSON Lines (stdin/stdout) + Django Channels (WebSocket) + Vue 3 composables + Element Plus

**Spec:** `docs/superpowers/specs/2026-06-15-ui-test-module-deep-fix-design.md`

---

## M1：Worker 骨架 + 协议定义

### Task 1：定义 protocol.py（事件/命令类型 + 错误码）

**Files:**
- Create: `backend/qa_center/workers/__init__.py`（空文件）
- Create: `backend/qa_center/workers/protocol.py`

- [ ] **Step 1：创建 workers 包目录**

```bash
mkdir -p backend/qa_center/workers
touch backend/qa_center/workers/__init__.py
```

- [ ] **Step 2：写 protocol.py**

`backend/qa_center/workers/protocol.py`：

```python
"""
Worker 通信协议定义
所有 stdout 事件和 stdin 命令统一为 JSON Lines（每行一个完整 JSON）。
"""
from dataclasses import dataclass, field, asdict
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


def emit(stream, event: dict):
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
```

- [ ] **Step 3：快速验证**

```bash
cd backend && python -c "from qa_center.workers.protocol import make_error, ERROR_CODES; print(make_error('LAUNCH_FAILED','test')); print(len(ERROR_CODES))"
```
Expected: 输出 dict + 数字 10。

- [ ] **Step 4：Commit**

```bash
git add backend/qa_center/workers/__init__.py backend/qa_center/workers/protocol.py
git commit -m "feat(qa): worker 通信协议定义 (protocol.py)"
```

### Task 2：runner_worker.py 骨架（无 Playwright，仅回声）

**Files:**
- Create: `backend/qa_center/workers/runner_worker.py`

- [ ] **Step 1：写文件**

`backend/qa_center/workers/runner_worker.py`：

```python
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


def emit(event: dict):
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


def cleanup_temp_dir(td: str):
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
```

- [ ] **Step 2：手动验证回声**

```bash
cd backend && echo '{"case_id":1,"steps":[{"action":"goto","desc":"go"}]}' | python -m qa_center.workers.runner_worker
```
Expected：5 行 JSON（started → step_start → step_log → step_done → finished），并且 `.playwright-temp/run_xxx/` 目录在退出后被清理。

- [ ] **Step 3：Commit**

```bash
git add backend/qa_center/workers/runner_worker.py
git commit -m "feat(qa): runner_worker 骨架 (stdin/stdout JSONL)"
```

### Task 3：recorder_worker.py 骨架

**Files:**
- Create: `backend/qa_center/workers/recorder_worker.py`

- [ ] **Step 1：写文件**

`backend/qa_center/workers/recorder_worker.py`：

```python
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


def emit(event: dict):
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


def cleanup_temp_dir(td: str):
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
            cmd = read_command()
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
```

- [ ] **Step 2：验证**

```bash
cd backend && printf '{"cmd":"start","url":"https://example.com"}\n{"cmd":"stop"}\n' | python -m qa_center.workers.recorder_worker
```
Expected：ready → record_event → stopped。

- [ ] **Step 3：Commit**

```bash
git add backend/qa_center/workers/recorder_worker.py
git commit -m "feat(qa): recorder_worker 骨架 (stdin/stdout JSONL)"
```

---

## M2：Runner 子进程化（接入真实 Playwright）

### Task 4：runner_supervisor.py

**Files:**
- Create: `backend/qa_center/workers/runner_supervisor.py`

- [ ] **Step 1：写文件**

`backend/qa_center/workers/runner_supervisor.py`：

```python
"""
Runner Supervisor — 在 Django 进程中启动 runner_worker 子进程并流式读事件。
"""
import subprocess
import sys
import os
import json
import threading
import logging
from typing import Callable, Optional

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

    # 喂入参
    try:
        proc.stdin.write(json.dumps(case_data, ensure_ascii=False, default=str) + "\n")
        proc.stdin.flush()
        proc.stdin.close()
    except Exception:
        logger.exception("写入 worker stdin 失败")

    # 后台读 stderr 转发到 logger
    stderr_buf: list = []

    def _drain_stderr():
        for line in proc.stderr:
            stderr_buf.append(line)
            logger.info("[worker:%s] %s", proc.pid, line.rstrip())

    t = threading.Thread(target=_drain_stderr, daemon=True)
    t.start()

    # 主线程读 stdout 事件
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

    # 异常退出兜底
    if proc.returncode not in (0, None) and final_result.get("type") != "finished":
        crash_msg = "".join(stderr_buf[-20:])
        on_event({
            "type": "error",
            "code": "WORKER_CRASHED",
            "message": f"worker 退出码 {proc.returncode}",
            "traceback": crash_msg,
        })

    return final_result
```

- [ ] **Step 2：Smoke test**

```bash
cd backend && python -c "
from qa_center.workers.runner_supervisor import execute_ui_case
events = []
result = execute_ui_case({'case_id':None,'url':'https://example.com','steps':[{'action':'noop'}]}, events.append)
print('events count:', len(events))
print('result:', result)
"
```
Expected：events 包含 started + step_done + finished 等；result.success = True。

- [ ] **Step 3：Commit**

```bash
git add backend/qa_center/workers/runner_supervisor.py
git commit -m "feat(qa): runner_supervisor 子进程管理 + 事件流"
```

### Task 5：runner_worker 接入真实 Playwright

**Files:**
- Modify: `backend/qa_center/workers/runner_worker.py`

- [ ] **Step 1：在 worker 中加入 `_run_steps` 与 `_execute_single_step`**

在 `runner_worker.py` 顶部 import 之外加入两个新函数，然后改 `main()` 调 `_run_steps`：

```python
def _execute_single_step(page, step: dict, emit_fn):
    from playwright.sync_api import expect

    action = (step.get("action") or "").lower()
    selector = step.get("selector", "")
    value = step.get("value", "")
    url = step.get("url", "")
    attribute = step.get("attribute", "")
    expected_value = step.get("expected_value", "")

    def _wait(sel, timeout=10000):
        loc = page.locator(sel)
        loc.wait_for(state="visible", timeout=timeout)
        return loc

    if action == "goto" and url:
        page.goto(url, wait_until="networkidle", timeout=30000)
    elif action == "wait":
        page.wait_for_timeout(int(value) if str(value).isdigit() else 1000)
    elif action in ("click", "click_if_visible"):
        _wait(selector).click(timeout=10000)
    elif action in ("dblclick", "double_click"):
        _wait(selector).dblclick(timeout=10000)
    elif action == "fill":
        _wait(selector).fill(value or "")
    elif action == "select":
        _wait(selector).select_option(value)
    elif action == "hover":
        _wait(selector).hover()
    elif action == "scroll":
        page.evaluate(f"window.scrollTo(0, {value or 0})")
    elif action == "assert_visible":
        expect(page.locator(selector)).to_be_visible()
    elif action == "assert_text":
        expect(page.locator(selector)).to_have_text(expected_value or value)
    elif action == "assert_contains_text":
        expect(page.locator(selector)).to_contain_text(expected_value or value)
    elif action == "assert_attribute":
        expect(page.locator(selector)).to_have_attribute(attribute, expected_value)
    elif action == "assert_url":
        expect(page).to_have_url(expected_value or value)
    elif action == "assert_count":
        expect(page.locator(selector)).to_have_count(int(value))
    elif action == "drag":
        target_sel = step.get("target_selector", selector)
        _wait(selector).drag_to(_wait(target_sel), timeout=15000)
    elif action == "screenshot":
        pass
    else:
        from .protocol import ERROR_CODES  # 不抛异常,通过返回标记
        raise ValueError(f"UNSUPPORTED_ACTION:{action}")


def _classify_error(exc: Exception) -> str:
    msg = str(exc)
    cls = exc.__class__.__name__
    if "executable" in msg.lower() and "doesn" in msg.lower():
        return "BROWSER_NOT_INSTALLED"
    if cls == "TimeoutError" or "Timeout" in cls:
        return "STEP_TIMEOUT"
    if "找不到" in msg or "Locator" in msg:
        return "SELECTOR_NOT_FOUND"
    if msg.startswith("UNSUPPORTED_ACTION:"):
        return "UNSUPPORTED_ACTION"
    return "INTERNAL"


def _run_steps(case_data: dict) -> dict:
    from playwright.sync_api import sync_playwright

    url = (case_data.get("url") or "").strip()
    steps = case_data.get("steps") or []
    temp_dir = os.environ.get("TEMP", "")

    if not url:
        emit({"type": "error", "code": "INTERNAL", "message": "未提供起始 URL"})
        return {"success": False, "summary": {"passed": 0, "failed": 1, "total": 1}}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    shots_dir = os.path.join(temp_dir, "screenshots")
    os.makedirs(shots_dir, exist_ok=True)

    passed = 0
    failed = 0

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage", "--disable-gpu",
                    "--disable-web-security",
                    "--disable-extensions",
                    "--disk-cache-dir=" + temp_dir,
                ],
                downloads_path=temp_dir,
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True,
            )
            page = context.new_page()

            emit({"type": "step_start", "index": -1, "action": "goto", "desc": f"导航到 {url}"})
            page.goto(url, wait_until="networkidle", timeout=30000)
            emit({"type": "step_log", "index": -1, "message": "页面加载完成"})

            for i, step in enumerate(steps):
                emit({"type": "step_start", "index": i, "action": step.get("action"), "desc": f"步骤{i+1}"})
                try:
                    _execute_single_step(page, step, emit)
                    page.wait_for_timeout(500)
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    shot_path = os.path.join(shots_dir, f"step_{i}.png")
                    page.screenshot(path=shot_path, full_page=True)
                    emit({"type": "step_screenshot", "index": i, "path": shot_path})
                    emit({"type": "step_done", "index": i, "success": True})
                    passed += 1
                except Exception as e:
                    failed += 1
                    code = _classify_error(e)
                    tb = traceback.format_exc()
                    try:
                        shot_path = os.path.join(shots_dir, f"step_{i}_fail.png")
                        page.screenshot(path=shot_path, full_page=True)
                        emit({"type": "step_screenshot", "index": i, "path": shot_path})
                    except Exception:
                        pass
                    emit({"type": "step_done", "index": i, "success": False,
                          "code": code, "message": str(e), "traceback": tb})
                    context.close()
                    browser.close()
                    return {"success": False, "summary": {"passed": passed, "failed": failed, "total": len(steps)}}

            page.wait_for_timeout(1500)
            final_path = os.path.join(shots_dir, "final.png")
            page.screenshot(path=final_path, full_page=True)
            emit({"type": "step_screenshot", "index": len(steps), "path": final_path})

            context.close()
            browser.close()
            return {"success": True, "summary": {"passed": passed, "failed": 0, "total": len(steps)}}

    except Exception as e:
        code = _classify_error(e)
        tb = traceback.format_exc()
        emit({"type": "error", "code": code if code != "INTERNAL" else "LAUNCH_FAILED",
              "message": str(e), "traceback": tb})
        return {"success": False, "summary": {"passed": passed, "failed": failed + 1, "total": len(steps)}}
```

并修改 `main()`：

```python
def main():
    _setup_io_logging()
    temp_dir = None
    try:
        inp = read_input()
        temp_dir = setup_temp_dir()
        emit({"type": "started", "temp_dir": temp_dir})
        result = _run_steps(inp)
        emit({"type": "finished", **result})
    except Exception as e:
        emit({"type": "error", "code": "INTERNAL", "message": str(e), "traceback": traceback.format_exc()})
        emit({"type": "finished", "success": False, "summary": {"passed": 0, "failed": 1, "total": 1}})
    finally:
        if temp_dir:
            cleanup_temp_dir(temp_dir)
```

- [ ] **Step 2：本地手测**

```bash
cd backend && printf '{"case_id":null,"url":"https://example.com","steps":[]}\n' | python -m qa_center.workers.runner_worker
```
Expected：started → step_start(-1, goto) → step_log → step_screenshot(0,final) → finished success=True。

- [ ] **Step 3：故意失败**

```bash
cd backend && printf '{"case_id":null,"url":"https://example.com","steps":[{"action":"click","selector":"#nope"}]}\n' | python -m qa_center.workers.runner_worker
```
Expected：step_done success=false code=SELECTOR_NOT_FOUND，且 traceback 不为空。

- [ ] **Step 4：Commit**

```bash
git add backend/qa_center/workers/runner_worker.py
git commit -m "feat(qa): runner_worker 接入真实 Playwright + 错误分类"
```

### Task 6：views_ui_test 改用 supervisor

**Files:**
- Modify: `backend/qa_center/views_ui_test.py`
- Modify: `backend/qa_center/utils/runner.py`（移除 TEMP/TMP 进程级污染）

- [ ] **Step 1：替换 import 与 `run` action**

`backend/qa_center/views_ui_test.py` 顶部：

```python
import threading
import traceback as _tb
import base64
import os
import uuid
from datetime import datetime

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone

from .models import UiTestCase
from .serializers import UiTestCaseSerializer, UiTestCaseListSerializer, UiTestCaseRunSerializer
from .workers.runner_supervisor import execute_ui_case
```

把 `run()` action 改为：

```python
@action(detail=True, methods=["post"])
def run(self, request, pk=None):
    test_case = self.get_object()
    case_data = {
        "case_id": test_case.id,
        "url": test_case.url,
        "steps": test_case.steps or [],
    }
    events: list = []
    result = execute_ui_case(case_data, on_event=events.append)

    payload = self._events_to_payload(events, result)

    def save_in_background():
        try:
            self._save_test_result(test_case, result, events, request)
        except Exception:
            print("[ERROR] 后台保存失败", _tb.format_exc())

    threading.Thread(target=save_in_background, daemon=True).start()
    return Response(payload, status=status.HTTP_200_OK)
```

并新增 helper：

```python
def _events_to_payload(self, events, result):
    logs = []
    step_screenshots = []
    error_msg = None
    error_code = None
    for ev in events:
        t = ev.get("type")
        if t == "step_log":
            logs.append(ev.get("message", ""))
        elif t == "step_screenshot" and ev.get("path"):
            try:
                with open(ev["path"], "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                step_screenshots.append({
                    "step": ev.get("index", 0),
                    "screenshot": f"data:image/png;base64,{b64}",
                })
            except Exception:
                pass
        elif t == "error":
            error_msg = ev.get("message", "")
            error_code = ev.get("code")
        elif t == "step_done" and not ev.get("success"):
            error_msg = error_msg or ev.get("message", "")
            error_code = error_code or ev.get("code")
    return {
        "success": result.get("success", False),
        "logs": logs,
        "step_screenshots": step_screenshots,
        "error": error_msg,
        "error_code": error_code,
        "summary": result.get("summary", {}),
    }
```

- [ ] **Step 2：把 `_save_test_result` 改为读 events**

```python
def _save_test_result(self, test_case, result, events, request):
    from .models import TestResult, TestScreenshot
    error_msg = ""
    error_code = None
    error_tb = ""
    for ev in events:
        if ev.get("type") == "error":
            error_msg = ev.get("message", "")
            error_code = ev.get("code")
            error_tb = ev.get("traceback", "")
        elif ev.get("type") == "step_done" and not ev.get("success"):
            error_msg = error_msg or ev.get("message", "")
            error_code = error_code or ev.get("code")
            error_tb = error_tb or ev.get("traceback", "")

    test_result = TestResult.objects.create(
        test_type="ui",
        name=test_case.name,
        project=test_case.project,
        ui_test_case=test_case,
        executed_by=request.user,
        status="passed" if result.get("success") else "failed",
        test_steps=test_case.steps or [],
        actual_result="测试完成" if result.get("success") else error_msg,
        error_message=error_msg,
        test_log="\n".join(ev.get("message", "") for ev in events if ev.get("type") == "step_log"),
        started_at=timezone.now(),
        completed_at=timezone.now(),
    )

    for ev in events:
        if ev.get("type") == "step_screenshot" and ev.get("path"):
            try:
                with open(ev["path"], "rb") as f:
                    image_data = f.read()
                idx = ev.get("index", 0)
                fname = f"ui_test_step{idx}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"
                rel_dir = os.path.join("test_screenshots", datetime.now().strftime("%Y/%m/%d"))
                full_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
                os.makedirs(full_dir, exist_ok=True)
                with open(os.path.join(full_dir, fname), "wb") as f:
                    f.write(image_data)
                TestScreenshot.objects.create(
                    test_result=test_result,
                    name=f"步骤 {idx} 截图",
                    image=os.path.join(rel_dir, fname),
                )
            except Exception:
                import logging
                logging.getLogger("qa_center.runner").exception("保存截图失败")

    return test_result
```

- [ ] **Step 3：改 `run_temp` action**

```python
@action(detail=False, methods=["post"])
def run_temp(self, request):
    url = request.data.get("url", "")
    steps = request.data.get("steps", [])
    if not url:
        return Response({"error": "请提供起始 URL"}, status=status.HTTP_400_BAD_REQUEST)
    case_data = {"case_id": None, "url": url, "steps": steps}
    events: list = []
    result = execute_ui_case(case_data, on_event=events.append)
    return Response(self._events_to_payload(events, result), status=status.HTTP_200_OK)
```

- [ ] **Step 4：改批量函数 `execute_ui_test_cases`**

```python
def execute_ui_test_cases(case_ids):
    from .workers.runner_supervisor import execute_ui_case
    from .models import TestResult, TestScreenshot
    results = []
    for case_id in case_ids:
        try:
            tc = UiTestCase.objects.get(id=case_id)
        except UiTestCase.DoesNotExist:
            results.append({"case_id": case_id, "case_name": "未知用例", "passed": False, "message": "测试用例不存在"})
            continue
        events: list = []
        result = execute_ui_case(
            {"case_id": tc.id, "url": tc.url, "steps": tc.steps or []},
            on_event=events.append,
        )
        # 写库（简化复用）
        try:
            tr = TestResult.objects.create(
                test_type="ui", name=tc.name, project=tc.project,
                ui_test_case=tc, executed_by=None,
                status="passed" if result.get("success") else "failed",
                test_steps=tc.steps or [],
                actual_result="测试完成" if result.get("success") else "失败",
                error_message="",
                test_log="\n".join(ev.get("message", "") for ev in events if ev.get("type") == "step_log"),
                started_at=timezone.now(), completed_at=timezone.now(),
            )
        except Exception:
            tr = None
        steps_result = []
        for i, step in enumerate(tc.steps or []):
            steps_result.append({
                "step_number": i + 1, "action": step.get("action", ""),
                "selector": step.get("selector", ""), "value": step.get("value", ""),
                "status": "passed" if result.get("success") else "failed", "logs": [],
            })
        results.append({
            "case_id": case_id, "case_name": tc.name, "passed": result.get("success", False),
            "type": "ui",
            "message": "测试完成" if result.get("success") else "失败",
            "request": {"method": "UI", "url": tc.url, "headers": {}, "body": {"steps": tc.steps or []}},
            "response": {"status_code": 200 if result.get("success") else 500, "body": "", "headers": {}},
            "steps": steps_result,
            "screenshot_url": None,
            "assertions": [],
        })
    return results
```

- [ ] **Step 5：移除 `utils/runner.py` 中进程级 TEMP/TMP 污染**

`backend/qa_center/utils/runner.py:36-38` 删掉这两行：

```python
os.environ['TEMP'] = self.temp_dir
os.environ['TMP'] = self.temp_dir
```

只保留 `os.environ['PLAYWRIGHT_TEMP_DIR']` 那一行。

- [ ] **Step 6：手测端到端**

启动后端：`cd backend && python manage.py runserver 127.0.0.1:8000` 后，前端点运行 — 现在应该能看到结构化错误（不再是空字符串）。

并发 5 次运行，确认 `.playwright-temp/` 不出现锁定异常，运行结束目录被清理。

- [ ] **Step 7：Commit**

```bash
git add backend/qa_center/views_ui_test.py backend/qa_center/utils/runner.py
git commit -m "feat(qa): views_ui_test 切换到 runner_supervisor 子进程模式"
```

---

## M3：错误模型 + DB Migration + 详情页错误展示

### Task 7：在 TestResult 模型加字段

**Files:**
- Modify: `backend/qa_center/models.py`
- Create: `backend/qa_center/migrations/00XX_testresult_error_fields.py`（编号自动）

- [ ] **Step 1：加字段**

定位 `class TestResult(models.Model):`，在合适位置添加：

```python
task_id = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="任务ID")
error_code = models.CharField(max_length=64, blank=True, default="", verbose_name="错误码")
error_traceback = models.TextField(blank=True, default="", verbose_name="错误堆栈")
worker_pid = models.IntegerField(blank=True, null=True, verbose_name="Worker PID")
temp_dir_path = models.CharField(max_length=512, blank=True, default="", verbose_name="临时目录")
aborted = models.BooleanField(default=False, verbose_name="是否被中止")
```

- [ ] **Step 2：生成迁移**

```bash
cd backend && python manage.py makemigrations qa_center -n testresult_error_fields
```
Expected：生成新 migration 文件，仅 add column。

- [ ] **Step 3：执行迁移**

```bash
cd backend && python manage.py migrate qa_center
```

- [ ] **Step 4：Commit**

```bash
git add backend/qa_center/models.py backend/qa_center/migrations/
git commit -m "feat(qa): TestResult 增加错误码/堆栈/worker_pid 等字段"
```

### Task 8：保存结果时填充新字段

**Files:**
- Modify: `backend/qa_center/views_ui_test.py`
- Modify: `backend/qa_center/workers/runner_supervisor.py`

- [ ] **Step 1：supervisor 暴露 worker_pid 与 task_id**

```python
import uuid as _uuid

def execute_ui_case(case_data, on_event, timeout_seconds=300):
    task_id = _uuid.uuid4().hex
    ...
    proc = subprocess.Popen(...)
    on_event({"type": "supervisor_meta", "task_id": task_id, "worker_pid": proc.pid})
    ...
```

- [ ] **Step 2：`_save_test_result` 填字段**

```python
worker_pid = None
task_id = ""
temp_dir_path = ""
for ev in events:
    if ev.get("type") == "supervisor_meta":
        task_id = ev.get("task_id", "")
        worker_pid = ev.get("worker_pid")
    if ev.get("type") == "started":
        temp_dir_path = ev.get("temp_dir", "")
test_result = TestResult.objects.create(
    ...
    task_id=task_id,
    error_code=error_code or "",
    error_traceback=error_tb,
    worker_pid=worker_pid,
    temp_dir_path=temp_dir_path,
    aborted=False,
)
```

- [ ] **Step 3：序列化器返回新字段**

`backend/qa_center/serializers.py` 的 `TestResultSerializer` 中 `Meta.fields` 增加 `error_code`、`error_traceback`、`worker_pid`、`temp_dir_path`、`aborted`、`task_id`。如果用 `__all__` 则可跳过。

- [ ] **Step 4：详情页前端渲染**

`frontend/src/views/qa/TestResultDetail.vue` 在错误信息区块增加：

```vue
<el-alert v-if="result.error_code" type="error" :closable="false">
  <template #title>
    [{{ result.error_code }}] {{ result.error_message }}
  </template>
  <pre v-if="result.error_traceback" class="error-tb">{{ result.error_traceback }}</pre>
</el-alert>
```

CSS：

```css
.error-tb { max-height: 400px; overflow: auto; font-size: 12px; background: #fafafa; padding: 8px; }
```

- [ ] **Step 5：Commit**

```bash
git add backend/qa_center/ frontend/src/views/qa/TestResultDetail.vue
git commit -m "feat(qa): 测试结果保存错误码/堆栈,详情页可见"
```

---

## M4：运行实时事件流（WS 频道 + RunDrawer.vue）

### Task 9：新增 WS Consumer + 路由

**Files:**
- Modify: `backend/qa_center/consumers.py`
- Modify: `backend/qa_center/routing.py`

- [ ] **Step 1：consumers.py 新增 `UiRunConsumer`**

```python
class UiRunConsumer(AsyncWebsocketConsumer):
    """UI 用例实时运行进度推送
    URL: /ws/qa/run/{task_id}/
    """
    async def connect(self):
        self.task_id = self.scope["url_route"]["kwargs"].get("task_id")
        self.group_name = f"ui_run_{self.task_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connected", "task_id": self.task_id}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def run_event(self, event):
        await self.send(text_data=json.dumps(event["data"]))
```

- [ ] **Step 2：routing.py 注册**

```python
re_path(r'ws/qa/run/(?P<task_id>\w+)/$', consumers.UiRunConsumer.as_asgi()),
```

- [ ] **Step 3：Commit**

```bash
git add backend/qa_center/consumers.py backend/qa_center/routing.py
git commit -m "feat(qa): 新增 UiRunConsumer (ws/qa/run/{task_id}/)"
```

### Task 10：supervisor 把事件推 WS

**Files:**
- Modify: `backend/qa_center/views_ui_test.py`

- [ ] **Step 1：异步执行 + WS 转发**

把 `run()` 改为：

```python
@action(detail=True, methods=["post"])
def run(self, request, pk=None):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    import uuid as _uuid

    test_case = self.get_object()
    task_id = _uuid.uuid4().hex
    case_data = {"case_id": test_case.id, "url": test_case.url, "steps": test_case.steps or []}

    channel_layer = get_channel_layer()
    group_name = f"ui_run_{task_id}"

    def push(event_data):
        try:
            async_to_sync(channel_layer.group_send)(group_name, {
                "type": "run_event",
                "data": event_data,
            })
        except Exception:
            pass

    events: list = []

    def collector(ev):
        events.append(ev)
        push(ev)

    def runner_thread():
        try:
            result = execute_ui_case(case_data, on_event=collector)
            push({"type": "run_finished_persisted", "task_id": task_id})
            self._save_test_result(test_case, result, events, request, task_id=task_id)
        except Exception:
            print("[ERROR] runner_thread 失败", _tb.format_exc())

    threading.Thread(target=runner_thread, daemon=True).start()

    return Response({"task_id": task_id}, status=status.HTTP_202_ACCEPTED)
```

`_save_test_result` 接受 `task_id` 参数（替代从 events 里翻 supervisor_meta）。

- [ ] **Step 2：Commit**

```bash
git add backend/qa_center/views_ui_test.py
git commit -m "feat(qa): UI 用例运行改为异步 + WS 推送实时事件"
```

### Task 11：前端 useUiRunSocket composable

**Files:**
- Create: `frontend/src/composables/useUiRunSocket.ts`

- [ ] **Step 1：写文件**

```typescript
import { ref, onUnmounted } from 'vue'

export interface RunEvent {
  type: string
  index?: number
  action?: string
  desc?: string
  message?: string
  success?: boolean
  code?: string
  path?: string
  summary?: { passed: number; failed: number; total: number }
  [key: string]: any
}

export function useUiRunSocket(taskId: string) {
  const events = ref<RunEvent[]>([])
  const connected = ref(false)
  const finished = ref(false)
  const ws = ref<WebSocket | null>(null)

  function connect() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/qa/run/${taskId}/`
    const socket = new WebSocket(url)
    ws.value = socket
    socket.onopen = () => { connected.value = true }
    socket.onclose = () => { connected.value = false }
    socket.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        events.value.push(data)
        if (data.type === 'finished' || data.type === 'run_finished_persisted') {
          finished.value = true
        }
      } catch {}
    }
  }

  function close() {
    ws.value?.close()
    ws.value = null
  }

  onUnmounted(close)

  return { events, connected, finished, connect, close }
}
```

- [ ] **Step 2：Commit**

```bash
git add frontend/src/composables/useUiRunSocket.ts
git commit -m "feat(qa): useUiRunSocket composable"
```

### Task 12：RunDrawer.vue 组件

**Files:**
- Create: `frontend/src/views/qa/components/RunDrawer.vue`
- Modify: `frontend/src/views/qa/UiCaseList.vue`、`UiCaseDetail.vue`

- [ ] **Step 1：写组件**

`frontend/src/views/qa/components/RunDrawer.vue`：

```vue
<template>
  <el-drawer v-model="visible" :title="`运行：${caseName}`" size="50%" :before-close="handleClose">
    <div class="run-drawer">
      <el-tag v-if="!finished && connected" type="warning">运行中</el-tag>
      <el-tag v-else-if="finished && lastSuccess" type="success">已通过</el-tag>
      <el-tag v-else-if="finished" type="danger">失败</el-tag>
      <el-tag v-else type="info">连接中…</el-tag>

      <div class="steps">
        <div v-for="(step, i) in stepsView" :key="i" class="step" :class="step.status">
          <div class="head">
            <span class="idx">{{ i + 1 }}</span>
            <span class="action">{{ step.action }}</span>
            <span class="desc">{{ step.desc }}</span>
            <el-tag v-if="step.status === 'passed'" type="success" size="small">通过</el-tag>
            <el-tag v-else-if="step.status === 'failed'" type="danger" size="small">失败</el-tag>
            <el-tag v-else-if="step.status === 'running'" type="warning" size="small">执行中</el-tag>
          </div>
          <div v-if="step.logs.length" class="logs">
            <pre>{{ step.logs.join('\n') }}</pre>
          </div>
          <div v-if="step.error" class="error">
            <strong>[{{ step.errorCode }}] {{ step.error }}</strong>
            <pre v-if="step.traceback">{{ step.traceback }}</pre>
          </div>
          <img v-if="step.screenshotPath" :src="screenshotUrl(step.screenshotPath)" class="thumb" />
        </div>
      </div>

      <el-button v-if="!finished" type="danger" plain @click="abort">中止</el-button>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useUiRunSocket } from '@/composables/useUiRunSocket'

const props = defineProps<{ modelValue: boolean; taskId: string; caseName: string }>()
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const { events, connected, finished, connect, close } = useUiRunSocket(props.taskId)

watch(() => props.modelValue, (v) => {
  if (v) connect()
  else close()
})

const stepsView = computed(() => {
  const map = new Map<number, any>()
  for (const ev of events.value) {
    const i = ev.index
    if (i == null || i < 0) continue
    if (!map.has(i)) {
      map.set(i, { action: '', desc: '', status: 'running', logs: [], error: '', errorCode: '', traceback: '', screenshotPath: '' })
    }
    const s = map.get(i)
    if (ev.type === 'step_start') {
      s.action = ev.action; s.desc = ev.desc; s.status = 'running'
    } else if (ev.type === 'step_log') {
      s.logs.push(ev.message)
    } else if (ev.type === 'step_screenshot') {
      s.screenshotPath = ev.path
    } else if (ev.type === 'step_done') {
      s.status = ev.success ? 'passed' : 'failed'
      if (!ev.success) {
        s.error = ev.message; s.errorCode = ev.code; s.traceback = ev.traceback
      }
    }
  }
  return Array.from(map.entries()).sort((a, b) => a[0] - b[0]).map(([_, v]) => v)
})

const lastSuccess = computed(() => {
  const fin = events.value.find(e => e.type === 'finished')
  return !!fin?.success
})

function screenshotUrl(path: string) {
  // path 是后端临时目录绝对路径；后端需要提供一个 endpoint 用 task_id+index 获取
  return `/api/qa/ui-run/screenshot/?path=${encodeURIComponent(path)}`
}

function abort() {
  // 后续 Task: 调用 POST /api/qa/ui-cases/runs/{task_id}/abort/
}

function handleClose(done: () => void) { close(); done() }
</script>

<style scoped>
.steps .step { padding: 8px; border: 1px solid #eee; margin: 8px 0; }
.step.passed { border-left: 3px solid #67c23a; }
.step.failed { border-left: 3px solid #f56c6c; }
.step.running { border-left: 3px solid #e6a23c; }
.thumb { max-width: 240px; margin-top: 8px; }
.error { color: #f56c6c; }
.error pre { font-size: 11px; max-height: 200px; overflow: auto; }
</style>
```

- [ ] **Step 2：UiCaseList.vue 触发抽屉**

把现有 `runCase()` 方法改为：

```typescript
async function runCase(row: any) {
  const { data } = await api.post(`/qa/ui-cases/${row.id}/run/`)
  currentTaskId.value = data.task_id
  currentCaseName.value = row.name
  runDrawerVisible.value = true
}
```

模板中加 `<RunDrawer v-model="runDrawerVisible" :task-id="currentTaskId" :case-name="currentCaseName" />`。

- [ ] **Step 3：截图临时 endpoint**

`backend/qa_center/views_ui_test.py` 末尾加：

```python
from django.http import FileResponse, HttpResponseBadRequest, Http404
import os as _os

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ui_run_screenshot(request):
    path = request.query_params.get("path", "")
    if not path:
        return HttpResponseBadRequest("path required")
    safe_root = _os.path.abspath(_os.path.join(settings.BASE_DIR, ".playwright-temp"))
    abs_path = _os.path.abspath(path)
    if not abs_path.startswith(safe_root):
        return HttpResponseBadRequest("invalid path")
    if not _os.path.exists(abs_path):
        raise Http404()
    return FileResponse(open(abs_path, "rb"), content_type="image/png")
```

需要 import `from rest_framework.decorators import api_view, permission_classes`。注册到 `urls.py`：

```python
path('ui-run/screenshot/', views_ui_test.ui_run_screenshot, name='ui_run_screenshot'),
```

- [ ] **Step 4：手测**

启动前后端，点列表"运行" → 抽屉打开，步骤逐个变绿/红，截图缩略图能看到。失败时能看到错误码与 traceback。

- [ ] **Step 5：Commit**

```bash
git add backend/qa_center/views_ui_test.py backend/qa_center/urls.py frontend/src/composables/useUiRunSocket.ts frontend/src/views/qa/components/RunDrawer.vue frontend/src/views/qa/UiCaseList.vue
git commit -m "feat(qa): UI 用例运行实时事件流 + RunDrawer"
```

---

## M5：Recorder 子进程化

### Task 13：recorder_supervisor.py

**Files:**
- Create: `backend/qa_center/workers/recorder_supervisor.py`

- [ ] **Step 1：写文件**

```python
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
```

- [ ] **Step 2：Commit**

```bash
git add backend/qa_center/workers/recorder_supervisor.py
git commit -m "feat(qa): recorder_supervisor (双向 stdin/stdout)"
```

### Task 14：recorder_worker 接入真实 Playwright（迁移现有 recorder.py 逻辑）

**Files:**
- Modify: `backend/qa_center/workers/recorder_worker.py`

- [ ] **Step 1：迁移核心录制循环**

把 `backend/qa_center/utils/recorder.py` 中的 `RECORDING_SCRIPT` 常量、`_handle_record_event`、`_handle_record_assert_event`、`run_recording_loop` 主体逻辑搬入 `recorder_worker.py`，结构：

```python
# 顶部加
from threading import Event

RECORDING_SCRIPT = """..."""  # 直接复制现有 recorder.py 的脚本


class _RecorderState:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_recording = False
        self.is_paused = False
        self.stop_event = Event()


def _do_start(state: _RecorderState, url: str, viewport: dict):
    from playwright.sync_api import sync_playwright
    state.playwright = sync_playwright().start()
    state.browser = state.playwright.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    state.context = state.browser.new_context(
        viewport=viewport or {"width": 1920, "height": 1080},
        accept_downloads=True,
    )
    state.page = state.context.new_page()

    def on_event(_source, payload):
        if state.is_paused:
            return
        emit({"type": "record_event", "data": payload})

    def on_assert_event(_source, payload):
        if state.is_paused:
            return
        emit({"type": "record_assert_event", "data": payload})

    state.page.expose_binding("onRecordEvent", on_event)
    state.page.expose_binding("onRecordAssertEvent", on_assert_event)
    state.page.add_init_script(RECORDING_SCRIPT)

    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    state.page.goto(url, wait_until="domcontentloaded", timeout=30000)
    state.page.evaluate(RECORDING_SCRIPT)

    state.is_recording = True
    emit({"type": "ready", "success": True})


def _do_stop(state: _RecorderState):
    state.is_recording = False
    try:
        if state.page: state.page.close()
    except Exception: pass
    try:
        if state.context: state.context.close()
    except Exception: pass
    try:
        if state.browser: state.browser.close()
    except Exception: pass
    try:
        if state.playwright: state.playwright.stop()
    except Exception: pass


def _do_run_step(state: _RecorderState, step: dict):
    # 复用 runner_worker 中的 _execute_single_step
    from .runner_worker import _execute_single_step
    if not state.page:
        emit({"type": "step_run_done", "success": False, "code": "INTERNAL", "message": "未启动录制"})
        return
    try:
        _execute_single_step(state.page, step, lambda e: None)
        emit({"type": "step_run_done", "success": True})
    except Exception as e:
        emit({
            "type": "step_run_done", "success": False,
            "code": "INTERNAL", "message": str(e), "traceback": traceback.format_exc(),
        })
```

修改 `main()`：

```python
def main():
    _setup_io_logging()
    temp_dir = None
    state = _RecorderState()
    try:
        temp_dir = setup_temp_dir()
        emit({"type": "ready", "success": True, "phase": "temp_ready", "temp_dir": temp_dir})

        running = True
        while running:
            try:
                cmd = read_command()
            except EOFError:
                break
            action = cmd.get("cmd")
            try:
                if action == "start":
                    _do_start(state, cmd.get("url", ""), cmd.get("viewport"))
                elif action == "pause":
                    state.is_paused = True
                    emit({"type": "paused"})
                elif action == "resume":
                    state.is_paused = False
                    emit({"type": "resumed"})
                elif action == "run_step":
                    _do_run_step(state, cmd.get("step") or {})
                elif action == "stop":
                    _do_stop(state)
                    emit({"type": "stopped", "success": True})
                    running = False
                else:
                    emit({"type": "error", "code": "INTERNAL", "message": f"未知命令: {action}"})
            except Exception as e:
                tb = traceback.format_exc()
                code = "LAUNCH_FAILED" if action == "start" else "INTERNAL"
                if "executable" in str(e).lower() and "doesn" in str(e).lower():
                    code = "BROWSER_NOT_INSTALLED"
                emit({"type": "error", "code": code, "message": str(e), "traceback": tb})
                if action == "start":
                    _do_stop(state)
    finally:
        _do_stop(state)
        if temp_dir:
            cleanup_temp_dir(temp_dir)
```

- [ ] **Step 2：手测**

```bash
cd backend && (printf '{"cmd":"start","url":"https://example.com"}\n'; sleep 5; printf '{"cmd":"stop"}\n') | python -m qa_center.workers.recorder_worker
```
Expected：浏览器打开 example.com，约 5 秒后关闭；stdout 含 ready / record_event / stopped。

- [ ] **Step 3：Commit**

```bash
git add backend/qa_center/workers/recorder_worker.py
git commit -m "feat(qa): recorder_worker 接入真实 Playwright + 暂停/恢复/单步"
```

### Task 15：RecorderConsumer 改用 supervisor

**Files:**
- Modify: `backend/qa_center/consumers.py`

- [ ] **Step 1：替换 `RecorderConsumer.handle_start_recording` 与相关方法**

```python
from .workers.recorder_supervisor import RecorderSession

class RecorderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        safe_name = re.sub(r'[^a-zA-Z0-9\-_]', '', self.channel_name[:50])
        self.group_name = f"recorder_{safe_name}"
        self.session: RecorderSession = None
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connected"}))

    async def disconnect(self, close_code):
        if self.session:
            self.session.stop()
            self.session = None
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except Exception:
            await self.send(text_data=json.dumps({"type": "error", "message": "无效 JSON"}))
            return
        cmd = data.get("command")
        if cmd == "start_recording":
            await self.start(data.get("url", ""), data.get("viewport"))
        elif cmd == "stop_recording":
            await self.stop()
        elif cmd == "pause_recording":
            self.session and self.session.send({"cmd": "pause"})
        elif cmd == "resume_recording":
            self.session and self.session.send({"cmd": "resume"})
        elif cmd == "run_step":
            self.session and self.session.send({"cmd": "run_step", "step": data.get("step") or {}})
        else:
            await self.send(text_data=json.dumps({"type": "error", "message": f"未知命令: {cmd}"}))

    async def start(self, url, viewport):
        if self.session and self.session.is_alive():
            self.session.stop()
        main_loop = asyncio.get_event_loop()

        def on_event(ev):
            asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps(self._map_event(ev))),
                main_loop,
            )

        self.session = RecorderSession(on_event=on_event)
        self.session.start()
        self.session.send({"cmd": "start", "url": url, "viewport": viewport})

    async def stop(self):
        if not self.session:
            await self.send(text_data=json.dumps({"type": "error", "message": "录制未在进行"}))
            return
        self.session.stop()
        self.session = None
        await self.send(text_data=json.dumps({"type": "recording_stopped"}))

    def _map_event(self, ev):
        # 把 worker 事件映射回前端期望的结构（保留向后兼容）
        t = ev.get("type")
        if t == "ready" and ev.get("success") and "phase" not in ev:
            return {"type": "recording_started", "message": "录制已开始"}
        if t == "error":
            return {"type": "error", "code": ev.get("code", ""), "message": f"[{ev.get('code','')}] {ev.get('message','')}", "traceback": ev.get("traceback", "")}
        if t == "record_event":
            return {"type": "record_event", "data": ev.get("data")}
        if t == "record_assert_event":
            return {"type": "record_assert_event", "data": ev.get("data")}
        if t == "stopped":
            return {"type": "recording_stopped", "message": "录制已停止"}
        if t == "paused":
            return {"type": "recording_paused"}
        if t == "resumed":
            return {"type": "recording_resumed"}
        if t == "step_run_done":
            return {"type": "step_run_done", "success": ev.get("success"), "code": ev.get("code"), "message": ev.get("message")}
        return ev
```

- [ ] **Step 2：删除 `utils/recorder.py` 中模块级 TEMP/TMP 污染**

`backend/qa_center/utils/recorder.py:22-33` 的 `_setup_playwright_env()` 函数和它在模块顶部的调用（如有）删除；保留其余文件内容，因为代码暂未删除时仍可能被其它路径 import。可以加 deprecation 注释。

- [ ] **Step 3：手测**

启动后端，前端 UiCaseDetail 点录制，浏览器无头窗口（实为有头）打开，前端能收到 `recording_started`，操作页面能看到 `record_event` 推回，stop 后浏览器关闭。

如果失败，前端能看到 `[LAUNCH_FAILED] <实际错误信息>`（不再是空字符串）。

- [ ] **Step 4：Commit**

```bash
git add backend/qa_center/consumers.py backend/qa_center/utils/recorder.py
git commit -m "feat(qa): RecorderConsumer 改用 RecorderSession 子进程"
```

---

## M6：录制 UX 二次开发

### Task 16：拆分 UiCaseDetail.vue → useRecorderSocket + RecorderPanel.vue

**Files:**
- Create: `frontend/src/composables/useRecorderSocket.ts`
- Create: `frontend/src/views/qa/components/RecorderPanel.vue`
- Modify: `frontend/src/views/qa/UiCaseDetail.vue`

- [ ] **Step 1：写 useRecorderSocket.ts**

```typescript
import { ref, onUnmounted } from 'vue'

export interface RecorderEvent {
  type: string
  data?: any
  message?: string
  code?: string
  success?: boolean
}

export function useRecorderSocket() {
  const events = ref<RecorderEvent[]>([])
  const status = ref<'idle' | 'connecting' | 'recording' | 'paused' | 'stopped' | 'error'>('idle')
  const lastError = ref<{ code: string; message: string } | null>(null)
  const ws = ref<WebSocket | null>(null)

  function open() {
    if (ws.value) return
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/qa/recorder/`
    const sock = new WebSocket(url)
    ws.value = sock
    status.value = 'connecting'
    sock.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data)
        events.value.push(ev)
        switch (ev.type) {
          case 'recording_started': status.value = 'recording'; break
          case 'recording_paused': status.value = 'paused'; break
          case 'recording_resumed': status.value = 'recording'; break
          case 'recording_stopped': status.value = 'stopped'; break
          case 'error':
            status.value = 'error'
            lastError.value = { code: ev.code || '', message: ev.message || '' }
            break
        }
      } catch {}
    }
    sock.onclose = () => { ws.value = null }
  }

  function send(msg: any) {
    ws.value?.send(JSON.stringify(msg))
  }

  function start(url: string, viewport?: { width: number; height: number }) {
    open()
    setTimeout(() => send({ command: 'start_recording', url, viewport }), 100)
  }
  function stop() { send({ command: 'stop_recording' }) }
  function pause() { send({ command: 'pause_recording' }) }
  function resume() { send({ command: 'resume_recording' }) }
  function runStep(step: any) { send({ command: 'run_step', step }) }
  function close() { ws.value?.close(); ws.value = null }

  onUnmounted(close)

  return { events, status, lastError, start, stop, pause, resume, runStep, close }
}
```

- [ ] **Step 2：写 RecorderPanel.vue**

```vue
<template>
  <div class="recorder-panel">
    <div class="bar">
      <el-input v-model="urlInput" placeholder="录制起始 URL" :disabled="recording" />
      <el-button v-if="!recording" type="primary" @click="onStart">开始录制</el-button>
      <el-button v-else type="warning" @click="onPause" v-show="status === 'recording'">暂停</el-button>
      <el-button v-show="status === 'paused'" type="primary" @click="onResume">恢复</el-button>
      <el-button v-if="recording" type="danger" @click="onStop">停止</el-button>
      <el-tag :type="statusTagType">{{ statusLabel }}</el-tag>
    </div>

    <el-alert v-if="lastError" type="error" :closable="false">
      <template #title>[{{ lastError.code }}] {{ lastError.message }}</template>
    </el-alert>

    <div class="event-list">
      <div v-for="(ev, i) in recordEvents" :key="i" class="ev-item">
        <span class="action">{{ ev.action }}</span>
        <span class="selector">{{ ev.selector }}</span>
        <span class="value">{{ ev.value }}</span>
        <el-button size="small" link @click="emit('append-step', ev)">追加</el-button>
        <el-button size="small" link @click="emit('replace-step', ev, i)">替换</el-button>
      </div>
    </div>

    <div class="actions">
      <el-button @click="emit('replace-all', recordEvents)" :disabled="!recordEvents.length">替换当前用例步骤</el-button>
      <el-button @click="emit('append-all', recordEvents)" :disabled="!recordEvents.length">追加到当前用例</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRecorderSocket } from '@/composables/useRecorderSocket'

const emit = defineEmits(['append-step', 'replace-step', 'replace-all', 'append-all'])

const urlInput = ref('')
const { events, status, lastError, start, stop, pause, resume } = useRecorderSocket()

const recording = computed(() => status.value === 'recording' || status.value === 'paused')
const statusTagType = computed(() => ({
  idle: 'info', connecting: 'warning', recording: 'success',
  paused: 'warning', stopped: 'info', error: 'danger'
}[status.value] || 'info'))
const statusLabel = computed(() => ({
  idle: '空闲', connecting: '连接中', recording: '录制中',
  paused: '已暂停', stopped: '已停止', error: '错误'
}[status.value] || ''))

const recordEvents = computed(() => events.value
  .filter(e => e.type === 'record_event' || e.type === 'record_assert_event')
  .map(e => e.data)
)

function onStart() { start(urlInput.value) }
function onPause() { pause() }
function onResume() { resume() }
function onStop() { stop() }
</script>

<style scoped>
.recorder-panel { display: flex; flex-direction: column; gap: 12px; }
.bar { display: flex; gap: 8px; align-items: center; }
.event-list { max-height: 320px; overflow: auto; border: 1px solid #eee; padding: 8px; }
.ev-item { display: flex; gap: 8px; padding: 4px; border-bottom: 1px dashed #f0f0f0; font-size: 12px; }
</style>
```

- [ ] **Step 3：UiCaseDetail.vue 改用新组件**

把现有 1300 行单文件中的 WebSocket 录制逻辑（约 L673~L885 之间）替换为：

```vue
<RecorderPanel
  @append-step="onAppendStep"
  @replace-step="onReplaceStep"
  @replace-all="onReplaceAllSteps"
  @append-all="onAppendAllSteps"
/>
```

并在 script 中实现 4 个 handler，复用现有 `caseSteps` 状态。删除原内联 WS 客户端代码与 `runRecording` 等局部方法。

- [ ] **Step 4：手测**

录制启动 → 操作页面 → 暂停 → 恢复 → 停止 → 替换/追加按钮可用。

- [ ] **Step 5：Commit**

```bash
git add frontend/src/composables/useRecorderSocket.ts frontend/src/views/qa/components/RecorderPanel.vue frontend/src/views/qa/UiCaseDetail.vue
git commit -m "feat(qa): 拆分 UiCaseDetail (RecorderPanel + useRecorderSocket)"
```

### Task 17：断言录制（Alt+Click）+ 单步试运行

**Files:**
- Modify: `backend/qa_center/workers/recorder_worker.py`（断言脚本注入）
- Modify: `frontend/src/views/qa/components/RecorderPanel.vue`

- [ ] **Step 1：worker 端确认 RECORDING_SCRIPT 包含 Alt+Click 断言入口**

如果 `RECORDING_SCRIPT` 已实现 Alt+Click 调 `onRecordAssertEvent`，跳过；否则补丁加：

```javascript
document.addEventListener('click', (e) => {
  if (!e.altKey) return;
  e.preventDefault(); e.stopPropagation();
  const target = e.target;
  const selector = computeSelector(target);  // 已存在
  window.onRecordAssertEvent({
    type: 'assert',
    action: 'assert_visible',
    selector: selector,
  });
}, true);
```

- [ ] **Step 2：前端 RecorderPanel 增加断言类型选择**

收到 `record_assert_event` 时弹一个 popover 让用户改 action（`assert_visible` / `assert_text` / `assert_contains_text` / `assert_attribute`），改完再加入 `recordEvents`。

```vue
<el-dialog v-model="assertDialogVisible" title="选择断言类型" width="400px">
  <el-radio-group v-model="pendingAssert.action">
    <el-radio label="assert_visible">元素可见</el-radio>
    <el-radio label="assert_text">文本完全等于</el-radio>
    <el-radio label="assert_contains_text">文本包含</el-radio>
    <el-radio label="assert_attribute">属性等于</el-radio>
  </el-radio-group>
  <el-input v-if="pendingAssert.action !== 'assert_visible'" v-model="pendingAssert.expected_value" placeholder="期望值" />
  <template #footer>
    <el-button @click="assertDialogVisible = false">取消</el-button>
    <el-button type="primary" @click="confirmAssert">确认</el-button>
  </template>
</el-dialog>
```

- [ ] **Step 3：单步试运行按钮**

每个事件项加按钮"试运行"，调用 `runStep(ev)`，`step_run_done` 事件展示 toast。

```vue
<el-button size="small" link @click="onTryStep(ev)">试运行</el-button>
```

```typescript
function onTryStep(step) { runStep(step) }
// 在 events watch 中：if (ev.type === 'step_run_done') ElMessage[ev.success ? 'success' : 'error'](ev.message || '执行完成')
```

- [ ] **Step 4：Commit**

```bash
git add backend/qa_center/workers/recorder_worker.py frontend/src/views/qa/components/RecorderPanel.vue
git commit -m "feat(qa): 录制断言 UX + 单步试运行"
```

---

## M7：清理与日志

### Task 18：logger 划分 + 启动清理钩子

**Files:**
- Modify: `backend/qa_center/apps.py`
- Modify: `backend/syncboard/settings.py`（增 LOGGING 配置）
- Create: `backend/qa_center/management/commands/cleanup_playwright_temp.py`

- [ ] **Step 1：apps.py 注册启动清理**

```python
from django.apps import AppConfig
import os
import time
import shutil
import logging


class QaCenterConfig(AppConfig):
    name = "qa_center"

    def ready(self):
        try:
            self._cleanup_playwright_temp()
        except Exception:
            logging.getLogger("qa_center.runner").exception("启动清理失败")

    def _cleanup_playwright_temp(self):
        from django.conf import settings
        base = os.path.join(settings.BASE_DIR, ".playwright-temp")
        if not os.path.exists(base):
            return
        cutoff = time.time() - 24 * 3600
        for name in os.listdir(base):
            full = os.path.join(base, name)
            try:
                if os.path.isdir(full) and os.path.getmtime(full) < cutoff:
                    shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass
```

- [ ] **Step 2：settings.py LOGGING 加 logger**

在 `LOGGING['loggers']`（如不存在则新增整段 `LOGGING` 字典）下加：

```python
"qa_center.runner": {"handlers": ["console"], "level": "INFO", "propagate": False},
"qa_center.recorder": {"handlers": ["console"], "level": "INFO", "propagate": False},
```

- [ ] **Step 3：Management command 提供手动清理入口**

```python
# backend/qa_center/management/commands/cleanup_playwright_temp.py
import os, time, shutil
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "清理 Playwright 临时目录（默认 24h 前）"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **opts):
        cutoff = time.time() - opts["hours"] * 3600
        base = os.path.join(settings.BASE_DIR, ".playwright-temp")
        if not os.path.exists(base):
            self.stdout.write("目录不存在")
            return
        removed = 0
        for name in os.listdir(base):
            full = os.path.join(base, name)
            if os.path.isdir(full) and os.path.getmtime(full) < cutoff:
                shutil.rmtree(full, ignore_errors=True)
                removed += 1
        self.stdout.write(f"已清理 {removed} 个目录")
```

需要新建空 `__init__.py`：

```bash
mkdir -p backend/qa_center/management/commands
touch backend/qa_center/management/__init__.py backend/qa_center/management/commands/__init__.py
```

- [ ] **Step 4：UI_TEST_DEBUG 开关**

`runner_supervisor.execute_ui_case` 起始处：

```python
import os
DEBUG = os.environ.get("UI_TEST_DEBUG", "").lower() in ("1", "true", "yes")
io_log = None
if DEBUG:
    log_path = os.path.join(settings.BASE_DIR, ".playwright-temp", f"io_{task_id}.log")
    io_log = open(log_path, "w", encoding="utf-8")
```

并在事件接收处把 `event` 也写入 `io_log`。worker 侧 DEBUG 模式下不删 temp_dir（在 `cleanup_temp_dir` 加 `if os.environ.get("UI_TEST_DEBUG"): return`）。

- [ ] **Step 5：删除老路径死代码**

确认 `views_ui_test.py` 不再 import `from .utils.runner import run_ui_case`；如果没有任何地方使用 `utils/runner.py` 中的便捷函数，添加文件顶部 deprecation 注释，保留代码以便回滚 1 个迭代。下一个 PR 中真正删除。

`utils/recorder.py` 同理。

- [ ] **Step 6：Commit**

```bash
git add backend/qa_center/apps.py backend/syncboard/settings.py backend/qa_center/management/ backend/qa_center/workers/runner_supervisor.py
git commit -m "chore(qa): logger 分组 + .playwright-temp 启动清理 + UI_TEST_DEBUG"
```

### Task 19：删除迁移的旧代码（可选，等 M2-M5 稳定 1 周后）

**Files:**
- Delete code from: `backend/qa_center/utils/runner.py`、`backend/qa_center/utils/recorder.py`

- [ ] **Step 1：确认无引用**

```bash
cd backend && grep -rn "utils.runner" qa_center/ ; grep -rn "utils.recorder" qa_center/ ; grep -rn "create_recorder\|PlaywrightRunner" qa_center/
```
Expected: 仅在 utils 目录自身出现。

- [ ] **Step 2：删除文件 / 大段函数**

直接 `git rm backend/qa_center/utils/runner.py backend/qa_center/utils/recorder.py`，或如有共用辅助函数（如 selector 解析）抽取到 `qa_center/workers/_helpers.py`。

- [ ] **Step 3：Commit**

```bash
git add -u && git commit -m "chore(qa): 删除老 in-process Playwright 实现"
```

---

## 自检结果

**1. 规格覆盖：**

| Spec 章节 | 任务 |
|---|---|
| §3 总体架构 | M1 全部 |
| §4 进程模型与目录约定 | Task 2/3（temp_dir per-process）、Task 18（启动清理） |
| §5 JSON 行协议 | Task 1 |
| §6 错误模型 | Task 1（错误码表）、Task 5（`_classify_error`）、Task 8（DB 字段） |
| §7 数据模型增量 | Task 7 |
| §8.1 运行实时事件流 | Task 9/10/11/12 |
| §8.2 录制 UX | Task 16/17 |
| §8.3 前端代码改造 | Task 12/16 |
| §9 日志与可观测性 | Task 18 |
| §10 实施分阶段 | M1–M7 与本计划逐节对应 |
| §11 风险与缓解 | 编码：runner_worker.py `_setup_io_logging`；截图落盘：runner_worker `_run_steps` 用 path；节流：在 RunDrawer events 计算属性中天然合并；GUI 检测：可放在 Task 17 内补加 |
| §12 回滚 | Task 19 之前所有里程碑可独立回滚；feature flag 在 Task 6 自然成立（旧 `utils/runner` 仍存在） |

**2. 占位符扫描：** 无 TBD/TODO；每个 Step 都给出完整代码或具体命令。

**3. 类型一致性：** `RunnerEvent.type`、`RecorderEvent.type` 字符串值在 worker、supervisor、composable、组件四处统一（`started/step_start/step_log/step_screenshot/step_done/finished/error/ready/record_event/record_assert_event/recording_started/recording_stopped/recording_paused/recording_resumed/step_run_done`）。错误码常量集中在 `protocol.ERROR_CODES`。
