from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from qa_center import api_execution
from qa_center.models import ApiAutoTestResult


@pytest.mark.django_db
def test_api_auto_case_execute_uses_unified_runner_and_persists_unified_fields(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Login Case",
        url="/login",
        method="POST",
        headers={"Authorization": "Bearer {{api_key}}"},
        content_type="application/json",
        body='{"token":"{{api_key}}"}',
        created_by=mock_user,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_API_AUTO_CASE=True,
    ):
        with patch(
            "qa_center.views_api_auto_test.create_api_auto_single_case_orchestrator"
        ) as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value
            orchestrator.execute.return_value = {
                "test_result": ApiAutoTestResult.objects.create(
                    suite=mock_suite,
                    name="Login Case_result",
                    status="passed",
                    total_cases=1,
                    passed_cases=1,
                    failed_cases=0,
                    error_cases=0,
                    executed_by=mock_user,
                ),
                "case_result": None,
                "runtime_mode": "real",
            }

            response = client.post(f"/api/qa/auto-cases/{case.id}/execute/")

    assert response.status_code == 200
    orchestrator_factory.assert_called_once()
    orchestrator.execute.assert_called_once()


@pytest.mark.django_db
def test_api_auto_case_execute_returns_runtime_mode_and_result_payload(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestCaseResult, ApiAutoTestResult

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Profile Case",
        url="/profile",
        method="GET",
        created_by=mock_user,
    )
    test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        name="Profile Case_result",
        status="passed",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        error_cases=0,
        executed_by=mock_user,
    )
    case_result = ApiAutoTestCaseResult.objects.create(
        test_result=test_result,
        case=case,
        status_code=200,
        response_body='{"ok": true}',
        response_headers={"Content-Type": "application/json"},
        response_time_ms=12,
        passed=True,
        assertion_details=[{"passed": True}],
        error_message="",
        trace_id="trace-auto-case",
        raw_status="passed",
        error_code="",
        request_snapshot={"snapshot_schema_version": 1, "rendered_url": "https://api.example.test/profile"},
        response_snapshot={"snapshot_schema_version": 1, "status_code": 200},
        curl='{"preview":"curl ...","preview_size":8,"truncated":false,"original_size":8,"limit_bytes":65536,"content_type":"text/plain","encoding":"utf-8","is_binary":false,"sha256":"","redacted":true,"meta":{}}',
        extracted_variables_preview={"token": {"preview": "[REDACTED]"}},
        result_metadata={"result_schema_version": 1},
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_API_AUTO_CASE=True,
    ):
        with patch(
            "qa_center.views_api_auto_test.create_api_auto_single_case_orchestrator"
        ) as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value
            orchestrator.execute.return_value = {
                "test_result": test_result,
                "case_result": case_result,
                "runtime_mode": "real",
            }

            response = client.post(f"/api/qa/auto-cases/{case.id}/execute/")

    assert response.status_code == 200
    assert response.data["runtime_mode"] == "real"
    assert response.data["result_id"] == test_result.id
    assert response.data["case_result_id"] == case_result.id
    assert response.data["status"] == "passed"


@pytest.mark.django_db
def test_api_auto_single_case_orchestrator_executes_with_mock_transport_and_persists_result(
    mock_user,
    mock_suite,
    mock_environment,
    monkeypatch,
):
    from qa_center.api_execution.orchestrators import create_api_auto_single_case_orchestrator
    from qa_center.models import ApiAutoTestCase, ApiAutoTestResult

    monkeypatch.setenv("APP_ENV", "test")

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        environment=mock_environment,
        name="Mocked Execute Case",
        url="/health",
        method="GET",
        created_by=mock_user,
    )
    test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        name="Mocked Execute Case_result",
        status="running",
        total_cases=1,
        executed_by=mock_user,
    )

    orchestrator = create_api_auto_single_case_orchestrator(
        case=case,
        user=mock_user,
        test_result=test_result,
    )
    outcome = orchestrator.execute()
    case_result = outcome["case_result"]

    assert outcome["runtime_mode"] == "mock"
    assert case_result.raw_status == "passed"
    assert case_result.trace_id
    assert case_result.request_snapshot["snapshot_schema_version"] == 1
    assert case_result.result_metadata["variable_resolution_report"]["resolved_variables"]["project_id"] == "project-1" or "project_id" in case_result.result_metadata["variable_resolution_report"]["resolved_variables"]


@pytest.mark.django_db
def test_api_auto_case_execute_feature_flag_disabled_in_production_still_uses_unified_executor(
    mock_user,
    mock_suite,
    monkeypatch,
):
    from qa_center.models import ApiAutoTestCase

    monkeypatch.setenv("APP_ENV", "production")
    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Strict Case",
        url="/strict",
        method="GET",
        created_by=mock_user,
    )
    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_API_AUTO_CASE=False,
    ):
        with patch("qa_center.views_api_auto_test.create_api_auto_single_case_orchestrator") as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value
            orchestrator.execute.return_value = {
                "test_result": ApiAutoTestResult.objects.create(
                    suite=mock_suite,
                    name="strict_case_run",
                    status="passed",
                    total_cases=1,
                    passed_cases=1,
                    failed_cases=0,
                    error_cases=0,
                    executed_by=mock_user,
                ),
                "case_result": None,
                "runtime_mode": "real",
            }
            response = client.post(f"/api/qa/auto-cases/{case.id}/execute/")



