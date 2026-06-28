# QA Center Verification Closure Design

## Goal

Close the current DevOps/QA verification loop by making the existing verified paths pass with evidence. This phase is not new feature development; it is a narrow stabilization pass for the already-wired QA center paths.

## Scope

This phase covers only the verification blockers listed in the current closure work:

1. API single-run response extraction verification.
2. Performance test result persistence and failure-threshold verification.
3. Four E2E smoke flows: login, create task, drag task to Done, and search.
4. Minimal regression coverage required to keep those paths from breaking again.

Out of scope:

- Real Jenkins/GitLab/GitHub Actions pipeline triggering.
- Report export implementation.
- New QA editor features or broad UI redesign.
- Business scenario performance testing.
- Large test infrastructure rewrites.

## Success Criteria

The phase is complete when:

- `test_single_run_extracts_response_variables` passes and verifies extracted variable `name`, `value`, and `success`.
- `tests/test_api_case_run.py` passes.
- `qa_center/tests/test_performance_persistence.py` passes.
- The four E2E smoke tests pass when required backend/frontend services are available.
- Any E2E environment blocker is documented with the exact missing prerequisite and command evidence.
- A QA-related backend regression subset covering API case run, performance persistence, run plan extraction, and request features passes.
- No feature-scope changes are introduced beyond what is required to make the existing verified paths work.

## Design

### 1. API Single-Run Extractor Path

The API case run endpoint executes the configured request, parses the response body, evaluates assertions, runs response extractors, and returns enough evidence for the frontend and tests to inspect extracted variables.

The boundary shape for each extraction item is:

```python
{
    'name': '<variable name>',
    'value': <extracted value>,
    'success': <boolean>
}
```

A value is successful when extraction found a value, including valid falsy values such as `''`, `0`, or `False`. Only a missing value should be treated as unsuccessful unless the existing extractor contract uses a richer error marker.

Implementation should prefer the narrowest change in the existing extractor summary or API run response assembly. Existing legacy result writes should remain intact unless the failing test proves they are inconsistent with the consumed result shape.

### 2. Performance Persistence Path

The performance task starts from the existing `run_performance_test` task. Tests should mock the Locust runner rather than depend on a real Locust subprocess.

The task maps final runner metrics into:

- `TestResult` status and summary fields.
- A queryable `PerformanceTestResult` record with aggregate metrics and time-series fields.

Failure-threshold behavior is based on the configured expected error rate. When the final error rate exceeds the threshold, the persisted status must be failed. The persistence step should be deterministic for tests and should not depend on transient websocket delivery.

This phase does not add performance scenarios, new Locust generation behavior, or real distributed load testing.

### 3. E2E Smoke Path

The E2E smoke tests verify user-visible behavior through the real frontend and backend:

- Login succeeds.
- Creating a task succeeds.
- Dragging a task to Done succeeds.
- Searching succeeds.

For each failure, first classify the cause as one of:

- Missing environment or service startup.
- Missing or stale fixture data.
- Stale selector.
- Timing/waiting issue.
- Product behavior bug.

Fix only the narrowest cause. Prefer stable user-facing selectors and explicit visible-state waits over arbitrary sleeps. If the local environment cannot run the smoke tests, record the missing prerequisite and the command/output that proves the blocker.

## Error Handling Rules

- Reproduce each failure before modifying code.
- Do not skip tests, add `xfail`, or weaken assertions to pass.
- Treat environment blockers separately from product bugs.
- Keep compatibility changes at API/frontend-consumed boundaries, not as broad internal shims.
- Preserve existing behavior unless the failing verification demonstrates it is wrong.

## Verification Commands

Run targeted tests first, then broader subsets:

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
cd backend && python -m pytest tests/test_api_case_run.py -v
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py -v
```

After targeted backend tests pass, run a QA regression subset including run plan and request-feature coverage:

```bash
cd backend && python -m pytest \
  tests/test_api_case_run.py \
  qa_center/tests/test_performance_persistence.py \
  tests/test_run_plan.py \
  tests/test_run_plan_extractors.py \
  tests/test_run_plan_request_features.py \
  -v
```

For E2E, first inspect the existing test runner and service requirements, then run the four smoke tests individually or as the project configuration supports:

```bash
python -m pytest e2e/test_login_flow.py -v
python -m pytest e2e/test_task_flow.py -v
python -m pytest e2e/test_drag_drop.py -v
python -m pytest e2e/test_search_flow.py -v
```

If services are required, start the existing backend/frontend dev servers according to the repo scripts and record any missing dependency or startup failure.

## Implementation Boundaries

Expected files to inspect or change if tests prove they are involved:

- `backend/qa_center/views_api_test.py`
- `backend/qa_center/extractors.py`
- `backend/tests/test_api_case_run.py`
- `backend/qa_center/tasks.py`
- `backend/qa_center/locust_runner.py`
- `backend/qa_center/models.py`
- `backend/qa_center/tests/test_performance_persistence.py`
- `e2e/test_login_flow.py`
- `e2e/test_task_flow.py`
- `e2e/test_drag_drop.py`
- `e2e/test_search_flow.py`
- Frontend/backend code directly touched by the E2E failure root cause.

Do not modify CI/CD trigger behavior, report export, or unrelated QA UI flows in this phase.
