# QA Test Center Production Upgrade - Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Upgrade QA test center from feature-complete to production-reliable.

**Architecture:** Progressive hardening Route A. 16 Tasks: P0 fixes 8 blockers, P1 establishes quality baseline.

**Tech Stack:** Django 5.x + DRF + Celery + Redis + Playwright + Locust + Jenkins/GitLab API + Vue 3 + Vitest

---

## Phase 0: Preparation

### Task 0: Environment Setup

Files: Modify backend/requirements.txt, backend/settings.py; Create backend/celery_app.py

- [ ] Add celery[redis] and django-fernet-fields to requirements.txt
- [ ] pip install new deps
- [ ] Add Celery config to settings.py (BROKER_URL, ACKS_LATE, REJECT_ON_WORKER_LOST, PREFETCH_MULTIPLIER=1, visibility_timeout=7200)
- [ ] Add feature flags: USE_CELERY_TASKS, USE_REAL_CI, USE_SEMAPHORE, PERF_MAX_CONCURRENT
- [ ] Create backend/celery_app.py with Celery app instance
- [ ] Verify: celery -A celery_app inspect ping
- [ ] Commit: chore: add Celery dependency and base configuration

---

## Phase 1: P0 Core Hardening

### Task 1: P0-1 - conftest + fixtures
Create: backend/qa_center/tests/__init__.py, backend/qa_center/tests/conftest.py
- [ ] Create mock_user, mock_project, mock_environment, mock_suite, mock_global_var, mock_case fixtures
- [ ] Verify: pytest backend/qa_center/tests/conftest.py --collect-only
- [ ] Commit

### Task 2: P0-1 - test_template_engine.py
Create: backend/qa_center/tests/test_template_engine.py
- [ ] TestBuildVariablePool: overrides>env>global priority, base_url, empty all (5 tests)
- [ ] TestRender: substitution, missing preserved, int/bool types, whitespace, nested dict/list, multiple placeholders (8 tests)
- [ ] Run: pytest backend/qa_center/tests/test_template_engine.py -v (13 passed)
- [ ] Commit

### Task 3: P0-1 - test_unified_assertions.py
Create: backend/qa_center/tests/test_unified_assertions.py
- [ ] TestStatusCodeAssertions: eq_pass, eq_fail, ne_pass (3 tests)
- [ ] TestJSONPathAssertions: eq, ne, gt, lt, nested, contains, exists, null, empty, multiple (12 tests)
- [ ] TestHeaderAssertions: header_exists (1 test)
- [ ] Run: 16 passed. Commit

### Task 4: P0-1 - test_extractors.py
Create: backend/qa_center/tests/test_extractors.py
- [ ] TestJsonPathExtract: single, nested, array, not_found, invalid_json (5 tests)
- [ ] TestChainedExtraction: two-step chain (1 test)
- [ ] Run: 6 passed. Commit

### Task 5: P0-1 - test_api_auto_executor.py
Create: backend/qa_center/tests/test_api_auto_executor.py
- [ ] TestAssertionExecutorBasic: all_passed, partial_fail, non_json, header_case_insensitive (4 tests, using MagicMock)
- [ ] TestTemplateIntegration: variable_substitution_before_request (1 test)
- [ ] Run: 5 passed. Commit

### Task 6: P0-1 - test_run_plan_executor.py + test_locust_runner.py
Create both test files
- [ ] test_run_plan_executor: _get_or_create_plan_suite (create+reuse), executor init, broadcast mock (5 tests)
- [ ] test_locust_runner: init, port_offset, start (patch Popen), stop (4 tests)
- [ ] Full run: pytest backend/qa_center/tests/ -v --cov=qa_center --cov-report=term
- [ ] Expected: all pass, coverage > 60%, core path > 80%. Commit

### Task 7: P0-2 - Celery Task Migration
Create: backend/qa_center/tasks_test_exec.py; Modify: views_api_test.py, views_devops.py
- [ ] Create 3 Celery tasks in tasks_test_exec.py:
    run_batch_api_tests (qa_long, 1800s): idempotent check + state machine + batch execution
    execute_test_task (qa_long, 1800s): idempotent check + TestTask execution
    poll_pipeline_status (qa_pipeline, 120s): single poll + countdown self-reschedule (30->60->120...), fail_count>=5 mark failed
    Each generates trace_id, bind=True, max_retries with exponential backoff
