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
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
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
    if os.environ.get("UI_TEST_DEBUG"):
        logger.info("UI_TEST_DEBUG 开启，保留 temp_dir=%s", td)
        return
    if td and os.path.exists(td):
        shutil.rmtree(td, ignore_errors=True)


def _to_int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _close_open_selects(page) -> None:
    try:
        if page.locator(".el-select-dropdown:visible").count() > 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(120)
            if page.locator(".el-select-dropdown:visible").count() > 0:
                page.evaluate("document.body.click()")
                page.wait_for_timeout(120)
    except Exception:
        pass


def _execute_single_step(page, step: dict, emit_fn, frame_holder: dict):
    from playwright.sync_api import expect

    action = (step.get("action") or "").lower().strip()
    # 别名归一
    if action == "drag_and_drop":
        action = "drag"
    if action == "context_click":
        action = "right_click"

    selector = step.get("selector", "") or ""
    value = step.get("value", "")
    url = step.get("url", "")
    attribute = step.get("attribute", "")
    expected_value = step.get("expected_value", "")

    # 当前作用域：主 page 或 iframe frame
    scope = frame_holder.get("scope") or page

    if action != "select":
        _close_open_selects(page)

    def _wait(sel, timeout=10000):
        loc = scope.locator(sel)
        loc.wait_for(state="visible", timeout=timeout)
        return loc

    if action == "goto" and url:
        page.goto(url, wait_until="networkidle", timeout=30000)
        frame_holder["scope"] = page
    elif action == "wait":
        page.wait_for_timeout(_to_int(value, 1000))
    elif action in ("click", "click_if_visible"):
        _wait(selector).click(timeout=10000)
    elif action in ("dblclick", "double_click"):
        _wait(selector).dblclick(timeout=10000)
    elif action == "right_click":
        _wait(selector).click(button="right", timeout=10000)
    elif action == "fill":
        _wait(selector).fill("" if value is None else str(value))
    elif action == "select":
        loc = _wait(selector)
        try:
            loc.select_option("" if value is None else str(value))
        except Exception:
            try:
                already_open = page.locator(".el-select-dropdown:visible").count() > 0
            except Exception:
                already_open = False
            if not already_open:
                loc.click(timeout=10000)
            page.locator(
                ".el-select-dropdown__item:visible", has_text="" if value is None else str(value)
            ).first.click(timeout=5000)
    elif action == "upload":
        # value 为文件路径；selector 指向 input[type=file] 或可触发文件选择的控件
        path = "" if value is None else str(value)
        loc = scope.locator(selector)
        try:
            loc.set_input_files(path, timeout=10000)
        except Exception:
            # 有些上传控件不是 file input 本身
            with page.expect_file_chooser(timeout=5000) as fc_info:
                loc.click(timeout=10000)
            fc_info.value.set_files(path)
    elif action == "keydown":
        key = "" if value is None else str(value)
        if selector:
            _wait(selector).press(key)
        else:
            page.keyboard.press(key)
    elif action == "hover":
        _wait(selector).hover()
    elif action == "scroll":
        y = _to_int(value, 0)
        page.evaluate("y => window.scrollTo(0, y)", y)
    elif action == "iframe_switch":
        # value 为空：切回主页面；否则按 name/id/selector 找 frame
        target = "" if value is None else str(value).strip()
        if not target:
            frame_holder["scope"] = page
        else:
            frame = None
            try:
                frame = page.frame(name=target)
            except Exception:
                frame = None
            if frame is None:
                try:
                    handle = page.query_selector(target)
                    if handle is not None:
                        frame = handle.content_frame()
                except Exception:
                    frame = None
            if frame is None:
                raise ValueError(f"SELECTOR_NOT_FOUND:iframe {target}")
            frame_holder["scope"] = frame
    elif action == "alert_handle":
        mode = ("" if value is None else str(value)).strip().lower() or "accept"
        dialog = getattr(page, "_pending_dialog", None)
        # Playwright 推荐 once 监听；这里用 once 处理下一个 dialog，并尽量立即处理已出现的
        def _handle(dlg):
            try:
                if mode in ("dismiss", "cancel"):
                    dlg.dismiss()
                elif mode not in ("accept", "ok") and mode:
                    dlg.accept(mode)
                else:
                    dlg.accept()
            except Exception:
                try:
                    dlg.dismiss()
                except Exception:
                    pass

        page.once("dialog", _handle)
        # 若用户在上一步已触发弹窗，这里无同步句柄可取；依赖 once 处理后续。
        # 为兼容“先出现 dialog 再执行本步”，额外 wait 很短时间。
        page.wait_for_timeout(50)
    elif action == "assert_visible":
        expect(scope.locator(selector)).to_be_visible()
    elif action == "assert_exists":
        expect(scope.locator(selector)).to_have_count(1)
    elif action == "assert_text":
        expect(scope.locator(selector)).to_have_text(expected_value or value)
    elif action == "assert_contains_text":
        expect(scope.locator(selector)).to_contain_text(expected_value or value)
    elif action == "assert_attribute":
        expect(scope.locator(selector)).to_have_attribute(attribute, expected_value)
    elif action == "assert_url":
        expect(page).to_have_url(expected_value or value)
    elif action == "assert_count":
        expect(scope.locator(selector)).to_have_count(_to_int(value, 0))
    elif action == "drag":
        target_sel = step.get("target_selector") or value or selector
        _wait(selector).drag_to(_wait(str(target_sel)), timeout=15000)
    elif action == "screenshot":
        pass
    else:
        raise ValueError(f"UNSUPPORTED_ACTION:{action}")


