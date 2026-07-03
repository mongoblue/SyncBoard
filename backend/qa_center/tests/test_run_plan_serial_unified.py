from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from qa_center import api_execution


@pytest.mark.django_db
def test_run_plan_execute_uses_unified_serial_path_when_feature_enabled(
    mock_user,
    mock_project,
):
    from qa_center.models import TestRunPlan

    plan = TestRunPlan.objects.create(
        name="Unified Serial Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[],
        parallel=False,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_RUNPLAN_SERIAL=True,
    ):
        with patch("qa_center.views_run_plan._execute_run_plan_async_unified_serial") as unified_async:
            with patch("qa_center.views_run_plan._execute_run_plan_async_legacy") as legacy_async:
                response = client.post(f"/api/qa/run-plans/{plan.id}/execute/", {})

    assert response.status_code == 202
    assert response.data["runtime_mode"] == "real"
    unified_async.assert_called_once()
    legacy_async.assert_not_called()


@pytest.mark.django_db
def test_run_plan_execute_feature_flag_disabled_in_production_does_not_fallback_to_unsafe_legacy_executor(
    mock_user,
    mock_project,
    monkeypatch,
):
    from qa_center.models import TestRunPlan

    monkeypatch.setenv("APP_ENV", "production")
    plan = TestRunPlan.objects.create(
        name="Strict Serial Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[],
        parallel=False,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_RUNPLAN_SERIAL=False,
    ):
        with patch("qa_center.views_run_plan._execute_run_plan_async_unified_serial") as unified_async:
            with patch("qa_center.views_run_plan._execute_run_plan_async_legacy") as legacy_async:
                response = client.post(f"/api/qa/run-plans/{plan.id}/execute/", {})

    assert response.status_code == 409
    assert response.data["runtime_mode"] == "guarded_rejected"
    assert response.data["error_code"] == "runner_required"
    unified_async.assert_not_called()
    legacy_async.assert_not_called()


@pytest.mark.django_db
def test_run_plan_execute_feature_flag_disabled_in_local_uses_legacy_executor(
    mock_user,
    mock_project,
    monkeypatch,
):
    from qa_center.models import TestRunPlan

    monkeypatch.setenv("APP_ENV", "local")
    plan = TestRunPlan.objects.create(
        name="Legacy Serial Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[],
        parallel=False,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_RUNPLAN_SERIAL=False,
    ):
        with patch("qa_center.views_run_plan._execute_run_plan_async_unified_serial") as unified_async:
            with patch("qa_center.views_run_plan._execute_run_plan_async_legacy") as legacy_async:
                response = client.post(f"/api/qa/run-plans/{plan.id}/execute/", {})

    assert response.status_code == 202
    assert response.data["runtime_mode"] == "real"
    unified_async.assert_not_called()
    legacy_async.assert_called_once()


@pytest.mark.django_db
def test_run_plan_executor_unified_serial_propagates_extracted_variables_between_passed_cases(
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

    case1 = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Login",
        url="/login",
        method="POST",
        content_type="application/json",
        body='{"user":"alice"}',
        created_by=mock_user,
        sort_order=1,
    )
    ApiAutoTestAssertion.objects.create(
        case=case1,
        assertion_type="status_code",
        expected_value="200",
        comparison_operator="eq",
        is_active=True,
    )
    ApiAutoTestExtractor.objects.create(
        case=case1,
        name="token",
        source="body",
        expression="$.token",
        is_active=True,
    )

    case2 = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Profile",
        url="/profile",
        method="GET",
        headers={"Authorization": "Bearer {{token}}"},
        created_by=mock_user,
        sort_order=2,
    )
    ApiAutoTestAssertion.objects.create(
        case=case2,
        assertion_type="status_code",
        expected_value="200",
        comparison_operator="eq",
        is_active=True,
    )

    plan = TestRunPlan.objects.create(
        name="Unified Serial Chain Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[case1.id, case2.id],
        parallel=False,
    )

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"token":"plan-secret-token"}',
                text='{"token":"plan-secret-token"}',
                elapsed_ms=11,
                final_url="https://api.example.test/login",
                redirect_chain=[],
            ),
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"ok":true}',
                text='{"ok":true}',
                elapsed_ms=7,
                final_url="https://api.example.test/profile",
                redirect_chain=[],
            ),
        ]
    )

    with patch("qa_center.run_plan_executor.MockTransport", return_value=transport):
        executor = TestRunPlanExecutor(plan, user=mock_user, use_unified_serial=True)
        result = executor.execute()

    assert result.passed_cases == 2
    assert transport.sent_requests[1].headers["Authorization"] == "Bearer plan-secret-token"
