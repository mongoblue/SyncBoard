from __future__ import annotations

import pytest
from django.utils import timezone

from qa_center import api_execution
from qa_center.api_execution.mappers import ApiAutoTestCaseResultMapper


def _execution_result():
    return api_execution.ApiCaseExecutionResult(
        status="assertion_failed",
        error_code="assertion_failed",
        error_message="assertion failed",
        trace_id="trace-map-1",
        runtime_outputs=api_execution.RuntimeOutputs(
            extracted_variables={"token": "real-secret-token"},
            eligible_for_chain=False,
        ),
        persistable_result=api_execution.PersistableResult(
            result_schema_version=1,
            trace_id="trace-map-1",
            raw_status="assertion_failed",
            error_code="assertion_failed",
            error_message="assertion failed",
            request_snapshot={"snapshot_schema_version": 1, "rendered_url": "https://api.example.test/profile"},
            response_snapshot={
                "snapshot_schema_version": 1,
                "status_code": 401,
                "headers": {"Content-Type": "application/json"},
                "elapsed_ms": 15,
                "body": {
                    "preview": '{"error":"unauthorized"}',
                    "preview_size": 24,
                    "truncated": False,
                    "original_size": 24,
                    "limit_bytes": 1024,
                    "content_type": "application/json",
                    "encoding": "utf-8",
                    "is_binary": False,
                    "sha256": "",
                    "redacted": False,
                    "meta": {},
                },
            },
            assertion_details=[{"passed": False, "assertion_type": "status_code"}],
            extracted_variables_preview={
                "token": {
                    "preview": "[REDACTED]",
                    "preview_size": 10,
                    "truncated": False,
                    "original_size": 10,
                    "limit_bytes": 4096,
                    "content_type": "application/json",
                    "encoding": "utf-8",
                    "is_binary": False,
                    "sha256": "",
                    "redacted": True,
                    "meta": {},
                }
            },
            curl={"preview": "curl https://api.example.test/profile"},
            metadata={"status_breakdown": {"assertion_failed": 1}},
            failure_type="assertion_failed",
            summary="断言失败",
            diagnosis={"framework": "django", "title": "test", "root_cause": "r", "suggested_fixes": [], "message": "m"},
        ),
        failure_type="assertion_failed",
        summary="断言失败",
        diagnosis={"framework": "django", "title": "test", "root_cause": "r", "suggested_fixes": [], "message": "m"},
    )


@pytest.mark.django_db
def test_result_mapping_keeps_core_fields_consistent(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestResult

    execution_result = _execution_result()

    auto_case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="Auto Case",
        url="/auto",
        method="GET",
        created_by=mock_user,
    )
    auto_test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="auto-run",
        status="running",
        total_cases=1,
        executed_by=mock_user,
    )

    auto_case_result = ApiAutoTestCaseResultMapper().create_case_result(
        case=auto_case,
        test_result=auto_test_result,
        execution_result=execution_result,
    )

    assert auto_case_result.trace_id == "trace-map-1"
    assert auto_case_result.raw_status == "assertion_failed"
    assert auto_case_result.failure_type == "assertion_failed"
    assert auto_case_result.response_body == '{"error":"unauthorized"}'
    assert auto_case_result.error_code == "assertion_failed"


@pytest.mark.django_db
def test_result_mapping_persists_expected_error_semantic_fields(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestResult

    execution_result = api_execution.ApiCaseExecutionResult(
        status="passed",
        error_code="",
        error_message="",
        trace_id="trace-map-expected-error",
        runtime_outputs=api_execution.RuntimeOutputs(
            extracted_variables={},
            eligible_for_chain=True,
        ),
        persistable_result=api_execution.PersistableResult(
            result_schema_version=1,
            trace_id="trace-map-expected-error",
            raw_status="passed",
            error_code="",
            error_message="",
            request_snapshot={"snapshot_schema_version": 1, "rendered_url": "https://api.example.test/missing"},
            response_snapshot={
                "snapshot_schema_version": 1,
                "status_code": 404,
                "headers": {"Content-Type": "application/json"},
                "elapsed_ms": 12,
                "body": {
                    "preview": '{"detail":"not found"}',
                    "preview_size": 22,
                    "truncated": False,
                    "original_size": 22,
                    "limit_bytes": 1024,
                    "content_type": "application/json",
                    "encoding": "utf-8",
                    "is_binary": False,
                    "sha256": "",
                    "redacted": False,
                    "meta": {},
                },
            },
            assertion_details=[{"passed": True, "assertion_type": "status_code"}],
            extracted_variables_preview={},
            curl={"preview": "curl https://api.example.test/missing"},
            metadata={
                "provider": "http",
                "expectation_type": "error_response",
                "default_assertion_policy": "expected_error_response",
                "expected_status": 404,
            },
            failure_type="passed",
            summary="断言全部通过",
        ),
        failure_type="passed",
        summary="断言全部通过",
        diagnosis=None,
    )

    auto_case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="Expected Error Case",
        url="https://api.example.test/missing",
        method="GET",
        expected_status=404,
        created_by=mock_user,
    )
    auto_test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="expected-error-run",
        status="running",
        total_cases=1,
        executed_by=mock_user,
    )

    auto_case_result = ApiAutoTestCaseResultMapper().create_case_result(
        case=auto_case,
        test_result=auto_test_result,
        execution_result=execution_result,
    )

    metadata = auto_case_result.result_metadata or {}
    assert metadata.get("expectation_type") == "error_response"
    assert metadata.get("default_assertion_policy") == "expected_error_response"
    assert metadata.get("expected_status") == 404


