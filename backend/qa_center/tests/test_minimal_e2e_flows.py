from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from qa_center import api_execution


@pytest.mark.django_db
def test_minimal_api_e2e_token_chain_with_auto_suite(
    mock_user,
    mock_project,
    mock_suite,
    mock_environment,
    monkeypatch,
):
    from qa_center.api_execution.orchestrators import create_api_auto_suite_orchestrator
    from qa_center.models import (
        ApiAutoTestAssertion,
        ApiAutoTestCase,
        ApiAutoTestExtractor,
        TestGlobalVar,
    )

    TestGlobalVar.objects.create(
        project=mock_project,
        key="shared_secret",
        value="global-secret-token",
        is_secret=True,
        created_by=mock_user,
    )

    login_case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Login",
        url="/login",
        method="POST",
        content_type="application/json",
        body='{"username":"alice","password":"{{shared_secret}}"}',
        created_by=mock_user,
        sort_order=1,
    )
    ApiAutoTestAssertion.objects.create(
        case=login_case,
        assertion_type="status_code",
        expected_value="200",
        comparison_operator="eq",
        is_active=True,
    )
    ApiAutoTestExtractor.objects.create(
        case=login_case,
        name="token",
        source="body",
        expression="$.token",
        is_active=True,
    )

    profile_case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Profile",
        url="/profile",
        method="GET",
        headers={"Authorization": "Bearer {{token}}"},
        created_by=mock_user,
        sort_order=2,
    )
    ApiAutoTestAssertion.objects.create(
        case=profile_case,
        assertion_type="status_code",
        expected_value="200",
        comparison_operator="eq",
        is_active=True,
    )

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"token":"super-secret-token"}',
                text='{"token":"super-secret-token"}',
                elapsed_ms=8,
                final_url="https://api.example.test/login",
                redirect_chain=[],
            ),
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"user":"alice"}',
                text='{"user":"alice"}',
                elapsed_ms=5,
                final_url="https://api.example.test/profile",
                redirect_chain=[],
            ),
        ]
    )

    with patch("qa_center.api_execution.orchestrators.MockTransport", return_value=transport):
        with patch("qa_center.api_execution.orchestrators.RuntimeGuard.choose_default_transport", return_value="mock_transport"):
            orchestrator = create_api_auto_suite_orchestrator(
                suite=mock_suite,
                user=mock_user,
            )
            outcome = orchestrator.execute()

    result = outcome["test_result"]
    case_results = list(result.case_results.order_by("id"))

    assert outcome["runtime_mode"] == "mock"
    assert result.passed_cases == 2
    assert transport.sent_requests[1].headers["Authorization"] == "Bearer super-secret-token"
    assert "super-secret-token" not in str(case_results[0].request_snapshot)
    assert case_results[0].raw_status == "passed"
    assert case_results[1].raw_status == "passed"


@pytest.mark.django_db
def test_minimal_runplan_e2e_serial_token_chain_and_stop_on_failure(
    mock_user,
    mock_project,
    mock_suite,
    mock_environment,
    monkeypatch,
):
    from qa_center.models import (
        ApiAutoTestAssertion,
        ApiAutoTestCase,
        ApiAutoTestExtractor,
        TestRunPlan,
    )
    from qa_center.run_plan_executor import TestRunPlanExecutor

    monkeypatch.setenv("APP_ENV", "test")

    login_case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Login",
        url="/login",
        method="POST",
        content_type="application/json",
        body='{"username":"alice"}',
        created_by=mock_user,
        sort_order=1,
    )
    ApiAutoTestAssertion.objects.create(
        case=login_case,
        assertion_type="status_code",
        expected_value="200",
        comparison_operator="eq",
        is_active=True,
    )
    ApiAutoTestExtractor.objects.create(
        case=login_case,
        name="token",
        source="body",
        expression="$.token",
        is_active=True,
    )

    failing_case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Profile",
        url="/profile",
        method="GET",
        headers={"Authorization": "Bearer {{token}}"},
        created_by=mock_user,
        sort_order=2,
    )
    ApiAutoTestAssertion.objects.create(
        case=failing_case,
        assertion_type="status_code",
        expected_value="200",
        comparison_operator="eq",
        is_active=True,
    )

    skipped_case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="After Failure",
        url="/after-failure",
        method="GET",
        created_by=mock_user,
        sort_order=3,
    )

    plan = TestRunPlan.objects.create(
        name="RunPlan E2E",
        project=mock_project,
        created_by=mock_user,
        case_ids=[login_case.id, failing_case.id, skipped_case.id],
        parallel=False,
        stop_on_failure=True,
    )

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"token":"chain-token"}',
                text='{"token":"chain-token"}',
                elapsed_ms=7,
                final_url="https://api.example.test/login",
                redirect_chain=[],
            ),
            api_execution.TransportResponse(
                status_code=500,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"error":"failed"}',
                text='{"error":"failed"}',
                elapsed_ms=6,
                final_url="https://api.example.test/profile",
                redirect_chain=[],
            ),
        ]
    )

    events = []

    with patch("qa_center.run_plan_executor.MockTransport", return_value=transport):
        with patch("qa_center.run_plan_executor.RuntimeGuard.choose_default_transport", return_value="mock_transport"):
            with patch("qa_center.run_plan_executor._broadcast", side_effect=lambda event, project_id: events.append(event)):
                executor = TestRunPlanExecutor(
                    plan,
                    user=mock_user,
                    stop_on_failure=True,
                    use_unified_serial=True,
                )
                result = executor.execute()

    executed_case_ids = [event.get("case_id") for event in events if event.get("phase") == "case_done"]

    assert result.passed_cases == 1
    assert result.failed_cases == 1
    assert result.error_cases == 0
    assert executed_case_ids == [login_case.id, failing_case.id]
    assert transport.sent_requests[1].headers["Authorization"] == "Bearer chain-token"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_ENV", "test")
