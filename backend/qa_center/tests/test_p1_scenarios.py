"""P1 重构验收测试：覆盖 A/B/C/D 四个核心场景。

A：Django DisallowedHost 框架错误识别（单元 + 集成）
B：MockTransport 返回 200 JSON、断言 status_code=200 → PASSED
C：MockTransport 返回 200、断言 status_code=201 → ASSERTION_FAILED，expected/actual 含 201/200
D：MockTransport 返回 timeout → failure_type=TIMEOUT，断言被跳过
"""
from __future__ import annotations

import pytest

from qa_center import api_execution
from qa_center.api_execution import (
    ApiExecutionContext,
    ApiExecutionDefinition,
    FailureType,
    MockTransport,
    TransportResponse,
    UnifiedApiRunner,
    classify_framework_error,
)


def _make_context(**overrides) -> ApiExecutionContext:
    defaults = {
        "trace_id": "trace-p1",
        "project_id": "project-p1",
        "environment_id": "env-p1",
        "system_vars": {
            "base_url": "https://api.example.test",
            "project_id": "project-p1",
            "environment_id": "env-p1",
        },
        "global_vars": {},
        "environment_vars": {},
        "run_overrides": {},
        "chain_vars": {},
        "locked_variables": {"base_url", "project_id", "environment_id"},
        "secret_names": {"authorization", "token", "password", "api_key", "cookie"},
        "secret_values": set(),
        "policies": {},
        "runtime_mode": "mock",
        "metadata": {},
    }
    defaults.update(overrides)
    return ApiExecutionContext(**defaults)


def _make_definition(**overrides) -> ApiExecutionDefinition:
    defaults = {
        "source_type": "api_auto",
        "source_id": "case-p1",
        "name": "case-p1",
        "method": "GET",
        "url_template": "/users",
        "headers_template": {},
        "query_params_template": None,
        "body_template": None,
        "body_mode": "none",
        "files_template": None,
        "cookies_template": None,
        "auth_template": None,
        "timeout_seconds": 30,
        "allow_redirects": False,
        "assertions": [],
        "extractors": [],
        "metadata": {},
    }
    defaults.update(overrides)
    return ApiExecutionDefinition(**defaults)


def _make_response(**overrides) -> TransportResponse:
    defaults = {
        "status_code": 200,
        "headers": {"Content-Type": "application/json"},
        "cookies": {},
        "body_bytes": b"",
        "text": "",
        "elapsed_ms": 10,
        "final_url": "https://api.example.test/users",
        "redirect_chain": [],
        "error_type": None,
        "error_message": "",
    }
    defaults.update(overrides)
    return TransportResponse(**defaults)


# ---------- 场景 A：Django DisallowedHost ----------


def test_A_unit_classify_django_disallowed_host():
    """A 单元：classify_framework_error 直接识别 Django DisallowedHost body。"""
    body = (
        "<html><body><h1>DisallowedHost at /api/projects/</h1>"
        "<p>Invalid HTTP_HOST header: 'testserver'. "
        "You may need to add 'testserver' to ALLOWED_HOSTS.</p>"
        "<pre>Django Version: 6.0</pre></body></html>"
    )
    snapshot = {
        "status_code": 400,
        "headers": {"Content-Type": "text/html"},
        "body": {
            "preview": body,
            "preview_size": len(body),
            "truncated": False,
            "original_size": len(body),
            "limit_bytes": 524288,
            "content_type": "text/html",
            "encoding": "utf-8",
            "is_binary": False,
            "sha256": "",
            "redacted": False,
            "meta": {},
        },
    }

    diag = classify_framework_error(snapshot, None)

    assert diag is not None
    assert diag.framework == "django"
    assert "DisallowedHost" in diag.title
    assert "ALLOWED_HOSTS" in diag.root_cause or "Host" in diag.root_cause
    assert diag.suggested_fixes, "suggested_fixes should not be empty"
    assert any("base_url" in fix for fix in diag.suggested_fixes)


def test_A_integration_relative_url_without_base_url_returns_config_error():
    """A 集成：相对 URL `/api/tasks/` 且 base_url 为空 → 早守卫返回 CONFIG_ERROR。

    不发请求，不走 transport；这正是当前 DisallowedHost 静默 400 错误应当变成的显式错误。
    """
    definition = _make_definition(url_template="/api/tasks/")
    context = _make_context(system_vars={})  # 清掉 base_url
    transport = MockTransport([])  # 不应被调用

    runner = UnifiedApiRunner(transport=transport)
    result = runner.run(definition, context)

    assert result.failure_type == FailureType.CONFIG_ERROR
    assert result.error_code == "missing_base_url"
    assert result.persistable_result.diagnosis is not None
    assert result.persistable_result.diagnosis["title"] == "缺少 base_url"
    assert transport.sent_requests == [], "transport must not be called when base_url missing"


# ---------- 场景 B：200 + 断言 status_code=200 → PASSED ----------


def test_B_passes_when_status_code_matches_assertion():
    definition = _make_definition(
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 200,
            }
        ],
    )
    context = _make_context()
    transport = MockTransport(
        [
            _make_response(
                body_bytes=b'{"ok":true}',
                text='{"ok":true}',
            )
        ]
    )

    runner = UnifiedApiRunner(transport=transport)
    result = runner.run(definition, context)

    assert result.failure_type == FailureType.PASSED
    assert result.status == "passed"
    assert result.persistable_result.assertion_details[0]["passed"] is True


# ---------- 场景 C：200 但断言期望 201 → ASSERTION_FAILED ----------


def test_C_assertion_failed_when_expected_201_but_got_200():
    definition = _make_definition(
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 201,
            }
        ],
    )
    context = _make_context()
    transport = MockTransport(
        [
            _make_response(
                status_code=200,
                body_bytes=b'{"ok":true}',
                text='{"ok":true}',
            )
        ]
    )

    runner = UnifiedApiRunner(transport=transport)
    result = runner.run(definition, context)

    assert result.failure_type == FailureType.ASSERTION_FAILED
    assert result.status == "assertion_failed"

    detail = result.persistable_result.assertion_details[0]
    assert detail["passed"] is False
    expected_preview = detail["expected_value"]["preview"]
    actual_preview = detail["actual_value"]["preview"]
    assert "201" in str(expected_preview)
    assert "200" in str(actual_preview)


# ---------- 场景 D：transport timeout → TIMEOUT，断言被跳过 ----------


def test_D_timeout_skips_assertions_and_sets_failure_type():
    definition = _make_definition(
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 200,
            }
        ],
    )
    context = _make_context()
    transport = MockTransport(
        [
            _make_response(
                error_type="timeout",
                error_message="request timed out after 30s",
            )
        ]
    )

    runner = UnifiedApiRunner(transport=transport)
    result = runner.run(definition, context)

    assert result.failure_type == FailureType.TIMEOUT
    assert result.status == "timeout"
    assert result.persistable_result.assertion_details == [], "assertions must be skipped on transport error"
