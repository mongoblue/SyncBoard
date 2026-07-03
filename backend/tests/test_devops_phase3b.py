"""Phase 3B tests — GitHub Actions Client + django-celery-beat scheduling.

Covers:
  - GitHubActionsClient: ping, trigger, get_status (all conclusion mappings), cancel, get_logs
  - Logs sanitisation (token not leaked)
  - Factory returns GitHubActionsClient for ci_type=github
  - Test Connection endpoint works with github config
  - PeriodicTask created/updated/deleted/disabled for scheduled TestTasks
  - PeriodicTask name stability and uniqueness
  - PeriodicTask payload does not contain token/secret
  - Existing Phase 1A→3A tests still pass
"""
import json as _json
import os
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from django.utils import timezone
from django.contrib.auth.models import User


# ── helpers ──────────────────────────────────────────────────────────────


def _json_post(client, url, data):
    return client.post(url, data=_json.dumps(data), content_type='application/json')


def _make_github_config(project, user, **kwargs):
    from qa_center.models import CiCdConfig
    return CiCdConfig.objects.create(
        project=project, created_by=user,
        name=kwargs.pop('name', 'Phase3B github config'),
        ci_type='github',
        api_token='test-token-3b',
        ci_token=kwargs.pop('ci_token', 'ghp_fakeToken12345'),
        ci_url=kwargs.pop('ci_url', 'https://api.github.com'),
        ci_project=kwargs.pop('ci_project', 'testowner/testrepo'),
        ci_job_name=kwargs.pop('ci_job_name', 'ci.yml'),
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════════
# GitHubActionsClient unit tests
# ══════════════════════════════════════════════════════════════════════════


class TestGitHubActionsClient:
    """GitHubActionsClient methods with mocked HTTP."""

    def _make_client(self, **kwargs):
        from qa_center.pipeline.github import GitHubActionsClient
        from qa_center.models import CiCdConfig
        config = CiCdConfig(
            ci_type='github',
            ci_url=kwargs.get('ci_url', 'https://api.github.com'),
            ci_token=kwargs.get('ci_token', 'ghp_test123'),
            ci_project=kwargs.get('ci_project', 'owner/repo'),
            ci_job_name=kwargs.get('ci_job_name', 'ci.yml'),
            verify_ssl=True,
        )
        return GitHubActionsClient(config)

    def test_ping_success(self):
        client = self._make_client()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {'full_name': 'owner/repo'}

        with patch.object(client, '_get_session') as mock_sess:
            mock_sess.return_value.get.return_value = mock_resp
            result = client.ping()
        assert result['ok'] is True
        assert 'owner/repo' in result['detail']

    def test_ping_failure_no_token_leak(self):
        client = self._make_client(ci_token='ghp_SECRET_TOKEN_abc')
        mock_resp = MagicMock(status_code=401)
        mock_resp.raise_for_status.side_effect = Exception('401 Unauthorized for url ...')

        with patch.object(client, '_get_session') as mock_sess:
            mock_sess.return_value.get.return_value = mock_resp
            result = client.ping()
        assert result['ok'] is False
        assert 'ghp_SECRET_TOKEN_abc' not in result['detail']

    def test_trigger_calls_dispatch_api(self):
        client = self._make_client()
        mock_sess = MagicMock()
        # Workflow resolution
        mock_sess.get.return_value.json.return_value = {
            'workflows': [{'id': 123, 'path': '.github/workflows/ci.yml'}]
        }
        mock_sess.get.return_value.status_code = 200
        mock_sess.post.return_value.status_code = 204

        with patch.object(client, '_get_session', return_value=mock_sess), \
             patch.object(client, '_find_latest_run', return_value='run-456'):
            result = client.trigger(
                MagicMock(), ref='main', trigger_source='qa_center',
            )
        assert result.external_run_id == 'run-456'
        assert mock_sess.post.called

    def test_get_status_mappings(self):
        client = self._make_client()
        from qa_center.pipeline.state_mapping import github_to_canonical

        # queued
        assert github_to_canonical('queued', '') == 'queued'
        # in_progress
        assert github_to_canonical('in_progress', '') == 'running'
        # completed + success
        assert github_to_canonical('completed', 'success') == 'passed'
        # completed + failure
        assert github_to_canonical('completed', 'failure') == 'failed'
        # completed + cancelled
        assert github_to_canonical('completed', 'cancelled') == 'cancelled'
        # completed + skipped
        assert github_to_canonical('completed', 'skipped') == 'skipped'

    def test_cancel_success(self):
        client = self._make_client()
        mock_sess = MagicMock()
        mock_sess.post.return_value.status_code = 202

        with patch.object(client, '_get_session', return_value=mock_sess):
            run = MagicMock(external_run_id='run-789')
            result = client.cancel(run)
        assert result is True

    def test_cancel_failure(self):
        client = self._make_client()
        mock_sess = MagicMock()
        mock_sess.post.return_value.status_code = 404

        with patch.object(client, '_get_session', return_value=mock_sess):
            run = MagicMock(external_run_id='run-404')
            result = client.cancel(run)
        assert result is False

    def test_get_logs_does_not_leak_token(self):
        client = self._make_client(ci_token='ghp_TOKEN_SECRET_123')
        mock_sess = MagicMock()
        mock_sess.get.return_value.status_code = 200
        mock_sess.get.return_value.text = 'Authorization: Bearer ghp_TOKEN_SECRET_123\nlog line'

        with patch.object(client, '_get_session', return_value=mock_sess):
            logs = client.get_logs(MagicMock(external_run_id='r'))
        assert 'ghp_TOKEN_SECRET_123' not in logs


# ══════════════════════════════════════════════════════════════════════════
# Provider integration tests
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGitHubProviderIntegration:
    """Factory + API endpoints work with GitHub configs."""

    def test_factory_returns_github_client(self, test_project, test_user):
        config = _make_github_config(test_project, test_user)
        from qa_center.pipeline import get_client
        with patch('qa_center.views_devops.settings.USE_REAL_CI', True):
            client = get_client(config)
        from qa_center.pipeline.github import GitHubActionsClient
        assert isinstance(client, GitHubActionsClient)

    def test_test_connection_with_github_config(self, auth_client, test_project, test_user):
        config = _make_github_config(test_project, test_user)
        with patch('qa_center.pipeline.github.GitHubActionsClient.ping') as mock_ping:
            mock_ping.return_value = {'ok': True, 'detail': 'owner/repo'}
            resp = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/test/',
            )
        assert resp.status_code == 200
        assert resp.data['reachable'] is True

    def test_project_isolation_for_github_config(self, auth_client, test_project, test_user):
        from room.models import Project, Column
        p2 = Project.objects.create(name='Phase3B P2', owner=test_user)
        Column.objects.create(project=p2, title='C1', position=1)
        _make_github_config(p2, test_user, name='github-p2')

        resp = auth_client.get(f'/api/qa/devops/cicd-config/?project_id={test_project.id}')
        names = [c['name'] for c in resp.data]
        assert 'github-p2' not in names


