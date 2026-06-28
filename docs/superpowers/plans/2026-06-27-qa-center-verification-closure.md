# QA Center Verification Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the QA Center verification loop by proving API extraction, performance persistence, and E2E smoke paths pass or have documented environment blockers.

**Architecture:** Keep the existing QA Center architecture intact. Treat API single-run extraction, performance persistence, and E2E smoke as three independent verification tracks; each track starts with a failing-or-passing evidence run, then applies the narrowest code change only when the evidence requires it.

**Tech Stack:** Django, Django REST Framework, pytest, pytest-django, Celery task functions, Playwright Python, Vue 3/Vite frontend.

---

## File Structure

### Backend API extraction track

- `backend/tests/test_api_case_run.py` — regression coverage for the single API case run endpoint. The extraction test must verify `name`, `value`, and `success`.
- `backend/qa_center/extractors.py` — response extraction helpers. `summarize_extractions()` owns the API/frontend-facing extraction item shape.
- `backend/qa_center/views_api_test.py` — single API case run endpoint. It parses response body, invokes extractor helpers, appends extraction evidence to `assertion_results`, and writes result records.
- `backend/backend/urls.py` — `/health/` test fixture endpoint. It must return `{'status': 'ok'}` for the extraction regression.

### Backend performance persistence track

- `backend/qa_center/tests/test_performance_persistence.py` — mocked LocustRunner tests proving `run_performance_test` writes `PerformanceTestResult` and marks high-error-rate runs failed.
- `backend/qa_center/tasks.py` — `run_performance_test` Celery task function. It maps runner metrics into `TestResult` and `PerformanceTestResult`.
- `backend/qa_center/locust_runner.py` — runner API used by the task. This plan does not redesign Locust generation; inspect only if mocked runner behavior and task expectations disagree.
- `backend/qa_center/models.py` — `PerformanceTestCase`, `TestResult`, and `PerformanceTestResult` fields.

### E2E smoke track

- `e2e/helpers.py` — shared login, project lookup/creation, and board navigation helpers.
- `e2e/test_login_flow.py` — login smoke test.
- `e2e/test_task_flow.py` — create-task smoke test.
- `e2e/test_drag_drop.py` — drag-to-Done smoke test.
- `e2e/test_search_flow.py` — search smoke test and Haystack index refresh helper.
- Frontend/backend files directly identified by an E2E failure root cause. Do not preemptively redesign UI flows.

---

### Task 1: Verify API Extraction Regression

**Files:**
- Inspect: `backend/backend/urls.py:21-22`
- Test: `backend/tests/test_api_case_run.py:18-44`
- Modify only on failure: `backend/tests/test_api_case_run.py`
- Modify only on failure: `backend/qa_center/extractors.py:94-109`
- Modify only on failure: `backend/qa_center/views_api_test.py:182-230`

- [ ] **Step 1: Confirm the `/health/` fixture shape**

Read `backend/backend/urls.py` and confirm it contains this exact endpoint behavior:

```python
def health_check(request):
    return JsonResponse({'status': 'ok'})
```

Expected: `/health/` returns JSON with `status` equal to `ok`. If this is not true, update the endpoint to the snippet above and continue.

- [ ] **Step 2: Run the targeted API extraction test**

Run from repository root:

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
```

Expected: PASS if the current workspace already contains the extraction fix. If it fails, the failure should identify one of these issues: no `extractions` block, missing `name`, missing `value`, missing `success`, or wrong extracted value.

- [ ] **Step 3: Ensure the regression test verifies the consumed extraction shape**

If `backend/tests/test_api_case_run.py::test_single_run_extracts_response_variables` does not already verify `value` and `success`, replace the assertions after `data = response.json()` with this block:

```python
# assertion_results 末尾应该有 extractions 块
assert any(isinstance(r, dict) and 'extractions' in r for r in data['assertion_results'])
# 找出 extractions 块,确认 health_status 被抽取出来
ext_block = next(r for r in data['assertion_results'] if isinstance(r, dict) and 'extractions' in r)
extractions = {it['name']: it for it in ext_block['extractions']}
assert 'health_status' in extractions
assert extractions['health_status']['value'] == 'ok'
assert extractions['health_status']['success'] is True
```

Run the same targeted test again:

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
```

