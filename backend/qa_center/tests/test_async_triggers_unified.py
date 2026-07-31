from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient


@pytest.fixture
def cicd_config(db, mock_project, mock_user):
    from qa_center.models import CiCdConfig

    return CiCdConfig.objects.create(
        name="CI Config",
        ci_type="gitlab",
        branch="main",
        project=mock_project,
        created_by=mock_user,
        is_active=True,
        ci_url="https://ci.example.test",
        ci_project="group/project",
        ci_token="token-123456",
    )


@pytest.mark.django_db
def test_test_task_execute_view_strict_env_requires_celery_no_thread_fallback(
    mock_user,
    mock_project,
    monkeypatch,
):
    from qa_center.models import ApiAutoTestCase, TestTask

    monkeypatch.setenv("APP_ENV", "production")
    case = ApiAutoTestCase.objects.create(
        project=mock_project,
        name="Async API Case",
        url="/async-case",
        method="GET",
        created_by=mock_user,
    )
    task = TestTask.objects.create(
        name="Async API Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"api_cases": [case.id]},
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_CELERY_TASKS=False,
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_ASYNC_TRIGGERS=True,
    ):
        with patch("qa_center.views_devops.threading.Thread") as thread_cls:
            response = client.post(f"/api/qa/devops/tasks/{task.id}/execute/")

    assert response.status_code == 409
    assert response.data["runtime_mode"] == "guarded_rejected"
    assert response.data["error_code"] == "runner_required"
    thread_cls.assert_not_called()


