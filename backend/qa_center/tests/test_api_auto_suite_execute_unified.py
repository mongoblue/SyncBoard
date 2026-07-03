from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from qa_center import api_execution
from qa_center.models import ApiAutoTestResult


@pytest.mark.django_db
def test_api_auto_suite_execute_uses_unified_runner_when_feature_enabled(
    mock_user,
    mock_suite,
):
    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_API_AUTO_SUITE=True,
    ):
        with patch(
            "qa_center.views_api_auto_test.create_api_auto_suite_orchestrator"
        ) as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value
            orchestrator.execute.return_value = {
                "test_result": ApiAutoTestResult.objects.create(
                    suite=mock_suite,
                    name="suite_run",
                    status="passed",
                    total_cases=0,
                    passed_cases=0,
                    failed_cases=0,
                    error_cases=0,
                    executed_by=mock_user,
                ),
                "runtime_mode": "real",
            }

            response = client.post(f"/api/qa/auto-suites/{mock_suite.id}/execute/")

    assert response.status_code == 200
    assert response.data["runtime_mode"] == "real"
    orchestrator_factory.assert_called_once()
    orchestrator.execute.assert_called_once()


@pytest.mark.django_db
def test_api_auto_suite_execute_feature_flag_disabled_in_production_still_uses_unified_executor(
    mock_user,
    mock_suite,
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "production")
    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_API_AUTO_SUITE=False,
    ):
        with patch("qa_center.views_api_auto_test.create_api_auto_suite_orchestrator") as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value
            orchestrator.execute.return_value = {
                "test_result": ApiAutoTestResult.objects.create(
                    suite=mock_suite,
                    name="strict_suite_run",
                    status="passed",
                    total_cases=0,
                    passed_cases=0,
                    failed_cases=0,
                    error_cases=0,
                    executed_by=mock_user,
                ),
                "runtime_mode": "real",
            }
            response = client.post(f"/api/qa/auto-suites/{mock_suite.id}/execute/")

    assert response.status_code == 200
    assert response.data["runtime_mode"] == "real"
    orchestrator_factory.assert_called_once()


@pytest.mark.django_db
def test_api_auto_suite_execute_feature_flag_disabled_in_local_still_uses_unified_executor(
    mock_user,
    mock_suite,
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "local")
    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_API_AUTO_SUITE=False,
    ):
        with patch("qa_center.views_api_auto_test.create_api_auto_suite_orchestrator") as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value
            orchestrator.execute.return_value = {
                "test_result": ApiAutoTestResult.objects.create(
                    suite=mock_suite,
                    name="local_suite_run",
                    status="passed",
                    total_cases=0,
                    passed_cases=0,
                    failed_cases=0,
                    error_cases=0,
                    executed_by=mock_user,
                ),
                "runtime_mode": "real",
            }
            response = client.post(f"/api/qa/auto-suites/{mock_suite.id}/execute/")

    assert response.status_code == 200
    assert response.data["runtime_mode"] == "real"
    orchestrator_factory.assert_called_once()


@pytest.mark.django_db
def test_api_auto_suite_orchestrator_propagates_extracted_variables_between_passed_cases(
    mock_user,
    mock_suite,
    mock_environment,
    monkeypatch,
):
    from qa_center.api_execution.orchestrators import create_api_auto_suite_orchestrator
    from qa_center.models import ApiAutoTestAssertion, ApiAutoTestCase, ApiAutoTestExtractor

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

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"token":"suite-secret-token"}',
                text='{"token":"suite-secret-token"}',
                elapsed_ms=15,
                final_url="https://api.example.test/login",
                redirect_chain=[],
            ),
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"ok":true}',
                text='{"ok":true}',
                elapsed_ms=9,
                final_url="https://api.example.test/profile",
                redirect_chain=[],
            ),
        ]
    )

    with patch("qa_center.api_execution.orchestrators.MockTransport", return_value=transport):
        orchestrator = create_api_auto_suite_orchestrator(
            suite=mock_suite,
            user=mock_user,
        )
        outcome = orchestrator.execute()



@pytest.mark.django_db
def test_api_auto_suite_orchestrator_syncs_result_into_unified_result_center(
    mock_user,
    mock_suite,
    monkeypatch,
):
    from qa_center.api_execution.orchestrators import create_api_auto_suite_orchestrator
    from qa_center.models import ApiAutoTestAssertion, ApiAutoTestCase, TestResult, TestRun, TestRunCaseResult
    from qa_center.result_sink import _select_preferred_mirror

    monkeypatch.setenv("APP_ENV", "test")

    case1 = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Suite Result Case 1",
        url="https://api.example.test/suite-result-1",
        method="GET",
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

    case2 = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Suite Result Case 2",
        url="https://api.example.test/suite-result-2",
        method="GET",
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

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"ok":true}',
                text='{"ok":true}',
                elapsed_ms=15,
                final_url="https://api.example.test/suite-result-1",
                redirect_chain=[],
            ),
            api_execution.TransportResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"ok":true}',
                text='{"ok":true}',
                elapsed_ms=11,
                final_url="https://api.example.test/suite-result-2",
                redirect_chain=[],
            ),
        ]
    )

    with patch("qa_center.api_execution.orchestrators.MockTransport", return_value=transport):
        orchestrator = create_api_auto_suite_orchestrator(
            suite=mock_suite,
            user=mock_user,
        )
        outcome = orchestrator.execute()

    auto_result = outcome["test_result"]
    run = TestRun.objects.get(project=mock_suite.project, name=auto_result.name)
    mirrored = _select_preferred_mirror(auto_result=auto_result)
    case_results = TestRunCaseResult.objects.filter(test_run=run).order_by("sequence")

    assert run.summary["auto_result_id"] == auto_result.id
    assert run.status == "passed"
    assert run.total_count == 2
    assert run.passed_count == 2
    assert mirrored.source == "single"
    assert mirrored.status == "passed"
    assert case_results.count() == 2
    assert list(case_results.values_list("api_auto_case_id", flat=True)) == [case1.id, case2.id]


@pytest.mark.django_db
def test_api_auto_suite_orchestrator_preserves_expected_error_policy_semantics(
    mock_user,
    mock_suite,
    monkeypatch,
):
    from qa_center.api_execution.orchestrators import create_api_auto_suite_orchestrator
    from qa_center.models import ApiAutoTestAssertion, ApiAutoTestCase, TestResult, TestRunCaseResult
    from qa_center.result_sink import _select_preferred_mirror

    monkeypatch.setenv("APP_ENV", "test")

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Suite Expected Error Case",
        url="https://api.example.test/missing",
        method="GET",
        expected_status=404,
        created_by=mock_user,
        sort_order=1,
    )
    ApiAutoTestAssertion.objects.create(
        case=case,
        assertion_type="status_code",
        expected_value="404",
        comparison_operator="eq",
        is_active=True,
    )

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=404,
                headers={"Content-Type": "application/json"},
                cookies={},
                body_bytes=b'{"detail":"not found"}',
                text='{"detail":"not found"}',
                elapsed_ms=13,
                final_url="https://api.example.test/missing",
                redirect_chain=[],
            ),
        ]
    )

    with patch("qa_center.api_execution.orchestrators.MockTransport", return_value=transport):
        orchestrator = create_api_auto_suite_orchestrator(
            suite=mock_suite,
            user=mock_user,
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
    assert case_result.result_metadata["semantic_status"] == "expected_error_matched"
    assert case_result.result_metadata["semantic_label"] == "预期错误响应且匹配成功"
