import os
import re
from playwright.sync_api import Page, expect


BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost"))
API_URL = os.getenv("API_URL", BASE_URL)


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


def _get_csrf_token(page: Page) -> str:
    for c in page.context.cookies():
        if c.get("name") == "csrftoken":
            return c.get("value", "")
    return ""


def get_or_create_project(page: Page, name: str | None = None) -> dict:
    """通过 API 取一个项目；没有就创建一个。返回 {id, name}。

    SPA 卡片的 hover 动画导致 click/dispatch_event 都不稳；改走 API 直接拿
    project id，再 page.goto 看板 URL —— 最稳。session cookie 已由 login
    写入 page.context，page.request 自动带上。
    """
    resp = page.request.get(f"{BASE_URL}/api/projects/")
    assert resp.ok, f"GET /api/projects/ failed: {resp.status} {resp.text()}"
    data = resp.json()
    items = data.get("results", data) if isinstance(data, dict) else data

    if name:
        for p in items:
            if p.get("name") == name:
                return {"id": p["id"], "name": p["name"]}
    elif items:
        return {"id": items[0]["id"], "name": items[0]["name"]}

    new_name = name or "E2E Default Project"
    csrf = _get_csrf_token(page)
    headers = {"X-CSRFToken": csrf, "Referer": BASE_URL} if csrf else {}
    create = page.request.post(
        f"{BASE_URL}/api/projects/",
        data={"name": new_name},
        headers=headers,
    )
    assert create.ok, f"POST /api/projects/ failed: {create.status} {create.text()}"
    payload = create.json()
    return {"id": payload["id"], "name": payload["name"]}


def open_board(page: Page, project_id: str) -> None:
    """直接跳板看板 URL，绕过项目卡片点击。

    不能用 wait_for_load_state('networkidle') —— 看板有 WebSocket 长连接，
    networkidle 永远不会到。改成等第一列可见即认为页面就绪。
    """
    page.goto(f"{BASE_URL}/projects/{project_id}/board")
    expect(page).to_have_url(re.compile(rf"/projects/{re.escape(str(project_id))}/board"), timeout=15000)
    expect(page.locator(".board-column").first).to_be_visible(timeout=15000)


def open_project_card(page: Page, name: str | None = None) -> str:
    """登录后从 /projects 跳到看板。返回 project_id。"""
    project = get_or_create_project(page, name=name)
    open_board(page, project["id"])
    return project["id"]
