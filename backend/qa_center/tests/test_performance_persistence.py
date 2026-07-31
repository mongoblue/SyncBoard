"""验证 run_performance_test 会把指标写入 PerformanceTestResult 表。

mock LocustRunner（纯适配器），Worker 自行轮询 read_stats()。
"""
import pytest
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.utils import timezone

from room.models import Project
from qa_center.models import PerformanceTestCase, PerformanceTestResult, TestResult, TestRun, TestRunCaseResult
from qa_center.tasks import run_performance_test


@pytest.fixture
def test_user(db):
    return User.objects.create_user(username='perfuser', password='testpass123')


@pytest.fixture
def test_project(db, test_user):
    return Project.objects.create(name='Perf Project', owner=test_user)


FINAL_STATS = {
    'ok': True,
    'runner_status': 'locust_running_with_requests',
    'metrics_status': 'ok',
    'stats': {
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
        'current_rps': 40.0,
        'error_rate': 1.6,
        'errors': [{'type': 'ConnectionError', 'message': 'boom', 'endpoint': '/', 'count': 20}],
        'per_endpoint': {},
        'throughput_over_time': [{'t': 1.0, 'rps': 40.0}],
        'response_time_over_time': [{'t': 1.0, 'avg': 123.0, 'p95': 320.0}],
        'error_rate_over_time': [{'t': 1.0, 'error_rate': 1.6}],
        'response_time_distribution': {'100-150ms': 800, '150-200ms': 300},
    },
    'diagnostics': {},
}

FULL_PAYLOAD = {
    **FINAL_STATS,
    'diagnostics': {'artifact_dir': '/fake/perf_runs/99'},
}


class _FakeRunner:
    """Mock LocustRunner（纯适配器，无回调/无业务逻辑）。

    start_test 立即返回 True 并设置 _running=False，
    Worker 的 _wait() 循环第一次 is_running() 即退出。
    """

    def __init__(self, execution_id=None, port_offset=0):
        self.execution_id = execution_id
        self._running = False
        self.process = None          # is_running 检查 poll()
        self.metrics_file_path = '/fake/metrics.json'
        self.port_offset = port_offset

    # -- 子进程管理 --
    def ensure_artifact_dir(self):
        return '/fake/perf_runs/99'

    @property
    def artifact_dir(self):
        return '/fake/perf_runs/99'

    def generate_locustfile(self, test_case, metrics_file):
        self.metrics_file_path = '/fake/metrics.json'
        return '/fake/locustfile.py'

    def start_test(self, test_case, host, users, spawn_rate, run_time,
                   use_web_ui=False):
        self._running = False        # 立即"完成"
        return True

    def stop_test(self):
        self._running = False
        return True

    def is_running(self):
        return self._running

    def exit_code(self):
        return None

    # -- 被动读取 --
    def read_stats(self):
        return dict(FINAL_STATS)

    def read_full_payload(self):
        return dict(FULL_PAYLOAD)

    # -- 诊断信息 --
    def get_diagnostic_info(self):
        return {
            'execution_id': self.execution_id,
            'host': 'https://example.com',
            'users': 10,
            'spawn_rate': 1,
            'run_time': '10s',
            'is_running': self._running,
            'exit_code': None,
        }

    def read_stderr_tail(self, lines=50):
        return ''

    def read_stdout_tail(self, lines=50):
        return ''

    def start_watchdog(self, max_runtime=None, on_timeout=None):
        pass

    def cancel_watchdog(self):
        pass

    def get_resource_usage(self):
        return {}

    @property
    def web_port(self):
        return 8089 + self.port_offset


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

    class _ProbeOkResponse:
        status_code = 200

    with patch('qa_center.semaphore.PerfSemaphore') as sem_cls, \
         patch('qa_center.execution.worker.create_runner', return_value=_FakeRunner(execution_id=tr.id)), \
         patch('qa_center.execution.worker.TargetProbeService.probe', return_value=MagicMock(ok=True, to_dict=lambda: {})):
        sem_cls.return_value.acquire.return_value = True
        result = run_performance_test(
            execution_id=tr.id,
            test_case_id=case.id,
            host='https://example.com',
            users=10,
            spawn_rate=1,
            run_time='10s',
        )

    assert result['ok'] is True
    assert result['status'] == 'passed'

    tr.refresh_from_db()
    assert tr.status == 'passed'
    assert tr.status in dict(TestResult._meta.get_field('status').choices)
    assert tr.throughput == pytest.approx(40.0)
    assert tr.response_time_ms == 123
    assert tr.error_rate == pytest.approx(1.6)
    assert tr.duration_ms is not None

    perf = PerformanceTestResult.objects.get(test_result=tr)
    run = TestRun.objects.get(project=test_project, name=case.name)
    case_result = TestRunCaseResult.objects.get(test_run=run, sequence=1)
    assert perf.test_case_id == case.id
    assert perf.total_requests == 1200
    assert perf.failed_requests == 20
    assert perf.p95_response_time_ms == pytest.approx(320.0)
    assert perf.throughput == pytest.approx(40.0)
    assert perf.error_rate == pytest.approx(1.6)
    assert perf.response_time_distribution == FULL_PAYLOAD['stats']['response_time_distribution']
    assert perf.throughput_over_time == FULL_PAYLOAD['stats']['throughput_over_time']
    assert perf.response_time_over_time == FULL_PAYLOAD['stats']['response_time_over_time']
    assert perf.error_details == FINAL_STATS['stats']['errors']
    assert run.test_type == 'performance'
    assert run.status == 'passed'
    assert run.total_count == 1
    assert run.passed_count == 1
    assert run.failed_count == 0
    assert run.error_count == 0
    assert case_result.case_type == 'performance'
    assert case_result.status == 'passed'
    assert case_result.duration_ms == tr.duration_ms
    assert case_result.result_metadata['provider'] == 'performance'
    assert case_result.result_metadata['performance_test_case_id'] == case.id
    assert case_result.result_metadata['total_requests'] == 1200
    assert case_result.result_metadata['error_rate'] == pytest.approx(1.6)


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

    class _ProbeOkResponse:
        status_code = 200

    with patch('qa_center.semaphore.PerfSemaphore') as sem_cls, \
         patch('qa_center.execution.worker.create_runner', return_value=_FakeRunner(execution_id=tr.id)), \
         patch('qa_center.execution.worker.TargetProbeService.probe', return_value=MagicMock(ok=True, to_dict=lambda: {})):
        sem_cls.return_value.acquire.return_value = True
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
    run = TestRun.objects.get(project=test_project, name=case.name)
    case_result = TestRunCaseResult.objects.get(test_run=run, sequence=1)
    assert tr.status == 'failed'
    assert tr.status in dict(TestResult._meta.get_field('status').choices)
    assert PerformanceTestResult.objects.filter(test_result=tr).exists()
    assert run.test_type == 'performance'
    assert run.status == 'failed'
    assert run.total_count == 1
    assert run.passed_count == 0
    assert run.failed_count == 1
    assert run.error_count == 0
    assert case_result.case_type == 'performance'
    assert case_result.status == 'failed'
    assert case_result.result_metadata['provider'] == 'performance'
    assert case_result.result_metadata['error_rate'] == pytest.approx(1.6)


