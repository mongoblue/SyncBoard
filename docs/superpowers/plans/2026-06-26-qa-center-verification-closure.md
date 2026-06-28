# QA Center Verification Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current QA center verification set pass by fixing the existing failed backend and E2E tests and adding only focused regression coverage for the repaired behavior.

**Architecture:** Keep the existing QA center architecture intact. Fix the narrowest failing path in API single-run extraction, performance result persistence, and E2E smoke flows. Do not unify executors, redesign Locust, replace DevOps mocks, or add a reporting command in this phase.

**Tech Stack:** Django + Django REST Framework + pytest + pytest-django + Celery task functions + Playwright Python E2E + Vue 3 frontend.

---

## File Structure

**Read/modify only as needed after reproducing each failure:**

- `backend/tests/test_api_case_run.py` — existing backend tests for single API case run and extraction behavior.
- `backend/qa_center/views_api_test.py` — legacy API case run endpoint that creates `ApiTestResult`, `TestRun`, and `TestRunCaseResult`.
- `backend/qa_center/extractors.py` — response extraction helpers used by API run.
- `backend/qa_center/models.py` — QA result models; inspect only unless a field mismatch is the root cause.
- `backend/qa_center/tests/test_performance_persistence.py` — existing performance persistence tests using a fake Locust runner.
- `backend/qa_center/tasks.py` — `run_performance_test` task that maps Locust stats into `TestResult` and `PerformanceTestResult`.
- `backend/qa_center/locust_runner.py` — inspect if task/runner contract mismatch causes persistence failures.
- `e2e/helpers.py` — shared login, project lookup, and board navigation helpers.
- `e2e/test_login_flow.py` — E2E login smoke test.
- `e2e/test_task_flow.py` — E2E task creation smoke test.
- `e2e/test_drag_drop.py` — E2E drag-to-Done smoke test.
- `e2e/test_search_flow.py` — E2E search smoke test.
- Frontend/backend files used by E2E flows — modify only if reproduction proves product behavior is broken rather than test setup/selectors/timing.

---

### Task 1: Reproduce Backend API Extraction Failure

**Files:**
- Test: `backend/tests/test_api_case_run.py`
- Inspect: `backend/qa_center/views_api_test.py`
- Inspect: `backend/qa_center/extractors.py`
- Inspect: `backend/backend/urls.py`

- [ ] **Step 1: Run the failing API extraction test**

Run from repository root:

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
```

Expected before fixing: either FAIL matching the cached failure, or PASS if the issue has already been fixed. Record the exact assertion or traceback if it fails.

- [ ] **Step 2: Confirm the test fixture response shape**

Read `backend/backend/urls.py` and confirm `/health/` returns:

```python
def health_check(request):
    return JsonResponse({'status': 'ok'})
```

Expected: the extractor for `$.status` should be able to extract `ok` as `health_status`.

- [ ] **Step 3: Inspect the run endpoint extraction path**

In `backend/qa_center/views_api_test.py`, confirm the successful path performs these operations in order:

```python
parsed_body = json.loads(response_body)
extracted[name] = ext.extract_value(...)
extractions_summary = ext.summarize_extractions(extracted)
if extractions_summary:
    assertion_results = list(assertion_results) + [{'extractions': extractions_summary}]
```

Expected: if the test fails, one of these values is not shaped as the test expects.

- [ ] **Step 4: Fix the narrow extraction shape mismatch**

If the failure is that extraction items do not expose `name`, update the narrowest code in `backend/qa_center/extractors.py` or `backend/qa_center/views_api_test.py` so the final response contains this shape:

```python
{
    'extractions': [
        {'name': 'health_status', 'value': 'ok', 'success': True}
    ]
}
```

If the failure is that no extraction block is appended, fix the condition so configured response extractions append the block even when the extracted value is falsey but valid, such as `''`, `0`, or `False`.

- [ ] **Step 5: Run the API extraction test again**

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
```

Expected: PASS.

- [ ] **Step 6: Run all API case run tests**

```bash
cd backend && python -m pytest tests/test_api_case_run.py -v
```

Expected: all tests in `test_api_case_run.py` PASS, including `test_single_run_creates_test_run` and `test_single_run_response_curl_omits_cookie`.

---

### Task 2: Add or Tighten Minimal API Extraction Regression

**Files:**
- Modify if needed: `backend/tests/test_api_case_run.py`
- Modify if needed: `backend/qa_center/views_api_test.py`
- Modify if needed: `backend/qa_center/extractors.py`

