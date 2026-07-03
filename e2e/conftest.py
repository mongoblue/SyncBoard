"""Shared Playwright fixtures for repository E2E tests."""

import os
import re
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect, sync_playwright


BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost:5173"))
API_URL = os.getenv("API_URL", BASE_URL)
HEADLESS = os.getenv("E2E_HEADLESS", "true").lower() == "true"
TEST_USER = os.getenv("E2E_USER", "mongoblue")
TEST_PASS = os.getenv("E2E_PASS", "13579mnb")


def _login(page: Page) -> None:
    page.goto(f"{BASE_URL}/login")
    expect(page).to_have_title(re.compile("FlowSpace"), timeout=10000)

    inputs = page.locator("input")
    expect(inputs.nth(0)).to_be_visible(timeout=10000)
    inputs.nth(0).fill(TEST_USER)
    inputs.nth(1).fill(TEST_PASS)

    page.locator(".login-btn").click()
    expect(page).to_have_url(re.compile(r"/projects"), timeout=15000)


def _build_auth_cookies(pytestconfig: pytest.Config) -> list[dict]:
    backend_dir = os.path.join(pytestconfig.rootpath, "backend")
    script = r"""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.middleware.csrf import _get_new_csrf_string

username = os.environ["E2E_USER"]
password = os.environ["E2E_PASS"]

User = get_user_model()
user, created = User.objects.get_or_create(
    username=username,
    defaults={"is_staff": True, "is_superuser": True},
)
if created or not user.check_password(password):
    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.save()

session = SessionStore()
session["_auth_user_id"] = str(user.pk)
session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
session["_auth_user_hash"] = user.get_session_auth_hash()
session.save()
print(session.session_key)
print(_get_new_csrf_string())
"""
    result = pytest.importorskip("subprocess").run(
        ["python", "-c", script],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "E2E_USER": TEST_USER,
            "E2E_PASS": TEST_PASS,
        },
        check=True,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    session_key = lines[-2]
    csrf_token = lines[-1]
    parsed = urlparse(BASE_URL)
    domain = parsed.hostname or "127.0.0.1"
    return [
        {
            "name": "sessionid",
            "value": session_key,
            "domain": domain,
            "path": "/",
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        },
        {
            "name": "csrftoken",
            "value": csrf_token,
            "domain": domain,
            "path": "/",
            "httpOnly": False,
            "secure": False,
            "sameSite": "Lax",
        },
    ]


@pytest.fixture(scope="session")
def browser() -> Browser:
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=HEADLESS)
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def context(browser: Browser) -> BrowserContext:
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
    )
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    pg = context.new_page()
    yield pg
    pg.close()


@pytest.fixture(scope="session")
def authenticated_storage_state(
    browser: Browser,
    pytestconfig: pytest.Config,
    tmp_path_factory: pytest.TempPathFactory,
) -> str:
    state_path = tmp_path_factory.mktemp("playwright-auth") / "storage-state.json"
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
    )
    context.add_cookies(_build_auth_cookies(pytestconfig))
    page = context.new_page()
    page.goto(f"{BASE_URL}/projects")
    expect(page).to_have_url(re.compile(r"/projects"), timeout=15000)
    context.storage_state(path=str(state_path))
    page.close()
    context.close()
    return str(state_path)


@pytest.fixture
def authenticated_context(browser: Browser, authenticated_storage_state: str) -> BrowserContext:
    ctx = browser.new_context(
        storage_state=authenticated_storage_state,
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
    )
    yield ctx
    ctx.close()


@pytest.fixture
def logged_in_page(authenticated_context: BrowserContext) -> Page:
    page = authenticated_context.new_page()
    page.goto(f"{BASE_URL}/login")
    expect(page).to_have_title(re.compile("FlowSpace"), timeout=10000)
    page.goto(f"{BASE_URL}/projects")
    expect(page).to_have_url(re.compile(r"/projects"), timeout=10000)
    yield page
    page.close()


def get_csrf(page: Page) -> str:
    for cookie in page.context.cookies():
        if cookie.get("name") == "csrftoken":
            return cookie.get("value", "")
    return ""
