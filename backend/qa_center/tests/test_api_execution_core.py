import ast
import importlib
import json
from pathlib import Path

import pytest


def _import_api_execution():
    return importlib.import_module("qa_center.api_execution")


def _import_runner_module():
    return importlib.import_module("qa_center.api_execution.runner")


def _make_context(**overrides):
    api_execution = _import_api_execution()
    defaults = {
        "trace_id": "trace-123",
        "project_id": "project-1",
        "environment_id": "env-1",
        "system_vars": {
            "base_url": "https://api.example.test",
            "project_id": "project-1",
            "environment_id": "env-1",
        },
        "global_vars": {},
        "environment_vars": {},
        "run_overrides": {},
        "chain_vars": {},
        "locked_variables": {"base_url", "project_id", "environment_id"},
        "secret_names": {"authorization", "token", "password", "api_key", "cookie"},
        "secret_values": {"super-secret-token", "Bearer super-secret-token", "cookie-secret"},
        "policies": {},
        "runtime_mode": "mock",
        "metadata": {},
    }
    defaults.update(overrides)
    return api_execution.ApiExecutionContext(**defaults)


def _make_definition(**overrides):
    api_execution = _import_api_execution()
    defaults = {
        "source_type": "api_auto",
        "source_id": "case-1",
        "name": "case-1",
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
    return api_execution.ApiExecutionDefinition(**defaults)


def _make_response(**overrides):
    api_execution = _import_api_execution()
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
    return api_execution.TransportResponse(**defaults)


def test_api_execution_layer_does_not_import_django_models_or_requests_in_runner():
    package_dir = Path(__file__).resolve().parents[1] / "api_execution"
    assert package_dir.exists(), "qa_center.api_execution package must exist"

    forbidden_package_prefixes = (
        "qa_center.models",
        "qa_center.views",
        "qa_center.consumers",
        "qa_center.tasks",
        "qa_center.tasks_test_exec",
    )
    violations = []

    for py_file in package_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if py_file.name == "runner.py" and name == "requests":
                        violations.append((py_file.name, name))
                    if any(
                        name == prefix or name.startswith(prefix + ".")
                        for prefix in forbidden_package_prefixes
                    ):
                        violations.append((py_file.name, name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if py_file.name == "runner.py" and module == "requests":
                    violations.append((py_file.name, module))
                if any(
                    module == prefix or module.startswith(prefix + ".")
                    for prefix in forbidden_package_prefixes
                ):
                    violations.append((py_file.name, module))

    assert not violations, f"forbidden imports found: {violations}"


def test_runtime_guard_chooses_mock_transport_in_test_env(monkeypatch):
    api_execution = _import_api_execution()

    monkeypatch.setenv("APP_ENV", "test")
    guard = api_execution.RuntimeGuard()

    assert guard.get_app_env() == "test"
    assert guard.is_production() is False
    assert guard.is_strict() is False
    assert guard.choose_default_transport() == "mock_transport"
    assert guard.build_runtime_mode(celery_eager=True) == "celery_eager"


def test_unified_api_runner_get_with_mock_transport():
    api_execution = _import_api_execution()

    definition = _make_definition(
        headers_template={"Authorization": "Bearer {{api_key}}"},
        query_params_template={"q": "{{query}}"},
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 200,
            }
        ],
        extractors=[
            {
                "name": "token",
                "source": "body",
                "expression": "$.token",
                "is_active": True,
            }
        ],
    )
    context = _make_context(
        environment_vars={"api_key": "super-secret-token", "query": "alice"}
    )
    transport = api_execution.MockTransport(
        [
            _make_response(
                body_bytes=b'{"token":"super-secret-token","name":"Alice"}',
                text='{"token":"super-secret-token","name":"Alice"}',
                final_url="https://api.example.test/users?q=alice",
            )
        ]
    )
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)
    persistable = result.to_persistable_dict()

    assert result.status == "passed"
    assert transport.sent_requests[0].rendered_url == "https://api.example.test/users"
    assert transport.sent_requests[0].query_params == [("q", "alice")]
    assert result.runtime_outputs.extracted_variables["token"] == "super-secret-token"
    assert result.persistable_result.extracted_variables_preview["token"]["redacted"] is True
    assert result.persistable_result.assertion_details[0]["passed"] is True
    assert "super-secret-token" not in json.dumps(persistable, ensure_ascii=False)
    assert persistable["request_snapshot"]["snapshot_schema_version"] == 1
    assert persistable["result_schema_version"] == 1


