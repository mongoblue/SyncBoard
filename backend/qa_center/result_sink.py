"""Result Sink：API 自动化执行结果镜像到 TestResult。

P1.5 架构约束：所有 API 自动化执行路径（单条/suite/run_plan）在 ApiAutoTestResult
落库后，必须调用 `mirror_to_test_result` 同步创建/更新一条 TestResult。测试结果中心
只查 TestResult，保证"执行一次 → 测试结果中心一定能看到"。

TestResult.api_auto_result 是 1:1 指针（一个 ApiAutoTestResult 对应一条镜像
TestResult）。镜像不重复写明细——明细查 ApiAutoTestCaseResult，详情页跳 AutoResultDetail。
"""
from __future__ import annotations

from typing import Optional

from django.db.models.functions import Coalesce
from django.utils import timezone

from qa_center.models import ApiAutoTestResult, TestResult, TestRun, TestRunCaseResult


def _select_preferred_mirror(
    *,
    auto_result: ApiAutoTestResult,
    task_id: str = "",
    exclude_id: Optional[int] = None,
) -> TestResult | None:
    mirrors = TestResult.objects.filter(api_auto_result=auto_result).defer(
        "lifecycle_state",
        "lifecycle_reason",
    )
    if exclude_id is not None:
        mirrors = mirrors.exclude(id=exclude_id)
    ordering = (
        Coalesce("started_at", "created_at").desc(),
        "-created_at",
        "-id",
    )
    if task_id:
        preferred = mirrors.filter(task_id=task_id).order_by(*ordering).first()
        if preferred is not None:
            return preferred
        preferred = mirrors.filter(task_id="").order_by(*ordering).first()
        if preferred is not None:
            return preferred
        return None
    preferred = mirrors.filter(task_id="").order_by(*ordering).first()
    if preferred is not None:
        return preferred
    return None


def open_unified_run(*, auto_result: ApiAutoTestResult, source: str = "single") -> TestRun:
    project = auto_result.project or (auto_result.suite.project if auto_result.suite_id else None)
    total_count = auto_result.total_cases or 0
    passed_count = auto_result.passed_cases or 0
    failed_count = auto_result.failed_cases or 0
    error_count = auto_result.error_cases or 0
    completed = passed_count + failed_count + error_count
    pass_rate = round((passed_count / completed) * 100, 2) if completed else 0
    defaults = {
        "trigger": "manual",
        "test_type": "api",
        "status": auto_result.status if auto_result.status in {"pending", "running", "passed", "failed", "error", "cancelled"} else "running",
        "total_count": total_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "error_count": error_count,
        "pass_rate": pass_rate,
        "duration_ms": auto_result.duration_ms,
        "triggered_by": auto_result.executed_by,
        "started_at": auto_result.started_at,
        "completed_at": auto_result.completed_at,
        "summary": {
            "source": source,
            "auto_result_id": auto_result.id,
        },
    }
    run, _ = TestRun.objects.update_or_create(
        project=project,
        name=auto_result.name,
        started_at=auto_result.started_at,
        defaults=defaults,
    )
    return run


def record_api_case_result(*, run: TestRun, case_result, sequence: int = 1) -> TestRunCaseResult:
    return TestRunCaseResult.objects.update_or_create(
        test_run=run,
        sequence=sequence,
        defaults={
            "case_type": "api",
            "api_auto_case": case_result.case,
            "status": "passed" if case_result.passed else ("failed" if case_result.failure_type == "assertion_failed" else "error"),
            "duration_ms": case_result.response_time_ms,
            "status_code": case_result.status_code,
            "response_body": case_result.response_body,
            "response_headers": case_result.response_headers,
            "assertion_results": case_result.assertion_details,
            "request_snapshot": case_result.request_snapshot,
            "curl": case_result.curl.get("preview", "") if isinstance(case_result.curl, dict) else (case_result.curl or ""),
            "error_message": case_result.error_message,
            "trace_id": case_result.trace_id,
            "raw_status": case_result.raw_status,
            "error_code": case_result.error_code,
            "response_snapshot": case_result.response_snapshot,
            "extracted_variables_preview": case_result.extracted_variables_preview,
            "result_metadata": case_result.result_metadata,
            "legacy_api_result_id": case_result.test_result_id,
            "started_at": run.started_at,
            "completed_at": run.completed_at or timezone.now(),
        },
    )[0]


