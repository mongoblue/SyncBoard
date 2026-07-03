import os
import re

from playwright.sync_api import Page, expect


BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost"))


def test_login_success(page: Page):
    page.goto(f"{BASE_URL}/login")
    expect(page).to_have_title(re.compile("FlowSpace"))

    inputs = page.locator("input")
    expect(inputs.nth(0)).to_be_visible(timeout=10000)
    inputs.nth(0).fill("mongoblue")
    inputs.nth(1).fill("13579mnb")

    page.locator(".login-btn").click()
    expect(page).to_have_url(re.compile("/projects"), timeout=10000)
