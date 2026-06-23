"""验证 run_performance_test 会把指标写入 PerformanceTestResult 表。

我们 mock LocustRunner，让它不实际启动 Locust 子进程，直接喂回最终统计，
然后断言 worker 任务回填了 TestResult 与 PerformanceTestResult。
"""
import pytest
from unittest.mock import patch

from django.utils import timezone

from qa_center.models import PerformanceTestCase, PerformanceTestResult, TestResult
from qa_center.tasks import run_performance_test


FINAL_STATS = {
    'state': 'completed',
    'total_requests': 1200,
    'successful_requests': 1180,
    'failed_requests': 20,
    'avg_response_time': 123.45,
    'min_response_time': 12.0,
    'max_response_time': 789.0,
    'p50_response_time': 110.0,
    'p90_response_time': 250.0,
    'p95_response_time': 320.0,
    'p99_response_time': 600.0,
    'throughput': 40.0,
    'error_rate': 1.6,
    'errors': [{'message': 'boom', 'count': 20}],
    'current_users': 10,
    'start_time': '2026-06-23T00:00:00',
    'duration': 30,
}

FULL_PAYLOAD = {
    **FINAL_STATS,
    'throughput_over_time': [{'t': 1.0, 'rps': 40.0}],
    'response_time_over_time': [{'t': 1.0, 'avg': 123.0, 'p95': 320.0}],
    'response_time_distribution': {'100-150ms': 800, '150-200ms': 300},
}


class _FakeRunner:
    """假的 LocustRunner：start 立即"完成"，无子进程。"""

    def __init__(self, execution_id=None):
        self.execution_id = execution_id
        self._callbacks = []
        self._running = False

    def register_callback(self, cb):
        self._callbacks.append(cb)

    def start_test(self, test_case, host, users, spawn_rate, run_time):
        # 标记为"已结束"：worker 第一次 is_running 检查就会跳出循环
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


@pytest.mark.django_db
def test_run_performance_test_persists_result(test_project, test_user):
    case = PerformanceTestCase.objects.create(
        name='perf-case',
        url='https://example.com/api/foo',
        method='GET',
        project=test_project,
        created_by=test_user,
        concurrent_users=10,
        duration_seconds=10,
        expected_error_rate=5.0,
    )
    tr = TestResult.objects.create(
        test_type='performance',
        name=case.name,
        project=test_project,
        status='running',
        executed_by=test_user,
        started_at=timezone.now(),
    )

    with patch('qa_center.tasks.LocustRunner', _FakeRunner):
        result = run_performance_test(
            execution_id=tr.id,
            test_case_id=case.id,
            host='https://example.com',
            users=10,
            spawn_rate=1,
            run_time='10s',
        )

    assert result['ok'] is True
    assert result['status'] == 'completed'

    tr.refresh_from_db()
    assert tr.status == 'completed'
    assert tr.throughput == pytest.approx(40.0)
    assert tr.response_time_ms == pytest.approx(123.45)
    assert tr.error_rate == pytest.approx(1.6)
    assert tr.duration_ms is not None

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


@pytest.mark.django_db
def test_run_performance_test_marks_failed_when_error_rate_exceeds(test_project, test_user):
    case = PerformanceTestCase.objects.create(
        name='strict-case',
        url='https://example.com/api/bar',
        method='GET',
        project=test_project,
        created_by=test_user,
        concurrent_users=5,
        duration_seconds=5,
        expected_error_rate=1.0,  # 严格阈值：1.6% 会判失败
    )
    tr = TestResult.objects.create(
        test_type='performance',
        name=case.name,
        project=test_project,
        status='running',
        executed_by=test_user,
        started_at=timezone.now(),
    )

    with patch('qa_center.tasks.LocustRunner', _FakeRunner):
        result = run_performance_test(
            execution_id=tr.id,
            test_case_id=case.id,
            host='https://example.com',
            users=5,
            spawn_rate=1,
            run_time='5s',
        )

    assert result['status'] == 'failed'
    tr.refresh_from_db()
    assert tr.status == 'failed'
    assert PerformanceTestResult.objects.filter(test_result=tr).exists()