- [ ] views_api_test.py: add USE_CELERY_TASKS feature flag for batch execution
- [ ] views_devops.py: add USE_REAL_CI feature flag in PipelineRunTriggerView
- [ ] Verify: celery -A celery_app inspect registered lists all 3 tasks
- [ ] Commit

### Task 8: P0-3 - Pipeline Real CI Integration
Create: backend/qa_center/pipeline/__init__.py, jenkins.py, gitlab.py, state_mapping.py; Modify: models.py
- [ ] pipeline/__init__.py: CiClient ABC + CiTriggerResult/CiRunStatus/CiJobResult dataclasses + get_client() factory
- [ ] state_mapping.py: Jenkins 6 states (QUEUED->queued), GitLab 9 states, TERMINAL_STATUSES
- [ ] jenkins.py: trigger (POST + queue polling), get_status, get_jobs, get_logs (max 64KB), cancel, verify_webhook
- [ ] gitlab.py: trigger (POST pipeline), get_status, get_jobs, get_logs (max 64KB), cancel, verify_webhook
- [ ] models.py: CiCdConfig add ci_type/ci_url/ci_token/ci_project/ci_job_name/verify_ssl; PipelineRun add ci fields + unique (ci_config_id, external_run_id)
- [ ] makemigrations && migrate. Commit

### Task 9: P0-4 - Webhook Security + PipelineWebhookEvent
Modify: models.py (add PipelineWebhookEvent), views_devops.py (harden webhook)
- [ ] PipelineWebhookEvent model: ci_type, delivery_id, payload_hash, raw_payload (256KB max), process_status, indexes
- [ ] makemigrations && migrate
- [ ] Harden PipelineRunWebhookView: write event -> idempotency check -> secret verify -> state machine -> update
- [ ] Commit

