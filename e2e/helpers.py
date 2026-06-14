import os
import re
from playwright.sync_api import Page, expect


BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost"))


def login(page: Page, username: str = "mongoblue", password: str = "13579mnb") -> None:
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


def open_project_card(page: Page, name: str | None = None) -> None:
    """
    点击项目卡片进入看板。

    el-card 的 hover transform/opacity 动画会让 actionability 永不稳定,
    用 dispatch_event 派合成 click 事件,Vue 的 @click="goToBoard(p.id)"
    仍会被触发,且绕过 stability/hit-test 检查。
    """
    if name:
        card = page.locator(".project-card", has_text=name).first
    else:
        card = page.locator(".project-card").first
    expect(card).to_be_visible(timeout=10000)
    card.scroll_into_view_if_needed(timeout=5000)
    card.dispatch_event("click")
    expect(page).to_have_url(re.compile(r"/projects/[\w-]+/board"), timeout=15000)
    page.wait_for_load_state("networkidle")
