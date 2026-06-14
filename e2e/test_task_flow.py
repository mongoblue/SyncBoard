import re
import time
from playwright.sync_api import Page, expect

from e2e.helpers import login, open_project_card


def test_create_task_success(page: Page):
    print("1. 正在登录...")
    login(page)

    print("2. 正在进入第一个项目...")
    open_project_card(page)

    print("3. 等待第一列出现...")
    todo_column = page.locator(".board-column").first
    expect(todo_column).to_be_visible(timeout=10000)

    print("4. 点击新增任务按钮...")
    add_btn = todo_column.locator('button[title="新增任务"]').first
    expect(add_btn).to_be_visible(timeout=10000)
    add_btn.click()

    print("5. 等待新建任务弹窗...")
    dialog = page.locator(".el-dialog").filter(has_text="新建任务").first
    expect(dialog).to_be_visible(timeout=10000)

    task_title = f"E2E测试任务_{int(time.time())}"
    print(f"6. 填写任务标题: {task_title}")
    dialog.locator("input[placeholder='输入任务标题']").fill(task_title)

    print("7. 点击创建任务...")
    dialog.get_by_role("button", name="创建任务").click()

    print("8. 验证任务卡片出现...")
    new_card = todo_column.get_by_text(task_title, exact=True).first
    expect(new_card).to_be_visible(timeout=10000)

    print("✅ 任务创建流程测试通过")
