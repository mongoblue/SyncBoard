import re
import time
from playwright.sync_api import Page, expect

# 封装一个登录动作，方便复用
def login(page: Page):
    page.goto("http://localhost/login")
    page.get_by_placeholder("用户名").fill("mongoblue")
    page.get_by_placeholder("密码").fill("13579mnb")
    page.get_by_role("button", name="登录").click()
    # 等待进入项目列表页
    expect(page).to_have_url(re.compile("/projects"))

def test_create_task_success(page: Page):
    # 1. 先登录
    print("1. 正在登录...")
    login(page)
    
    # 2. 进入第一个项目
    print("2. 正在进入第一个项目...")
    # 等待项目列表加载出来 (通过寻找项目卡片或文字)
    # 假设项目卡片上有"点击进入"或者项目名称，我们这里简单粗暴点，找第一个箭头图标或者卡片
    # 注意：你需要确保你的账号里至少有一个项目！
    # 这里我们尝试点击页面上出现的第一个"进入"相关的元素，或者直接点击第一个 .chat-list-item (如果复用了样式)
    # 最稳妥的方式：点击第一个出现的项目卡片
    # 假设项目列表里的项目有特定类名，或者我们直接找文本
    
    # ⚠️ 调试点：这里可能需要根据你实际页面调整。
    # 假设卡片上有个按钮或者整个卡片可点。我们试着点第一个 .project-card (如果有) 或者直接根据文本
    # 先截图看看列表页长啥样，防止抓瞎，不过通常页面会有 "进入项目" 按钮？
    # 让我们尝试点击页面上第一个非导航栏的链接或卡片
    
    # 【策略】等待页面上出现 "2026" (日期) 或 你的项目名，或者直接找 .el-card
    # 这里假设你之前创建过一个项目。
    # 我们用 css 选择器找第一个卡片
    first_project = page.locator(".el-card").first
    first_project.click()

    # 3. 验证进入了看板
    print("3. 验证进入看板...")
    expect(page).to_have_url(re.compile(r"/board"))
    
    # 4. 点击 "To Do" 列的 "+" 号
    print("4. 点击创建按钮...")
    # 找到包含 "To Do" 文本的列，然后找它里面的加号按钮
    # 这是一个级联查找
    todo_column = page.locator(".board-column", has_text="To Do")
    add_btn = todo_column.locator(".add-btn") # 假设你在 Vue 里给加号按钮加了这个类
    # 如果没加类名，可以用 icon 查找：
    if add_btn.count() == 0:
        add_btn = todo_column.locator("button").first 
        
    add_btn.click()

    # 5. 填写任务标题
    print("5. 填写任务标题...")
    # ElementPlus 的 MessageBox 输入框通常有 placeholder 或者特定的结构
    # 这里的 placeholder 取决于你 ElMessageBox.prompt 的配置
    # 你之前的代码是：ElMessageBox.prompt('请输入任务标题', ...)
    # 所以 placeholder 可能是空，或者我们直接找 input 标签
    page.get_by_role("textbox").fill("E2E自动测试任务")
    
    # 点击弹窗上的 "确定" 或 "Create"
    # ElementPlus 的确定按钮通常叫 "OK" 或者根据你设置的 confirmButtonText: '创建'
    page.get_by_role("button", name="创建").click()

    # 6. 验证任务是否出现
    print("6. 验证任务是否存在...")
    # 等待页面上出现这个文本
    expect(page.get_by_text("E2E自动测试任务")).to_be_visible()
    
    print("✅ 业务流测试通过！截图保存中...")
    page.screenshot(path="task_create_success.png")