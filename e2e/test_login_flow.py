import re
import os
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost"))


def test_login_success(page: Page):
    print(f"1. 访问登录页: {BASE_URL}/login")
    page.goto(f"{BASE_URL}/login")

    expect(page).to_have_title(re.compile("FlowSpace"))

    print("2. 输入账号密码...")
    page.get_by_placeholder("用户名").fill("mongoblue")
    page.get_by_placeholder("密码").fill("13579mnb")

    print("3. 点击登录...")
    page.get_by_role("button", name=re.compile(r"登\s*录")).click()

    print("4. 等待跳转...")
    expect(page).to_have_url(re.compile("/projects"), timeout=10000)
    print("✅ 测试通过")
