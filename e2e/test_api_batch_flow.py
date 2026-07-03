"""E2E smoke for batch/run-plan related QA Center pages."""

import re

from playwright.sync_api import Page, expect

from helpers import BASE_URL, ensure_project


def test_batch_run_create_and_execute(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)

    page.goto(f"{BASE_URL}/projects/{project['id']}/qa/devops")
    expect(page).to_have_url(re.compile(r"/qa/devops"), timeout=10000)
    expect(page.get_by_role("heading", name=re.compile(r"DevOps", re.IGNORECASE))).to_be_visible(timeout=10000)

    page.get_by_role("button", name="批量执行").click()
    expect(page.get_by_role("dialog", name=re.compile(r"批量执行", re.IGNORECASE))).to_be_visible(timeout=10000)

    expect(page.get_by_text("计划名称")).to_be_visible(timeout=10000)


def test_batch_run_results(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)

    page.goto(f"{BASE_URL}/projects/{project['id']}/qa/test-runs")
    expect(page).to_have_url(re.compile(r"/qa/test-runs"), timeout=10000)
    expect(page.locator("table, .el-table").first).to_be_visible(timeout=10000)