- [ ] **Step 1: Check whether current test already proves value extraction**

Open `backend/tests/test_api_case_run.py::test_single_run_extracts_response_variables`. If it only checks the extracted variable name, extend it to check value and success state.

Use this assertion block:

```python
ext_block = next(r for r in data['assertion_results'] if isinstance(r, dict) and 'extractions' in r)
extractions = {it['name']: it for it in ext_block['extractions']}
assert 'health_status' in extractions
assert extractions['health_status']['value'] == 'ok'
assert extractions['health_status']['success'] is True
```

Expected: the test now guards the actual extracted value, not just the variable name.

- [ ] **Step 2: Run the tightened test and verify it fails or passes meaningfully**

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
```

Expected: FAIL if the implementation still omits `value` or `success`; PASS if Task 1 already fixed the shape.

- [ ] **Step 3: Implement the minimal missing fields**

If Step 2 fails because `value` or `success` is missing, update the extraction summary code so each item includes:

```python
{'name': name, 'value': value, 'success': value is not None}
```

If the existing helper already has richer fields, preserve them and add only the missing keys required by the regression.

- [ ] **Step 4: Run the full API case run file**

```bash
cd backend && python -m pytest tests/test_api_case_run.py -v
```

Expected: all tests PASS.

---

### Task 3: Reproduce Performance Persistence Failures

**Files:**
- Test: `backend/qa_center/tests/test_performance_persistence.py`
- Inspect: `backend/qa_center/tasks.py`
- Inspect: `backend/qa_center/models.py`

- [ ] **Step 1: Run the failing performance persistence tests**

```bash
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py -v
```

Expected before fixing: one or both cached failures reproduce, or the file passes if already fixed. Record the exact traceback.

- [ ] **Step 2: Confirm fake runner contract**

In `backend/qa_center/tests/test_performance_persistence.py`, confirm `_FakeRunner` returns:

```python
def get_current_stats(self):
    return dict(FINAL_STATS)

def get_full_payload(self):
    return dict(FULL_PAYLOAD)
```

Expected: `run_performance_test` must be able to persist from these dictionaries without starting a real Locust process.

- [ ] **Step 3: Inspect persistence field mapping**

In `backend/qa_center/tasks.py`, confirm the task maps stats into `PerformanceTestResult.objects.create(...)` using model field names:

```python
p95_response_time_ms=final_stats.get('p95_response_time', 0) or 0,
p99_response_time_ms=final_stats.get('p99_response_time', 0) or 0,
throughput=final_stats.get('throughput', 0) or 0,
error_rate=error_rate,
```

Expected: every created field exists in `backend/qa_center/models.py::PerformanceTestResult`.

- [ ] **Step 4: Fix the narrow task/fixture mismatch**

If the failure shows `PerformanceTestResult.create failed`, update `backend/qa_center/tasks.py` so creation uses only actual model fields from `PerformanceTestResult`:

```python
PerformanceTestResult.objects.create(
    test_case=test_case,
    test_result=test_result,
    executed_by=test_result.executed_by,
    total_requests=final_stats.get('total_requests', 0),
    successful_requests=final_stats.get('successful_requests', 0),
    failed_requests=final_stats.get('failed_requests', 0),
    avg_response_time_ms=final_stats.get('avg_response_time', 0) or 0,
    min_response_time_ms=final_stats.get('min_response_time', 0) or 0,
    max_response_time_ms=final_stats.get('max_response_time', 0) or 0,
    p50_response_time_ms=final_stats.get('p50_response_time', 0) or 0,
    p90_response_time_ms=final_stats.get('p90_response_time', 0) or 0,
    p95_response_time_ms=final_stats.get('p95_response_time', 0) or 0,
    p99_response_time_ms=final_stats.get('p99_response_time', 0) or 0,
    throughput=final_stats.get('throughput', 0) or 0,
    error_rate=error_rate,
    response_time_distribution=payload.get('response_time_distribution', {}) or {},
    throughput_over_time=payload.get('throughput_over_time', []) or [],
    response_time_over_time=payload.get('response_time_over_time', []) or [],
    error_details=final_stats.get('errors', []) or [],
)
```

If the failure is status threshold logic, keep the intended behavior:

```python
elif error_rate < (test_case.expected_error_rate or 5.0):
    final_status = 'completed'
else:
    final_status = 'failed'