Expected: PASS when extraction shape is correct; FAIL with a missing key or wrong value if implementation still needs the fix.

- [ ] **Step 4: Apply the narrow extractor shape fix when the test fails on missing fields**

If the targeted test fails because extraction items do not contain `name`, `value`, or `success`, replace `summarize_extractions()` in `backend/qa_center/extractors.py` with this implementation:

```python
def summarize_extractions(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把抽取结果转成前端友好的列表（用于结果详情展示 / 日志）。

    值如果太长会截断，避免污染日志和数据库。
    """
    items: List[Dict[str, Any]] = []
    for name, value in extracted.items():
        text = '' if value is None else str(value)
        items.append({
            'name': name,
            'value': value,
            'success': value is not None,
            'value_preview': text[:200] + ('…' if len(text) > 200 else ''),
            'is_none': value is None,
        })
    return items
```

Run the targeted test:

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
```

Expected: PASS.

- [ ] **Step 5: Apply the narrow append fix when the test fails because no extraction block exists**

If the targeted test fails because no `extractions` block is appended, update the extraction block in `backend/qa_center/views_api_test.py` so the successful path contains this code after `assertion_results` is computed:

```python
# 变量提取(M3.3): 从响应里抽出变量,稍后挂到 assertion_results 末尾
from . import extractors as ext
parsed_body = None
if response_body:
    try:
        parsed_body = json.loads(response_body)
    except (json.JSONDecodeError, TypeError):
        parsed_body = None
extracted = {}
for spec in (test_case.response_extractions or []):
    if not isinstance(spec, dict):
        continue
    name = (spec.get('var_name') or spec.get('name') or '').strip()
    if not name:
        continue
    value = ext.extract_value(
        source=spec.get('source', 'body'),
        expression=spec.get('json_path') or spec.get('expression') or '',
        response_json=parsed_body,
        response_headers=response_headers,
        status_code=status_code,
        response_time_ms=response_time_ms,
        default=spec.get('default'),
    )
    extracted[name] = value
extractions_summary = ext.summarize_extractions(extracted)
```

Then ensure the append point contains this exact condition:

```python
# 把 extractions 块挂到 assertion_results 末尾(不影响 passed 判定)
if extractions_summary:
    assertion_results = list(assertion_results) + [{'extractions': extractions_summary}]
```

Run the targeted test:

```bash
cd backend && python -m pytest tests/test_api_case_run.py::test_single_run_extracts_response_variables -v
```

Expected: PASS.

- [ ] **Step 6: Run the API case run test file**

Run:

```bash
cd backend && python -m pytest tests/test_api_case_run.py -v
```

Expected: all tests in `tests/test_api_case_run.py` PASS, including `test_single_run_creates_test_run` and `test_single_run_response_curl_omits_cookie`.

- [ ] **Step 7: Checkpoint the API extraction result**

Record the passing command output in the session summary. Do not create a git commit unless the user explicitly asks for one.

---

### Task 2: Verify Performance Result Persistence

**Files:**
- Test: `backend/qa_center/tests/test_performance_persistence.py:72-160`
- Modify only on failure: `backend/qa_center/tasks.py:44-186`
- Inspect only on mismatch: `backend/qa_center/locust_runner.py`
- Inspect only on mismatch: `backend/qa_center/models.py`

- [ ] **Step 1: Run the performance persistence tests**

Run from repository root:

```bash
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py -v
```

Expected: both tests PASS if the current workspace already contains the persistence fix. If it fails, continue with the specific failing assertion.

- [ ] **Step 2: Ensure the tests mock LocustRunner and do not start a subprocess**

Confirm `backend/qa_center/tests/test_performance_persistence.py` contains a fake runner with this interface:

```python
class _FakeRunner:
    """假的 LocustRunner：start 立即"完成"，无子进程。"""

    def __init__(self, execution_id=None):
        self.execution_id = execution_id
        self._callbacks = []
        self._running = False

    def register_callback(self, cb):
        self._callbacks.append(cb)

    def start_test(self, test_case, host, users, spawn_rate, run_time):
        self._running = False
        return True

    def is_running(self):
        return self._running

    def stop_test(self):
        self._running = False

    def get_current_stats(self):
        return dict(FINAL_STATS)

    def get_full_payload(self):
        return dict(FULL_PAYLOAD)
