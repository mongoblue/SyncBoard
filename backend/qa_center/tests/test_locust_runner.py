import pytest
from unittest.mock import patch, MagicMock
from qa_center.locust_runner import LocustRunner
from qa_center.execution.constants import LOCUST_NOT_STARTED


class TestLocustRunner:
    """验证 LocustRunner 纯适配器行为。"""

    def test_runner_initialization(self):
        """初始化后 process / metrics_file_path 为 None。"""
        runner = LocustRunner(execution_id=42)
        assert runner.execution_id == 42
        assert runner.process is None
        assert runner.locustfile_path is None
        assert runner.metrics_file_path is None

    def test_is_running_false_when_no_process(self):
        """无子进程时 is_running 返回 False。"""
        runner = LocustRunner(execution_id=1)
        assert runner.is_running() is False

    def test_stop_test_terminates_process(self):
        """stop_test 清理进程并置 process 为 None。"""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # 进程仍在运行

        runner = LocustRunner(execution_id=1)
        runner.process = mock_process
        # cannot test _terminate_process_group with mock; just ensure cleanup
        runner.stop_test()
        assert runner.process is None

    def test_read_stats_returns_status_when_no_file(self):
        """未启动时 read_stats 返回统一 schema（locust_not_started）。"""
        runner = LocustRunner(execution_id=99)
        result = runner.read_stats()
        assert result['runner_status'] == LOCUST_NOT_STARTED
        assert result['ok'] is False
        assert result['metrics_status'] == 'no_runner'
        assert 'stats' in result
        assert result['stats']['total_requests'] == 0

    def test_read_full_payload_returns_with_diagnostic_when_no_file(self):
        """未启动时 read_full_payload 返回含 diagnostics 的统一 schema（含 is_running）。"""
        runner = LocustRunner(execution_id=99)
        payload = runner.read_full_payload()
        assert payload['runner_status'] == LOCUST_NOT_STARTED
        assert 'diagnostics' in payload
        assert payload['diagnostics']['is_running'] is False
        assert payload['ok'] is False