@pytest.mark.django_db
def test_test_task_execute_view_local_without_celery_uses_thread_fallback(
    mock_user,
    mock_project,
    monkeypatch,
):
    from qa_center.models import ApiAutoTestCase, TestTask

    monkeypatch.setenv("APP_ENV", "local")
    case = ApiAutoTestCase.objects.create(
        project=mock_project,
        name="Local Async API Case",
        url="/local-async-case",
        method="GET",
        created_by=mock_user,
    )
    task = TestTask.objects.create(
        name="Local Async API Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"api_cases": [case.id]},
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(
        USE_CELERY_TASKS=False,
        USE_UNIFIED_API_RUNNER=False,
        USE_UNIFIED_RUNNER_FOR_ASYNC_TRIGGERS=False,
    ):
        with patch("qa_center.views_devops.threading.Thread") as thread_cls:
            thread_cls.return_value = MagicMock()
            response = client.post(f"/api/qa/devops/tasks/{task.id}/execute/")

    assert response.status_code == 200
    assert response.data["runtime_mode"] == "thread_fallback"
    assert response.data["execution_id"] is not None
    from qa_center.models import TestResult
    created_result = TestResult.objects.get(id=response.data["execution_id"])
    assert created_result.task_id == str(task.id)
    thread_cls.assert_called_once()


@pytest.mark.django_db
def test_execute_test_task_uses_unified_single_case_orchestrator_when_feature_enabled(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, TestTask
    from qa_center.tasks_test_exec import execute_test_task

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="Async Case",
        url="/async",
        method="GET",
        created_by=mock_user,
    )
    task = TestTask.objects.create(
        name="Scheduled API Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"case_ids": [case.id]},
        status="idle",
    )

    with override_settings(
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_ASYNC_TRIGGERS=True,
    ):
        with patch("qa_center.tasks_test_exec.create_api_auto_single_case_orchestrator") as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value
            orchestrator.execute.return_value = {"runtime_mode": "mock"}
            result = execute_test_task.run(task.id)

    task.refresh_from_db()
    assert result["status"] == "success"
    assert task.status in {"success", "completed"}
    orchestrator_factory.assert_called_once_with(
        case=case,
        user=mock_user,
        test_result=orchestrator_factory.call_args.kwargs["test_result"],
        source="devops",
    )


@pytest.mark.django_db
def test_execute_test_task_prefers_unlinked_mirror_over_newer_foreign_duplicate(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, TestResult, TestTask
    from qa_center.tasks_test_exec import execute_test_task

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="Async Duplicate Mirror Case",
        url="/async-duplicate-mirror",
        method="GET",
        created_by=mock_user,
    )
    task = TestTask.objects.create(
        name="Scheduled Duplicate Mirror Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"case_ids": [case.id]},
        status="idle",
    )
    created = {}

    with override_settings(
        USE_UNIFIED_API_RUNNER=True,
        USE_UNIFIED_RUNNER_FOR_ASYNC_TRIGGERS=True,
    ):
        with patch("qa_center.tasks_test_exec.create_api_auto_single_case_orchestrator") as orchestrator_factory:
            orchestrator = orchestrator_factory.return_value

            def _execute():
                auto_result = orchestrator_factory.call_args.kwargs["test_result"]
                primary = TestResult.objects.create(
                    test_type="api",
                    name=auto_result.name,
                    status="passed",
                    source="devops",
                    project=mock_project,
                    api_auto_result=auto_result,
                    task_id="",
                )
                duplicate = TestResult.objects.create(
                    test_type="api",
                    name=f"{auto_result.name}-duplicate",
                    status="passed",
                    source="devops",
                    project=mock_project,
                    api_auto_result=auto_result,
                    task_id="foreign-task",
                )
                created["primary_id"] = primary.id
                created["duplicate_id"] = duplicate.id
                return {"test_result": auto_result, "runtime_mode": "real"}

            orchestrator.execute.side_effect = _execute
            result = execute_test_task.run(task.id)

    task.refresh_from_db()
    primary = TestResult.objects.get(id=created["primary_id"])
    duplicate = TestResult.objects.get(id=created["duplicate_id"])

    assert result["status"] == "success"
    assert task.last_result_id == primary.id
    assert primary.task_id == str(task.id)
    assert duplicate.task_id == "foreign-task"


@pytest.mark.django_db
def test_pipeline_trigger_strict_env_rejects_mock_thread_fallback(
    mock_user,
    cicd_config,
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "production")
    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(USE_REAL_CI=False):
        with patch("qa_center.views_devops.threading.Thread") as thread_cls:
            response = client.post(f"/api/qa/devops/cicd-config/{cicd_config.id}/trigger/")

    assert response.status_code == 409
    assert response.data["runtime_mode"] == "guarded_rejected"
    assert response.data["error_code"] == "runner_required"
    thread_cls.assert_not_called()


@pytest.mark.django_db
def test_pipeline_trigger_local_mock_returns_runtime_mode_and_is_mock(
    mock_user,
    cicd_config,
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "local")
    client = APIClient()
    client.force_authenticate(user=mock_user)

    with override_settings(USE_REAL_CI=False):
        with patch("qa_center.views_devops.check_webhook_dedup", return_value=False):
            with patch("qa_center.views_devops.threading.Thread") as thread_cls:
                thread_cls.return_value = MagicMock()
                response = client.post(f"/api/qa/devops/cicd-config/{cicd_config.id}/trigger/")

    assert response.status_code == 201
    assert response.data["runtime_mode"] == "thread_fallback"
    assert response.data["is_mock"] is True
    thread_cls.assert_called_once()


@pytest.mark.django_db
def test_tasks_test_exec_no_longer_exports_removed_batch_task():
    import qa_center.tasks_test_exec as tasks_test_exec

    assert not hasattr(tasks_test_exec, "run_batch_api_tests")


@pytest.mark.django_db
def test_execute_api_cases_via_unified_passes_devops_source_to_single_case_orchestrator(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestCaseResult, ApiAutoTestResult
    from qa_center.views_devops import _execute_api_cases_via_unified

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Success Case",
        url="/devops-success",
        method="GET",
        created_by=mock_user,
    )
    test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Success Case_devops_20260702_000000",
        status="passed",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        error_cases=0,
        executed_by=None,
    )
    case_result = ApiAutoTestCaseResult.objects.create(
        test_result=test_result,
        case=case,
        status_code=200,
        response_body='{"ok": true}',
        response_headers={"Content-Type": "application/json"},
        response_time_ms=12,
        passed=True,
        assertion_details=[{"passed": True, "source": "provider_default"}],
        failure_type="passed",
        result_metadata={"provider": "http"},
    )

    with patch("qa_center.api_execution.orchestrators.create_api_auto_single_case_orchestrator") as orchestrator_factory:
        orchestrator = orchestrator_factory.return_value
        orchestrator.execute.return_value = {
            "test_result": test_result,
            "case_result": case_result,
            "runtime_mode": "real",
        }
        results = _execute_api_cases_via_unified([case.id])

    orchestrator_factory.assert_called_once_with(
        case=case,
        user=None,
        test_result=orchestrator_factory.call_args.kwargs["test_result"],
        source="devops",
        skip_sync=False,
    )
    assert results == [
        {
            "case_id": case.id,
            "case_name": case.name,
            "passed": True,
            "status_code": 200,
            "response_time_ms": 12,
            "error_message": case_result.error_message,
            "failure_type": "passed",
        }
    ]


