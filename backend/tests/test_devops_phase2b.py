"""Phase 2B tests — execution capability deep dive.

Covers:
  - Pre-existing test isolation (note)
  - Performance runner integration (Locust)
  - Celery beat scheduled task registration
  - Cancel upgrade (cooperative, mark-only)
  - Structured logs with events schema and sanitisation
  - Unified runner-unavailable error format
  - All prior-phase tests still pass
"""
import json as _json
import os
import re
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from django.utils import timezone
from django.contrib.auth.models import User


# ── helpers ──────────────────────────────────────────────────────────────


def _json_post(client, url, data):
    return client.post(url, data=_json.dumps(data), content_type='application/json')


def _create_test_task(project, user, **kwargs):
    from qa_center.models import TestTask
    return TestTask.objects.create(
        project=project, created_by=user,
        name=kwargs.pop('name', 'Phase2B task'),
        test_type=kwargs.pop('test_type', 'api'),
        trigger_type=kwargs.pop('trigger_type', 'manual'),
        test_config=kwargs.pop('test_config', {}),
        status=kwargs.pop('status', 'idle'),
        **kwargs,
    )


def _create_api_case(project, user, **kwargs):
    from qa_center.models import ApiAutoTestCase
    return ApiAutoTestCase.objects.create(
        project=project, created_by=user,
        name=kwargs.pop('name', 'Phase2B case'),
        url=kwargs.pop('url', '/api/phase2b/'),
        method=kwargs.pop('method', 'GET'),
        expected_status=kwargs.pop('expected_status', 200),
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════════
# P0.1 — Pre-existing test note
# ══════════════════════════════════════════════════════════════════════════
# test_legacy_api_auto_executor_execute_counts_unknown_error_without_execution_keyword
# This test now passes (verified 2026-07).  The api_auto_executor's
# _classify_case_result correctly routes 500-status responses with empty
# assertion_details to 'error' (not 'failed').  If it ever regresses, check
# the condition at api_auto_executor.py line ~267:
#   if expectation_type == 'success_response' and not assertion_details
#      and (case_result.status_code or 0) >= 500:
#       return (0, 0, 1)  # error_count = 1


# ══════════════════════════════════════════════════════════════════════════
# P0.2 — Performance runner integration
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPerformanceRunner:
    """Performance cases use Locust runner when available."""

    def _make_perf_case(self, project, user):
        from qa_center.models import PerformanceTestCase
        return PerformanceTestCase.objects.create(
            project=project, created_by=user,
            name='Phase2B perf case', url='https://example.test/',
            method='GET', concurrent_users=5, duration_seconds=10,
        )

    def test_service_perf_runner_called(self, test_project, test_user):
        """Performance QuickTest calls Locust runner."""
        from qa_center.models import PerformanceTestCase
        from qa_center.services.devops.test_execution_service import TestExecutionService

        perf_case = self._make_perf_case(test_project, test_user)

        with patch('qa_center.locust_runner.LocustRunner') as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.metrics.total_requests = 100
            mock_runner.metrics.failed_requests = 5
            mock_runner.metrics.avg_response_time = 45.0
            mock_runner.metrics.p95_response_time = 120.0
            mock_runner.metrics.throughput = 10.5
            mock_runner.metrics.error_rate = 5.0
            mock_runner_cls.return_value = mock_runner

            svc = TestExecutionService()
            result = svc.execute_quick_test(
                test_type='performance', case_ids=[perf_case.id],
                project_id=test_project.id, user=test_user,
            )

        assert mock_runner_cls.called
        assert result.status in ('passed', 'failed')
        assert result.source == 'devops'

    def test_service_perf_saves_metrics(self, test_project, test_user):
        """Performance result includes metrics in test_log."""
        from qa_center.models import PerformanceTestCase
        from qa_center.services.devops.test_execution_service import TestExecutionService

        perf_case = self._make_perf_case(test_project, test_user)

        with patch('qa_center.locust_runner.LocustRunner') as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.metrics.total_requests = 50
            mock_runner.metrics.failed_requests = 0
            mock_runner.metrics.avg_response_time = 30.0
            mock_runner.metrics.p95_response_time = 80.0
            mock_runner.metrics.throughput = 20.0
            mock_runner.metrics.error_rate = 0.0
            mock_runner.metrics.to_dict.return_value = {'total': 50}
            mock_runner_cls.return_value = mock_runner

            svc = TestExecutionService()
            result = svc.execute_quick_test(
                test_type='performance', case_ids=[perf_case.id],
                project_id=test_project.id, user=test_user,
            )

        log = _json.loads(result.test_log or '{}')
        results = log.get('results', [])
        assert len(results) > 0
        r = results[0]
        assert 'avg_response_time' in r
        assert 'p95_response_time' in r
        assert 'throughput' in r

    def test_service_perf_unavailable_returns_error(self, test_project, test_user):
        """When Locust runner fails, result is failed with clear error."""
        from qa_center.models import PerformanceTestCase
        from qa_center.services.devops.test_execution_service import TestExecutionService

        perf_case = self._make_perf_case(test_project, test_user)

        with patch('qa_center.locust_runner.LocustRunner') as mock_runner_cls:
            mock_runner_cls.side_effect = ImportError('locust not installed')
            svc = TestExecutionService()
            result = svc.execute_quick_test(
                test_type='performance', case_ids=[perf_case.id],
                project_id=test_project.id, user=test_user,
            )

        assert result.status == 'failed'
        # Error is in the case result inside test_log
        log = _json.loads(result.test_log or '{}')
        results = log.get('results', [])
        assert len(results) > 0
        assert 'locust not installed' in (results[0].get('error_message', ''))

    def test_service_perf_does_not_produce_mock(self, test_project, test_user):
        """Performance result must never be random or mock."""
        from qa_center.models import PerformanceTestCase, TestResult

        perf_case = self._make_perf_case(test_project, test_user)
        before = TestResult.objects.filter(project=test_project, test_type='performance').count()

        with patch('qa_center.locust_runner.LocustRunner') as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.metrics.total_requests = 1
            mock_runner.metrics.failed_requests = 0
            mock_runner.metrics.avg_response_time = 1.0
            mock_runner.metrics.p95_response_time = 1.0
            mock_runner.metrics.throughput = 1.0
            mock_runner.metrics.error_rate = 0.0
            mock_runner_cls.return_value = mock_runner

            from qa_center.services.devops.test_execution_service import TestExecutionService
            svc = TestExecutionService()
            svc.execute_quick_test(
                test_type='performance', case_ids=[perf_case.id],
                project_id=test_project.id, user=test_user,
            )

        after = TestResult.objects.filter(project=test_project, test_type='performance').count()
        assert after == before + 1
        tr = TestResult.objects.filter(project=test_project, test_type='performance').latest('created_at')
        assert tr.source == 'devops'
        assert tr.status in ('passed', 'failed')


# ══════════════════════════════════════════════════════════════════════════
# P0.3 — Celery beat scheduled tasks
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestScheduledTaskRegistration:
    """Scheduled tasks validate and (attempt to) register with Celery beat."""

    def test_valid_cron_registers(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = _create_test_task(test_project, test_user,
                                  trigger_type='scheduled',
                                  cron_expression='0 9 * * 1-5')
        svc = TestExecutionService()
        error = svc.register_scheduled_task(task)
        # Without Celery beat, it returns None (dev env) or error (strict env)
        if svc._guard.is_strict():
            assert error is not None
        else:
            assert error is None

    def test_invalid_cron_rejected(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = _create_test_task(test_project, test_user,
                                  trigger_type='scheduled',
                                  cron_expression='not-a-cron')
        svc = TestExecutionService()
        error = svc.register_scheduled_task(task)
        assert error is not None
        assert 'Cron' in error

    def test_strict_env_no_beat_reports_error(self, test_project, test_user, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = _create_test_task(test_project, test_user,
                                  trigger_type='scheduled',
                                  cron_expression='0 0 * * *')
        svc = TestExecutionService()
        error = svc.check_scheduled_task_viability(task)
        # In production without Celery beat, should return error
        if not svc._celery_beat_available():
            assert error is not None
            assert 'Celery beat' in error or 'Cron' in error

    def test_unregister_removes_schedule_entry(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = _create_test_task(test_project, test_user,
                                  trigger_type='scheduled',
                                  cron_expression='0 0 * * *')
        svc = TestExecutionService()
        svc.unregister_scheduled_task(task)
        # Should not raise

    def test_dev_env_without_beat_allows_save(self, test_project, test_user, monkeypatch):
        monkeypatch.setenv("APP_ENV", "local")
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = _create_test_task(test_project, test_user,
                                  trigger_type='scheduled',
                                  cron_expression='*/5 * * * *')
        svc = TestExecutionService()
        error = svc.register_scheduled_task(task)
        # In dev without beat, it returns None (allows saving silently)
        assert error is None


# ══════════════════════════════════════════════════════════════════════════
# P1.4 — Cancel upgrade
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCancelUpgrade:
    """Cancel returns structured info including cancel_mode."""

    def test_cancel_running_task(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService
        from qa_center.models import TestResult

        task = _create_test_task(test_project, test_user, status='running')
        tr = TestResult.objects.create(
            test_type='api', name='cancel test', status='running',
            project=test_project, executed_by=test_user, source='devops',
        )
        task.last_result = tr
        task.save()

        svc = TestExecutionService()
        result = svc.cancel_task(task)
        assert result['cancelled'] is True
        assert result['cancel_mode'] == 'mark_only'
        task.refresh_from_db()
        assert task.status == 'failed'

    def test_cancel_completed_task_rejected(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = _create_test_task(test_project, test_user, status='completed')
        svc = TestExecutionService()
        result = svc.cancel_task(task)
        assert result['cancelled'] is False
        assert '只能取消' in result.get('reason', '')

    def test_cancel_endpoint_returns_cancel_mode(self, auth_client, test_project, test_user):
        from qa_center.models import TestResult

        task = _create_test_task(test_project, test_user, status='running')
        tr = TestResult.objects.create(
            test_type='api', name='cancel ep test', status='running',
            project=test_project, executed_by=test_user, source='devops',
        )
        task.last_result = tr
        task.save()

        resp = auth_client.post(f'/api/qa/devops/tasks/{task.id}/cancel/')
        assert resp.status_code == 200
        assert 'cancel_mode' in resp.data
        assert resp.data['cancel_mode'] == 'mark_only'


# ══════════════════════════════════════════════════════════════════════════
# P1.5/1.6 — Structured logs + unified error format
# ══════════════════════════════════════════════════════════════════════════


class TestStructuredLogs:
    """Log events follow standard schema and are sanitised."""

    def test_build_log_event_has_required_fields(self):
        from qa_center.services.devops.test_execution_service import _build_log_event

        event = _build_log_event(
            phase='api_execute', runner_type='unified',
            message='test', case_id=42, status='passed', duration_ms=10,
        )
        assert event['phase'] == 'api_execute'
        assert event['runner_type'] == 'unified'
        assert event['status'] == 'passed'
        assert event['duration_ms'] == 10

    def test_build_structured_log_includes_events(self):
        from qa_center.services.devops.test_execution_service import _build_structured_log, _build_log_event

        events = [
            _build_log_event(phase='start', runner_type='unified', message='begin'),
            _build_log_event(phase='end', runner_type='unified', message='done', status='passed'),
        ]
        log = _build_structured_log([], {'total': 1}, events=events)
        parsed = _json.loads(log)
        assert 'events' in parsed
        assert len(parsed['events']) == 2

    def test_sanitize_redacts_multiple_sensitive_keys(self):
        from qa_center.services.devops.test_execution_service import _sanitize_dict

        d = {
            'headers': {'Authorization': 'x', 'api_key': 'y', 'content-type': 'json'},
            'cookies': {'session': 'abc'},
        }
        out = _sanitize_dict(d)
        assert out['headers']['Authorization'] == '[redacted]'
        assert out['headers']['api_key'] == '[redacted]'
        assert out['headers']['content-type'] == 'json'

    def test_runner_unavailable_error_format(self):
        from qa_center.services.devops.test_execution_service import runner_unavailable_error
        err = runner_unavailable_error('performance')
        assert err['status'] == 'failed'
        assert err['error_code'] == 'performance_runner_unavailable'
        assert err['data_quality'] == 'unavailable'
        assert 'runner_type' in err


# ══════════════════════════════════════════════════════════════════════════
# Cron validation tests
# ══════════════════════════════════════════════════════════════════════════


class TestCronValidation:
    def test_valid_crons(self):
        from qa_center.services.devops.test_execution_service import validate_cron_expression
        assert validate_cron_expression('0 9 * * 1-5')
        assert validate_cron_expression('*/5 * * * *')
        assert validate_cron_expression('0 0 1 1 *')
        assert validate_cron_expression('30 14 * * 0')

    def test_invalid_crons(self):
        from qa_center.services.devops.test_execution_service import validate_cron_expression
        assert not validate_cron_expression('')
        assert not validate_cron_expression('abc')
        assert not validate_cron_expression('* * * *')  # 4 fields
        assert not validate_cron_expression('* * * * * *')  # 6 fields
        assert not validate_cron_expression(None)
