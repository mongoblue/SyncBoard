# QA Center Verification Closure Design

## Goal

Make the existing QA center provably runnable by fixing the current failing verification set and adding only the smallest regression coverage needed for the core QA paths.

## Non-Goals

This phase will not redesign QA features or expand product scope. It explicitly excludes:

- Unifying the legacy API test executor with the newer API automation executor.
- Replacing DevOps Pipeline mock execution with real CI integration.
- Adding Locust multi-run concurrency support.
- Reworking the quality report scoring model.
- Adding a unified verification report or dashboard command.

## Current Evidence

The current failed-test cache shows these verification gaps:

- `e2e/test_drag_drop.py::test_drag_task_to_done[chromium]`
- `e2e/test_login_flow.py::test_login_success[chromium]`
- `e2e/test_search_flow.py::test_search_flow[chromium]`
- `e2e/test_task_flow.py::test_create_task_success[chromium]`
- `tests/test_api_case_run.py::test_single_run_extracts_response_variables`
- `qa_center/tests/test_performance_persistence.py::test_run_performance_test_persists_result`
- `qa_center/tests/test_performance_persistence.py::test_run_performance_test_marks_failed_when_error_rate_exceeds`

QA center routing and backend APIs are already broadly wired. The work should focus on making the existing paths pass verification, not replacing them.

## Scope

### 1. Backend API Case Run Verification

Fix the failing API single-run variable extraction test.

Expected behavior:

- Running an API test case stores response extraction data in the run/case result path used by the QA center.
- The extracted variables are available in the response shape expected by the test.
- The fix should preserve existing legacy result writes unless the failing test proves they are inconsistent.

Likely files to inspect:

- `backend/qa_center/views_api_test.py`
- `backend/qa_center/views_test_run.py`
- `backend/qa_center/models.py`
- `backend/tests/test_api_case_run.py`

### 2. Backend Performance Persistence Verification

Fix the failing performance persistence tests.

Expected behavior:

- A performance test run persists a `PerformanceTestResult` or equivalent persisted result record.
- A run with an error rate above the configured threshold is marked failed in the persisted result.
- Tests should not depend on a real Locust subprocess when the existing test is intended to mock execution.

Likely files to inspect:

- `backend/qa_center/tasks.py`
- `backend/qa_center/locust_runner.py`
- `backend/qa_center/models.py`
- `backend/qa_center/tests/test_performance_persistence.py`

### 3. E2E Smoke Verification

Fix the currently failing Playwright E2E smoke tests without redesigning the frontend.

Expected behavior:

- Login succeeds in the configured E2E environment.
- Creating a task succeeds through the UI.
- Dragging a task to Done succeeds through the UI.
- Search flow succeeds through the UI.

Likely files to inspect:

- `e2e/test_login_flow.py`
- `e2e/test_task_flow.py`
- `e2e/test_drag_drop.py`
- `e2e/test_search_flow.py`
- Frontend pages and stores involved in those flows.
- Backend endpoints used by those flows.

The first implementation step should determine whether each E2E failure is caused by product behavior, stale selectors, fixture data, missing server setup, or test timing. Fix the narrowest cause.

### 4. Minimal Regression Coverage

Add only missing coverage required to prevent the fixed failures from regressing.

Allowed additions:

- One focused backend regression test for API response extraction if the existing test does not already cover the final behavior.
- One focused backend regression test for performance result persistence or failure threshold if the existing tests are incomplete.
- A frontend or E2E smoke assertion only if a current failure is caused by missing route/page load coverage.

Avoid broad snapshot tests, large fixture rewrites, or test abstractions unless required by the failing tests.

## Data Flow Expectations

### API Single Run

1. The test invokes the API case run endpoint.
2. The backend executes the request using the existing API case execution path.
3. The response is evaluated and extraction rules are applied.
4. The run result persists request, response, assertion, and extraction evidence.
5. The endpoint returns enough result data for the test and frontend to inspect extracted variables.

### Performance Persistence

1. The performance task starts with a performance case and threshold configuration.
2. The runner returns metrics or a mocked metrics payload in tests.
3. The task maps metrics into persisted performance result fields.
4. The task marks the result failed when error-rate criteria are exceeded.
5. The persisted record is queryable by the QA center.

### E2E Smoke

1. Test setup creates or uses a known user/project/task state.
2. Browser actions use stable selectors and wait for visible state changes, not arbitrary sleeps.
3. The frontend calls the existing backend endpoints.
4. Assertions verify user-visible outcomes.

## Error Handling

- Treat failing tests as evidence first; do not patch around failures with skipped tests or weakened assertions.
- If an E2E failure is environment-related, document the missing prerequisite and make the test setup explicit where possible.
- If a product bug is found, fix the product behavior rather than changing the test expectation.
- If a selector is stale but behavior is correct, update the selector to match stable UI semantics.

## Verification Commands

The implementation plan should include exact commands after inspecting the repo scripts. At minimum it should cover:

- The failing backend API case run test.
- The failing backend performance persistence tests.
- The failing Playwright E2E tests.
- A QA-related backend test subset after individual fixes pass.

If UI verification requires starting backend/frontend servers, the plan should include those commands and record any blocker if the local environment cannot run them.

## Success Criteria

This phase is complete when:

- All currently listed failed tests either pass or have a documented environment blocker with evidence.
- Backend QA tests related to API case run and performance persistence pass locally.
- The E2E smoke tests pass locally when the required services are available.
- Any added regression tests are focused on the fixed behavior.
- No feature-scope changes are introduced beyond what is necessary to make the verified QA paths work.
