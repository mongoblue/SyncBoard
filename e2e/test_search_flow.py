import os
import sys
import uuid
import subprocess
from playwright.sync_api import Page, expect

from e2e.helpers import login, open_project_card


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
    login(page)

    create_btn = page.get_by_role("button", name="创建新项目")
    expect(create_btn).to_be_visible(timeout=10000)
    create_btn.click()

    project_name = f"Project {uuid.uuid4().hex[:6]}"
    page.get_by_role("textbox").fill(project_name)
    page.get_by_role("button", name="创建", exact=True).click()

    open_project_card(page, name=project_name)

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