@pytest.mark.django_db
def test_execute_api_cases_via_unified_backfills_task_id_into_success_mirror(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestCaseResult, ApiAutoTestResult, TestResult
    from qa_center.views_devops import _execute_api_cases_via_unified

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Task Linked Success Case",
        url="/devops-task-linked-success",
        method="GET",
        created_by=mock_user,
    )
    test_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Task Linked Success Case_devops_20260702_010000",
        status="passed",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        error_cases=0,
        executed_by=None,
    )
    case_result = ApiAutoTestCaseResult.objects.create(
        test_result=test_result,
        case=case,
        status_code=200,
        response_body='{"ok": true}',
        response_headers={"Content-Type": "application/json"},
        response_time_ms=12,
        passed=True,
        assertion_details=[{"passed": True, "source": "provider_default"}],
        failure_type="passed",
        result_metadata={"provider": "http"},
    )
    mirrored = TestResult.objects.create(
        test_type="api",
        name=test_result.name,
        status="passed",
        source="devops",
        project=mock_project,
        api_auto_result=test_result,
        task_id="",
    )

    with patch("qa_center.api_execution.orchestrators.create_api_auto_single_case_orchestrator") as orchestrator_factory:
        orchestrator = orchestrator_factory.return_value
        orchestrator.execute.return_value = {
            "test_result": test_result,
            "case_result": case_result,
            "runtime_mode": "real",
        }
        _execute_api_cases_via_unified([case.id], task_id="task-123")

    mirrored.refresh_from_db()
    assert mirrored.task_id == "task-123"




@pytest.mark.django_db
def test_execute_api_cases_via_unified_creates_task_linked_mirror_when_only_foreign_duplicate_exists(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestCaseResult, ApiAutoTestResult, TestResult
    from qa_center.views_devops import _execute_api_cases_via_unified

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Foreign Only Duplicate Helper Case",
        url="/devops-foreign-only-duplicate-helper",
        method="GET",
        created_by=mock_user,
    )
    created = {}

    with patch("qa_center.api_execution.orchestrators.create_api_auto_single_case_orchestrator") as orchestrator_factory:
        orchestrator = orchestrator_factory.return_value

        def _execute():
            auto_result = orchestrator_factory.call_args.kwargs["test_result"]
            case_result = ApiAutoTestCaseResult.objects.create(
                test_result=auto_result,
                case=case,
                status_code=200,
                response_body='{"ok": true}',
                response_headers={"Content-Type": "application/json"},
                response_time_ms=12,
                passed=True,
                assertion_details=[{"passed": True, "source": "provider_default"}],
                failure_type="passed",
                result_metadata={"provider": "http"},
            )
            foreign = TestResult.objects.create(
                test_type="api",
                name=f"{auto_result.name}-foreign",
                status="passed",
                source="devops",
                project=mock_project,
                api_auto_result=auto_result,
                task_id="foreign-task",
            )
            created["foreign_id"] = foreign.id
            return {
                "test_result": auto_result,
                "case_result": case_result,
                "runtime_mode": "real",
            }

        orchestrator.execute.side_effect = _execute
        results = _execute_api_cases_via_unified([case.id], task_id="task-901")

    foreign = TestResult.objects.get(id=created["foreign_id"])
    linked = TestResult.objects.get(api_auto_result_id=foreign.api_auto_result_id, task_id="task-901")

    assert results[0]["passed"] is True
    assert linked.id != foreign.id
    assert linked.task_id == "task-901"
    assert foreign.task_id == "foreign-task"
    assert TestResult.objects.filter(api_auto_result_id=foreign.api_auto_result_id).count() == 2