```

If the fake runner is missing one of these methods, add the missing method exactly as shown. Run the performance test file again.

- [ ] **Step 3: Apply the deterministic status mapping fix when threshold assertions fail**

If `test_run_performance_test_marks_failed_when_error_rate_exceeds` fails because status is not `failed`, update the status mapping in `backend/qa_center/tasks.py` to this code:

```python
error_rate = final_stats.get('error_rate', 0) or 0
if stopped_by_user:
    final_status = 'stopped'
elif error_rate < (test_case.expected_error_rate or 5.0):
    final_status = 'completed'
else:
    final_status = 'failed'
```

Run:

```bash
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py::test_run_performance_test_marks_failed_when_error_rate_exceeds -v
```

Expected: PASS.

- [ ] **Step 4: Apply the persistence mapping fix when `PerformanceTestResult` is missing or incomplete**

If `PerformanceTestResult.objects.get(test_result=tr)` fails or persisted metric assertions fail, update the persistence block in `backend/qa_center/tasks.py` to this code:

```python
# 持久化结构化指标
try:
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
except Exception as exc:
    print(f"[perf-task] PerformanceTestResult.create failed: {exc}")
```

Run:

```bash
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py::test_run_performance_test_persists_result -v
```

Expected: PASS.

- [ ] **Step 5: Run the full performance persistence test file**

Run:

```bash
cd backend && python -m pytest qa_center/tests/test_performance_persistence.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Checkpoint the performance result**

Record the passing command output in the session summary. Do not create a git commit unless the user explicitly asks for one.

---

### Task 3: Classify and Fix E2E Smoke Failures

**Files:**
- Test: `e2e/test_login_flow.py`
- Test: `e2e/test_task_flow.py`
- Test: `e2e/test_drag_drop.py`
- Test: `e2e/test_search_flow.py`
- Shared helper: `e2e/helpers.py`
- Modify only when root cause proves it: frontend/backend file directly responsible for the failure.

- [ ] **Step 1: Confirm E2E service assumptions**

The tests default to `BASE_URL=http://localhost`. Confirm a backend API and frontend app are reachable at the configured URL before treating failures as product bugs.

Run from repository root with the intended service URL:

```bash
python -m pytest e2e/test_login_flow.py -v
```

Expected when services are available: the browser opens `/login`, the page title matches `FlowSpace`, login succeeds, and URL moves to `/projects`.

If the command fails with connection refused, DNS failure, browser install failure, missing Playwright browser, or no login page, record the exact output as an environment blocker and do not modify product code for that failure.

- [ ] **Step 2: Fix login helper only when login selectors are stale**

If login fails because the username/password placeholders or login button selector changed while the UI still has equivalent fields, update `e2e/helpers.py::login` to this stable implementation:

```python
def login(page: Page, username: str = "mongoblue", password: str = "13579mnb") -> None:
    page.goto(f"{BASE_URL}/login")
    expect(page).to_have_title(re.compile("FlowSpace"), timeout=10000)
    username_input = page.get_by_placeholder("用户名")
    expect(username_input).to_be_visible(timeout=10000)
    username_input.fill(username)
    page.get_by_placeholder("密码").fill(password)
    login_btn = page.get_by_role("button", name=re.compile(r"登\s*录"))
    expect(login_btn).to_be_enabled(timeout=10000)
    login_btn.click()
    expect(page).to_have_url(re.compile(r"/projects"), timeout=15000)
```

Run:

```bash
python -m pytest e2e/test_login_flow.py -v
```

Expected: PASS.

- [ ] **Step 3: Run create-task smoke and classify failure**

Run:

```bash
python -m pytest e2e/test_task_flow.py -v
```