def test_unified_api_runner_post_with_mock_transport():
    api_execution = _import_api_execution()

    definition = _make_definition(
        method="POST",
        body_mode="json",
        body_template={"name": "{{user_name}}", "password": "{{api_key}}"},
        headers_template={"Content-Type": "application/json"},
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 201,
            }
        ],
    )
    context = _make_context(
        environment_vars={"user_name": "Alice", "api_key": "super-secret-token"}
    )
    transport = api_execution.MockTransport(
        [
            _make_response(
                status_code=201,
                body_bytes=b'{"ok":true}',
                text='{"ok":true}',
                final_url="https://api.example.test/users",
            )
        ]
    )
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)

    assert result.status == "passed"
    assert transport.sent_requests[0].body_mode == "json"
    assert transport.sent_requests[0].body == {
        "name": "Alice",
        "password": "super-secret-token",
    }


def test_unresolved_variables_block_before_transport_send():
    api_execution = _import_api_execution()

    definition = _make_definition(
        headers_template={"Authorization": "Bearer {{missing_token}}"}
    )
    context = _make_context()
    transport = api_execution.MockTransport([])
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)

    assert result.status == "unresolved_variables"
    assert result.error_code == "unresolved_variables"
    assert transport.sent_requests == []
    report = result.persistable_result.metadata["variable_resolution_report"]
    assert "missing_token" in report["unresolved_variables"]
    assert result.persistable_result.curl is None


def test_transport_error_skips_assertions_and_extractors():
    api_execution = _import_api_execution()

    definition = _make_definition(
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 200,
            }
        ],
        extractors=[
            {
                "name": "token",
                "source": "body",
                "expression": "$.token",
                "is_active": True,
            }
        ],
    )
    context = _make_context()
    transport = api_execution.MockTransport(
        [
            _make_response(
                error_type="connection_error",
                error_message="connection refused",
            )
        ]
    )
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)

    assert result.status == "network_error"
    assert result.failure_type == "network_error"
    assert result.persistable_result.assertion_details == []
    assert result.runtime_outputs.extracted_variables == {}


def test_curl_generated_before_transport_error_and_redacted():
    api_execution = _import_api_execution()

    definition = _make_definition(
        headers_template={"Authorization": "Bearer {{api_key}}"},
        body_mode="raw",
        body_template="token={{api_key}}",
        method="POST",
    )
    context = _make_context(environment_vars={"api_key": "super-secret-token"})
    transport = api_execution.MockTransport(
        [
            _make_response(
                error_type="timeout",
                error_message="request timeout",
            )
        ]
    )
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)
    curl_preview = result.persistable_result.curl["preview"]

    assert result.status == "timeout"
    assert curl_preview
    assert "super-secret-token" not in curl_preview




def test_http_provider_expected_error_policy_allows_404_when_assertion_matches():
    api_execution = _import_api_execution()

    definition = _make_definition(
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 404,
            }
        ],
        metadata={
            "provider": "http",
            "default_assertion_policy": "expected_error_response",
            "expected_status": 404,
        },
    )
    context = _make_context()
    transport = api_execution.MockTransport(
        [
            _make_response(
                status_code=404,
                body_bytes=b'{"detail":"not found"}',
                text='{"detail":"not found"}',
            )
        ]
    )
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)

    assert result.status == "passed"
    assert result.failure_type == api_execution.FailureType.PASSED
    assert result.persistable_result.assertion_details[0]["passed"] is True


def test_http_provider_expected_error_policy_mismatch_is_assertion_failed_not_http_error():
    api_execution = _import_api_execution()

    definition = _make_definition(
        assertions=[
            {
                "assertion_type": "status_code",
                "comparison_operator": "eq",
                "expected_value": 401,
            }
        ],
        metadata={
            "provider": "http",
            "default_assertion_policy": "expected_error_response",
            "expected_status": 401,
        },
    )
    context = _make_context()
    transport = api_execution.MockTransport(
        [
            _make_response(
                status_code=404,
                body_bytes=b'{"detail":"not found"}',
                text='{"detail":"not found"}',
            )
        ]
    )
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)

    assert result.status == "assertion_failed"
    assert result.failure_type == api_execution.FailureType.ASSERTION_FAILED


@pytest.mark.parametrize(
    ("body_mode", "body_template", "expected_body"),
    [
        ("json", {"name": "{{name}}"}, {"name": "Alice"}),
        ("form", {"name": "{{name}}"}, [("name", "Alice")]),
        ("raw", "name={{name}}", "name=Alice"),
    ],
)
def test_body_mode_controls_json_form_raw_serialization(
    body_mode,
    body_template,
    expected_body,
):
    api_execution = _import_api_execution()

    definition = _make_definition(
        method="POST",
        body_mode=body_mode,
        body_template=body_template,
    )
    context = _make_context(environment_vars={"name": "Alice"})
    transport = api_execution.MockTransport([_make_response(text='{"ok":true}', body_bytes=b'{"ok":true}')])
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)

    assert result.status == "passed"
    assert transport.sent_requests[0].body == expected_body
