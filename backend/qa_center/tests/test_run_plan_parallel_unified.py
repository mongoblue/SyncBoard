from __future__ import annotations

from unittest.mock import patch
from concurrent.futures import Future

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from qa_center import api_execution


class _ImmediateExecutor:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def submit(self, fn, *args, **kwargs):
        fut = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover
            fut.set_exception(exc)
        return fut


def _immediate_as_completed(futures):
    for fut in futures:
        yield fut


@pytest.mark.django_db
def test_run_plan_execute_uses_unified_parallel_path_when_feature_enabled(
    mock_user,
    mock_project,
):
    from qa_center.models import TestRunPlan

    plan = TestRunPlan.objects.create(
        name="Unified Parallel Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[],
        parallel=True,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_RUNPLAN_PARALLEL=True,
    ):
        with patch("qa_center.views_run_plan._execute_run_plan_async_unified_parallel") as unified_async:
            with patch("qa_center.views_run_plan._execute_run_plan_async_legacy") as legacy_async:
                response = client.post(
                    f"/api/qa/run-plans/{plan.id}/execute/",
                    {"parallel": True},
                    format="json",
                )

    assert response.status_code == 202
    assert response.data["runtime_mode"] == "real"
    unified_async.assert_called_once()
    legacy_async.assert_not_called()


@pytest.mark.django_db
def test_run_plan_parallel_feature_flag_disabled_in_production_does_not_fallback_to_unsafe_legacy_executor(
    mock_user,
    mock_project,
    monkeypatch,
):
    from qa_center.models import TestRunPlan

    monkeypatch.setenv("APP_ENV", "production")
    plan = TestRunPlan.objects.create(
        name="Strict Parallel Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[],
        parallel=True,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_RUNPLAN_PARALLEL=False,
    ):
        with patch("qa_center.views_run_plan._execute_run_plan_async_unified_parallel") as unified_async:
            with patch("qa_center.views_run_plan._execute_run_plan_async_legacy") as legacy_async:
                response = client.post(
                    f"/api/qa/run-plans/{plan.id}/execute/",
                    {"parallel": True},
                    format="json",
                )

    assert response.status_code == 409
    assert response.data["runtime_mode"] == "guarded_rejected"
    assert response.data["error_code"] == "runner_required"
    unified_async.assert_not_called()
    legacy_async.assert_not_called()


@pytest.mark.django_db
def test_run_plan_parallel_feature_flag_disabled_in_local_uses_legacy_executor(
    mock_user,
    mock_project,
    monkeypatch,
):
    from qa_center.models import TestRunPlan

    monkeypatch.setenv("APP_ENV", "local")
    plan = TestRunPlan.objects.create(
        name="Legacy Parallel Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[],
        parallel=True,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_RUNPLAN_PARALLEL=False,
    ):
        with patch("qa_center.views_run_plan._execute_run_plan_async_unified_parallel") as unified_async:
            with patch("qa_center.views_run_plan._execute_run_plan_async_legacy") as legacy_async:
                response = client.post(
                    f"/api/qa/run-plans/{plan.id}/execute/",
                    {"parallel": True},
                    format="json",
                )

    assert response.status_code == 202
    assert response.data["runtime_mode"] == "real"
    unified_async.assert_not_called()
    legacy_async.assert_called_once()


@pytest.mark.django_db
def test_run_plan_executor_unified_parallel_does_not_propagate_extracted_variables(
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

    plan = TestRunPlan.objects.create(
        name="Unified Parallel Chain Plan",
        project=mock_project,
        created_by=mock_user,
        case_ids=[case1.id, case2.id],
        parallel=True,
        max_workers=1,
    )

    transport1 = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"token":"parallel-secret-token"}',
                text='{"token":"parallel-secret-token"}',
                elapsed_ms=10,
                final_url="https://api.example.test/login",
                redirect_chain=[],
            ),
        ]
    )
    transport2 = api_execution.MockTransport()

    with patch(
        "qa_center.run_plan_executor.MockTransport",
        side_effect=[transport1, transport2],
    ):
        with patch("qa_center.run_plan_executor.ThreadPoolExecutor", _ImmediateExecutor):
            with patch("qa_center.run_plan_executor.as_completed", _immediate_as_completed):
                executor = TestRunPlanExecutor(
                    plan,
                    user=mock_user,
                    use_unified_parallel=True,
                )
                result = executor.execute()

    assert result.passed_cases == 1
    assert result.error_cases == 1
    assert transport2.sent_requests == []
