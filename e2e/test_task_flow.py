import re
import os
import time
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost"))


def login(page: Page):
    page.goto(f"{BASE_URL}/login")
    expect(page).to_have_title(re.compile("FlowSpace"), timeout=10000)
    username = page.get_by_placeholder("用户名")
    expect(username).to_be_visible(timeout=10000)
    username.fill("mongoblue")
    page.get_by_placeholder("密码").fill("13579mnb")
    login_btn = page.get_by_role("button", name=re.compile(r"登\s*录"))
    expect(login_btn).to_be_enabled(timeout=10000)
    login_btn.click()
    expect(page).to_have_url(re.compile("/projects"), timeout=15000)


def test_create_task_success(page: Page):
    print("1. 正在登录...")
    login(page)

    print("2. 正在进入第一个项目...")
    page.locator(".el-card, .project-card").first.click(timeout=10000)

    print("3. 验证进入看板...")
    expect(page).to_have_url(re.compile(r"/board"), timeout=10000)
    page.wait_for_load_state("networkidle")

    print("4. 等待第一列出现...")
    todo_column = page.locator(".board-column").first
    expect(todo_column).to_be_visible(timeout=10000)

    print("5. 点击新增任务按钮...")
    add_btn = todo_column.locator('button[title="新增任务"]').first
    expect(add_btn).to_be_visible(timeout=10000)
    add_btn.click()

    print("6. 等待新建任务弹窗...")
    dialog = page.locator(".el-dialog").filter(has_text="新建任务").first
    expect(dialog).to_be_visible(timeout=10000)

    task_title = f"E2E测试任务_{int(time.time())}"
    print(f"7. 填写任务标题: {task_title}")
    dialog.locator("input[placeholder='输入任务标题']").fill(task_title)

    print("8. 点击创建任务...")
    dialog.get_by_role("button", name="创建任务").click()

    print("9. 验证任务卡片出现...")
    new_card = todo_column.get_by_text(task_title, exact=True).first
    expect(new_card).to_be_visible(timeout=10000)

    print("✅ 任务创建流程测试通过")
