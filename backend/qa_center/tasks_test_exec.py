"""Test execution Celery tasks: TestTask execution, Pipeline polling.

Replaces the old threading.Thread approach with Celery for reliability:
- Idempotent via execution_id unique keys
- State machine enforcement (pending->queued->running->terminal)
- Per-task time limits and separate queues
- trace_id for full-chain observability via task_tracker
"""
from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .api_execution.orchestrators import create_api_auto_single_case_orchestrator
from .feature_flags import use_unified_runner_for_async_triggers
from .metrics import task_tracker, generate_trace_id, log_execution

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TestTask Execution
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=1800,
    soft_time_limit=1500,
    queue="qa_long",
    name="qa_center.execute_test_task",
)
def execute_test_task(self, task_id: int) -> dict:
    """Execute a scheduled TestTask.

    Idempotent: checks TestTask status before executing.
    """
    from .models import TestTask

    trace_id = generate_trace_id()

    with task_tracker("execute_test_task", str(task_id), trace_id=trace_id):
        try:
            test_task = TestTask.objects.select_for_update().get(id=task_id)
        except TestTask.DoesNotExist:
            return {"status": "error", "reason": "not_found"}

        if not test_task.is_active:
            return {"status": "skipped", "reason": "task_inactive"}

        if test_task.status in ("completed", "failed"):
            return {"status": "skipped", "reason": f"already_{test_task.status}"}

        already_running = test_task.status == "running"

        test_task.status = "running"
        test_task.save(update_fields=["status"])

        try:
            config = test_task.test_config or {}
            case_ids = config.get("case_ids", []) or config.get("api_cases", [])

            latest_result = None
            if case_ids:
                from .models import ApiAutoTestCase, ApiAutoTestResult, TestResult

                cases = ApiAutoTestCase.objects.filter(
                    id__in=case_ids, is_active=True,
                    project_id=test_task.project_id,
                )
                for case in cases:
                    if test_task.test_type == "api" and use_unified_runner_for_async_triggers():
                        auto_result = ApiAutoTestResult.objects.create(
                            suite=case.suite,
                            project=case.project or (case.suite.project if case.suite_id else None),
                            name=f"{case.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
                            status="running",
                            total_cases=1,
                            executed_by=test_task.created_by,
                            started_at=timezone.now(),
                        )
                        orchestrator = create_api_auto_single_case_orchestrator(
                            case=case,
                            user=test_task.created_by,
                            test_result=auto_result,
                            source="devops",
                        )
                        outcome = orchestrator.execute()
                        latest_result = outcome.get("test_result") if isinstance(outcome, dict) else auto_result
                    else:
                        from .api_auto_executor import ApiAutoTestExecutor

                        executor = ApiAutoTestExecutor(
                            suite_id=case.suite_id, user=test_task.created_by
                        )
                        latest_result = executor.execute_single_case(case).test_result

            last_result = None
            if latest_result is not None:
                from .result_sink import mirror_to_test_result, _select_preferred_mirror

                task_result_id = str(test_task.id)
                last_result = _select_preferred_mirror(
                    auto_result=latest_result,
                    task_id=task_result_id,
                )
                if last_result is None:
                    last_result = mirror_to_test_result(
                        auto_result=latest_result,
                        source="devops",
                        task_id=task_result_id,
                    )
                elif last_result.task_id != task_result_id:
                    last_result.task_id = task_result_id
                    last_result.save(update_fields=["task_id"])

            test_task.status = "completed"
            if not already_running:
                test_task.execution_count += 1
            test_task.last_executed = timezone.now()
            test_task.last_result = last_result
            test_task.save(update_fields=["status", "execution_count", "last_executed", "last_result"])
            return {"status": "success", "task_id": task_id, "trace_id": trace_id}

        except Exception as exc:
            test_task.status = "failed"
            test_task.save(update_fields=["status"])
            log_execution("test_task_failed", trace_id, str(task_id), level="error")
            raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Pipeline Status Polling (short-poll with self-reschedule)
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    max_retries=10,
    default_retry_delay=30,
    time_limit=120,
    soft_time_limit=90,
    queue="qa_pipeline",
    name="qa_center.poll_pipeline_status",
)
def poll_pipeline_status(self, pipeline_run_id: int, fail_count: int = 0,
                          trace_id: str = "") -> dict:
    """Poll CI pipeline status once, then reschedule if not terminal.

    Does NOT occupy a worker long-term. Each invocation:
    1. Queries CI once
    2. Updates PipelineRun
    3. If not terminal: reschedules with countdown backoff
    4. If terminal: writes result and finishes
    """
    from .models import PipelineRun
    from .pipeline import get_client

    trace_id = trace_id or generate_trace_id()

    with task_tracker("poll_pipeline_status", str(pipeline_run_id), trace_id=trace_id):
        try:
            run = PipelineRun.objects.select_related("cicd_config").get(id=pipeline_run_id)
        except PipelineRun.DoesNotExist:
            return {"status": "error", "reason": "not_found"}

        # Guard: if cicd_config was deleted or is unavailable, fail cleanly
        if run.cicd_config is None or not run.cicd_config.is_active:
            run.status = "failed"
            run.error_message = "CI/CD configuration has been deleted or is inactive"
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error_message", "completed_at"])
            log_execution(
                "pipeline_config_missing", trace_id, str(pipeline_run_id), level="error",
            )
            return {"status": "failed", "reason": "cicd_config_unavailable"}

        if run.status in ("passed", "failed", "cancelled", "skipped"):
            return {"status": "skipped", "reason": f"already_{run.status}"}

        try:
            client = get_client(run.cicd_config)
            ci_status = client.get_status(run.external_run_id)
            run.status = ci_status.status
            run.save(update_fields=["status"])

            if ci_status.status in ("passed", "failed", "cancelled"):
                jobs = client.get_jobs(run.external_run_id)
                passed = sum(1 for j in jobs if j.status == "success")
                failed = sum(1 for j in jobs if j.status == "failed")
                run.test_results_summary = {
                    "passed": passed,
                    "failed": failed,
                    "skipped": 0,
                    "total": len(jobs),
                }
                run.completed_at = timezone.now()
                run.save(update_fields=["test_results_summary", "completed_at"])
                log_execution(
                    "pipeline_completed", trace_id, str(pipeline_run_id),
                    result=run.test_results_summary,
                )
                return {"status": "completed", "pipeline_status": ci_status.status}
            else:
                countdown = min(30 * (2 ** fail_count), 300)
                poll_pipeline_status.apply_async(
                    args=[pipeline_run_id, fail_count + 1],
                    countdown=countdown,
                    queue="qa_pipeline",
                )
                return {"status": "polling", "next_countdown": countdown}

        except Exception as exc:
            if fail_count >= 5:
                run.status = "failed"
                run.error_message = str(exc)[:500]
                run.completed_at = timezone.now()
                run.save(update_fields=["status", "error_message", "completed_at"])
                log_execution(
                    "pipeline_polling_exhausted", trace_id, str(pipeline_run_id),
                    fail_count=fail_count, level="error",
                )
                return {"status": "failed", "reason": "max_retries_exceeded"}
            countdown = min(30 * (2 ** fail_count), 300)
            raise self.retry(exc=exc, countdown=countdown)
