# QA Center Functional P1 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix QA Center backend functional P1 crashes and execution correctness bugs with targeted regression tests.

**Architecture:** Keep fixes local to existing Django/DRF view and executor modules. Use model field metadata for choices, canonical model field names for performance metrics, a shared executor context initializer for API auto execution, and `TestResult.aborted` as the performance stop signal instead of invalid status values.

**Tech Stack:** Django, Django REST Framework, pytest, unittest.mock, Celery task function tests, requests mocking.

---

## File Structure

- Modify: `backend/tests/test_qa_center.py`
  - Add regression coverage for `GET /api/qa/test-results/statistics/`.
- Modify: `backend/qa_center/views_test_result.py`
  - Replace nonexistent `TestResult.TEST_TYPE_CHOICES` and `STATUS_CHOICES` usage with field metadata.
- Modify: `backend/tests/test_quality_report.py`
  - Add regression coverage for quality report when performance data exists.
- Modify: `backend/qa_center/views_devops.py`
  - Replace nonexistent `PerformanceTestResult.p95/p99` usage with `p95_response_time_ms/p99_response_time_ms`.
- Create: `backend/tests/test_api_auto_executor_extractors.py`
  - Add regressions for API auto extractor propagation and single-case environment variable initialization.
- Modify: `backend/qa_center/api_auto_executor.py`
  - Add shared variable initialization, public `execute_single_case()`, extractor execution, and extractor prefetching.
- Modify: `backend/qa_center/views_api_auto_test.py`
  - Call `execute_single_case()` instead of private `_execute_case()`.
- Modify: `backend/qa_center/tests/test_performance_persistence.py`
  - Update success expectation to `passed`; add valid-status and stop-signal coverage.
- Modify: `backend/qa_center/tasks.py`
  - Use valid `TestResult.status` values; poll `aborted=True` for stop.
- Modify: `backend/qa_center/views_performance.py`
  - Mark stop via `aborted=True`; do not write `status='stopped'`.

---

### Task 1: Fix test result statistics choices

**Files:**
- Modify: `backend/tests/test_qa_center.py`
- Modify: `backend/qa_center/views_test_result.py`

- [ ] **Step 1: Add failing statistics endpoint regression test**

Append this test method inside `TestQaCenterAPI` in `backend/tests/test_qa_center.py`:

```python
    def test_test_result_statistics_counts_by_type_and_status(self, auth_client, test_project, test_user):
        from qa_center.models import TestResult

        TestResult.objects.create(
            test_type='api',
            name='api passed',
            status='passed',
            project=test_project,
            executed_by=test_user,
        )
        TestResult.objects.create(
            test_type='ui',
            name='ui failed',
            status='failed',
            project=test_project,
            executed_by=test_user,
        )

        response = auth_client.get(f'/api/qa/test-results/statistics/?project={test_project.id}')

        assert response.status_code == 200
        assert response.data['total'] == 2
        assert response.data['passed'] == 1
        assert response.data['failed'] == 1
        assert response.data['error'] == 0
        assert response.data['pass_rate'] == 50.0
        assert response.data['by_type']['api'] == 1
        assert response.data['by_type']['ui'] == 1
        assert response.data['by_status']['passed'] == 1
        assert response.data['by_status']['failed'] == 1
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_qa_center.py::TestQaCenterAPI::test_test_result_statistics_counts_by_type_and_status -v
```

Expected: FAIL with `AttributeError: type object 'TestResult' has no attribute 'TEST_TYPE_CHOICES'`.

- [ ] **Step 3: Implement field metadata choices fix**

In `backend/qa_center/views_test_result.py`, replace the type/status loop block inside `statistics()`:

```python
        # 按类型统计
        type_stats = {}
        for test_type, _ in TestResult.TEST_TYPE_CHOICES:
            type_count = queryset.filter(test_type=test_type).count()
            type_stats[test_type] = type_count

        # 按状态统计
        status_stats = {}
        for status_code, _ in TestResult.STATUS_CHOICES:
            status_count = queryset.filter(status=status_code).count()
            status_stats[status_code] = status_count
```

with:

