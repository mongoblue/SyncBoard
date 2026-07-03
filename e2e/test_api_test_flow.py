"""E2E coverage for legacy API case UI flow and result visibility."""

import re
import uuid

from playwright.sync_api import Page, expect

from helpers import BASE_URL, ensure_project


def _create_api_case(page: Page, project_id: str, *, name: str, assertions: list[dict]) -> dict:
    csrf_token = next(
        (cookie.get("value", "") for cookie in page.context.cookies() if cookie.get("name") == "csrftoken"),
        "",
    )
    payload = {
        "project": project_id,
        "name": name,
        "url": "/api/projects/",
        "method": "GET",
        "headers": {},
        "body": "",
        "expected_status": 200,
        "assertions": assertions,
    }
    response = page.request.post(
        f"{BASE_URL}/api/qa/api-cases/",
        data=payload,
        headers={
            "X-CSRFToken": csrf_token,
            "Referer": BASE_URL,
        },
    )
    assert response.ok, f"POST /api/qa/api-cases/ failed: {response.status} {response.text()}"
    return response.json()


def test_api_test_create_and_execute(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)
    case_name = f"E2E API Case {uuid.uuid4().hex[:8]}"
    created = _create_api_case(
        page,
        str(project["id"]),
        name=case_name,
        assertions=[{"type": "status_code", "operator": "==", "value": "200"}],
    )

    page.goto(f"{BASE_URL}/projects/{project['id']}/qa/api-cases?project={project['id']}")
    expect(page).to_have_url(re.compile(r"/qa/api-cases"), timeout=10000)
    expect(page.get_by_text(case_name)).to_be_visible(timeout=10000)

    page.get_by_text(case_name).click()
    expect(page).to_have_url(re.compile(rf"/qa/api-cases/{created['id']}"), timeout=10000)

    page.get_by_role("button", name=re.compile(r"运行|执行|Run", re.IGNORECASE)).click()
    expect(page.locator(".test-result-container")).to_be_visible(timeout=15000)
    expect(page.locator(".result-header")).to_contain_text(re.compile(r"通过|失败"))
    expect(page.locator(".json-code")).to_be_visible(timeout=5000)


def test_api_test_assertion_checks(logged_in_page: Page):
    page = logged_in_page
    project = ensure_project(page)
    case_name = f"E2E API Assertion {uuid.uuid4().hex[:8]}"
    created = _create_api_case(
        page,
        str(project["id"]),
        name=case_name,
        assertions=[
            {"type": "status_code", "operator": "==", "value": "200"},
            {"type": "jsonpath", "expression": "$.results", "operator": "exists"},
        ],
    )

    csrf_token = next(
        (cookie.get("value", "") for cookie in page.context.cookies() if cookie.get("name") == "csrftoken"),
        "",
    )
    run_response = page.request.post(
        f"{BASE_URL}/api/qa/api-cases/{created['id']}/run/",
        data={},
        headers={
            "X-CSRFToken": csrf_token,
            "Referer": BASE_URL,
        },
    )
    assert run_response.ok, f"POST /api/qa/api-cases/{created['id']}/run/ failed: {run_response.status} {run_response.text()}"
    payload = run_response.json()
    assert payload.get("result_id"), f"Run payload missing result_id: {payload}"

    page.goto(f"{BASE_URL}/projects/{project['id']}/qa/test-results")
    expect(page).to_have_url(re.compile(r"/qa/test-results"), timeout=10000)
    expect(page.locator("table, .el-table").first).to_be_visible(timeout=10000)

    page.get_by_role("button", name=re.compile(r"查看|View", re.IGNORECASE)).first.click()
    expect(page).to_have_url(re.compile(r"/qa/test-results/"), timeout=10000)
    expect(page.get_by_text("测试结果详情")).to_be_visible(timeout=10000)
    expect(page.get_by_text("请求信息").first).to_be_visible(timeout=10000)
    expect(page.get_by_text("响应信息").first).to_be_visible(timeout=10000)
    expect(page.get_by_text("断言验证").first).to_be_visible(timeout=10000)