```

Do not change the test to accept failed persistence.

- [ ] **Step 5: Run performance persistence tests again**

```bash
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py -v
```

Expected: both tests PASS.

---

### Task 4: Add or Tighten Minimal Performance Regression

**Files:**
- Modify if needed: `backend/qa_center/tests/test_performance_persistence.py`
- Modify if needed: `backend/qa_center/tasks.py`

- [ ] **Step 1: Ensure persistence test checks the created detail record**

Confirm `test_run_performance_test_persists_result` asserts this full persisted detail behavior:

```python
perf = PerformanceTestResult.objects.get(test_result=tr)
assert perf.test_case_id == case.id
assert perf.total_requests == 1200
assert perf.failed_requests == 20
assert perf.p95_response_time_ms == pytest.approx(320.0)
assert perf.throughput == pytest.approx(40.0)
assert perf.error_rate == pytest.approx(1.6)
assert perf.response_time_distribution == FULL_PAYLOAD['response_time_distribution']
assert perf.throughput_over_time == FULL_PAYLOAD['throughput_over_time']
assert perf.response_time_over_time == FULL_PAYLOAD['response_time_over_time']
assert perf.error_details == FINAL_STATS['errors']
```

Expected: if this block already exists, no test change is needed.

- [ ] **Step 2: Ensure failure-threshold test checks persisted detail existence**

Confirm `test_run_performance_test_marks_failed_when_error_rate_exceeds` asserts:

```python
assert result['status'] == 'failed'
tr.refresh_from_db()
assert tr.status == 'failed'
assert PerformanceTestResult.objects.filter(test_result=tr).exists()
```

Expected: if this block already exists, no test change is needed.

- [ ] **Step 3: Run the performance file after any tightening**

```bash
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py -v
```

Expected: both tests PASS.

---

### Task 5: Reproduce E2E Login Failure

**Files:**
- Test: `e2e/test_login_flow.py`
- Inspect: `e2e/helpers.py`
- Inspect if product bug: `frontend/src/views/Login.vue`
- Inspect if auth API bug: backend auth/login endpoint files found during investigation.

- [ ] **Step 1: Confirm services are available**

Before running E2E, ensure backend and frontend are running in the expected local environment. The tests default to:

```python
BASE_URL = os.getenv("BASE_URL", os.getenv("E2E_BASE_URL", "http://localhost"))
```

If your frontend is not served at `http://localhost`, set `BASE_URL` or `E2E_BASE_URL` to the correct local URL.

- [ ] **Step 2: Run only the login E2E test**

```bash
python -m pytest e2e/test_login_flow.py::test_login_success --headed -v
```

Expected before fixing: either FAIL matching the cached failure, PASS if already fixed, or fail with a clear environment prerequisite such as server unavailable.

- [ ] **Step 3: Classify the failure**

Use this decision table:

```text
Title mismatch          -> update expected title only if app title intentionally changed from FlowSpace.
Login button not found  -> update selector to stable role/text used by current UI.
URL never reaches /projects -> inspect login API response and auth state.
Server unavailable      -> document service startup blocker; do not edit product code.
```

- [ ] **Step 4: Apply the narrowest fix**

If the UI title changed intentionally, update `e2e/test_login_flow.py` and `e2e/helpers.py` from:

```python
expect(page).to_have_title(re.compile("FlowSpace"))
```

to the actual app title regex observed in the browser.

If the login button text changed but still means login, update only the button locator in `e2e/test_login_flow.py` and `e2e/helpers.py`:

```python
page.get_by_role("button", name=re.compile(r"登\s*录"))
```

to the current stable accessible name.

If authentication fails with valid seeded credentials, inspect and fix the backend/frontend auth behavior instead of weakening the test.

- [ ] **Step 5: Run login E2E again**

```bash
python -m pytest e2e/test_login_flow.py::test_login_success --headed -v
```

Expected: PASS, or a documented environment blocker if local services cannot run.

---

### Task 6: Reproduce E2E Task Creation Failure

**Files:**
- Test: `e2e/test_task_flow.py`
- Shared helper: `e2e/helpers.py`
- Inspect if product bug: board/task frontend files and backend task endpoints discovered during failure classification.

- [ ] **Step 1: Run the task creation E2E test**

```bash
python -m pytest e2e/test_task_flow.py::test_create_task_success --headed -v
```

Expected before fixing: FAIL matching cached failure, PASS if already fixed, or environment blocker.

- [ ] **Step 2: Classify the failure**

Use this decision table:

```text
Cannot open board         -> inspect `e2e/helpers.py::open_board` error; likely permission or route guard.
Add button not visible    -> inspect current board column markup and update selector only if UI changed.
Dialog not visible        -> inspect create-task interaction and Element Plus dialog rendering.
Task card not visible     -> inspect API response, frontend store update, or timing around card creation.
```