```python
        # 按类型统计
        type_stats = {}
        test_type_choices = TestResult._meta.get_field('test_type').choices or []
        for test_type, _ in test_type_choices:
            type_count = queryset.filter(test_type=test_type).count()
            type_stats[test_type] = type_count

        # 按状态统计
        status_stats = {}
        status_choices = TestResult._meta.get_field('status').choices or []
        for status_code, _ in status_choices:
            status_count = queryset.filter(status=status_code).count()
            status_stats[status_code] = status_count
```

- [ ] **Step 4: Run the statistics test and verify GREEN**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_qa_center.py::TestQaCenterAPI::test_test_result_statistics_counts_by_type_and_status -v
```

Expected: PASS.

---

### Task 2: Fix DevOps quality report performance field names

**Files:**
- Modify: `backend/tests/test_quality_report.py`
- Modify: `backend/qa_center/views_devops.py`

- [ ] **Step 1: Add failing quality report performance regression test**

Append this test method inside `TestQualityReportBugDensity` in `backend/tests/test_quality_report.py`:

```python
    def test_quality_report_uses_performance_result_p95_response_time_ms(self, auth_client, test_project, test_user):
        from qa_center.models import PerformanceTestCase, PerformanceTestResult, TestResult

        case = PerformanceTestCase.objects.create(
            name='perf-case',
            url='https://example.com/api/foo',
            method='GET',
            project=test_project,
            created_by=test_user,
        )
        result = TestResult.objects.create(
            test_type='performance',
            name=case.name,
            project=test_project,
            status='passed',
            executed_by=test_user,
        )
        PerformanceTestResult.objects.create(
            test_case=case,
            test_result=result,
            executed_by=test_user,
            total_requests=100,
            successful_requests=100,
            failed_requests=0,
            avg_response_time_ms=100.0,
            min_response_time_ms=50.0,
            max_response_time_ms=250.0,
            p50_response_time_ms=90.0,
            p90_response_time_ms=150.0,
            p95_response_time_ms=320.0,
            p99_response_time_ms=600.0,
            throughput=20.0,
            error_rate=0.0,
        )

        resp = auth_client.get(f'/api/qa/devops/quality-report/?project_id={test_project.id}')

        assert resp.status_code == 200
        data = resp.json()
        perf_dim = next(d for d in data['dimensions'] if d['name'] == '性能指标')
        assert perf_dim['score'] == 20
        assert perf_dim['detail'] == 'P95: 320ms'
        assert data['summary']['has_perf_data'] is True
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_quality_report.py::TestQualityReportBugDensity::test_quality_report_uses_performance_result_p95_response_time_ms -v
```

Expected: FAIL with `AttributeError: 'PerformanceTestResult' object has no attribute 'p95'`.

- [ ] **Step 3: Implement canonical performance metric field usage**

In `backend/qa_center/views_devops.py`, replace:

```python
        perf_results = PerformanceTestResult.objects.filter(
            test_case__project_id=project_id
        ).order_by('-executed_at')[:5]
        if perf_results.exists():
            avg_p95 = sum(r.p95 or r.p99 or 0 for r in perf_results) / perf_results.count()
            perf_score = 20 if avg_p95 < 500 else (15 if avg_p95 < 1000 else (10 if avg_p95 < 2000 else 5))
        else:
            avg_p95 = 0
            perf_score = 0
```

with:

```python
        perf_results = list(PerformanceTestResult.objects.filter(
            test_case__project_id=project_id
        ).order_by('-executed_at')[:5])
        if perf_results:
            avg_p95 = sum(
                r.p95_response_time_ms or r.p99_response_time_ms or 0
                for r in perf_results
            ) / len(perf_results)
            perf_score = 20 if avg_p95 < 500 else (15 if avg_p95 < 1000 else (10 if avg_p95 < 2000 else 5))
        else:
            avg_p95 = 0
            perf_score = 0
```

Then replace the summary field:

```python
                'has_perf_data': perf_results.exists(),
```

with:

```python
                'has_perf_data': bool(perf_results),
```

- [ ] **Step 4: Run quality report tests and verify GREEN**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_quality_report.py -v
```