Expected when services and seed data are valid: test logs in, opens a board, creates a task in the first column, and sees the created title.

If failure says `open_board: 跳转 ... 失败`, classify it as RBAC/project access setup unless backend investigation proves the route guard is wrong. Record the exact current URL from the assertion message.

- [ ] **Step 4: Stabilize board navigation only when project-card clicking is the failure**

If the create-task smoke fails because project cards are not clickable or hover animation blocks navigation, ensure `e2e/helpers.py` uses API project lookup and direct board URL navigation with this implementation:

```python
def open_board(page: Page, project_id: str) -> None:
    target = f"{BASE_URL}/projects/{project_id}/board"
    page.goto(target)
    try:
        expect(page).to_have_url(re.compile(rf"/projects/{re.escape(str(project_id))}/board"), timeout=8000)
    except AssertionError:
        raise AssertionError(
            f"open_board: 跳转 {target} 失败，当前 URL = {page.url}。"
            "通常是后端 RBAC 没给当前用户 board:list 权限，router guard 把你踢回了 /projects。"
        )
    expect(page.locator(".board-column").first).to_be_visible(timeout=15000)


def open_project_card(page: Page, name: str | None = None) -> str:
    project = get_or_create_project(page, name=name)
    open_board(page, project["id"])
    return project["id"]
```

Run:

```bash
python -m pytest e2e/test_task_flow.py -v
```

Expected: PASS when project access is valid.

- [ ] **Step 5: Run drag-to-Done smoke and classify failure**

Run:

```bash
python -m pytest e2e/test_drag_drop.py -v
```

Expected when drag/drop works: task appears in the last board column after drag.

If failure occurs before drag starts, reuse the classification from login/project/board setup. If failure occurs during drag, capture whether the card or target column is invisible, drag action times out, or backend move request fails.

- [ ] **Step 6: Apply the mouse fallback only when Playwright `drag_to` is unreliable**

If `drag_to` fails but source and destination bounding boxes exist, ensure `e2e/test_drag_drop.py` contains this fallback:

```python
try:
    task_card.drag_to(done_column, force=True)
except Exception:
    src_box = task_card.bounding_box()
    dst_box = done_column.bounding_box()
    if src_box and dst_box:
        page.mouse.move(src_box["x"] + src_box["width"] / 2, src_box["y"] + src_box["height"] / 2)
        page.mouse.down()
        page.wait_for_timeout(200)
        page.mouse.move(dst_box["x"] + dst_box["width"] / 2, dst_box["y"] + dst_box["height"] / 2, steps=30)
        page.wait_for_timeout(200)
        page.mouse.up()
```

Run:

```bash
python -m pytest e2e/test_drag_drop.py -v
```

Expected: PASS when product drag/drop behavior is working.

- [ ] **Step 7: Run search smoke and classify failure**

Run:

```bash
python -m pytest e2e/test_search_flow.py -v
```

Expected when search indexing works: created task appears after search input is filled.

If search fails because the index is stale, verify `_refresh_haystack_index()` runs before the search assertion. If both Docker and local `manage.py update_index` fail, record both failures as an environment/indexing blocker.

- [ ] **Step 8: Replace arbitrary search wait only when UI has a stable loading/result signal**

If the search smoke fails because the fixed wait is too short but the UI exposes no stable loading indicator, keep the existing short wait and record the flake evidence. If the UI exposes a visible search result after indexing, use this assertion pattern instead of adding a longer sleep:

```python
search_input = page.get_by_placeholder("搜索任务...")
search_input.fill(task_title)
expect(page.get_by_text(task_title).first).to_be_visible(timeout=10000)
```

Run:

```bash
python -m pytest e2e/test_search_flow.py -v
```

Expected: PASS when indexing and search are available.

- [ ] **Step 9: Record E2E evidence**

For each E2E test, record one of these outcomes in the session summary:

```text
e2e/test_login_flow.py: PASS
e2e/test_task_flow.py: PASS
e2e/test_drag_drop.py: PASS
e2e/test_search_flow.py: PASS
```

or:

```text
e2e/<file>.py: BLOCKED — <exact missing service/dependency/setup>, proven by <command and key output>
```