### Task 10: P0-5 - Performance Concurrency Control
Create: semaphore_lua/*.lua, semaphore.py, tasks_watchdog.py; Modify: views_performance.py, locust_runner.py
- [ ] 3 Lua scripts: acquire (tonumber + ZREMRANGEBYSCORE + ZCARD + ZADD), release (ZREM), heartbeat (ZSCORE + ZADD)
- [ ] semaphore.py: acquire/release/heartbeat/get_running_count using redis.register_script
- [ ] tasks_watchdog.py: watchdog_check_performance scans heartbeat timeout -> timeout + release_slot
- [ ] views_performance.py: USE_SEMAPHORE -> acquire_slot, fail returns 429
- [ ] locust_runner.py: add port_offset, web_port = 8089 + offset
- [ ] Commit

### Task 11: P0-6 - Security Hardening (SSRF + Token + Audit)
Create: backend/qa_center/ssrf.py; Modify: views_api_test.py, serializers.py
- [ ] ssrf.py: validate_target_url (scheme whitelist -> @ bypass -> normalize -> blocklist -> allowlist -> DNS resolve -> IP classify 11 networks -> metadata IPs)
- [ ] SSRFProtectedSession: no auto-redirect, manual redirect re-validation
- [ ] views_api_test.py: call validate_target_url before API test execution
- [ ] serializers.py: CiCdConfigSerializer.ci_token returns masked value
- [ ] Commit

### Task 12: P0-7 - Observability
Create: backend/qa_center/metrics.py; Modify: tasks_test_exec.py
- [ ] metrics.py: task_tracker context manager (started/finished/failed + duration_ms), log_execution (trace_id + execution_id)
- [ ] tasks_test_exec.py: generate trace_id at entry, wrap with task_tracker
- [ ] Commit

### Task 13: P0-8 - Data Migration + Rollback
Create: backend/qa_center/management/commands/migrate_qa_data.py
- [ ] migrate_qa_data.py: _migrate_pipeline_status (map old statuses), _mark_mock_data (external_run_id IS NULL -> is_mock=True)
- [ ] Ensure all migrations use RunPython with if-not-exists checks
- [ ] Commit

---

## Phase 2: P1 Quality Baseline

### Task 14: P1-1 - E2E Tests (6 new scenarios)
Create: e2e/conftest.py + 6 test files
- [ ] conftest.py: browser (session scope, headless), logged_in_page (login admin/admin123)
- [ ] test_api_test_flow.py: create API case -> execute -> view result -> assertions
- [ ] test_api_batch_flow.py: create plan -> add cases -> batch execute -> progress
- [ ] test_ui_test_flow.py: record steps -> save -> replay -> screenshots
- [ ] test_performance_flow.py: create case -> execute -> metrics -> report
- [ ] test_devops_flow.py: Pipeline -> status -> quality report
- [ ] test_bug_flow.py: failure -> create Bug -> status transitions
- [ ] Run: pytest e2e/ -v (all pass). Commit

### Task 15: P1-2/P1-3/P1-4/P1-5 - Frontend Tests + Rate Limiting + De-mock + Attribution
Create: 5 frontend __tests__ files, backend/qa_center/throttling.py; Modify: views_devops.py
- [ ] 5 frontend tests: ApiCaseRunDetail, DevOpsPlatform, TestResultDetail, TestRunList, PerformanceTestResult
    Using Vitest + Vue Test Utils + vi.mock()
- [ ] Run: npx vitest run (all pass)
- [ ] throttling.py: 4 throttle classes (10/min, 5/min, 3/min, 2/min). Add to Views.
- [ ] views_devops.py: _calc_deploy_score uses PipelineRun(is_mock=False). total==0 returns None.
- [ ] Commit

---

## Final Verification

### Task 16: Full Test Suite + Acceptance
- [ ] Backend: pytest backend/ -v --cov=qa_center --cov-report=term (all pass, coverage > 60%)
- [ ] Frontend: npx vitest run (all pass)
- [ ] E2E: pytest e2e/ -v (all pass)
- [ ] Migration: python manage.py makemigrations --check --dry-run (no changes)
- [ ] Celery: celery -A celery_app inspect registered (lists all tasks)
- [ ] SSRF manual: validate_target_url(127.0.0.1) raises; validate_target_url(https://httpbin.org) passes
- [ ] Commit: chore(qa): finalize production upgrade

---

## Acceptance Checklist

### P0 (21 items)
- [ ] 1. pytest pass, qa_center coverage > 60%, core path > 80%
- [ ] 2. Django restart: tasks not lost
- [ ] 3. Worker kill: tasks not stuck running
- [ ] 4. Same batch_id: no duplicate execution
- [ ] 5. Jenkins/GitLab: real trigger works
- [ ] 6. Webhook duplicate push: not double-counted
- [ ] 7. CI token: not in response/logs/stacktraces
- [ ] 8. 3 concurrent perf tests: ports/processes/WS isolated
- [ ] 9. Over concurrency limit: clear error returned
- [ ] 10. Locust crash: auto-marked failed
- [ ] 11. No PipelineRun data: deploy score shows No Data
- [ ] 12. SSRF: 127.0.0.1 and internal DNS blocked
- [ ] 13. Illegal webhook: 401 + security log
- [ ] 14. CI coverage drop > 2%: CI fails
- [ ] 15. Migration: repeatable + rollback exercised
- [ ] 16. Pipeline polling: no long worker occupation
- [ ] 17. response_snapshot > 128KB: truncated
- [ ] 18. Redirect to internal: blocked
- [ ] 19. DNS rebinding: blocked
- [ ] 20. BatchExecution: status matches child TestExecutions
- [ ] 21. Old threading path: deletion plan exists

### P1 (5 items)
- [ ] 22. E2E: 10+ scenarios pass
- [ ] 23. Frontend tests: all pass
- [ ] 24. Rate limiting: returns 429
- [ ] 25. Deploy success rate: from real data
- [ ] 26. Failure attribution: classified by type

### Fault Drills (11 items)
- [ ] Django restart -> tasks continue
- [ ] Worker kill -9 -> re-enqueue, idempotent
- [ ] Redis brief disconnect -> auto reconnect
- [ ] CI unreachable -> failed + error_message
- [ ] Locust kill -9 -> timeout + release_slot
- [ ] Webhook 3x duplicate -> marked duplicate
- [ ] SSRF metadata -> blocked
- [ ] DNS rebinding -> blocked
- [ ] Redirect to internal -> blocked
- [ ] Celery timeout -> timeout status -> retryable
- [ ] Semaphore crash -> Lua auto-cleanup