Expected: PASS.

---

### Task 3: Add API auto executor regression tests

**Files:**
- Create: `backend/tests/test_api_auto_executor_extractors.py`

- [ ] **Step 1: Create failing tests for extractor propagation and single-case variables**

Create `backend/tests/test_api_auto_executor_extractors.py` with this complete content:

```python
from unittest.mock import Mock, patch

import pytest

from qa_center.models import (
    ApiAutoTestCase,
    ApiAutoTestExtractor,
    ApiAutoTestSuite,
    TestEnvironment,
)
from qa_center.api_auto_executor import run_api_auto_test


class _FakeElapsed:
    def total_seconds(self):
        return 0.123


def _fake_response(payload, status_code=200, headers=None, text=None, cookies=None):
    response = Mock()
    response.status_code = status_code
    response.headers = headers or {'Content-Type': 'application/json'}
    response.text = text if text is not None else payload
    response.elapsed = _FakeElapsed()
    response.cookies = cookies or {}
    response.json.return_value = payload
    return response


@pytest.mark.django_db
def test_api_auto_executor_propagates_extracted_variable_to_later_case(test_project, test_user):
    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        name='extractor suite',
        created_by=test_user,
    )
    login_case = ApiAutoTestCase.objects.create(
        suite=suite,
        name='login',
        method='GET',
        url='https://example.com/login',
        expected_status=200,
        sort_order=1,
        created_by=test_user,
    )
    ApiAutoTestExtractor.objects.create(
        case=login_case,
        name='token',
        source='body',
        expression='token',
        sort_order=1,
    )
    ApiAutoTestCase.objects.create(
        suite=suite,
        name='profile',
        method='GET',
        url='https://example.com/profile',
        headers={'Authorization': 'Bearer {{token}}'},
        expected_status=200,
        sort_order=2,
        created_by=test_user,
    )

    responses = [
        _fake_response({'token': 'T123'}),
        _fake_response({'ok': True}),
    ]

    with patch('qa_center.api_auto_executor.requests.request', side_effect=responses) as request_mock:
        result = run_api_auto_test(suite.id, test_user)

    assert result.status == 'passed'
    assert request_mock.call_count == 2
    second_call = request_mock.call_args_list[1]
    assert second_call.kwargs['headers']['Authorization'] == 'Bearer T123'


@pytest.mark.django_db
def test_single_auto_case_execute_initializes_environment_variables(auth_client, test_project, test_user):
    TestEnvironment.objects.create(
        project=test_project,
        name='default',
        base_url='https://example.com',
        variables={'api_key': 'KEY123'},
        is_default=True,
        created_by=test_user,
    )
    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        name='single suite',
        created_by=test_user,
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        name='ping',
        method='GET',
        url='/ping',
        headers={'X-Api-Key': '{{api_key}}'},
        expected_status=200,
        created_by=test_user,
    )

    with patch('qa_center.api_auto_executor.requests.request', return_value=_fake_response({'ok': True})) as request_mock:
        response = auth_client.post(f'/api/qa/auto-cases/{case.id}/execute/')

    assert response.status_code == 200
    assert request_mock.call_count == 1
    call = request_mock.call_args
    assert call.kwargs['url'] == 'https://example.com/ping'
    assert call.kwargs['headers']['X-Api-Key'] == 'KEY123'
```

