"""Phase 1A regression tests — P0 fixes for DevOps platform.

Covers:
  - Empty TestTask returns 400 (no TestResult, no execution_count bump)
  - QuickTest refuses to simulate (returns 501)
  - UI executor missing returns clear error
  - Celery state machine uses completed/failed/running
  - Webhook invalid status rejected with 400
  - Strict env refuses mock pipeline trigger
  - Dev env allows mock with PipelineRun.is_mock=True
"""
import json as _json
import os
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import status as http_status


# ── helpers ──────────────────────────────────────────────────────────────


def _json_post(client, url, data):
    """POST with explicit JSON encoding to avoid test client UUID issues."""
    return client.post(url, data=_json.dumps(data), content_type='application/json')


def _create_test_task(*, project, user, name='Phase1A task', test_config=None,
                      test_type='api', trigger_type='manual', status='idle'):
    from qa_center.models import TestTask
    return TestTask.objects.create(
        project=project,
        created_by=user,
        name=name,
        test_type=test_type,
        trigger_type=trigger_type,
        test_config=test_config or {},
        status=status,
    )


def _create_api_case(*, project, user, name='Phase1A case', url='/api/phase1a/',
                     method='GET', expected_status=200):
    from qa_center.models import ApiAutoTestCase
    return ApiAutoTestCase.objects.create(
        project=project,
        created_by=user,
        name=name,
        url=url,
        method=method,
        expected_status=expected_status,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Empty TestTask must refuse execution
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEmptyTaskRejected:
    """Task with no api_cases or ui_cases must NOT execute."""

    def test_empty_task_execute_returns_400(self, auth_client, test_project, test_user):
        task = _create_test_task(project=test_project, user=test_user,
                                 test_config={})
        response = auth_client.post(f'/api/qa/devops/tasks/{task.id}/execute/')
        assert response.status_code == 400
        assert '未绑定任何真实测试用例' in response.data.get('error', '')

    def test_empty_task_execute_does_not_create_test_result(self, auth_client, test_project, test_user):
        from qa_center.models import TestResult
        before = TestResult.objects.filter(source='devops', project=test_project).count()
        task = _create_test_task(project=test_project, user=test_user, test_config={})
        auth_client.post(f'/api/qa/devops/tasks/{task.id}/execute/')
        after = TestResult.objects.filter(source='devops', project=test_project).count()
        assert before == after

    def test_empty_task_execute_does_not_increment_execution_count(self, auth_client, test_project, test_user):
        task = _create_test_task(project=test_project, user=test_user,
                                 test_config={})
        original_count = task.execution_count
        auth_client.post(f'/api/qa/devops/tasks/{task.id}/execute/')
        task.refresh_from_db()
        assert task.execution_count == original_count

    def test_empty_task_execute_does_not_change_status_to_running(self, auth_client, test_project, test_user):
        task = _create_test_task(project=test_project, user=test_user,
                                 test_config={})
        assert task.status == 'idle'
        auth_client.post(f'/api/qa/devops/tasks/{task.id}/execute/')
        task.refresh_from_db()
        assert task.status == 'idle'

    def test_task_with_api_cases_still_executes(self, auth_client, test_project, test_user, monkeypatch):
        """Sanity check: a task with valid cases must still be accepted."""
        monkeypatch.setenv("APP_ENV", "test")
        case = _create_api_case(project=test_project, user=test_user)
        task = _create_test_task(project=test_project, user=test_user,
                                 test_config={'api_cases': [case.id]})

        # Mock the execution so no background thread runs
        with patch('qa_center.views_devops._execute_ui_cases_safe', return_value=([], 0, 0)), \
             patch('qa_center.views_devops.threading.Thread') as mock_thread:
            response = auth_client.post(f'/api/qa/devops/tasks/{task.id}/execute/')

        assert response.status_code == 200
        task.refresh_from_db()
        assert task.status == 'running'


# ══════════════════════════════════════════════════════════════════════════
# 2. QuickTest refuses to simulate
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestQuickTestRefused:
    """QuickTest must NOT produce random results."""

    def test_quicktest_returns_501_without_real_executor(self, auth_client, test_project, test_user):
        # Phase 2A: QuickTest now uses real executor — returns 200 on success
        case = _create_api_case(project=test_project, user=test_user)
        with patch('qa_center.views_devops._execute_api_cases_via_unified') as mock_exec:
            mock_exec.return_value = [{
                'case_id': case.id, 'case_name': case.name,
                'passed': True, 'status_code': 200, 'response_time_ms': 5,
                'error_message': '', 'failure_type': '',
            }]
            response = _json_post(auth_client, '/api/qa/devops/quick-test/', {
                'type': 'api',
                'test_cases': [case.id],
                'project_id': str(test_project.id),
            })
        assert response.status_code == 200

    def test_quicktest_requires_project_id(self, auth_client):
        response = _json_post(auth_client, '/api/qa/devops/quick-test/', {
            'type': 'api',
            'test_cases': [1, 2],
        })
        assert response.status_code == 400
        assert 'project_id' in response.data.get('error', '').lower()

    def test_quicktest_requires_test_cases(self, auth_client, test_project):
        response = _json_post(auth_client, '/api/qa/devops/quick-test/', {
            'type': 'api',
            'project_id': str(test_project.id),
        })
        assert response.status_code == 400

    def test_quicktest_rejects_bad_test_type(self, auth_client, test_project):
        response = _json_post(auth_client, '/api/qa/devops/quick-test/', {
            'type': 'invalid_type',
            'test_cases': [1],
            'project_id': str(test_project.id),
        })
        assert response.status_code == 400

    def test_quicktest_does_not_create_test_result(self, auth_client, test_project):
        from qa_center.models import TestResult
        before = TestResult.objects.filter(project=test_project).count()
        _json_post(auth_client, '/api/qa/devops/quick-test/', {
            'type': 'api',
            'test_cases': [],
            'project_id': str(test_project.id),
        })
        after = TestResult.objects.filter(project=test_project).count()
        assert before == after

    def test_quicktest_validates_cases_belong_to_project(self, auth_client, test_project):
        """QuickTest now validates project ownership BEFORE returning 501."""
        response = _json_post(auth_client, '/api/qa/devops/quick-test/', {
            'type': 'api',
            'test_cases': [99999],
            'project_id': str(test_project.id),
        })
        # Permission check runs before 501: cross-project or non-existent cases → 400
        assert response.status_code == 400
        assert '不存在' in response.data.get('error', '')


# ══════════════════════════════════════════════════════════════════════════
# 3. UI executor missing returns clear error
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestUIExecutorSafe:
    """_execute_ui_cases_safe must not raise ImportError; returns structured errors."""

    def test_ui_cases_safe_handles_missing_executor(self, monkeypatch):
        """When views_ui_test module is absent, _execute_ui_cases_safe returns errors."""
        from qa_center.views_devops import _execute_ui_cases_safe

        # Make the import inside _execute_ui_cases_safe raise ImportError
        def _raise_import_error(*args, **kwargs):
            raise ImportError('Simulated missing module')

        monkeypatch.setattr(
            'qa_center.views_devops.execute_ui_test_cases',
            None,
            raising=False,
        )
        # Also make the actual import statement raise
        import builtins
        original_import = builtins.__import__

        def _mock_import(name, globals=None, locals=None, fromlist=(), level=0):
            if fromlist and 'execute_ui_test_cases' in fromlist:
                raise ImportError(f'Simulated missing module: {name}')
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, '__import__', _mock_import)

        results, passed, failed = _execute_ui_cases_safe([1, 2, 3])

        assert len(results) == 3
        assert passed == 0
        assert failed == 3
        for r in results:
            assert r['passed'] is False
            assert '未配置或不可用' in r['error_message']


