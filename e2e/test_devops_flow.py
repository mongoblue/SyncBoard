"""E2E smoke for DevOps and quality-report entrypoints."""

import re

from playwright.sync_api import Page, expect

from helpers import BASE_URL, ensure_project


def test_devops_pipeline_trigger(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)

    page.goto(f"{BASE_URL}/projects/{project['id']}/qa/devops")
    expect(page).to_have_url(re.compile(r"/qa/devops"), timeout=10000)
    expect(page.get_by_text("CI/CD").first).to_be_visible(timeout=10000)

    page.get_by_role("button", name="配置集成").click()
    expect(page.locator("[role=dialog]:visible").first).to_be_visible(timeout=10000)


def test_devops_quality_report(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)

    page.goto(f"{BASE_URL}/projects/{project['id']}/quality")
    expect(page).to_have_url(re.compile(r"/quality"), timeout=10000)
    expect(
        page.get_by_text("质量").first.or_(page.get_by_text("Quality").first)
    ).to_be_visible(timeout=10000)