- [ ] **Step 2: Run new API auto tests and verify RED**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_api_auto_executor_extractors.py -v
```

Expected: FAIL. The extractor test should show `Bearer {{token}}` instead of `Bearer T123`; the single-case test should show unresolved `/ping` and/or `{{api_key}}`.

---

### Task 4: Implement API auto extractor propagation and single-case context

**Files:**
- Modify: `backend/qa_center/api_auto_executor.py`
- Modify: `backend/qa_center/views_api_auto_test.py`

- [ ] **Step 1: Import extractor helper**

In `backend/qa_center/api_auto_executor.py`, add this import near the existing internal imports:

```python
from . import extractors as ex_engine
```

The import block should include:

```python
from . import unified_assertions as ua
from . import template_engine as te
from . import request_builder as rb
from . import extractors as ex_engine
```

- [ ] **Step 2: Add shared initialization and single-case public method**

Inside `class ApiAutoTestExecutor`, after `__init__()`, add:

```python
    def _load_suite(self) -> ApiAutoTestSuite:
        if self.suite is None:
            self.suite = ApiAutoTestSuite.objects.select_related('project').get(id=self.suite_id)
        return self.suite

    def _initialize_variables(self) -> None:
        suite = self._load_suite()
        env = te.resolve_project_environment(suite.project, env_id=self._environment_id)
        globals_ = te.load_project_globals(suite.project)
        self._variables = te.build_variable_pool(environment=env, global_vars=globals_)

    def execute_single_case(self, case: ApiAutoTestCase, test_result: Optional[ApiAutoTestResult] = None) -> ApiAutoTestCaseResult:
        self.suite = case.suite
        self.suite_id = case.suite_id
        self._initialize_variables()
        if test_result is not None:
            self.test_result = test_result
        return self._execute_case(case)
```

- [ ] **Step 3: Use shared initialization and prefetch extractors in suite execution**

In `execute()`, replace:

```python
        self.suite = ApiAutoTestSuite.objects.get(id=self.suite_id)
        active_cases = self.suite.test_cases.filter(is_active=True).order_by('sort_order', 'created_at')

        # M3.2: 解析变量池（环境 + 项目全局变量）
        env = te.resolve_project_environment(self.suite.project, env_id=self._environment_id)
        globals_ = te.load_project_globals(self.suite.project)
        self._variables = te.build_variable_pool(environment=env, global_vars=globals_)
```

with:

```python
        self.suite = ApiAutoTestSuite.objects.select_related('project').get(id=self.suite_id)
        active_cases = (
            self.suite.test_cases
            .filter(is_active=True)
            .prefetch_related('assertions', 'extractors')
            .order_by('sort_order', 'created_at')
        )

        # M3.2: 解析变量池（环境 + 项目全局变量）
        self._initialize_variables()
```

- [ ] **Step 4: Run extractors after assertions**

In `_execute_case()`, after:

```python
            response_headers = dict(response.headers)
```

keep the existing assertion block, and after the expected-status assertion block but before:

```python
            passed = all_passed
```

insert:

```python
            active_extractors = list(case.extractors.filter(is_active=True).order_by('sort_order', 'id'))
            if active_extractors:
                extracted = ex_engine.run_extractors(
                    active_extractors,
                    response_json=response_data,
                    response_headers=response_headers,
                    status_code=status_code,
                    cookies=dict(getattr(response, 'cookies', {}) or {}),
                    response_time_ms=response_time_ms,
                )
                self._variables.update(extracted)
```

The final section should be:

```python
            if not has_status_code_assertion and case.expected_status and status_code != case.expected_status:
                all_passed = False
                assertion_details.insert(0, {
                    'assertion_type': 'status_code',
                    'expected_value': case.expected_status,
                    'actual_value': status_code,
                    'passed': False,
                    'error_message': f"Expected status {case.expected_status}, got {status_code}"
                })

            active_extractors = list(case.extractors.filter(is_active=True).order_by('sort_order', 'id'))
            if active_extractors:
                extracted = ex_engine.run_extractors(
                    active_extractors,
                    response_json=response_data,
                    response_headers=response_headers,
                    status_code=status_code,
                    cookies=dict(getattr(response, 'cookies', {}) or {}),
                    response_time_ms=response_time_ms,
                )
                self._variables.update(extracted)

            passed = all_passed
```

- [ ] **Step 5: Update single-case view to use public method**

In `backend/qa_center/views_api_auto_test.py`, replace:

```python
        executor = ApiAutoTestExecutor(suite.id, request.user)
        executor.test_result = test_result
        case_result = executor._execute_case(case)
```

with:

```python
        executor = ApiAutoTestExecutor(suite.id, request.user)
        case_result = executor.execute_single_case(case, test_result=test_result)
```

- [ ] **Step 6: Run API auto tests and verify GREEN**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_api_auto_executor_extractors.py -v
```

Expected: PASS.

