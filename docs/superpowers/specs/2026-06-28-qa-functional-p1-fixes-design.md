# QA Center Functional P1 Fixes Design

Date: 2026-06-28

## Goal

Fix the next backend QA Center P1 functional bug slice while keeping the scope focused and test-driven. This slice covers endpoint crashes, API auto execution correctness, and performance result status consistency.

## Scope

In scope:

1. `TestResultViewSet.statistics()` must not crash when reading test type/status choices.
2. `ProjectQualityReportView` must not crash when a project has performance results.
3. `ApiAutoTestExecutor` must run configured `ApiAutoTestExtractor` rows and pass extracted variables to later cases.
4. Single-case API auto execution must initialize environment/global variables the same way suite execution does.
5. Performance execution must persist only valid `TestResult.status` values.

Out of scope:

- WebSocket authorization/origin validation.
- Frontend WebSocket URL/lifecycle fixes.
- Room/Board project validation fixes.
- Bug Tracker assignee membership policy changes.
- Deployment/config hardening.

## Existing Problems

### Test result statistics

`backend/qa_center/views_test_result.py` references `TestResult.TEST_TYPE_CHOICES` and `TestResult.STATUS_CHOICES`. The `TestResult` model defines choices inline on the fields, so these class attributes do not exist. The statistics action can raise `AttributeError`.

### DevOps quality report

`backend/qa_center/views_devops.py` reads `PerformanceTestResult.p95` and `p99`. The model fields are `p95_response_time_ms` and `p99_response_time_ms`. Projects with performance results can trigger `AttributeError`.

### API auto extractor chain

`backend/qa_center/api_auto_executor.py` has comments/docstrings describing extractor support, but `_execute_case()` does not run `case.extractors`. Variables extracted from case A are not available to case B.

### Single-case auto execution variables

`ApiAutoTestCaseViewSet.execute()` creates an executor and directly calls private `_execute_case(case)`. This bypasses the suite execution path that loads the default environment and project global variables.

### Performance status enum

`TestResult.status` allows `passed`, `failed`, `error`, `running`, and `pending`. Performance execution currently uses invalid values such as `completed` and `stopped`. Django does not validate choices on save by default, so invalid values can be persisted and then break statistics, display labels, and API consumers.

## Design

### 1. Statistics choices

Use Django field metadata instead of nonexistent model class constants:

- `TestResult._meta.get_field('test_type').choices`
- `TestResult._meta.get_field('status').choices`

The response shape remains unchanged: total counts, pass/fail/error counts, pass rate, `by_type`, and `by_status`.

### 2. Quality report performance metrics

Use canonical performance result field names:

- Primary value: `p95_response_time_ms`
- Fallback value: `p99_response_time_ms`

Convert the latest performance result queryset to a list before averaging so the code can use `len()` and `bool()` without repeated queryset evaluation. The report semantics remain unchanged: lower P95 yields a higher performance score.

### 3. API auto extractor execution

After an API auto case receives a response and before the case result is finalized, `_execute_case()` will:

1. Load active extractors from `case.extractors`, ordered by `sort_order, id`.
2. Parse response JSON when available, while still passing response text/headers/status/cookies/timing context to the extractor engine as supported by the existing helper.
3. Call `qa_center.extractors.run_extractors()`.
4. Merge extracted values into `self._variables`.

This makes later cases in the same suite render `{{token}}`-style values from earlier extractor output. Extractor failures should not crash unrelated execution beyond the existing extractor engine behavior; failures are represented in extraction output/summary according to the helper's existing contract.

### 4. Single-case executor API

Add a public executor method for single-case execution, for example `execute_single_case(case, test_result=None)`, and a shared context initializer.

Both suite execution and single-case execution will use the same initialization logic:

1. Resolve the project environment, including the default environment when no explicit environment id is supplied.
2. Load project global variables.
3. Build the variable pool.

`ApiAutoTestCaseViewSet.execute()` will call the public method instead of directly calling private `_execute_case()`.

### 5. Performance status consistency

Do not add new status choices or migrations in this slice. Align performance code with the existing `TestResult.status` enum.

Rules:

- Newly started run: `running`.
- Successful performance run: `passed`.
- Threshold failure: `failed`.
- Runtime/setup error: `error`.
- User stop signal: set `TestResult.aborted = True`; do not store `status='stopped'`.
- Final status for a user-stopped run: `error` with `aborted=True` and an explanatory message.

`_should_stop()` will poll `aborted=True` instead of `status='stopped'`. Stop endpoint logic will treat `aborted=True` and terminal statuses as not actively running.

## Testing Strategy

Use TDD for this slice.

### Regression tests to add or update

1. Add statistics endpoint coverage:
   - create `TestResult` rows with different types/statuses;
   - call `/api/qa/test-results/statistics/`;
   - assert 200 and correct `by_type`, `by_status`, and pass rate.

2. Add quality report performance coverage:
   - create `PerformanceTestCase`, `TestResult`, and `PerformanceTestResult` with `p95_response_time_ms`;
   - call `/api/qa/devops/quality-report/?project_id=...`;
   - assert 200 and performance dimension uses the P95 value.

3. Add API auto extractor propagation coverage:
   - suite case A returns a token;
   - case A has an active extractor for that token;
   - case B uses `{{token}}` in a header;
   - mocked request call for case B receives the rendered token.

4. Add single-case variable initialization coverage:
   - create a default environment with `base_url` and variables;
   - execute one auto case through the API endpoint;
   - mocked request receives resolved base URL and rendered headers.

5. Update/add performance status tests:
   - successful performance task returns and persists `passed`, not `completed`;
   - failed threshold still persists `failed`;
   - stop signaling uses `aborted=True` and does not persist `stopped`;
   - performance code stores only choices allowed by `TestResult.status`.

### Verification commands

Run targeted backend tests after implementation. Expected command shape:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_qa_center.py tests/test_quality_report.py tests/test_api_auto_executor_extractors.py qa_center/tests/test_performance_persistence.py -v
```

Also run compile verification for touched backend modules:

```bash
cd /d/Projects/SyncBoard/backend && python -m compileall qa_center
```

The exact test file list may be adjusted after inspecting current test organization.

## Risks and Mitigations

### Risk: changing performance success status breaks existing expectations

Mitigation: update tests to assert the model's declared enum. `passed` is the canonical success status used by other QA result flows.

### Risk: extractor execution changes result details expected by UI

Mitigation: keep result response shape unchanged unless existing code already supports extractor summaries. The core requirement is variable propagation; result-detail display can be a later UI/UX enhancement.

### Risk: single-case public method duplicates suite execution logic

Mitigation: extract shared initialization into one helper method used by both paths.

### Risk: stopping a run needs a signal visible to the worker

Mitigation: reuse existing `TestResult.aborted` as the signal. This avoids adding a new enum value or database migration.

## Acceptance Criteria

The slice is complete when:

1. Statistics endpoint returns 200 and correct counts for valid test data.
2. Quality report returns 200 for projects with performance results.
3. API auto extractors feed variables into later cases in the same suite.
4. Single-case auto execution resolves environment base URL and global/environment variables.
5. Performance code no longer writes `completed` or `stopped` to `TestResult.status`.
6. Targeted regression tests and compile verification pass.
