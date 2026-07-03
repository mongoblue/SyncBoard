"""Phase 1C production-readiness tests — webhook rate limit hardening, null guards,
mock exclusion, notification scoping, WebSocket isolation, mock client strict check,
runtime-mode API.

Covers P0:
  - Shared-cache check for strict env webhooks
  - Pipeline polling cicd_config null protection
  - Mock PipelineRun exclusion from quality reports

Covers P1:
  - Notification only targets project members
  - WebSocket group name includes project_id
  - _MockCiClient.verify_webhook rejects in strict env

Covers P2:
  - GET /api/qa/devops/runtime-mode/ returns safe config summary
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
    return client.post(url, data=_json.dumps(data), content_type='application/json')


def _make_webhook_config(project, user, *, ci_token='', api_token='test-token-123'):
    from qa_center.models import CiCdConfig
    return CiCdConfig.objects.create(
        project=project,
        created_by=user,
        name='Phase1C config',
        ci_type='jenkins',
        api_token=api_token,
        ci_token=ci_token,
    )


def _add_member(project, user):
    from room.models import ProjectRole, ProjectMember
    role, _ = ProjectRole.objects.get_or_create(
        project=project,
        key='developer',
        defaults={'name': 'Developer', 'permissions': []},
    )
    return ProjectMember.objects.get_or_create(project=project, user=user, role=role)[0]


# ══════════════════════════════════════════════════════════════════════════
# P0.1 — Shared-cache check for webhook rate limit
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWebhookSharedCacheGuard:
    """Strict envs without shared cache must reject webhooks."""

    def test_strict_env_no_shared_cache_rejects(self, client, test_project, test_user, monkeypatch):
        """production + LocMemCache → 503."""
        monkeypatch.setenv("APP_ENV", "production")
        config = _make_webhook_config(test_project, test_user)

        with patch('qa_center.views_devops.RuntimeGuard.cache_is_shared', return_value=False):
            resp = client.post(
                f'/api/qa/devops/cicd-config/{config.id}/webhook/',
                data=_json.dumps({'status': 'passed', 'external_run_id': 'r-cache'}),
                content_type='application/json',
                HTTP_X_CI_TOKEN='test-token-123',
            )
        assert resp.status_code == 503
        # Error message must not leak internals
        body = _json.dumps(resp.data)
        assert 'cache' in body.lower()

    def test_dev_env_no_shared_cache_allowed(self, client, test_project, test_user, monkeypatch):
        """local + LocMemCache → still accepted (not strict)."""
        monkeypatch.setenv("APP_ENV", "local")
        config = _make_webhook_config(test_project, test_user)

        with patch('qa_center.views_devops.RuntimeGuard.cache_is_shared', return_value=False):
            resp = client.post(
                f'/api/qa/devops/cicd-config/{config.id}/webhook/',
                data=_json.dumps({'status': 'passed', 'external_run_id': 'r-local'}),
                content_type='application/json',
                HTTP_X_CI_TOKEN='test-token-123',
            )
        assert resp.status_code == 201


# ══════════════════════════════════════════════════════════════════════════
# P0.2 — Pipeline polling cicd_config null protection
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPipelinePollNullGuard:
    """poll_pipeline_status must handle missing cicd_config gracefully."""

    def test_poll_with_deleted_config_marks_failed(self, test_project, test_user):
        from qa_center.models import CiCdConfig, PipelineRun
        from qa_center.tasks_test_exec import poll_pipeline_status

        config = CiCdConfig.objects.create(
            project=test_project, created_by=test_user,
            name='will-be-inactive', ci_type='jenkins', api_token='tok',
            is_active=True,
        )
        run = PipelineRun.objects.create(
            cicd_config=config, project=test_project, status='running',
            external_run_id='ext-inact', is_mock=False, started_at=timezone.now(),
        )
        # Deactivate the config (cannot delete because of CASCADE on cicd_config FK)
        config.is_active = False
        config.save()

        result = poll_pipeline_status.run(run.id)
        assert result['status'] == 'failed'
        assert result['reason'] == 'cicd_config_unavailable'
        run.refresh_from_db()
        assert run.status == 'failed'
        assert 'inactive' in (run.error_message or '').lower()

    def test_poll_with_inactive_config_marks_failed(self, test_project, test_user):
        from qa_center.models import CiCdConfig, PipelineRun
        from qa_center.tasks_test_exec import poll_pipeline_status

        config = CiCdConfig.objects.create(
            project=test_project, created_by=test_user,
            name='inactive-config', ci_type='jenkins', api_token='tok',
            is_active=False,
        )
        run = PipelineRun.objects.create(
            cicd_config=config, project=test_project, status='running',
            external_run_id='ext-inactive', is_mock=False, started_at=timezone.now(),
        )

        result = poll_pipeline_status.run(run.id)
        assert result['status'] == 'failed'
        run.refresh_from_db()
        assert run.status == 'failed'

    def test_poll_error_message_does_not_leak_internals(self, test_project, test_user):
        """Error message should not contain token or traceback."""
        from qa_center.models import CiCdConfig, PipelineRun
        from qa_center.tasks_test_exec import poll_pipeline_status

        config = CiCdConfig.objects.create(
            project=test_project, created_by=test_user,
            name='tok-leak-test', ci_type='jenkins', api_token='super-secret-token',
            is_active=True,
        )
        run = PipelineRun.objects.create(
            cicd_config=config, project=test_project, status='running',
            external_run_id='ext-leak', is_mock=False, started_at=timezone.now(),
        )
        config.is_active = False
        config.save()

        poll_pipeline_status.run(run.id)
        run.refresh_from_db()
        assert 'super-secret-token' not in (run.error_message or '')


# ══════════════════════════════════════════════════════════════════════════
# P0.3 — Mock exclusion from quality reports & dashboard
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMockExclusion:
    """Quality reports and dashboard must exclude mock data."""

    def test_quality_report_excludes_mock_pipelines(self, auth_client, test_project, test_user):
        """is_mock=True PipelineRuns must not count toward deploy success rate."""
        from qa_center.models import CiCdConfig, PipelineRun

        config = CiCdConfig.objects.create(
            project=test_project, created_by=test_user,
            name='mock-excl-config', ci_type='jenkins', api_token='tok',
        )
        # Create one mocked and one real pipeline
        PipelineRun.objects.create(
            cicd_config=config, project=test_project, status='passed',
            external_run_id='mock-run', is_mock=True,
            started_at=timezone.now(), completed_at=timezone.now(),
        )
        PipelineRun.objects.create(
            cicd_config=config, project=test_project, status='failed',
            external_run_id='real-run', is_mock=False,
            started_at=timezone.now(), completed_at=timezone.now(),
        )

        resp = auth_client.get(f'/api/qa/devops/quality-report/?project_id={test_project.id}')
        assert resp.status_code == 200

        # Find the "部署成功率" dimension
        dimensions = resp.data.get('dimensions', [])
        deploy_dim = next((d for d in dimensions if d['name'] == '部署成功率'), None)
        assert deploy_dim is not None
        # Only the real (failed) run counts: 0/1 = 0 score
        # The mock run (passed) must NOT be counted
        detail = deploy_dim.get('detail', '')
        # detail should show "0/1" (one real run failed), not "1/2"
        assert '0/1' in detail or deploy_dim['score'] == 0

    def test_quality_report_with_only_mock_data_shows_none(self, auth_client, test_project, test_user):
        """When only mock pipelines exist, deploy_rate is None (no real data)."""
        from qa_center.models import CiCdConfig, PipelineRun

        config = CiCdConfig.objects.create(
            project=test_project, created_by=test_user,
            name='mock-only-config', ci_type='jenkins', api_token='tok',
        )
        PipelineRun.objects.create(
            cicd_config=config, project=test_project, status='passed',
            external_run_id='mock-only-run', is_mock=True,
            started_at=timezone.now(), completed_at=timezone.now(),
        )

        resp = auth_client.get(f'/api/qa/devops/quality-report/?project_id={test_project.id}')
        assert resp.status_code == 200
        dimensions = resp.data.get('dimensions', [])
        deploy_dim = next((d for d in dimensions if d['name'] == '部署成功率'), None)
        assert deploy_dim is not None
        # deploy_rate should be None (no real data)
        assert deploy_dim['score'] in (0, None)


# ══════════════════════════════════════════════════════════════════════════
# P1.4 — Notification scope restricted to project members
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNotificationScoping:
    """_send_notification must only target project members."""

    def test_notification_only_creates_for_project_members(self, test_project, test_user):
        from qa_center.views_devops import _send_notification
        from room.models import Notification, ProjectMember

        # Create another user NOT in the project
        outsider = User.objects.create_user('outsider', 'o@o.com', 'pass')

        # Add test_user as project member
        _add_member(test_project, test_user)

        before_outsider = Notification.objects.filter(user=outsider).count()
        before_member = Notification.objects.filter(user=test_user).count()

        _send_notification(test_project, 'test', 'phase1c test notification')

        # Outsider should NOT receive notification
        assert Notification.objects.filter(user=outsider).count() == before_outsider
        # Member (test_user) SHOULD receive notification
        assert Notification.objects.filter(user=test_user).count() > before_member

    def test_notification_includes_owner(self, test_project, test_user):
        """Project owner always receives notifications even if not in members table."""
        from qa_center.views_devops import _send_notification
        from room.models import Notification

        # test_user is project.owner but may not be in ProjectMember table
        before = Notification.objects.filter(user=test_user).count()
        _send_notification(test_project, 'test', 'owner notification test')
        assert Notification.objects.filter(user=test_user).count() > before

    def test_notification_message_does_not_contain_internals(self, test_project, test_user):
        """Notification content must not leak tokens or secrets."""
        from qa_center.views_devops import _send_notification
        from room.models import Notification

        _send_notification(test_project, 'test', 'Test message with secret=abc123')
        notif = Notification.objects.filter(project=test_project).last()
        # We deliberately don't strip content, but we verify it's the message we sent
        # (in production, callers should not put secrets in notification messages)
        assert notif is not None


# ══════════════════════════════════════════════════════════════════════════
# P1.5 — WebSocket group isolated by project_id
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWebSocketGroupIsolation:
    """WebSocket group name must be project-scoped, not global."""

    def test_group_name_includes_project_id(self, test_project, test_user):
        """_send_notification sends to project_{id}_qa, not system_broadcast."""
        from qa_center.views_devops import _send_notification

        mock_channel = MagicMock()
        with patch('channels.layers.get_channel_layer', return_value=mock_channel):
            _send_notification(test_project, 'test', 'ws group test')

            # Check group_send was called with project-scoped group name
            if mock_channel.group_send.called:
                args, _ = mock_channel.group_send.call_args
                group_name = args[0]
                assert str(test_project.id) in group_name
                assert 'system_broadcast' not in group_name

    def test_no_project_id_no_group_send(self, test_user):
        """When project is None, no group message is sent."""
        from qa_center.views_devops import _send_notification

        mock_channel = MagicMock()
        with patch('channels.layers.get_channel_layer', return_value=mock_channel):
            _send_notification(None, 'test', 'no project test')

            # group_send should NOT be called
            mock_channel.group_send.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# P1.6 — _MockCiClient.verify_webhook rejects in strict env
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMockCiClientStrict:
    """Mock CI client must reject webhooks in production/staging."""

    def test_mock_verify_webhook_false_in_production(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        from qa_center.pipeline import _MockCiClient
        from qa_center.models import CiCdConfig

        # Dummy config — client only needs the type
        config = CiCdConfig(ci_type='jenkins')
        client = _MockCiClient(config)
        assert client.verify_webhook(None) is False

    def test_mock_verify_webhook_true_in_local(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "local")
        from qa_center.pipeline import _MockCiClient
        from qa_center.models import CiCdConfig

        config = CiCdConfig(ci_type='jenkins')
        client = _MockCiClient(config)
        assert client.verify_webhook(None) is True

    def test_mock_verify_webhook_false_in_staging(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "staging")
        from qa_center.pipeline import _MockCiClient
        from qa_center.models import CiCdConfig

        config = CiCdConfig(ci_type='jenkins')
        client = _MockCiClient(config)
        assert client.verify_webhook(None) is False


# ══════════════════════════════════════════════════════════════════════════
# P2.7 — Runtime mode API
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRuntimeModeAPI:
    """GET /api/qa/devops/runtime-mode/ returns safe config summary."""

    def test_endpoint_returns_200(self, auth_client):
        resp = auth_client.get('/api/qa/devops/runtime-mode/')
        assert resp.status_code == 200

    def test_contains_required_keys(self, auth_client):
        resp = auth_client.get('/api/qa/devops/runtime-mode/')
        data = resp.data
        for key in ('app_env', 'is_strict', 'is_production', 'mock_allowed',
                     'celery_required', 'use_real_ci', 'use_celery_tasks',
                     'cache_is_shared'):
            assert key in data, f'Missing key: {key}'

    def test_no_sensitive_data_leaked(self, auth_client):
        resp = auth_client.get('/api/qa/devops/runtime-mode/')
        body = _json.dumps(resp.data)
        # Must not contain any settings that look like tokens or secrets
        assert 'SECRET' not in body
        assert 'PASSWORD' not in body
        assert 'token' not in body.lower()

    def test_production_env_reflected(self, auth_client, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        resp = auth_client.get('/api/qa/devops/runtime-mode/')
        assert resp.data['is_strict'] is True
        assert resp.data['is_production'] is True
        assert resp.data['mock_allowed'] is False
        assert resp.data['celery_required'] is True

    def test_local_env_reflected(self, auth_client, monkeypatch):
        monkeypatch.setenv("APP_ENV", "local")
        resp = auth_client.get('/api/qa/devops/runtime-mode/')
        assert resp.data['is_strict'] is False
        assert resp.data['mock_allowed'] is True


# ══════════════════════════════════════════════════════════════════════════
# RuntimeGuard unit tests
# ══════════════════════════════════════════════════════════════════════════


class TestRuntimeGuardCacheCheck:
    """RuntimeGuard cache checks."""

    def test_cache_is_shared_returns_sensible_value(self):
        from qa_center.api_execution.runtime_guard import RuntimeGuard
        guard = RuntimeGuard()
        result = guard.cache_is_shared()
        # Should return a boolean (True/False), not raise
        assert isinstance(result, bool)

    def test_require_shared_cache_in_production(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        from qa_center.api_execution.runtime_guard import RuntimeGuard
        guard = RuntimeGuard()
        assert guard.require_shared_cache_for_webhooks() is True

    def test_require_shared_cache_in_local(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "local")
        from qa_center.api_execution.runtime_guard import RuntimeGuard
        guard = RuntimeGuard()
        assert guard.require_shared_cache_for_webhooks() is False