# ══════════════════════════════════════════════════════════════════════════
# 4. Celery state machine uses completed / failed / running
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCeleryStateMachine:
    """Celery task must use the TestTask status vocabulary."""

    def test_already_completed_task_is_skipped(self, test_project, test_user):
        from qa_center.tasks_test_exec import execute_test_task

        task = _create_test_task(project=test_project, user=test_user,
                                 status='completed', test_config={'api_cases': [1]})
        result = execute_test_task.run(task.id)
        assert result['status'] == 'skipped'
        task.refresh_from_db()
        assert task.status == 'completed'

    def test_already_failed_task_is_skipped(self, test_project, test_user):
        from qa_center.tasks_test_exec import execute_test_task

        task = _create_test_task(project=test_project, user=test_user,
                                 status='failed', test_config={'api_cases': [1]})
        result = execute_test_task.run(task.id)
        assert result['status'] == 'skipped'
        task.refresh_from_db()
        assert task.status == 'failed'

    def test_running_task_is_allowed_to_retry(self, test_project, test_user, monkeypatch):
        """A task that is already 'running' is not skipped; Celery may retry it."""
        monkeypatch.setenv("APP_ENV", "test")
        from qa_center.tasks_test_exec import execute_test_task
        from qa_center.models import ApiAutoTestCase, ApiAutoTestResult, TestResult

        case = _create_api_case(project=test_project, user=test_user)
        task = _create_test_task(project=test_project, user=test_user,
                                 status='running', test_config={'api_cases': [case.id]})

        # Create a real ApiAutoTestResult and mirror so the Celery task
        # can find it via the TestResult filter chain.
        from django.utils import timezone
        auto_result = ApiAutoTestResult.objects.create(
            suite=case.suite,
            project=test_project,
            name='celery retry result',
            status='passed',
            total_cases=1,
            passed_cases=1,
            executed_by=test_user,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        TestResult.objects.create(
            test_type='api',
            name='celery retry mirrored',
            status='passed',
            project=test_project,
            executed_by=test_user,
            api_auto_result=auto_result,
            source='devops',
        )

        # Patch unified runner so it produces the pre-created result
        with patch('qa_center.tasks_test_exec.use_unified_runner_for_async_triggers', return_value=True), \
             patch('qa_center.tasks_test_exec.create_api_auto_single_case_orchestrator') as mock_orch:
            mock_orch.return_value.execute.return_value = {'test_result': auto_result}
            result = execute_test_task.run(task.id)

        assert result['status'] == 'success'
        task.refresh_from_db()
        assert task.status == 'completed'


# ══════════════════════════════════════════════════════════════════════════
# 5. Webhook invalid status rejected
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWebhookStatusWhitelist:
    """Webhook must validate status against a whitelist."""

    def _make_config(self, test_project, test_user):
        from qa_center.models import CiCdConfig
        return CiCdConfig.objects.create(
            project=test_project,
            created_by=test_user,
            name='Phase1A config',
            ci_type='jenkins',
            api_token='test-webhook-token-123',
        )

    def test_webhook_invalid_status_returns_400(self, client, test_project, test_user):
        config = self._make_config(test_project, test_user)
        response = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'bogus_status', 'external_run_id': 'run-1'},
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-webhook-token-123',
        )
        assert response.status_code == 400

    def test_webhook_valid_status_accepted(self, client, test_project, test_user):
        config = self._make_config(test_project, test_user)
        response = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'passed', 'external_run_id': 'run-2'},
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-webhook-token-123',
        )
        assert response.status_code == 201

    def test_webhook_missing_token_returns_403(self, client, test_project, test_user):
        config = self._make_config(test_project, test_user)
        response = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'passed', 'external_run_id': 'run-3'},
            content_type='application/json',
        )
        assert response.status_code == 403

    def test_webhook_invalid_status_does_not_create_pipeline_run(self, client, test_project, test_user):
        from qa_center.models import PipelineRun
        config = self._make_config(test_project, test_user)
        before = PipelineRun.objects.filter(cicd_config=config).count()
        client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'evil_hack_status', 'external_run_id': 'evil-1'},
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-webhook-token-123',
        )
        after = PipelineRun.objects.filter(cicd_config=config).count()
        assert before == after

    def test_webhook_error_messages_are_readable(self, client, test_project, test_user):
        """No garbled or escaped Chinese characters in error messages."""
        config = self._make_config(test_project, test_user)

        # Missing config
        resp = client.post('/api/qa/devops/cicd-config/99999/webhook/',
                           data={}, content_type='application/json')
        assert resp.status_code == 404
        error_text = resp.data.get('error', '')
        assert '?' not in error_text  # no garbled chars

        # Invalid status
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'invalid!!', 'external_run_id': 'r-1'},
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-webhook-token-123',
        )
        assert resp.status_code == 400
        error_text = resp.data.get('error', '')
        assert '?' not in error_text