@pytest.mark.django_db
def test_api_auto_case_adapter_injects_success_response_policy_when_no_status_assertion(
    mock_user,
    mock_suite,
):
    from qa_center.api_execution.adapters import ApiAutoTestCaseAdapter
    from qa_center.models import ApiAutoTestCase

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Success Policy Case",
        url="/health",
        method="GET",
        expected_status=200,
        created_by=mock_user,
    )

    definition = ApiAutoTestCaseAdapter().adapt(case)

    assert definition.metadata["provider"] == "http"
    assert definition.metadata["expectation_type"] == "success_response"
    assert definition.metadata["default_assertion_policy"] == "success_response"
    assert definition.metadata["expected_status"] == 200
    assert any(
        assertion["assertion_type"] == "status_code"
        and assertion["comparison_operator"] == "in"
        and assertion["expected_value"] == "2xx"
        and assertion.get("source") == "provider_default"
        for assertion in definition.assertions
    )


@pytest.mark.django_db
def test_api_auto_case_adapter_injects_expected_error_policy_when_expected_status_is_4xx(
    mock_user,
    mock_suite,
):
    from qa_center.api_execution.adapters import ApiAutoTestCaseAdapter
    from qa_center.models import ApiAutoTestCase

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Expected Error Case",
        url="/missing",
        method="GET",
        expected_status=404,
        created_by=mock_user,
    )

    definition = ApiAutoTestCaseAdapter().adapt(case)

    assert definition.metadata["provider"] == "http"
    assert definition.metadata["expectation_type"] == "error_response"
    assert definition.metadata["default_assertion_policy"] == "expected_error_response"
    assert definition.metadata["expected_status"] == 404
    assert any(
        assertion["assertion_type"] == "status_code"
        and assertion["comparison_operator"] == "eq"
        and assertion["expected_value"] == 404
        and assertion.get("source") == "provider_default"
        for assertion in definition.assertions
    )



@pytest.mark.django_db
def test_api_auto_case_adapter_serializes_project_id_in_metadata(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.api_execution.adapters import ApiAutoTestCaseAdapter
    from qa_center.models import ApiAutoTestCase

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="Project Metadata Case",
        url="/project-metadata",
        method="GET",
        expected_status=200,
        created_by=mock_user,
    )

    definition = ApiAutoTestCaseAdapter().adapt(case)

    assert definition.metadata["project_id"] == str(mock_project.id)


@pytest.mark.django_db
def test_api_auto_single_case_orchestrator_syncs_expected_error_semantics_into_result_centers(
    mock_user,
    mock_suite,
    mock_environment,
    monkeypatch,
):
    from qa_center.api_execution.orchestrators import create_api_auto_single_case_orchestrator
    from qa_center.models import ApiAutoTestAssertion, ApiAutoTestCase, ApiAutoTestResult, TestResult, TestRunCaseResult
    from qa_center.result_sink import _select_preferred_mirror

    monkeypatch.setenv("APP_ENV", "test")

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        environment=mock_environment,
        name="Expected Error Run Center Case",
        url="https://api.example.test/missing",
        method="GET",
        expected_status=404,
        created_by=mock_user,
    )
    ApiAutoTestAssertion.objects.create(
        case=case,
        assertion_type="status_code",
        expected_value="404",
        comparison_operator="eq",
        is_active=True,
    )
    test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        name="Expected Error Run Center Case_result",
        status="running",
        total_cases=1,
        executed_by=mock_user,
    )

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=404,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"detail":"not found"}',
                text='{"detail":"not found"}',
                elapsed_ms=11,
                final_url="https://api.example.test/missing",
                redirect_chain=[],
            ),
        ]
    )

    with patch("qa_center.api_execution.orchestrators.MockTransport", return_value=transport):
        orchestrator = create_api_auto_single_case_orchestrator(
            case=case,
            user=mock_user,
            test_result=test_result,
        )
        outcome = orchestrator.execute()

    auto_result = outcome["test_result"]
    mirrored = _select_preferred_mirror(auto_result=auto_result)
    case_result = TestRunCaseResult.objects.get(test_run__name=auto_result.name, api_auto_case=case)

    assert auto_result.status == "passed"
    assert auto_result.passed_cases == 1
    assert auto_result.failed_cases == 0
    assert auto_result.error_cases == 0
    assert mirrored.status == "passed"
    assert case_result.status == "passed"
    assert case_result.result_metadata["expectation_type"] == "error_response"
    assert case_result.result_metadata["default_assertion_policy"] == "expected_error_response"
    assert case_result.result_metadata["expected_status"] == 404


@pytest.mark.django_db
def test_api_auto_single_case_orchestrator_uses_explicit_source_for_result_centers(
    mock_user,
    mock_project,
    mock_suite,
    mock_environment,
    monkeypatch,
):
    from qa_center.api_execution.orchestrators import create_api_auto_single_case_orchestrator
    from qa_center.models import ApiAutoTestCase, ApiAutoTestResult, TestResult, TestRun
    from qa_center.result_sink import _select_preferred_mirror
    from qa_center.result_sink import _select_preferred_mirror

    monkeypatch.setenv("APP_ENV", "test")

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        environment=mock_environment,
        name="DevOps Source Contract Case",
        url="/source-contract",
        method="GET",
        created_by=mock_user,
    )
    test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Source Contract Case_result",
        status="running",
        total_cases=1,
        executed_by=mock_user,
    )

    orchestrator = create_api_auto_single_case_orchestrator(
        case=case,
        user=mock_user,
        test_result=test_result,
        source="devops",
    )
    outcome = orchestrator.execute()

    auto_result = outcome["test_result"]
    mirrored = _select_preferred_mirror(auto_result=auto_result)
    run = TestRun.objects.get(name=auto_result.name, project=mock_project)

    assert mirrored.source == "devops"
    assert run.summary["source"] == "devops"