@pytest.mark.django_db
def test_execute_api_cases_via_unified_prefers_unlinked_mirror_over_newer_foreign_duplicate(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestCaseResult, TestResult
    from qa_center.views_devops import _execute_api_cases_via_unified

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Duplicate Mirror Helper Case",
        url="/devops-duplicate-helper",
        method="GET",
        created_by=mock_user,
    )
    created = {}

    with patch("qa_center.api_execution.orchestrators.create_api_auto_single_case_orchestrator") as orchestrator_factory:
        orchestrator = orchestrator_factory.return_value

        def _execute():
            auto_result = orchestrator_factory.call_args.kwargs["test_result"]
            case_result = ApiAutoTestCaseResult.objects.create(
                test_result=auto_result,
                case=case,
                status_code=200,
                response_body='{"ok": true}',
                response_headers={"Content-Type": "application/json"},
                response_time_ms=12,
                passed=True,
                assertion_details=[{"passed": True, "source": "provider_default"}],
                failure_type="passed",
                result_metadata={"provider": "http"},
            )
            primary = TestResult.objects.create(
                test_type="api",
                name=auto_result.name,
                status="passed",
                source="devops",
                project=mock_project,
                api_auto_result=auto_result,
                task_id="",
            )
            duplicate = TestResult.objects.create(
                test_type="api",
                name=f"{auto_result.name}-duplicate",
                status="passed",
                source="devops",
                project=mock_project,
                api_auto_result=auto_result,
                task_id="foreign-task",
            )
            created["primary_id"] = primary.id
            created["duplicate_id"] = duplicate.id
            return {
                "test_result": auto_result,
                "case_result": case_result,
                "runtime_mode": "real",
            }

        orchestrator.execute.side_effect = _execute
        results = _execute_api_cases_via_unified([case.id], task_id="task-789")

    primary = TestResult.objects.get(id=created["primary_id"])
    duplicate = TestResult.objects.get(id=created["duplicate_id"])


@pytest.mark.django_db
def test_execute_api_cases_via_unified_backfills_task_id_into_error_mirror(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, TestResult
    from qa_center.views_devops import _execute_api_cases_via_unified

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="DevOps Task Linked Error Case",
        url="/devops-task-linked-error",
        method="GET",
        created_by=mock_user,
    )

    with patch(
        "qa_center.api_execution.orchestrators.create_api_auto_single_case_orchestrator",
        side_effect=RuntimeError("boom"),
    ):
        _execute_api_cases_via_unified([case.id], task_id="task-456")



@pytest.mark.django_db
def test_devops_task_history_includes_task_linked_single_source_results(
    mock_user,
    mock_project,
):
    from qa_center.models import TestResult, TestTask

    task = TestTask.objects.create(
        name="History Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"api_cases": [1]},
    )
    single_result = TestResult.objects.create(
        test_type="api",
        name="unrelated-single-name",
        status="passed",
        source="single",
        project=mock_project,
        task_id=str(task.id),
    )
    legacy_devops_result = TestResult.objects.create(
        test_type="api",
        name=f"{task.name} - 执行 #1",
        status="passed",
        source="devops",
        project=mock_project,
    )
    task.last_result = legacy_devops_result
    task.save(update_fields=["last_result"])

    client = APIClient()
    client.force_authenticate(user=mock_user)
    response = client.get(f"/api/qa/devops/tasks/{task.id}/history/")
    assert response.status_code == 200
    result_ids = {item["id"] for item in response.data}
    assert legacy_devops_result.id in result_ids
    assert single_result.id in result_ids


@pytest.mark.django_db
def test_devops_task_history_excludes_spoofed_same_name_devops_results(
    mock_user,
    mock_project,
):
    from qa_center.models import TestResult, TestTask

    task = TestTask.objects.create(
        name="History Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"api_cases": [1]},
    )
    linked_result = TestResult.objects.create(
        test_type="api",
        name="linked-history-result",
        status="passed",
        source="single",
        project=mock_project,
        task_id=str(task.id),
    )
    legacy_compatible_result = TestResult.objects.create(
        test_type="api",
        name=f"{task.name} - 执行 #3",
        status="passed",
        source="devops",
        project=mock_project,
    )
    spoofed_same_name_result = TestResult.objects.create(
        test_type="api",
        name=f"{task.name} - injected fake history",
        status="failed",
        source="devops",
        project=mock_project,
    )

    client = APIClient()
    client.force_authenticate(user=mock_user)
    response = client.get(f"/api/qa/devops/tasks/{task.id}/history/")
    assert response.status_code == 200
    result_ids = {item["id"] for item in response.data}
    assert linked_result.id in result_ids
    assert legacy_compatible_result.id in result_ids
    assert spoofed_same_name_result.id not in result_ids