Do not report E2E completion without either PASS output or a blocker record.

---

### Task 4: Run Backend QA Regression Subset

**Files:**
- Test: `backend/tests/test_api_case_run.py`
- Test: `backend/qa_center/tests/test_performance_persistence.py`
- Test: `backend/tests/test_run_plan.py`
- Test: `backend/tests/test_run_plan_extractors.py`
- Test: `backend/tests/test_run_plan_request_features.py`

- [ ] **Step 1: Run the backend QA regression subset**

Run from repository root:

```bash
cd backend && python -m pytest \
  tests/test_api_case_run.py \
  qa_center/tests/test_performance_persistence.py \
  tests/test_run_plan.py \
  tests/test_run_plan_extractors.py \
  tests/test_run_plan_request_features.py \
  -v
```

Expected: all selected tests PASS.

- [ ] **Step 2: Triage any regression failure by owner track**

If the subset fails, map the failure to exactly one owner track:

```text
API extraction owner: tests/test_api_case_run.py
Performance persistence owner: qa_center/tests/test_performance_persistence.py
Run plan owner: tests/test_run_plan.py, tests/test_run_plan_extractors.py, tests/test_run_plan_request_features.py
```

Return to the matching earlier task and apply only the narrow fix for that track. Do not modify unrelated tracks.

- [ ] **Step 3: Re-run the full subset after the narrow fix**

Run the same subset command again:

```bash
cd backend && python -m pytest \
  tests/test_api_case_run.py \
  qa_center/tests/test_performance_persistence.py \
  tests/test_run_plan.py \
  tests/test_run_plan_extractors.py \
  tests/test_run_plan_request_features.py \
  -v
```

Expected: all selected tests PASS.

---

### Task 5: Final Verification Report

**Files:**
- Inspect: `git status --short`
- No code changes in this task.

- [ ] **Step 1: Inspect final working tree state**

Run:

```bash
git status --short
```

Expected: only intentional changes from this verification closure are modified. Existing unrelated untracked files may remain, but identify them separately from closure changes.

- [ ] **Step 2: Summarize verification evidence**

Prepare a final summary in this exact structure:

```text
Backend API extraction:
- Command: cd backend && python -m pytest tests/test_api_case_run.py -v
- Result: PASS or FAIL/BLOCKED with reason

Backend performance persistence:
- Command: cd backend && python -m pytest qa_center/tests/test_performance_persistence.py -v
- Result: PASS or FAIL/BLOCKED with reason

Backend QA regression subset:
- Command: cd backend && python -m pytest tests/test_api_case_run.py qa_center/tests/test_performance_persistence.py tests/test_run_plan.py tests/test_run_plan_extractors.py tests/test_run_plan_request_features.py -v
- Result: PASS or FAIL/BLOCKED with reason

E2E smoke:
- e2e/test_login_flow.py: PASS or BLOCKED with command evidence
- e2e/test_task_flow.py: PASS or BLOCKED with command evidence
- e2e/test_drag_drop.py: PASS or BLOCKED with command evidence
- e2e/test_search_flow.py: PASS or BLOCKED with command evidence

Changed files:
- <closure-related file list>

Not changed:
- Real CI/CD trigger remains out of scope.
- Report export remains out of scope.
```

Do not claim completion unless the commands above have passing output or a documented blocker with command evidence.

---

## Self-Review

Spec coverage:

- API single-run response extraction is covered by Task 1.
- Performance persistence and error-rate failure behavior are covered by Task 2.
- Four E2E smoke flows are covered by Task 3.
- Backend QA regression subset is covered by Task 4.
- Final evidence reporting and scope guardrails are covered by Task 5.

Placeholder scan:

- This plan contains no placeholder markers and no undefined future work items.
- Conditional fixes are tied to exact failing evidence and include concrete replacement code.

Type and name consistency:

- Extraction fields are consistently `name`, `value`, and `success`.
- Performance metric fields match `PerformanceTestResult` and `FINAL_STATS` names used by the current tests.
- E2E file names and helper function names match the current repository.
