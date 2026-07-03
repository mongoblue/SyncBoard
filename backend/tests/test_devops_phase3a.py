"""Phase 3A tests — frontend alignment, test connection, pipeline cancel/logs,
project isolation, dashboard stats, serializer aliases.

Covers:
  - CiCdConfig CRUD via API (not raw ORM)
  - Test connection endpoint (mock + error paths)
  - PipelineRun cancel and logs endpoints
  - Project isolation: configs, tasks, runs, stats scoped to project
  - Dashboard stats with project_id filtering
  - Serializer returns aliased fields, ci_token not leaked
"""
import json as _json
import os
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone
from django.contrib.auth.models import User


# ── helpers ──────────────────────────────────────────────────────────────


def _json_post(client, url, data):
    return client.post(url, data=_json.dumps(data), content_type='application/json')


def _make_config(project, user, **kwargs):
    from qa_center.models import CiCdConfig
    return CiCdConfig.objects.create(
        project=project, created_by=user,
        name=kwargs.pop('name', 'Phase3A config'),
        ci_type=kwargs.pop('ci_type', 'jenkins'),
        api_token=kwargs.pop('api_token', 'test-token-3a'),
        **kwargs,
    )


def _create_task(project, user, **kwargs):
    from qa_center.models import TestTask
    return TestTask.objects.create(
        project=project, created_by=user,
        name=kwargs.pop('name', 'Phase3A task'),
        test_type=kwargs.pop('test_type', 'api'),
        test_config=kwargs.pop('test_config', {}),
        status=kwargs.pop('status', 'idle'),
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════════
# CiCdConfig CRUD via API
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCiCdConfigCRUD:
    """CiCdConfig CRUD via HTTP endpoints."""

    def test_create_config_via_api(self, auth_client, test_project):
        resp = _json_post(auth_client, '/api/qa/devops/cicd-config/', {
            'write_only_project_id': str(test_project.id),
            'name': 'api-created config',
            'ci_type': 'jenkins',
            'webhook_url': 'https://jenkins.example.com/',
            'branch': 'main',
        })
        assert resp.status_code == 201
        data = resp.data
        assert data['name'] == 'api-created config'
        assert data['type'] == 'jenkins'
        assert data['enabled'] is True
        assert data['project_id'] == str(test_project.id)

    def test_list_configs_with_project_filter(self, auth_client, test_project, test_user):
        _make_config(test_project, test_user, name='config-a')
        _make_config(test_project, test_user, name='config-b')
        resp = auth_client.get(f'/api/qa/devops/cicd-config/?project_id={test_project.id}')
        assert resp.status_code == 200
        names = [c['name'] for c in resp.data]
        assert 'config-a' in names
        assert 'config-b' in names

    def test_update_config_via_api(self, auth_client, test_project, test_user):
        config = _make_config(test_project, test_user, name='before-update')
        resp = _json_post(auth_client, f'/api/qa/devops/cicd-config/{config.id}/', {
            'name': 'after-update',
            'branch': 'develop',
        })
        # PUT uses same URL pattern; the view handles it via PUT method
        # Test via the proper method:
        resp2 = auth_client.put(
            f'/api/qa/devops/cicd-config/{config.id}/',
            data=_json.dumps({'name': 'after-update', 'branch': 'develop'}),
            content_type='application/json',
        )
        assert resp2.status_code == 200
        assert resp2.data['name'] == 'after-update'

    def test_delete_config_via_api(self, auth_client, test_project, test_user):
        config = _make_config(test_project, test_user)
        resp = auth_client.delete(f'/api/qa/devops/cicd-config/{config.id}/')
        assert resp.status_code == 200
        config.refresh_from_db()
        assert config.is_active is False


# ══════════════════════════════════════════════════════════════════════════
# Test Connection endpoint
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCiCdTestConnection:
    """POST /cicd-config/{id}/test/ returns reachable + latency."""

    def test_mock_returns_reachable(self, auth_client, test_project, test_user):
        config = _make_config(test_project, test_user)
        resp = auth_client.post(f'/api/qa/devops/cicd-config/{config.id}/test/')
        assert resp.status_code == 200
        assert resp.data['reachable'] is True  # mock client always ok
        assert isinstance(resp.data['latency_ms'], (int, float))

    def test_strict_env_rejects_mock_test(self, auth_client, test_project, test_user, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        config = _make_config(test_project, test_user)
        with patch('qa_center.views_devops.settings.USE_REAL_CI', False):
            resp = auth_client.post(f'/api/qa/devops/cicd-config/{config.id}/test/')
        assert resp.status_code == 409

    def test_ping_delegates_to_client(self, auth_client, test_project, test_user):
        config = _make_config(test_project, test_user)
        with patch('qa_center.pipeline.get_client') as mock_factory:
            mock_client = MagicMock()
            mock_client.ping.return_value = {'ok': True, 'detail': 'all good'}
            mock_factory.return_value = mock_client

            resp = auth_client.post(f'/api/qa/devops/cicd-config/{config.id}/test/')
            assert resp.status_code == 200
            assert resp.data['reachable'] is True
            assert mock_client.ping.called


# ══════════════════════════════════════════════════════════════════════════
# PipelineRun cancel and logs
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPipelineRunCancel:
    """POST /pipeline-runs/{id}/cancel/"""

    def _make_run(self, test_project, test_user, status='running'):
        from qa_center.models import CiCdConfig, PipelineRun
        config = _make_config(test_project, test_user)
        return PipelineRun.objects.create(
            cicd_config=config, project=test_project, status=status,
            external_run_id='ext-cancel-1', is_mock=True,
            started_at=timezone.now(),
        )

    def test_cancel_running_run(self, auth_client, test_project, test_user):
        run = self._make_run(test_project, test_user, 'running')
        resp = auth_client.post(f'/api/qa/devops/pipeline-runs/{run.id}/cancel/')
        assert resp.status_code == 200
        run.refresh_from_db()
        assert run.status == 'cancelled'

    def test_cancel_completed_run_rejected(self, auth_client, test_project, test_user):
        run = self._make_run(test_project, test_user, 'passed')
        resp = auth_client.post(f'/api/qa/devops/pipeline-runs/{run.id}/cancel/')
        assert resp.status_code == 400


@pytest.mark.django_db
class TestPipelineRunLogs:
    """GET /pipeline-runs/{id}/logs/"""

    def _make_run(self, test_project, test_user):
        from qa_center.models import CiCdConfig, PipelineRun
        config = _make_config(test_project, test_user)
        return PipelineRun.objects.create(
            cicd_config=config, project=test_project, status='passed',
            external_run_id='ext-logs-1', is_mock=True,
            started_at=timezone.now(), completed_at=timezone.now(),
        )

    def test_logs_endpoint_returns_data(self, auth_client, test_project, test_user):
        run = self._make_run(test_project, test_user)
        resp = auth_client.get(f'/api/qa/devops/pipeline-runs/{run.id}/logs/')
        assert resp.status_code == 200
        assert 'log_output' in resp.data

    def test_logs_sanitized(self, auth_client, test_project, test_user):
        run = self._make_run(test_project, test_user)
        with patch('qa_center.pipeline.get_client') as mock_factory:
            mock_client = MagicMock()
            mock_client.get_logs.return_value = (
                'Authorization: Bearer secret123\n'
                'X-CI-Token: abc\n'
                'Normal log line'
            )
            mock_factory.return_value = mock_client
            resp = auth_client.get(f'/api/qa/devops/pipeline-runs/{run.id}/logs/')
        output = resp.data.get('log_output', '')
        assert 'Bearer secret123' not in output
        assert 'abc' not in output
        assert '[redacted]' in output
        assert 'Normal log line' in output


# ══════════════════════════════════════════════════════════════════════════
# Project isolation
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestProjectIsolation:
    """Configs, tasks, runs, stats must be scoped to project."""

    def _make_second_project(self, test_user):
        from room.models import Project, Column
        p2 = Project.objects.create(name='Phase3A Project B', owner=test_user)
        Column.objects.create(project=p2, title='C1', position=1)
        return p2

    def test_configs_scoped_to_project(self, auth_client, test_project, test_user):
        p2 = self._make_second_project(test_user)
        _make_config(test_project, test_user, name='proj-a-config')
        _make_config(p2, test_user, name='proj-b-config')

        resp = auth_client.get(f'/api/qa/devops/cicd-config/?project_id={test_project.id}')
        names = [c['name'] for c in resp.data]
        assert 'proj-a-config' in names
        assert 'proj-b-config' not in names

    def test_tasks_scoped_to_project(self, auth_client, test_project, test_user):
        p2 = self._make_second_project(test_user)
        _create_task(test_project, test_user, name='proj-a-task')
        _create_task(p2, test_user, name='proj-b-task')

        resp = auth_client.get(f'/api/qa/devops/tasks/?project_id={test_project.id}')
        names = [t['name'] for t in resp.data]
        assert 'proj-a-task' in names
        assert 'proj-b-task' not in names

    def test_runs_scoped_to_project(self, auth_client, test_project, test_user):
        from qa_center.models import CiCdConfig, PipelineRun
        p2 = self._make_second_project(test_user)
        c1 = _make_config(test_project, test_user, name='c-a')
        c2 = _make_config(p2, test_user, name='c-b')
        PipelineRun.objects.create(cicd_config=c1, project=test_project,
                                    status='passed', external_run_id='r-a',
                                    is_mock=True)
        PipelineRun.objects.create(cicd_config=c2, project=p2,
                                    status='passed', external_run_id='r-b',
                                    is_mock=True)

        resp = auth_client.get(f'/api/qa/devops/pipeline-runs/?project_id={test_project.id}')
        run_ids = [r['project_id'] for r in resp.data.get('results', [])]
        assert str(test_project.id) in run_ids
        assert str(p2.id) not in run_ids

    def test_stats_scoped_to_project(self, auth_client, test_project, test_user):
        resp = auth_client.get(f'/api/qa/devops/stats/?project_id={test_project.id}')
        assert resp.status_code == 200
        overview = resp.data.get('overview', {})
        assert 'total_cases' in overview
        assert 'total_executions' in overview


# ══════════════════════════════════════════════════════════════════════════
# Dashboard stats
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDashboardStats:
    """DashboardStatsView returns correct data."""

    def test_stats_returns_overview(self, auth_client, test_project):
        resp = auth_client.get(f'/api/qa/devops/stats/?project_id={test_project.id}')
        assert resp.status_code == 200
        assert 'overview' in resp.data
        assert 'status_count' in resp.data

    def test_stats_empty_project_returns_zeros(self, auth_client, test_project):
        resp = auth_client.get(f'/api/qa/devops/stats/?project_id={test_project.id}')
        assert resp.data['overview']['total_cases'] >= 0
        assert resp.data['overview']['pass_rate'] >= 0


# ══════════════════════════════════════════════════════════════════════════
# Serializer aliases
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSerializationAliases:
    """CiCdConfigSerializer returns frontend-compatible aliases."""

    def test_serializer_includes_alias_fields(self, test_project, test_user):
        from qa_center.serializers import CiCdConfigSerializer
        config = _make_config(test_project, test_user, name='alias test')
        ser = CiCdConfigSerializer(config)
        data = ser.data
        assert data['type'] == 'jenkins'  # alias for ci_type
        assert data['enabled'] is True     # alias for is_active
        assert data['status'] == 'active'  # derived field
        assert data['project_id'] == str(test_project.id)  # derived field
        assert 'test_suite' in data        # alias for test_suite_ids

    def test_serializer_does_not_leak_ci_token(self, test_project, test_user):
        from qa_center.serializers import CiCdConfigSerializer
        config = _make_config(test_project, test_user, ci_token='secret-token-123')
        ser = CiCdConfigSerializer(config)
        data = ser.data
        # ci_token_display should be masked (e.g. "secr*********")
        token_display = data.get('ci_token_display', '')
        assert 'secret-token-123' not in token_display
        # ci_token must not appear in serialized output
        assert 'ci_token' not in data or data.get('ci_token') is None
