import re
import os
import sys
import uuid
import subprocess
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost"))


def _refresh_haystack_index():
    """触发 Haystack 索引更新；CI 通过 docker compose exec，本地回退到本地 manage.py。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    candidates = [
        ["docker", "compose", "exec", "-T", "backend", "python", "manage.py", "update_index"],
        [sys.executable, "manage.py", "update_index"],
    ]
    for cmd in candidates:
        try:
            subprocess.run(cmd, check=True, env=env, timeout=60)
            return
        except Exception:
            continue


def test_search_flow(page: Page):
    username = "mongoblue"
    password = "13579mnb"

    page.goto(f"{BASE_URL}/login")
    expect(page).to_have_title(re.compile("FlowSpace"), timeout=10000)
    username_input = page.get_by_placeholder("用户名")
    expect(username_input).to_be_visible(timeout=10000)
    username_input.fill(username)
    page.get_by_placeholder("密码").fill(password)
    login_btn = page.get_by_role("button", name=re.compile(r"登\s*录"))
    expect(login_btn).to_be_enabled(timeout=10000)
    login_btn.click()
    expect(page).to_have_url(re.compile(r"/projects"), timeout=15000)

    create_btn = page.get_by_text("创建新项目")
    create_btn.wait_for(state="visible", timeout=10000)
    create_btn.click()

    project_name = f"Project {uuid.uuid4().hex[:6]}"
    page.get_by_role("textbox").fill(project_name)
    page.get_by_role("button", name="创建", exact=True).click()

    page.get_by_text(project_name).click()
    expect(page).to_have_url(re.compile(r"/projects/[\w-]+/board"), timeout=10000)
    page.wait_for_load_state("networkidle")

    todo_column = page.locator(".board-column").first
    expect(todo_column).to_be_visible(timeout=10000)
    todo_column.locator('button[title="新增任务"]').first.click()

    task_title = f"Task {uuid.uuid4().hex[:6]}"
    dialog = page.locator(".el-dialog").filter(has_text="新建任务").first
    expect(dialog).to_be_visible(timeout=10000)
    dialog.locator("input[placeholder='输入任务标题']").fill(task_title)
    dialog.get_by_role("button", name="创建任务").click()
    expect(page.get_by_text(task_title)).to_be_visible(timeout=10000)

    _refresh_haystack_index()

    search_input = page.get_by_placeholder("搜索任务...")
    search_input.fill(task_title)

    page.wait_for_timeout(2000)
    expect(page.get_by_text(task_title).first).to_be_visible(timeout=10000)