@pytest.mark.django_db
def test_devops_task_history_excludes_stale_foreign_duplicate_last_result(
    mock_user,
    mock_project,
):
    from qa_center.models import ApiAutoTestResult, TestResult, TestTask

    task = TestTask.objects.create(
        name="History Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"api_cases": [1]},
    )
    linked_result = TestResult.objects.create(
        test_type="api",
        name="linked-history-result",
        status="passed",
        source="single",
        project=mock_project,
        task_id=str(task.id),
    )
    auto_result = ApiAutoTestResult.objects.create(
        project=mock_project,
        name="foreign-history-auto-result",
        status="passed",
        total_cases=1,
        executed_by=mock_user,
    )
    foreign_duplicate = TestResult.objects.create(
        test_type="api",
        name="foreign-history-duplicate",
        status="passed",
        source="devops",
        project=mock_project,
        task_id="foreign-task",
        api_auto_result=auto_result,
    )
    task.last_result = foreign_duplicate
    task.save(update_fields=["last_result"])

    client = APIClient()
    client.force_authenticate(user=mock_user)
    response = client.get(f"/api/qa/devops/tasks/{task.id}/history/")
    assert response.status_code == 200
    result_ids = {item["id"] for item in response.data}
    assert linked_result.id in result_ids
    assert foreign_duplicate.id not in result_ids


@pytest.mark.django_db
def test_thread_fallback_execution_updates_task_last_result_to_real_mirror(
    mock_user,
    mock_project,
    mock_suite,
):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestCaseResult, ApiAutoTestResult, TestResult, TestTask
    from qa_center.views_devops import TestTaskExecuteView

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="Thread Fallback Linked Case",
        url="/thread-fallback-linked",
        method="GET",
        created_by=mock_user,
    )
    task = TestTask.objects.create(
        name="Thread Fallback Linked Task",
        test_type="api",
        project=mock_project,
        created_by=mock_user,
        test_config={"api_cases": [case.id]},
        status="running",
    )
    placeholder = TestResult.objects.create(
        test_type="api",
        name="Thread Fallback Placeholder",
        status="running",
        source="devops",
        project=mock_project,
        started_at=timezone.now(),
        task_id=str(task.id),
    )
    auto_result = ApiAutoTestResult.objects.create(
        suite=mock_suite,
        project=mock_project,
        name="Thread Fallback Linked Case_devops_20260702_020000",
        status="passed",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        error_cases=0,
        executed_by=None,
    )
    case_result = ApiAutoTestCaseResult.objects.create(
        test_result=auto_result,
        case=case,
        status_code=200,
        response_body='{"ok": true}',
        response_headers={"Content-Type": "application/json"},
        response_time_ms=9,
        passed=True,
        assertion_details=[{"passed": True, "source": "provider_default"}],
        failure_type="passed",
        result_metadata={"provider": "http"},
    )

    with patch("qa_center.api_execution.orchestrators.create_api_auto_single_case_orchestrator") as orchestrator_factory:
        orchestrator = orchestrator_factory.return_value
        orchestrator.execute.return_value = {
            "test_result": auto_result,
            "case_result": case_result,
            "runtime_mode": "real",
        }
        TestTaskExecuteView()._execute_test_task(task, placeholder)

    task.refresh_from_db()
    # last_result 应指向本次执行创建的父级镜像（而非占位符或历史镜像）
    assert task.last_result_id is not None
    assert task.last_result_id != placeholder.id
    last = TestResult.objects.get(id=task.last_result_id)
    assert last.api_auto_result_id is not None
    assert last.api_auto_result.name == f"{task.name} - 执行 #0"
