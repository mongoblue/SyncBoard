import re
import time
import os
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost")

def login(page: Page):
    page.goto(f"{BASE_URL}/login")
    page.get_by_placeholder("用户名").fill("mongoblue")
    page.get_by_placeholder("密码").fill("13579mnb")
    page.get_by_role("button", name="登录").click()
    expect(page).to_have_url(re.compile("/projects"))

def test_create_task_success(page: Page):
    # --- 准备工作 ---
    print("1. 正在登录...")
    login(page)
    
    print("2. 正在进入第一个项目...")
    try:
        page.locator(".el-card").first.click(timeout=5000)
    except:
        page.get_by_text("项目", exact=False).first.click()

    print("3. 验证进入看板...")
    expect(page).to_have_url(re.compile(r"/board"))
    page.wait_for_load_state("networkidle")

    # --- 第一阶段：创建任务 (Create) ---
    print("4. [Phase 1] 点击加号，开始创建...")
    todo_column = page.locator(".board-column").filter(has_text="To Do")
    
    # 点击加号
    if todo_column.locator(".add-btn").count() > 0:
        todo_column.locator(".add-btn").click()
    else:
        todo_column.locator("button").first.click()

    print("5. [Phase 1] 填写新任务标题...")
    # 这里的输入框可能是 ElementPlus 的 MessageBox 或者是 Dialog
    # 我们用 get_by_role("textbox") 可以通吃
    input_box = page.get_by_role("textbox").first
    input_box.fill("E2E测试任务")
    
    # 点击“确定”或者“创建”
    # ElementPlus 的 MessageBox 确定按钮通常叫 "OK" 或者 "确定"
    print("6. [Phase 1] 确认创建...")
    confirm_btn = page.get_by_role("button", name=re.compile(r"确定|创建|OK|Confirm"))
    confirm_btn.click()

    # --- 第二阶段：编辑详情 (Edit) ---
    print("7. [Phase 2] 等待任务卡片出现...")
    # 验证列表里出现了我们刚才创建的任务
    new_card = todo_column.get_by_text("E2E测试任务").first
    expect(new_card).to_be_visible()

    print("8. [Phase 2] 点击卡片，进入详情页...")
    # 点击卡片，打开大弹窗
    new_card.click()

    print("9. [Phase 2] 详情弹窗已打开，准备保存...")
    # 等待详情弹窗出现 (标题通常包含"任务详情"或者输入框里有我们的标题)
    detail_dialog = page.locator(".el-dialog__body")
    expect(detail_dialog).to_be_visible()
    
    # 验证一下标题对不对 (可选)
    # expect(detail_dialog.get_by_display_value("E2E测试任务")).to_be_visible()

    # === ✨ 关键修正：点击你截图里的“保存修改” ===
    # 不管它在 DOM 哪里，直接找页面上可见的、文字为"保存修改"的按钮
    save_btn = page.get_by_role("button", name="保存修改")
    
    # 确保它是可见的再点
    expect(save_btn).to_be_visible()
    save_btn.click()

    print("10. 验证弹窗关闭...")
    expect(detail_dialog).not_to_be_visible()
    
    print("✅ 完整流程测试通过！截图保存中...")
    page.screenshot(path="task_flow_success.png")