def _sync_all_api_case_results(*, run: TestRun, auto_result: ApiAutoTestResult) -> None:
    for sequence, stored_case_result in enumerate(
        auto_result.case_results.order_by("executed_at", "id"),
        start=1,
    ):
        record_api_case_result(
            run=run,
            case_result=stored_case_result,
            sequence=sequence,
        )


def sync_unified_run_from_auto_result(*, auto_result: ApiAutoTestResult, case_result=None, source: str = "single") -> TestRun:
    run = open_unified_run(auto_result=auto_result, source=source)
    run.status = auto_result.status if auto_result.status in {"pending", "running", "passed", "failed", "error", "cancelled"} else run.status
    run.total_count = auto_result.total_cases or run.total_count
    run.passed_count = auto_result.passed_cases or 0
    run.failed_count = auto_result.failed_cases or 0
    run.error_count = auto_result.error_cases or 0
    run.duration_ms = auto_result.duration_ms
    run.completed_at = auto_result.completed_at
    run.summary = {
        **(run.summary or {}),
        "source": source,
        "auto_result_id": auto_result.id,
    }
    run.recompute_pass_rate()
    run.save()
    if case_result is not None:
        record_api_case_result(run=run, case_result=case_result)
    else:
        _sync_all_api_case_results(run=run, auto_result=auto_result)
    return run


def sync_performance_run_from_test_result(*, test_result: TestResult, performance_result=None) -> TestRun:
    final_status = test_result.status if test_result.status in {"pending", "running", "passed", "failed", "error", "cancelled"} else "running"
    total_count = 1
    passed_count = 1 if final_status == "passed" else 0
    failed_count = 1 if final_status == "failed" else 0
    error_count = 1 if final_status in {"error", "cancelled"} else 0
    completed = passed_count + failed_count + error_count
    run, _ = TestRun.objects.update_or_create(
        project=test_result.project,
        name=test_result.name,
        started_at=test_result.started_at,
        defaults={
            "trigger": "manual",
            "test_type": "performance",
            "status": final_status,
            "total_count": total_count,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "pass_rate": round((passed_count / completed) * 100, 2) if completed else 0,
            "duration_ms": test_result.duration_ms,
            "triggered_by": test_result.executed_by,
            "started_at": test_result.started_at,
            "completed_at": test_result.completed_at,
            "summary": {
                "source": test_result.source,
                "test_result_id": test_result.id,
                "performance_test_case_id": performance_result.test_case_id if performance_result is not None else test_result.test_params.get("test_case_id"),
            },
        },
    )
    metadata = {
        "provider": "performance",
        "performance_test_case_id": performance_result.test_case_id if performance_result is not None else test_result.test_params.get("test_case_id"),
        "total_requests": performance_result.total_requests if performance_result is not None else 0,
        "successful_requests": performance_result.successful_requests if performance_result is not None else 0,
        "failed_requests": performance_result.failed_requests if performance_result is not None else 0,
        "avg_response_time_ms": performance_result.avg_response_time_ms if performance_result is not None else test_result.response_time_ms,
        "throughput": performance_result.throughput if performance_result is not None else test_result.throughput,
        "error_rate": performance_result.error_rate if performance_result is not None else test_result.error_rate,
        "aborted": test_result.aborted,
    }
    TestRunCaseResult.objects.update_or_create(
        test_run=run,
        sequence=1,
        defaults={
            "case_type": "performance",
            "status": "passed" if final_status == "passed" else ("failed" if final_status == "failed" else "error"),
            "duration_ms": test_result.duration_ms,
            "response_body": test_result.actual_result or "",
            "response_headers": {},
            "assertion_results": performance_result.assertion_results if performance_result is not None else [],
            "request_snapshot": test_result.test_params or {},
            "curl": "",
            "error_message": test_result.error_message or "",
            "trace_id": "",
            "raw_status": final_status,
            "error_code": test_result.error_code or "",
            "response_snapshot": {
                "summary": test_result.test_log,
            },
            "extracted_variables_preview": {},
            "result_metadata": metadata,
            "legacy_test_result_id": test_result.id,
            "started_at": test_result.started_at,
            "completed_at": test_result.completed_at or timezone.now(),
        },
    )
    return run


