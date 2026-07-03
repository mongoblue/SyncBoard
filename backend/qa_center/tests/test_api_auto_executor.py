import json
from unittest.mock import MagicMock
import pytest
from qa_center.api_auto_executor import AssertionExecutor
from qa_center.models import ApiAutoTestAssertion


def _make_assertion(**kwargs):
    defaults = {
        "assertion_type": "status_code",
        "json_path": "",
        "expected_value": "200",
        "comparison_operator": "eq",
        "error_message": "",
    }
    defaults.update(kwargs)
    mock = MagicMock(spec=ApiAutoTestAssertion)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_response(status_code=200, body=None, headers=None, elapsed_ms=100):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body or ""
    resp.headers = headers or {}
    resp.elapsed = MagicMock()
    resp.elapsed.total_seconds.return_value = elapsed_ms / 1000.0
    if body:
        try:
            resp.json.return_value = json.loads(body) if isinstance(body, str) else body
        except (json.JSONDecodeError, ValueError):
            resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = {}
    return resp


class TestStatusCodeAssertions:
    def test_eq_pass(self):
        assertion = _make_assertion(
            assertion_type="status_code", expected_value="200", comparison_operator="eq"
        )
        resp = _make_response(status_code=200)
        result = AssertionExecutor.execute_assertion(assertion, {}, resp)
        assert result["passed"] is True
        assert result["actual_value"] == 200

    def test_eq_fail(self):
        assertion = _make_assertion(
            assertion_type="status_code", expected_value="200", comparison_operator="eq"
        )
        resp = _make_response(status_code=404)
        result = AssertionExecutor.execute_assertion(assertion, {}, resp)
        assert result["passed"] is False

    def test_non_json_body(self):
        assertion = _make_assertion(
            assertion_type="status_code", expected_value="200", comparison_operator="eq"
        )
        resp = _make_response(status_code=200, body="plain text")
        result = AssertionExecutor.execute_assertion(assertion, {}, resp)
        assert result["passed"] is True


class TestTemplateIntegration:
    def test_variable_substitution_before_request(self, db, mock_case, mock_environment):
        from qa_center import template_engine as te

        mock_case.url = "/api/{{version}}/users"
        mock_case.headers = {"Authorization": "Bearer {{api_key}}"}

        pool = te.build_variable_pool(environment=mock_environment)
        rendered_url = te.render_string(mock_case.url, pool)
        rendered_headers = te.render_value(mock_case.headers, pool)

        assert rendered_url == "/api/v1/users"
        assert rendered_headers == {"Authorization": "Bearer test-key-123"}
