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


if __name__ == "__main__":
    main()