def _classify_error(exc: Exception) -> str:
    msg = str(exc)
    cls = exc.__class__.__name__
    lower = msg.lower()
    if "executable" in lower and "doesn" in lower:
        return "BROWSER_NOT_INSTALLED"
    if cls == "TimeoutError" or "Timeout" in cls:
        if "locator" in lower or "waiting for" in lower:
            return "SELECTOR_NOT_FOUND"
        return "STEP_TIMEOUT"
    if msg.startswith("SELECTOR_NOT_FOUND") or "找不到" in msg or "locator" in lower:
        return "SELECTOR_NOT_FOUND"
    if msg.startswith("UNSUPPORTED_ACTION:"):
        return "UNSUPPORTED_ACTION"
    return "INTERNAL"


def _run_steps(case_data: dict) -> dict:
    from playwright.sync_api import sync_playwright

    url = (case_data.get("url") or "").strip()
    steps = case_data.get("steps") or []
    temp_dir = os.environ.get("TEMP", "")
    shots_dir = os.path.join(temp_dir, "screenshots")
    os.makedirs(shots_dir, exist_ok=True)

    passed = 0
    failed = 0
    frame_holder = {"scope": None}

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
            try:
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    accept_downloads=True,
                )
                try:
                    page = context.new_page()
                    frame_holder["scope"] = page

                    if url:
                        emit({"type": "step_start", "index": -1, "action": "goto", "desc": f"导航到 {url}"})
                        page.goto(url, wait_until="networkidle", timeout=30000)
                        emit({"type": "step_log", "index": -1, "message": "页面加载完成"})

                    for i, step in enumerate(steps):
                        emit({
                            "type": "step_start",
                            "index": i,
                            "action": step.get("action"),
                            "desc": f"步骤{i+1}",
                            "selector": step.get("selector", ""),
                            "value": step.get("value", ""),
                        })
                        try:
                            _execute_single_step(page, step, emit, frame_holder)
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
                            emit({
                                "type": "step_done",
                                "index": i,
                                "success": False,
                                "code": code,
                                "message": str(e),
                                "traceback": tb,
                            })
                            return {
                                "success": False,
                                "summary": {"passed": passed, "failed": failed, "total": len(steps)},
                            }

                    page.wait_for_timeout(500)
                    final_path = os.path.join(shots_dir, "final.png")
                    page.screenshot(path=final_path, full_page=True)
                    emit({"type": "step_screenshot", "index": len(steps), "path": final_path})

                    return {
                        "success": True,
                        "summary": {"passed": passed, "failed": 0, "total": len(steps)},
                    }
                finally:
                    try:
                        context.close()
                    except Exception:
                        pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

    except Exception as e:
        code = _classify_error(e)
        tb = traceback.format_exc()
        emit({
            "type": "error",
            "code": code if code != "INTERNAL" else "LAUNCH_FAILED",
            "message": str(e),
            "traceback": tb,
        })
        return {
            "success": False,
            "summary": {"passed": passed, "failed": failed + 1, "total": len(steps)},
        }


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
        emit({
            "type": "error",
            "code": "INTERNAL",
            "message": str(e),
            "traceback": traceback.format_exc(),
        })
        emit({
            "type": "finished",
            "success": False,
            "summary": {"passed": 0, "failed": 1, "total": 1},
        })
    finally:
        # 不在这里删除 temp_dir：父进程需要读取截图。
        pass


if __name__ == "__main__":
    main()