---

### Task 5: Fix performance result status consistency

**Files:**
- Modify: `backend/qa_center/tests/test_performance_persistence.py`
- Modify: `backend/qa_center/tasks.py`
- Modify: `backend/qa_center/views_performance.py`

- [ ] **Step 1: Update success test to expect valid `passed` status**

In `backend/qa_center/tests/test_performance_persistence.py`, replace:

```python
    assert result['status'] == 'completed'

    tr.refresh_from_db()
    assert tr.status == 'completed'
```

with:

```python
    assert result['status'] == 'passed'

    tr.refresh_from_db()
    assert tr.status == 'passed'
    assert tr.status in dict(TestResult._meta.get_field('status').choices)
```

- [ ] **Step 2: Add valid-status assertion to failed test**

In `test_run_performance_test_marks_failed_when_error_rate_exceeds`, after:

```python
    tr.refresh_from_db()
    assert tr.status == 'failed'
```

add:

```python
    assert tr.status in dict(TestResult._meta.get_field('status').choices)
```

- [ ] **Step 3: Add stop-signal regression test**

Append this test to `backend/qa_center/tests/test_performance_persistence.py`:

```python
@pytest.mark.django_db
def test_should_stop_uses_aborted_flag_not_stopped_status(test_project, test_user):
    from qa_center.tasks import _should_stop

    tr = TestResult.objects.create(
        test_type='performance',
        name='stop-signal',
        project=test_project,
        status='running',
        executed_by=test_user,
        started_at=timezone.now(),
        aborted=True,
    )

    assert _should_stop(tr.id) is True

    tr.refresh_from_db()
    assert tr.status == 'running'
    assert tr.status in dict(TestResult._meta.get_field('status').choices)
```

- [ ] **Step 4: Add stopped-run final status regression test**

Append this fake runner and test to `backend/qa_center/tests/test_performance_persistence.py`:

```python
class _StoppedRunner(_FakeRunner):
    def __init__(self, execution_id=None):
        super().__init__(execution_id=execution_id)
        self._running = True
        self._checks = 0

    def is_running(self):
        self._checks += 1
        return self._checks == 1

    def stop_test(self):
        self._running = False


@pytest.mark.django_db
def test_run_performance_test_marks_user_stopped_run_as_error_and_aborted(test_project, test_user):
    case = PerformanceTestCase.objects.create(
        name='stopped-case',
        url='https://example.com/api/stop',
        method='GET',
        project=test_project,
        created_by=test_user,
        concurrent_users=5,
        duration_seconds=5,
        expected_error_rate=5.0,
    )
    tr = TestResult.objects.create(
        test_type='performance',
        name=case.name,
        project=test_project,
        status='running',
        executed_by=test_user,
        started_at=timezone.now(),
        aborted=True,
    )

    with patch('qa_center.tasks.LocustRunner', _StoppedRunner):
        result = run_performance_test(
            execution_id=tr.id,
            test_case_id=case.id,
            host='https://example.com',
            users=5,
            spawn_rate=1,
            run_time='5s',
        )

    assert result['status'] == 'error'
    tr.refresh_from_db()
    assert tr.status == 'error'
    assert tr.aborted is True
    assert tr.status in dict(TestResult._meta.get_field('status').choices)
    assert '用户停止' in tr.error_message
```

- [ ] **Step 5: Run performance tests and verify RED**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest qa_center/tests/test_performance_persistence.py -v
```

Expected: FAIL because successful run returns `completed` and `_should_stop()` ignores `aborted=True`.

- [ ] **Step 6: Update task stop polling and valid final statuses**

In `backend/qa_center/tasks.py`, update the module docstring lines that mention `status='stopped'` to say `aborted=True`.

Replace `_should_stop()`:

```python
def _should_stop(execution_id: int) -> bool:
    """检查 DB 中是否被标记为 stopped（由 views.stop 设置）。"""
    from .models import TestResult
    try:
        return TestResult.objects.filter(id=execution_id, status='stopped').exists()
    except Exception:
        return False
