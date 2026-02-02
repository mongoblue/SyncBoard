import re
import os  # ✨ 1. 引入 os
from playwright.sync_api import Page, expect

# ✨ 2. 获取基础 URL，如果没传环境变量，就默认用 localhost (方便你本地调试)
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost")

def test_login_success(page: Page):
    print(f"1. 访问登录页: {BASE_URL}/login")
    # ✨ 3. 使用变量
    page.goto(f"{BASE_URL}/login")

    # 检查标题 (保持现状)
    expect(page).to_have_title(re.compile("FlowSpace"))

    print("2. 输入账号密码...")
    page.get_by_placeholder("用户名").fill("mongoblue")
    page.get_by_placeholder("密码").fill("13579mnb") 

    print("3. 点击登录...")
    page.get_by_role("button", name="登录").click()

    print("4. 等待跳转...")
    expect(page).to_have_url(re.compile("/projects"))
    
    print("✅ 测试通过！截图保存中...")
    page.screenshot(path="login_success.png")