@pytest.mark.django_db
def test_should_stop_uses_aborted_flag_not_stopped_status(test_project, test_user):
    from qa_center.execution.worker import ExecutionWorker
    from qa_center.execution.job import TestJob

    tr = TestResult.objects.create(
        test_type='performance',
        name='stop-signal',
        project=test_project,
        status='running',
        executed_by=test_user,
        started_at=timezone.now(),
        aborted=True,
    )

    case = PerformanceTestCase.objects.create(
        name='dummy', url='https://example.com/', method='GET',
        project=test_project, created_by=test_user,
        concurrent_users=1, duration_seconds=1,
    )
    job = TestJob(test_case=case, host='https://example.com', execution_id=tr.id)
    worker = ExecutionWorker(job)

    assert worker._check_should_stop() is True

    tr.refresh_from_db()
    assert tr.status == 'running'
    assert tr.status in dict(TestResult._meta.get_field('status').choices)


class _StoppedRunner(_FakeRunner):
    """模拟用户中途停止：is_running 首次返回 True，之后返回 False。"""

    def __init__(self, execution_id=None, port_offset=0):
        super().__init__(execution_id=execution_id, port_offset=port_offset)
        self._running = True
        self._checks = 0

    def is_running(self):
        self._checks += 1
        return self._checks == 1


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

    class _ProbeOkResponse:
        status_code = 200
        ok = True

    with patch('qa_center.semaphore.PerfSemaphore') as sem_cls, \
         patch('qa_center.execution.worker.create_runner', return_value=_StoppedRunner(execution_id=tr.id)), \
         patch('qa_center.execution.worker.TargetProbeService.probe', return_value=MagicMock(ok=True, to_dict=lambda: {})):
        sem_cls.return_value.acquire.return_value = True
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