- [ ] **Step 3: Prefer stable selectors over sleeps**

If selector drift is the root cause, update test locators to stable visible semantics. For example, keep this pattern if still valid:

```python
todo_column = page.locator(".board-column").first
add_btn = todo_column.locator('button[title="新增任务"]').first
dialog = page.locator(".el-dialog").filter(has_text="新建任务").first
```

If the UI no longer exposes `title="新增任务"`, replace it with the current stable role/title/aria-label used by the add-task button.

- [ ] **Step 4: Fix product behavior only if the UI action is genuinely broken**

If task creation API succeeds but the card does not render, fix the frontend store/component update path so the new card appears without requiring a manual refresh.

If task creation API fails, fix the backend endpoint or request payload shape used by the frontend.

- [ ] **Step 5: Run task creation E2E again**

```bash
python -m pytest e2e/test_task_flow.py::test_create_task_success --headed -v
```

Expected: PASS, or documented environment blocker.

---

### Task 7: Reproduce E2E Drag-to-Done Failure

**Files:**
- Test: `e2e/test_drag_drop.py`
- Shared helper: `e2e/helpers.py`
- Inspect if product bug: board drag/drop frontend files and backend task move endpoint discovered during failure classification.

- [ ] **Step 1: Run only the drag E2E test**

```bash
python -m pytest e2e/test_drag_drop.py::test_drag_task_to_done --headed -v
```

Expected before fixing: FAIL matching cached failure, PASS if already fixed, or environment blocker.

- [ ] **Step 2: Classify the failure**

Use this decision table:

```text
Task creation setup fails  -> reuse Task 6 fix first.
Drag action throws         -> inspect current draggable implementation and target drop zone.
Task remains in first col  -> inspect frontend move request and backend response.
Done column selector wrong -> update selector to target the actual Done/status column.
```

- [ ] **Step 3: Replace arbitrary wait only if event-based state is available**

The current test contains:

```python
page.wait_for_timeout(1500)
```

If the failure is timing-related and there is a reliable UI state to wait for, replace the sleep with an assertion that waits for the card in the Done column:

```python
done_task = done_column.get_by_text(task_title, exact=True)
expect(done_task).to_be_visible(timeout=10000)
```

Do not increase the timeout without identifying the root cause.

- [ ] **Step 4: Fix product behavior if drag no longer persists**

If the UI visually moves the task but a refresh puts it back, fix the backend move persistence path or frontend request payload.

If drag never starts because the selector targets text instead of the draggable card container, update the test to drag the stable card element that contains the task title.

- [ ] **Step 5: Run drag E2E again**

```bash
python -m pytest e2e/test_drag_drop.py::test_drag_task_to_done --headed -v
```

Expected: PASS, or documented environment blocker.

---

### Task 8: Reproduce E2E Search Failure

**Files:**
- Test: `e2e/test_search_flow.py`
- Shared helper: `e2e/helpers.py`
- Inspect if product bug: search frontend files, backend search endpoints, and Haystack config discovered during failure classification.

- [ ] **Step 1: Run only the search E2E test**

```bash
python -m pytest e2e/test_search_flow.py::test_search_flow --headed -v
```

Expected before fixing: FAIL matching cached failure, PASS if already fixed, or environment blocker.

- [ ] **Step 2: Classify the failure**

Use this decision table:

```text
Project create fails       -> inspect project API or CSRF setup.
Task create fails          -> reuse Task 6 fix first.
update_index fails         -> inspect whether command must run from `backend/` locally.
Search input not found     -> update placeholder selector if UI changed intentionally.
Task not in search results -> inspect index update and search API behavior.
```

- [ ] **Step 3: Fix local update_index command path if needed**

If local fallback fails because `manage.py` is under `backend/`, update `_refresh_haystack_index()` in `e2e/test_search_flow.py` so the local candidate uses the backend working directory:

```python
subprocess.run(
    [sys.executable, "manage.py", "update_index"],
    check=True,
    env=env,
    timeout=60,
    cwd="backend",
)
```

Keep the Docker Compose candidate for CI if it is valid.

- [ ] **Step 4: Replace fixed search wait if a response/UI state can be observed**

The current test contains:

```python
page.wait_for_timeout(2000)
```

If the search UI updates based on request completion or visible results, rely on:

```python
expect(page.get_by_text(task_title).first).to_be_visible(timeout=10000)
```