```

with:

```python
def _should_stop(execution_id: int) -> bool:
    """检查 DB 中是否被标记为 aborted（由 views.stop 设置）。"""
    from .models import TestResult
    try:
        return TestResult.objects.filter(id=execution_id, aborted=True).exists()
    except Exception:
        return False
```

Then replace final status logic:

```python
    if stopped_by_user:
        final_status = 'stopped'
    elif error_rate < (test_case.expected_error_rate or 5.0):
        final_status = 'completed'
    else:
        final_status = 'failed'
```

with:

```python
    if stopped_by_user:
        final_status = 'error'
    elif error_rate < (test_case.expected_error_rate or 5.0):
        final_status = 'passed'
    else:
        final_status = 'failed'
```

After setting `test_result.error_rate = error_rate`, add:

```python
    if stopped_by_user:
        test_result.aborted = True
        test_result.error_message = '用户停止性能测试'
        test_result.error_code = 'USER_STOPPED'
```

Replace the execution log success checks:

```python
            'passed': 1 if final_status == 'completed' else 0,
            'failed': 0 if final_status == 'completed' else 1,
            'pass_rate': 100 if final_status == 'completed' else 0,
```

with:

```python
            'passed': 1 if final_status == 'passed' else 0,
            'failed': 0 if final_status == 'passed' else 1,
            'pass_rate': 100 if final_status == 'passed' else 0,
```

Replace:

```python
            'passed': final_status == 'completed',
```

with:

```python
            'passed': final_status == 'passed',
```

- [ ] **Step 7: Update performance stop endpoint**

In `backend/qa_center/views_performance.py`, update the module docstring line that mentions `status='stopped'` to say `aborted=True`.

Replace:

```python
        if test_result.status in ('completed', 'failed', 'stopped', 'error'):
            return Response({'message': f'测试已处于终态：{test_result.status}'})

        test_result.status = 'stopped'
        test_result.completed_at = timezone.now()
```

with:

```python
        if test_result.status in ('passed', 'failed', 'error') or test_result.aborted:
            return Response({'message': f'测试已处于终态：{test_result.status}'})

        test_result.aborted = True
        test_result.completed_at = timezone.now()
```

Keep the existing duration calculation and `test_result.save()`.

- [ ] **Step 8: Run performance tests and verify GREEN**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest qa_center/tests/test_performance_persistence.py -v
```

Expected: PASS.

---

### Task 6: Run targeted regression suite and compile verification

**Files:**
- No code changes expected unless verification reveals a regression.

- [ ] **Step 1: Run targeted QA functional tests**

Run:

```bash
cd /d/Projects/SyncBoard/backend && pytest tests/test_qa_center.py tests/test_quality_report.py tests/test_api_auto_executor_extractors.py qa_center/tests/test_performance_persistence.py -v
```

Expected: PASS.

- [ ] **Step 2: Run compile verification**

Run:

```bash
cd /d/Projects/SyncBoard/backend && python -m compileall qa_center
```

Expected: command exits with code 0.

- [ ] **Step 3: If failures occur, fix only the failing slice**

Use the failure output to identify the minimal related file. Do not broaden scope to WebSocket/frontend/config issues in this plan.

- [ ] **Step 4: Report final verification**

Report:

- tests added/updated;
- backend files changed;
- exact verification commands and results;
- any skipped full-suite verification.

---

## Self-Review

Spec coverage:

- Statistics choices crash: Task 1.
- Quality report P95/P99 field crash: Task 2.
- API auto extractor propagation: Tasks 3 and 4.
- Single-case environment/global variable initialization: Tasks 3 and 4.
- Performance status enum consistency: Task 5.
- Targeted verification: Task 6.

Placeholder scan: no placeholders remain. Every code-changing step includes exact code or exact replacement text.

Type consistency:

- `execute_single_case(case, test_result=None)` uses existing `ApiAutoTestCase`, `ApiAutoTestResult`, and `ApiAutoTestCaseResult` types.
- Performance statuses use only existing `TestResult.status` choices: `passed`, `failed`, `error`, `running`, `pending`.
- Performance metric fields use existing `PerformanceTestResult.p95_response_time_ms` and `p99_response_time_ms`.