def sync_ui_run_from_test_result(*, test_result: TestResult) -> TestRun:
    final_status = test_result.status if test_result.status in {"pending", "running", "passed", "failed", "error", "cancelled"} else "running"
    passed_count = 1 if final_status == "passed" else 0
    failed_count = 1 if final_status == "failed" else 0
    error_count = 1 if final_status in {"error", "cancelled"} else 0
    completed = passed_count + failed_count + error_count
    run, _ = TestRun.objects.update_or_create(
        project=test_result.project,
        name=test_result.name,
        started_at=test_result.started_at,
        defaults={
            "trigger": "manual",
            "test_type": "ui",
            "status": final_status,
            "total_count": 1,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "pass_rate": round((passed_count / completed) * 100, 2) if completed else 0,
            "duration_ms": test_result.duration_ms,
            "triggered_by": test_result.executed_by,
            "started_at": test_result.started_at,
            "completed_at": test_result.completed_at,
            "summary": {
                "source": test_result.source,
                "test_result_id": test_result.id,
                "ui_test_case_id": test_result.ui_test_case_id,
            },
        },
    )
    TestRunCaseResult.objects.update_or_create(
        test_run=run,
        sequence=1,
        defaults={
            "case_type": "ui",
            "ui_test_case_id": test_result.ui_test_case_id,
            "status": "passed" if final_status == "passed" else ("failed" if final_status == "failed" else "error"),
            "duration_ms": test_result.duration_ms,
            "response_body": test_result.actual_result or "",
            "response_headers": {},
            "assertion_results": [],
            "request_snapshot": {
                "steps": test_result.test_steps or [],
            },
            "curl": "",
            "error_message": test_result.error_message or "",
            "trace_id": "",
            "raw_status": final_status,
            "error_code": test_result.error_code or "",
            "response_snapshot": {
                "test_log": test_result.test_log or "",
            },
            "extracted_variables_preview": {},
            "result_metadata": {
                "provider": "ui",
                "ui_test_case_id": test_result.ui_test_case_id,
                "aborted": test_result.aborted,
            },
            "legacy_test_result_id": test_result.id,
            "started_at": test_result.started_at,
            "completed_at": test_result.completed_at or timezone.now(),
        },
    )
    return run


def mirror_to_test_result(*, auto_result: ApiAutoTestResult, source: str = "single", task_id: str = "") -> TestResult:
    """把 ApiAutoTestResult 镜像到 TestResult。

    幂等：同一 auto_result 重复调用只更新不重复创建（按 api_auto_result FK 查找）。

    Args:
        auto_result: 已落库的 ApiAutoTestResult（必须已 save）
        source: 'single' 单条用例执行 / 'devops' 批次/plan 执行
        task_id: 可选的上游任务 ID；用于把 DevOps 任务历史与真实结果稳定关联

    Returns:
        镜像后的 TestResult 实例
    """
    project = auto_result.project or (auto_result.suite.project if auto_result.suite_id else None)
    defaults = {
        "test_type": "api",
        "name": auto_result.name,
        "status": auto_result.status,
        "started_at": auto_result.started_at,
        "completed_at": auto_result.completed_at,
        "duration_ms": auto_result.duration_ms or 0,
        "executed_by": auto_result.executed_by,
        "project": project,
        "source": source,
        "error_message": auto_result.error_message,
        "task_id": task_id or "",
    }
    preferred = _select_preferred_mirror(auto_result=auto_result, task_id=task_id)
    if preferred is not None:
        for field, value in defaults.items():
            setattr(preferred, field, value)
        preferred.api_auto_result = auto_result
        preferred.save()
        return preferred
    return TestResult.objects.create(
        api_auto_result=auto_result,
        **defaults,
    )


def finalize_mirrored_test_result(*, auto_result: ApiAutoTestResult) -> TestResult | None:
    """ApiAutoTestResult 完成时同步更新镜像 TestResult 的终态字段。

    在 auto_result.save() 之后调用。若无镜像（旧数据），返回 None。
    """
    tr = _select_preferred_mirror(auto_result=auto_result)
    if tr is None:
        return None
    tr.status = auto_result.status
    tr.completed_at = auto_result.completed_at
    tr.duration_ms = auto_result.duration_ms or 0
    tr.error_message = auto_result.error_message
    tr.save()
    return tr
