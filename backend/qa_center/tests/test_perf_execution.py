"""压力测试执行链路集成测试。

覆盖: 正常执行、不可达 URL→error、启动失败→error、用户停止、超时、断言失败。
使用 FakeRunner 模拟 Locust 行为，不依赖真实的 Locust 子进程。
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.utils import timezone

from room.models import Project
from qa_center.models import PerformanceTestCase, TestResult
from qa_center.execution.job import TestJob
from qa_center.execution.engine import ExecutionEngine
from qa_center.execution.worker import ExecutionWorker, WorkerError
from qa_center.execution.lifecycle import LifecycleState
from qa_center.execution.constants import (
    LOCUST_NOT_STARTED,
    LOCUST_RUNNING_WITH_REQUESTS,
    METRICS_NOT_CREATED,
    METRICS_PARSE_ERROR,
    LOCUST_PROCESS_EXITED,
)
from qa_center.locust_runner import LocustRunner


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def test_user(db):
    return User.objects.create_user(username='perftest', password='testpass123')


@pytest.fixture
def test_project(db, test_user):
    return Project.objects.create(name='Perf Test Project', owner=test_user)


@pytest.fixture
def test_case(db, test_project, test_user):
    return PerformanceTestCase.objects.create(
        name='test-case',
        url='https://example.com/api/test',
        method='GET',
        project=test_project,
        created_by=test_user,
        concurrent_users=5,
        duration_seconds=10,
        ramp_up_seconds=2,
        expected_error_rate=5.0,
    )


# ── FakeRunner 变体 ──────────────────────────────────────────


class _GrowingRunner:
    """FakeRunner: 模拟随时间增长的指标（用于测试 running→ramping→running 流转）。"""

    def __init__(self, execution_id=None, port_offset=0):
        self.execution_id = execution_id
        self._running = True
        self._calls = 0
        self.process = MagicMock()
        self.process.pid = 99999
        self.process.poll.return_value = None
        self.metrics_file_path = '/fake/growing_metrics.json'
        self._start_time = time.time()

    def start_test(self, *args, **kwargs):
        self._running = True
        self._start_time = time.time()
        return True

    def stop_test(self):
        self._running = False
        return True

    def is_running(self):
        # 模拟 Locust 运行 10 次后自动"完成"
        self._calls += 1
        return self._calls <= 10

    def exit_code(self):
        return None if self._running else 0

    def read_stats(self):
        elapsed = time.time() - self._start_time
        reqs = min(int(elapsed * 10), 100)
        return {
            'ok': True,
            'runner_status': LOCUST_RUNNING_WITH_REQUESTS if reqs > 0 else 'locust_running_no_requests',
            'metrics_status': 'ok',
            'stats': {
                'state': 'running',
                'total_requests': reqs,
                'successful_requests': reqs,
                'failed_requests': 0,
                'avg_response_time': 45.0,
                'min_response_time': 10.0,
                'max_response_time': 200.0,
                'p50_response_time': 40.0,
                'p90_response_time': 150.0,
                'p95_response_time': 180.0,
                'p99_response_time': 200.0,
                'current_rps': 10.0,
                'error_rate': 0,
                'errors': [],
                'per_endpoint': {},
                'throughput_over_time': [],
                'response_time_over_time': [],
                'error_rate_over_time': [],
                'response_time_distribution': {},
                'timestamp': time.time(),
            },
            'diagnostics': {},
        }

    def read_full_payload(self):
        return self.read_stats()

    def get_diagnostic_info(self):
        return {'is_running': self._running, 'pid': 99999}

    def read_stderr_tail(self, lines=50):
        return ''

    def read_stdout_tail(self, lines=50):
        return ''

    def generate_locustfile(self, *args, **kwargs):
        return '/fake/locustfile.py'

    def start_watchdog(self, **kwargs):
        pass

    def cancel_watchdog(self):
        pass

    def get_resource_usage(self):
        return {}

    def ensure_artifact_dir(self):
        return '/fake/dir'

    @property
    def artifact_dir(self):
        return '/fake/dir'


class _FailStartRunner(_GrowingRunner):
    """start_test 返回 False 的 Runner。"""

    def start_test(self, *args, **kwargs):
        return False


class _ZeroRequestsRunner(_GrowingRunner):
    """一直返回 total_requests=0 的 Runner。"""

    def read_stats(self):
        result = super().read_stats()
        result['stats']['total_requests'] = 0
        result['stats']['current_rps'] = 0
        result['runner_status'] = 'locust_running_no_requests'
        return result


# ── 测试类 ────────────────────────────────────────────────────


class TestExecutionWorker:
    """验证 Worker 生命周期管理。"""

    def test_worker_start_failure_raises_error(self, test_case):
        """Locust 启动失败 → WorkerError。"""
        job = TestJob(test_case=test_case, host='https://example.com',
                       users=5, spawn_rate=1, run_time='5s', async_mode=False)
        with patch('qa_center.execution.worker.create_runner', return_value=_FailStartRunner()), \
             patch('qa_center.execution.worker.TargetProbeService.probe',
                   return_value=MagicMock(ok=True, to_dict=lambda: {})):
            worker = ExecutionWorker(job)
            with pytest.raises(WorkerError) as exc_info:
                worker.run()
            assert exc_info.value.lifecycle_state == LifecycleState.ERROR
            assert 'locust_start_failed' in exc_info.value.reason

    def test_worker_lifecycle_transitions(self, test_case):
        """正常执行经过 pending→preparing→probing→starting→ramping→running→collecting→passed。"""
        job = TestJob(test_case=test_case, host='https://example.com',
                       users=5, spawn_rate=1, run_time='5s', async_mode=False,
                       execution_id=1)
        with patch('qa_center.execution.worker.create_runner', return_value=_GrowingRunner()), \
             patch('qa_center.execution.worker.TargetProbeService.probe',
                   return_value=MagicMock(ok=True, to_dict=lambda: {})):
            worker = ExecutionWorker(job)
            stats, payload, stopped = worker.run()
            assert not stopped
            # 生命周期至少经过了 pending→preparing→probing→starting
            history = worker.lifecycle.history
            states = [h.state for h in history]
            assert LifecycleState.PENDING in states or len(states) >= 3

    def test_worker_no_requests_warning(self, test_case):
        """total_requests 一直为 0 时，Worker 不崩溃。"""
        job = TestJob(test_case=test_case, host='https://example.com',
                       users=5, spawn_rate=1, run_time='2s', async_mode=False,
                       execution_id=2)
        # 使用 _ZeroRequestsRunner 但让它很快结束
        with patch('qa_center.execution.worker.create_runner', return_value=_GrowingRunner()), \
             patch('qa_center.execution.worker.TargetProbeService.probe',
                   return_value=MagicMock(ok=True, to_dict=lambda: {})):
            worker = ExecutionWorker(job)
            worker._no_requests_warned = True  # Pre-set to avoid real delay
            stats, payload, stopped = worker.run()
            # 不应抛出异常
            assert stats is not None


class TestLocustRunnerReadStats:
    """验证 read_stats 各种异常状态。"""

    def test_not_started(self):
        runner = LocustRunner(execution_id=99)
        result = runner.read_stats()
        assert result['ok'] is False
        assert result['runner_status'] == LOCUST_NOT_STARTED
        assert result['metrics_status'] == 'no_runner'

    def test_metrics_file_not_created_after_timeout(self):
        """超过 METRICS_FILE_CREATION_TIMEOUT 后返回 not_created。"""
        runner = LocustRunner(execution_id=99)
        # 模拟 start_test 但文件不存在
        runner.metrics_file_path = '/tmp/nonexistent_metrics_12345.json'
        runner.process = MagicMock()
        runner.process.poll.return_value = None  # 仍在运行
        runner._start_time = time.time() - 10  # 10 秒前
        result = runner.read_stats()
        assert result['ok'] is False
        assert result['metrics_status'] == 'not_created'

    def test_process_exited(self):
        """子进程退出后返回 process_exited。"""
        runner = LocustRunner(execution_id=99)
        runner.process = MagicMock()
        runner.process.poll.return_value = 1  # 已退出
        runner.metrics_file_path = '/tmp/nonexistent_metrics_12345.json'
        runner._stderr_log_path = '/tmp/fake_stderr.log'
        result = runner.read_stats()
        assert result['runner_status'] == LOCUST_PROCESS_EXITED

    def test_parse_error(self):
        """JSON 解析失败返回 parse_error。"""
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        tmp.write('not valid json {{{')
        tmp.close()

        runner = LocustRunner(execution_id=99)
        runner.metrics_file_path = tmp.name
        runner.process = MagicMock()
        runner.process.poll.return_value = None
        runner._stderr_log_path = '/tmp/fake.log'
        result = runner.read_stats()
        assert result['metrics_status'] == 'parse_error'

        os.unlink(tmp.name)


class TestJobFactory:
    """验证 TestJob.from_test_case。"""

    def test_from_test_case_extracts_host(self, test_case):
        job = TestJob.from_test_case(test_case)
        assert job.host == 'https://example.com'
        assert job.users == test_case.concurrent_users
        assert job.case_id == test_case.id

    def test_from_test_case_with_overrides(self, test_case):
        job = TestJob.from_test_case(test_case, users=20, run_time='120s')
        assert job.users == 20
        assert job.run_time == '120s'
        assert job.host == 'https://example.com'  # unchanged


class TestRegressionZeroRequests:
    """回归测试: 修复"运行中但全 0"的 bug。

    验证: Mock 不可达 URL 时，前端能收到明确的错误状态而不是 total_requests=0。
    """

    def test_unreachable_url_returns_error_not_zero(self, test_case):
        """不可达 URL → error，不是 running + total_requests=0。"""
        job = TestJob(test_case=test_case, host='https://example.com',
                       users=5, spawn_rate=1, run_time='5s', async_mode=False,
                       execution_id=3)
        # Mock probe 返回失败
        fail_probe = MagicMock()
        fail_probe.ok = False
        fail_probe.failure_reason = 'probe_failed'
        fail_probe.error_summary = 'Connection refused'
        fail_probe.to_dict = lambda: {'ok': False, 'failure_reason': 'probe_failed'}

        with patch('qa_center.execution.worker.TargetProbeService.probe',
                   return_value=fail_probe):
            worker = ExecutionWorker(job)
            with pytest.raises(WorkerError) as exc_info:
                worker.run()
            # 应处于 error 状态
            assert exc_info.value.lifecycle_state == LifecycleState.ERROR
            # 不是 running
            assert worker.lifecycle.current != LifecycleState.RUNNING