@pytest.mark.django_db
def test_select_preferred_mirror_prefers_unlinked_before_foreign_duplicate(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestResult, TestResult
    from qa_center.result_sink import _select_preferred_mirror

    auto_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="mirror-selection-run",
        status="passed",
        total_cases=1,
        executed_by=mock_user,
    )
    primary = TestResult.objects.create(
        test_type="api",
        name="mirror-selection-run",
        status="passed",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="",
    )
    duplicate = TestResult.objects.create(
        test_type="api",
        name="mirror-selection-run-duplicate",
        status="passed",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="foreign-task",
    )

    selected = _select_preferred_mirror(auto_result=auto_result, task_id="task-999")

    assert selected.id == primary.id
    assert selected.id != duplicate.id


@pytest.mark.django_db
def test_finalize_mirrored_test_result_prefers_unlinked_mirror_when_duplicates_exist(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestResult, TestResult
    from qa_center.result_sink import finalize_mirrored_test_result

    auto_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="finalize-duplicate-run",
        status="running",
        total_cases=1,
        executed_by=mock_user,
    )
    primary = TestResult.objects.create(
        test_type="api",
        name="finalize-duplicate-run",
        status="running",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="",
    )
    foreign = TestResult.objects.create(
        test_type="api",
        name="finalize-duplicate-run-foreign",
        status="running",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="foreign-task",
    )
    auto_result.status = "passed"
    auto_result.error_message = ""
    auto_result.duration_ms = 88
    auto_result.save(update_fields=["status", "error_message", "duration_ms"])

    finalized = finalize_mirrored_test_result(auto_result=auto_result)

    primary.refresh_from_db()
    foreign.refresh_from_db()

    assert finalized is not None
    assert finalized.id == primary.id




@pytest.mark.django_db
def test_select_preferred_mirror_prefers_latest_started_task_linked_mirror_over_newer_created_stale_one(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestResult, TestResult
    from qa_center.result_sink import _select_preferred_mirror

    auto_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="mirror-started-at-selection-run",
        status="passed",
        total_cases=1,
        executed_by=mock_user,
    )
    current = TestResult.objects.create(
        test_type="api",
        name="mirror current linked",
        status="passed",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="task-999",
        started_at=timezone.now(),
    )
    stale = TestResult.objects.create(
        test_type="api",
        name="mirror stale linked",
        status="failed",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="task-999",
        started_at=timezone.now() - timezone.timedelta(days=1),
    )
    TestResult.objects.filter(id=current.id).update(
        created_at=timezone.now() - timezone.timedelta(days=2)
    )
    current.refresh_from_db()
    stale.refresh_from_db()

    selected = _select_preferred_mirror(auto_result=auto_result, task_id="task-999")

    assert stale.created_at > current.created_at
    assert selected is not None
    assert selected.id == current.id
    assert selected.id != stale.id


@pytest.mark.django_db
def test_finalize_mirrored_test_result_prefers_latest_started_unlinked_mirror_over_newer_created_stale_one(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestResult, TestResult
    from qa_center.result_sink import finalize_mirrored_test_result

    auto_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="finalize-started-at-selection-run",
        status="running",
        total_cases=1,
        executed_by=mock_user,
    )
    current = TestResult.objects.create(
        test_type="api",
        name="finalize current mirror",
        status="running",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="",
        started_at=timezone.now(),
    )
    stale = TestResult.objects.create(
        test_type="api",
        name="finalize stale mirror",
        status="running",
        source="devops",
        project=mock_project,
        api_auto_result=auto_result,
        task_id="",
        started_at=timezone.now() - timezone.timedelta(days=1),
    )
    TestResult.objects.filter(id=current.id).update(
        created_at=timezone.now() - timezone.timedelta(days=2)
    )
    current.refresh_from_db()
    stale.refresh_from_db()
    auto_result.status = "passed"
    auto_result.error_message = ""
    auto_result.duration_ms = 88
    auto_result.save(update_fields=["status", "error_message", "duration_ms"])

    finalized = finalize_mirrored_test_result(auto_result=auto_result)

    assert stale.created_at > current.created_at
    assert finalized is not None
    assert finalized.id == current.id
    assert finalized.id != stale.id
