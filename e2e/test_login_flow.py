import re
from playwright.sync_api import Page, expect

def test_login_success(page: Page):
    print("1. 访问登录页...")
    page.goto("http://localhost/login")

    # 检查标题 (保持现状)
    expect(page).to_have_title(re.compile("Vite App"))

    print("2. 输入账号密码...")
    # ✅ 修正：使用 grep 查出来的真实文案
    page.get_by_placeholder("用户名").fill("mongoblue")
    page.get_by_placeholder("密码").fill("13579mnb") 

    print("3. 点击登录...")
    page.get_by_role("button", name="登录").click()

    print("4. 等待跳转...")
    # 登录成功后应该跳到项目列表
    expect(page).to_have_url(re.compile("/projects"))
    
    print("✅ 测试通过！截图保存中...")
    page.screenshot(path="login_success.png")
