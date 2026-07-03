from __future__ import annotations

from qa_center import api_execution


def test_unresolved_variables_block_request_and_emit_warning_even_when_warn_policy_set():
    definition = api_execution.ApiExecutionDefinition(
        source_type="api_auto_case",
        source_id="case-1",
        name="case-1",
        method="GET",
        url_template="/users/{{missing_token}}",
        headers_template={},
        query_params_template=None,
        body_template=None,
        body_mode="none",
        files_template=None,
        cookies_template=None,
        auth_template=None,
        timeout_seconds=30,
        allow_redirects=False,
        assertions=[],
        extractors=[],
        metadata={},
    )
    context = api_execution.ApiExecutionContext(
        trace_id="trace-unresolved",
        project_id="project-1",
        environment_id="env-1",
        system_vars={"base_url": "https://api.example.test"},
        global_vars={},
        environment_vars={},
        run_overrides={},
        chain_vars={},
        locked_variables={"base_url", "project_id", "environment_id"},
        secret_names=set(),
        secret_values=set(),
        policies={"UNRESOLVED_VARIABLE_POLICY": "warn"},
        runtime_mode="mock",
        metadata={},
    )
    transport = api_execution.MockTransport()
    runner = api_execution.UnifiedApiRunner(transport=transport)

    result = runner.run(definition, context)

    assert result.status == "unresolved_variables"
    assert transport.sent_requests == []
    warnings = result.persistable_result.metadata["variable_resolution_report"]["warnings"]
    assert any(item["warning_code"] == "unresolved_variables_blocked" for item in warnings)
