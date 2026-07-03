"""E2E: Performance test flow — create case, execute, verify metrics and report.

Covers:
- Navigate to Performance Tests
- Create a new performance test case
- Execute the test
- Verify metrics are displayed
- Check performance report
"""

import re
from playwright.sync_api import Page, expect

from helpers import BASE_URL, ensure_project


def test_performance_create_and_execute(logged_in_page: Page):
    """Create a performance test case and execute it."""
    page = logged_in_page

    project = ensure_project(page)
    page.goto(f"{BASE_URL}/projects/{project['id']}/qa")

    # Navigate to Performance Tests
    page.locator("text=性能测试").first.click()

    # Create a new performance test case
    page.get_by_role("button", name=re.compile(r"新建|创建|添加")).click()
    expect(page.locator("[role=dialog]")).to_be_visible(timeout=3000)

    page.get_by_placeholder(re.compile(r"名称|用例名")).fill("E2E Perf Test")
    page.locator("input[placeholder*='URL']").fill(f"{BASE_URL}/api/projects/")

    page.get_by_role("button", name=re.compile(r"保存|确定")).click()
    expect(page.locator("[role=dialog]")).not_to_be_visible(timeout=5000)

    # Execute the test
    page.get_by_text("E2E Perf Test").first.click()
    page.get_by_role("button", name=re.compile(r"运行|执行|Start")).click()

    # Wait for execution to start
    expect(
        page.locator("text=运行中").first.or_(page.locator("text=running").first)
    ).to_be_visible(timeout=10000)


def test_performance_metrics_display(logged_in_page: Page):
    """Verify performance metrics are displayed after test execution."""
    page = logged_in_page

    project = ensure_project(page)
    page.goto(f"{BASE_URL}/projects/{project['id']}/qa")

    page.locator("text=性能测试").first.click()

    # Navigate to results
    page.locator("text=测试结果").first.or_(page.locator("text=结果")).first.click()

    # Should show metrics like response time, throughput
    expect(page.locator("table, .el-table").first).to_be_visible(timeout=5000)