Do not extend the sleep as the primary fix.

- [ ] **Step 5: Run search E2E again**

```bash
python -m pytest e2e/test_search_flow.py::test_search_flow --headed -v
```

Expected: PASS, or documented environment blocker.

---

### Task 9: Run QA Backend Regression Subset

**Files:**
- Verify: `backend/tests/test_api_case_run.py`
- Verify: `backend/qa_center/tests/test_performance_persistence.py`
- Verify optional QA subset files discovered during implementation.

- [ ] **Step 1: Run the API and performance regression subset together**

```bash
cd backend && python -m pytest tests/test_api_case_run.py qa_center/tests/test_performance_persistence.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run a broader QA backend subset**

Use the existing QA-related backend tests without running unrelated suites:

```bash
cd backend && python -m pytest tests/test_api_case_run.py tests/test_batch_run.py qa_center/tests -v
```

Expected: PASS for the subset, or only unrelated pre-existing failures documented with exact test names and tracebacks.

- [ ] **Step 3: Re-check failed-test cache after successful pytest runs**

```bash
cd backend && python -m pytest tests/test_api_case_run.py qa_center/tests/test_performance_persistence.py --lf -v
```

Expected: no remaining failures for the backend tests addressed in this phase.

---

### Task 10: Run E2E Smoke Regression Set

**Files:**
- Verify: `e2e/test_login_flow.py`
- Verify: `e2e/test_task_flow.py`
- Verify: `e2e/test_drag_drop.py`
- Verify: `e2e/test_search_flow.py`

- [ ] **Step 1: Run all four targeted E2E smoke tests**

With backend and frontend services running at `BASE_URL`:

```bash
python -m pytest e2e/test_login_flow.py e2e/test_task_flow.py e2e/test_drag_drop.py e2e/test_search_flow.py -v
```

Expected: all four PASS, or environment blockers documented with exact missing service/setup.

- [ ] **Step 2: Run headed mode for any remaining E2E failure**

For each remaining failure, run its single test in headed mode:

```bash
python -m pytest e2e/test_login_flow.py::test_login_success --headed -v
python -m pytest e2e/test_task_flow.py::test_create_task_success --headed -v
python -m pytest e2e/test_drag_drop.py::test_drag_task_to_done --headed -v
python -m pytest e2e/test_search_flow.py::test_search_flow --headed -v
```

Expected: each remaining failure is classified as product bug, selector drift, timing issue, fixture/setup issue, or environment blocker.

- [ ] **Step 3: Stop when the targeted E2E set is green**

Do not expand this phase into unrelated E2E coverage. The success target is the four cached QA-adjacent smoke failures.

---

### Task 11: Final Verification and Change Review

**Files:**
- Review all modified files from previous tasks.
- Do not modify `docs/superpowers/specs/2026-06-26-qa-center-verification-closure-design.md` unless implementation proves the approved scope was materially wrong.

- [ ] **Step 1: Check working tree changes**

```bash
git status --short
```

Expected: only implementation/test files relevant to this plan are modified, plus this plan file if not committed separately.

- [ ] **Step 2: Review the diff for scope creep**

```bash
git diff -- backend/tests/test_api_case_run.py backend/qa_center/views_api_test.py backend/qa_center/extractors.py backend/qa_center/tests/test_performance_persistence.py backend/qa_center/tasks.py e2e/helpers.py e2e/test_login_flow.py e2e/test_task_flow.py e2e/test_drag_drop.py e2e/test_search_flow.py
```

Expected: no API executor unification, no DevOps real CI integration, no Locust concurrency redesign, no quality report scoring redesign.

- [ ] **Step 3: Run final targeted backend verification**

```bash
cd backend && python -m pytest tests/test_api_case_run.py qa_center/tests/test_performance_persistence.py -v
```

Expected: PASS.

- [ ] **Step 4: Run final targeted E2E verification**

```bash
python -m pytest e2e/test_login_flow.py e2e/test_task_flow.py e2e/test_drag_drop.py e2e/test_search_flow.py -v
```

Expected: PASS, or documented environment blocker with exact command output.

- [ ] **Step 5: Prepare completion summary**

Summarize:

```text
Backend API extraction: PASS/blocked with evidence
Performance persistence: PASS/blocked with evidence
E2E login/task/drag/search: PASS/blocked with evidence
Added regression coverage: list exact tests changed or added
Deferred by design: API executor unification, DevOps real CI, Locust concurrency, quality report redesign
```

Expected: the summary can be used to decide the next QA center optimization phase.