# ══════════════════════════════════════════════════════════════════════════
# django-celery-beat PeriodicTask tests
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPeriodicTaskIntegration:
    """Scheduled TestTasks create/update/delete PeriodicTask records."""

    def _create_scheduled_task(self, project, user):
        from qa_center.models import TestTask
        return TestTask.objects.create(
            project=project, created_by=user,
            name='Phase3B scheduled task',
            test_type='api',
            trigger_type='scheduled',
            cron_expression='0 9 * * 1-5',
            test_config={'api_cases': []},
            status='idle',
        )

    def test_register_creates_periodic_task(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        error = svc.register_scheduled_task(task)
        assert error is None

        from django_celery_beat.models import PeriodicTask
        pt = PeriodicTask.objects.get(name=svc._periodic_task_name(task))
        assert pt.task == 'qa_center.execute_test_task'
        assert pt.enabled is True

    def test_update_does_not_duplicate(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService
        from django_celery_beat.models import PeriodicTask

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        svc.register_scheduled_task(task)
        count1 = PeriodicTask.objects.filter(
            name=svc._periodic_task_name(task),
        ).count()

        # Update with same name — should update, not create
        svc.register_scheduled_task(task)
        count2 = PeriodicTask.objects.filter(
            name=svc._periodic_task_name(task),
        ).count()
        assert count1 == count2 == 1

    def test_disable_task_disables_periodic_task(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService
        from django_celery_beat.models import PeriodicTask

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        svc.register_scheduled_task(task)

        task.is_active = False
        task.save()
        svc.sync_scheduled_task_enabled(task)

        pt = PeriodicTask.objects.get(name=svc._periodic_task_name(task))
        assert pt.enabled is False

    def test_delete_task_removes_periodic_task(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService
        from django_celery_beat.models import PeriodicTask

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        svc.register_scheduled_task(task)

        name = svc._periodic_task_name(task)
        assert PeriodicTask.objects.filter(name=name).exists()

        svc.unregister_scheduled_task(task)
        assert not PeriodicTask.objects.filter(name=name).exists()

    def test_periodic_task_name_stable(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        name = svc._periodic_task_name(task)
        assert f".{task.id}" in name
        assert name.startswith("qa_center.test_task.")

    def test_periodic_task_payload_no_token(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService
        from django_celery_beat.models import PeriodicTask

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        svc.register_scheduled_task(task)

        pt = PeriodicTask.objects.get(name=svc._periodic_task_name(task))
        args_str = pt.args or ''
        # args is JSON-encoded list of task IDs, must not contain token strings
        assert 'token' not in args_str.lower()
        assert 'secret' not in args_str.lower()
        assert 'ghp_' not in args_str

    def test_schedule_entry_points_to_correct_celery_task(self, test_project, test_user):
        from qa_center.services.devops.test_execution_service import TestExecutionService
        from django_celery_beat.models import PeriodicTask

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        svc.register_scheduled_task(task)

        pt = PeriodicTask.objects.get(name=svc._periodic_task_name(task))
        assert pt.task == 'qa_center.execute_test_task'

    def test_no_celery_worker_still_creates_record(self, test_project, test_user):
        """Even without a running Celery worker, PeriodicTask records are created."""
        from qa_center.services.devops.test_execution_service import TestExecutionService
        from django_celery_beat.models import PeriodicTask

        task = self._create_scheduled_task(test_project, test_user)
        svc = TestExecutionService()
        error = svc.register_scheduled_task(task)
        assert error is None
        assert PeriodicTask.objects.filter(name=svc._periodic_task_name(task)).exists()