# ══════════════════════════════════════════════════════════════════════════
# 6. Strict environment blocks mock pipeline trigger
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPipelineMockGuard:
    """Strict envs must not simulate pipelines. Dev env may use mock."""

    def _make_config(self, test_project, test_user):
        from qa_center.models import CiCdConfig
        return CiCdConfig.objects.create(
            project=test_project,
            created_by=test_user,
            name='Phase1A pipeline config',
            ci_type='jenkins',
            api_token='test-trigger-token',
        )

    def test_strict_env_rejects_mock_trigger(self, auth_client, test_project, test_user, monkeypatch):
        """When USE_REAL_CI=False and APP_ENV=production, trigger returns 409."""
        monkeypatch.setenv("APP_ENV", "production")
        config = self._make_config(test_project, test_user)

        with patch('qa_center.views_devops.settings.USE_REAL_CI', False):
            response = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )
        assert response.status_code == 409

    def test_strict_env_mock_trigger_does_not_create_pipeline_run(self, auth_client, test_project, test_user, monkeypatch):
        from qa_center.models import PipelineRun
        monkeypatch.setenv("APP_ENV", "production")
        config = self._make_config(test_project, test_user)
        before = PipelineRun.objects.filter(cicd_config=config).count()

        with patch('qa_center.views_devops.settings.USE_REAL_CI', False):
            auth_client.post(f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                             data={}, format='json')

        after = PipelineRun.objects.filter(cicd_config=config).count()
        assert before == after

    def test_dev_env_allows_mock_trigger(self, auth_client, test_project, test_user, monkeypatch):
        """In local/dev with USE_REAL_CI=False, trigger creates a mock PipelineRun."""
        monkeypatch.setenv("APP_ENV", "local")
        config = self._make_config(test_project, test_user)

        # Patch out the background thread to avoid DB cleanup race
        with patch('qa_center.views_devops.settings.USE_REAL_CI', False), \
             patch('qa_center.views_devops.threading.Thread') as mock_thread_cls:
            response = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )
        assert response.status_code == 201
        assert response.data.get('is_mock') is True

    def test_dev_env_mock_run_has_is_mock_true(self, auth_client, test_project, test_user, monkeypatch):
        """Mock PipelineRun must have is_mock=True in the database."""
        from qa_center.models import PipelineRun
        monkeypatch.setenv("APP_ENV", "local")
        config = self._make_config(test_project, test_user)

        with patch('qa_center.views_devops.settings.USE_REAL_CI', False), \
             patch('qa_center.views_devops.threading.Thread') as mock_thread_cls:
            resp = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )

        run_id = resp.data.get('run_id')
        assert run_id is not None
        run = PipelineRun.objects.get(id=run_id)
        assert run.is_mock is True

    def test_mock_run_result_is_deterministic_not_random(self, auth_client, test_project, test_user, monkeypatch):
        """Mock pipeline result must NOT use random — always 'passed' with empty summary."""
        from qa_center.models import PipelineRun
        from qa_center.views_devops import PipelineRunTriggerView

        monkeypatch.setenv("APP_ENV", "local")
        config = self._make_config(test_project, test_user)

        with patch('qa_center.views_devops.settings.USE_REAL_CI', False), \
             patch('qa_center.views_devops.threading.Thread') as mock_thread_cls:
            resp = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )

        run_id = resp.data.get('run_id')
        assert run_id is not None

        # Manually invoke _simulate_run to verify it's deterministic
        run = PipelineRun.objects.get(id=run_id)
        view = PipelineRunTriggerView()
        view._simulate_run(run)
        run.refresh_from_db()

        assert run.status == 'passed'
        assert run.is_mock is True
        summary = run.test_results_summary or {}
        assert summary.get('total', 0) == 0
        assert 'mock' in (run.log_output or '').lower()
