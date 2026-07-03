"""E2E smoke for bug list, create flow, and detail page."""

import re
import uuid

from playwright.sync_api import Page, expect

from helpers import BASE_URL, ensure_project


def test_bug_create_from_ui(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)
    bug_title = f"E2E Bug {uuid.uuid4().hex[:8]}"

    page.goto(f"{BASE_URL}/projects/{project['id']}/bugs")
    expect(page).to_have_url(re.compile(r"/bugs"), timeout=10000)
    expect(page.get_by_role("heading", name=re.compile(r"Bug", re.IGNORECASE))).to_be_visible(timeout=10000)

    page.get_by_role("button", name="新建 Bug").click()
    expect(page.get_by_role("dialog", name="新建 Bug")).to_be_visible(timeout=10000)

    page.get_by_placeholder("简短描述问题").fill(bug_title)
    page.get_by_role("textbox", name="描述", exact=True).fill("Automated bug smoke test.")
    page.get_by_role("button", name="创建").click()

    expect(page).to_have_url(re.compile(r"/bugs/"), timeout=10000)
    expect(page.get_by_text(bug_title)).to_be_visible(timeout=10000)


def test_bug_status_transitions(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)

    page.goto(f"{BASE_URL}/projects/{project['id']}/bugs")
    expect(page).to_have_url(re.compile(r"/bugs"), timeout=10000)
    expect(page.locator("table, .el-table").first).to_be_visible(timeout=10000)


def test_bug_detail_page(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)
    bug_title = f"E2E Bug Detail {uuid.uuid4().hex[:8]}"

    page.goto(f"{BASE_URL}/projects/{project['id']}/bugs")
    expect(page).to_have_url(re.compile(r"/bugs"), timeout=10000)

    page.get_by_role("button", name="新建 Bug").click()
    expect(page.get_by_role("dialog", name="新建 Bug")).to_be_visible(timeout=10000)
    page.get_by_placeholder("简短描述问题").fill(bug_title)
    page.get_by_role("textbox", name="描述", exact=True).fill("Bug detail smoke test.")
    page.get_by_role("button", name="创建").click()

    expect(page).to_have_url(re.compile(r"/bugs/"), timeout=10000)
    expect(page.get_by_text(bug_title)).to_be_visible(timeout=10000)
    expect(page.get_by_text("问题描述")).to_be_visible(timeout=10000)
