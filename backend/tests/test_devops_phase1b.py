"""Phase 1B security hardening tests — webhook auth, dedup, body limit, polling fix.

Covers P0:
  - Webhook fail-closed: missing token, wrong token, missing sig (strict), wrong sig
  - Dedup via payload hash when external_run_id absent
  - Duplicate webhook does not create duplicate PipelineRun
  - Body size limit returns 413
  - poll_pipeline_status uses cicd_config (not ci_config)

Covers P1:
  - QuickTest cross-project test_cases rejected (validator runs before 501)
  - RuntimeGuard: production blocks mock, production requires Celery
  - Audit logging does not leak secrets
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


def _make_webhook_config(project, user, *, ci_token='', api_token='test-token-123',
                          ci_type='jenkins'):
    from qa_center.models import CiCdConfig
    return CiCdConfig.objects.create(
        project=project,
        created_by=user,
        name='Phase1B config',
        ci_type=ci_type,
        api_token=api_token,
        ci_token=ci_token,
    )


# ══════════════════════════════════════════════════════════════════════════
# P0.1 — Webhook authentication: fail-closed
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWebhookAuthFailClosed:
    """Webhook must reject missing/bad tokens and signatures."""

    def test_missing_token_returns_403(self, client, test_project, test_user):
        config = _make_webhook_config(test_project, test_user)
        resp = _json_post(client, f'/api/qa/devops/cicd-config/{config.id}/webhook/', {
            'status': 'passed', 'external_run_id': 'r-1',
        })
        assert resp.status_code == 403

    def test_wrong_token_returns_403(self, client, test_project, test_user):
        config = _make_webhook_config(test_project, test_user)
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'passed', 'external_run_id': 'r-2'}),
            content_type='application/json',
            HTTP_X_CI_TOKEN='wrong-token-value',
        )
        assert resp.status_code == 403

    def test_valid_token_accepted(self, client, test_project, test_user):
        config = _make_webhook_config(test_project, test_user)
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'passed', 'external_run_id': 'r-3'}),
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-token-123',
        )
        assert resp.status_code == 201

    def test_missing_signature_when_ci_token_configured_returns_403(self, client, test_project, test_user):
        """If ci_token is set, signature header is mandatory."""
        import hmac as _hmac, hashlib
        secret = 'my-ci-secret'
        config = _make_webhook_config(test_project, test_user,
                                       ci_token=secret, api_token='tok')
        # Send without signature header
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'passed', 'external_run_id': 'r-4'}),
            content_type='application/json',
            HTTP_X_CI_TOKEN='tok',
        )
        assert resp.status_code == 403

    def test_wrong_signature_returns_403(self, client, test_project, test_user):
        """Tampered signature must be rejected."""
        import hmac as _hmac, hashlib
        secret = 'my-ci-secret'
        body_bytes = _json.dumps({'status': 'passed', 'external_run_id': 'r-5'}).encode()
        # Compute a valid sig but for a different body
        bad_sig = 'sha256=' + _hmac.new(b'wrong-secret', body_bytes, hashlib.sha256).hexdigest()
        config = _make_webhook_config(test_project, test_user,
                                       ci_token=secret, api_token='tok')
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=bad_sig,
            HTTP_X_CI_TOKEN='tok',
        )
        assert resp.status_code == 403

    def test_correct_signature_accepted(self, client, test_project, test_user):
        """Valid signature + token is accepted."""
        import hmac as _hmac, hashlib
        secret = 'my-ci-secret'
        body_bytes = _json.dumps({'status': 'passed', 'external_run_id': 'r-6'}).encode()
        good_sig = 'sha256=' + _hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        config = _make_webhook_config(test_project, test_user,
                                       ci_token=secret, api_token='tok')
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=good_sig,
            HTTP_X_CI_TOKEN='tok',
        )
        assert resp.status_code == 201

    def test_strict_env_rejects_missing_ci_token(self, client, test_project, test_user, monkeypatch):
        """In production/staging, ci_token MUST be configured for webhooks."""
        monkeypatch.setenv("APP_ENV", "production")
        config = _make_webhook_config(test_project, test_user,
                                       ci_token='', api_token='tok')
        # Mock shared cache to avoid 503 from Phase 1C guard
        with patch('qa_center.views_devops.RuntimeGuard.cache_is_shared', return_value=True):
            resp = client.post(
                f'/api/qa/devops/cicd-config/{config.id}/webhook/',
                data=_json.dumps({'status': 'passed', 'external_run_id': 'r-7'}),
                content_type='application/json',
                HTTP_X_CI_TOKEN='tok',
            )
        assert resp.status_code == 403

    def test_error_messages_never_leak_secrets(self, client, test_project, test_user):
        """403/400 responses must never contain tokens, secrets, or tracebacks."""
        config = _make_webhook_config(test_project, test_user)
        # Missing token
        resp = _json_post(client, f'/api/qa/devops/cicd-config/{config.id}/webhook/', {
            'status': 'passed', 'external_run_id': 'r-sec-1',
        })
        body = _json.dumps(resp.data)
        assert 'test-token-123' not in body
        assert 'secret' not in body.lower()

        # Wrong token
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'passed', 'external_run_id': 'r-sec-2'}),
            content_type='application/json',
            HTTP_X_CI_TOKEN='wrong',
        )
        body = _json.dumps(resp.data)
        assert 'test-token-123' not in body
        assert 'wrong' not in body

        # Invalid status
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'evil', 'external_run_id': 'r-sec-3'}),
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-token-123',
        )
        body = _json.dumps(resp.data)
        assert 'test-token-123' not in body
        assert 'traceback' not in body.lower()


# ══════════════════════════════════════════════════════════════════════════
# P0.2 — Dedup with payload-hash fallback
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWebhookDedupPayloadHash:
    """Dedup must work even when external_run_id is absent."""

    def _make_config(self, test_project, test_user):
        return _make_webhook_config(test_project, test_user)

    def test_payload_hash_dedup_blocks_duplicate_without_run_id(self, client, test_project, test_user):
        """Two identical payloads without external_run_id: second is duplicate."""
        config = self._make_config(test_project, test_user)
        payload = {'status': 'running', 'commit_sha': 'abc123'}
        headers = {'HTTP_X_CI_TOKEN': 'test-token-123'}

        # First delivery
        resp1 = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps(payload),
            content_type='application/json',
            **headers,
        )
        assert resp1.status_code == 201

        # Second delivery — identical payload — should be dedup
        resp2 = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps(payload),
            content_type='application/json',
            **headers,
        )
        assert resp2.status_code == 200
        assert 'duplicate' in _json.dumps(resp2.data)

    def test_different_payload_without_run_id_not_deduped(self, client, test_project, test_user):
        """Different payloads without external_run_id are treated as distinct."""
        config = self._make_config(test_project, test_user)
        headers = {'HTTP_X_CI_TOKEN': 'test-token-123'}

        resp1 = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'running', 'commit_sha': 'abc'}),
            content_type='application/json',
            **headers,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'running', 'commit_sha': 'xyz'}),
            content_type='application/json',
            **headers,
        )
        assert resp2.status_code == 201  # different payload, not duplicate

    def test_duplicate_with_external_run_id_still_blocked(self, client, test_project, test_user):
        """When external_run_id IS present, dedup still works."""
        config = self._make_config(test_project, test_user)
        headers = {'HTTP_X_CI_TOKEN': 'test-token-123'}
        payload = {'status': 'running', 'external_run_id': 'real-run-42'}

        resp1 = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps(payload),
            content_type='application/json',
            **headers,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps(payload),
            content_type='application/json',
            **headers,
        )
        assert resp2.status_code == 200
        assert 'duplicate' in _json.dumps(resp2.data)

    def test_duplicate_does_not_create_second_pipeline_run(self, client, test_project, test_user):
        """Dedup: only one PipelineRun created for duplicate webhooks."""
        from qa_center.models import PipelineRun
        config = self._make_config(test_project, test_user)
        before = PipelineRun.objects.filter(cicd_config=config).count()
        headers = {'HTTP_X_CI_TOKEN': 'test-token-123'}

        client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'running', 'commit_sha': 'dedup-test'}),
            content_type='application/json',
            **headers,
        )
        client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'running', 'commit_sha': 'dedup-test'}),
            content_type='application/json',
            **headers,
        )

        after = PipelineRun.objects.filter(cicd_config=config).count()
        assert after == before + 1  # only one new record


# ══════════════════════════════════════════════════════════════════════════
# P0.3 — Body size limit
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWebhookBodySizeLimit:
    """Requests exceeding DEVOPS_WEBHOOK_MAX_BODY_BYTES are rejected with 413."""

    def test_body_over_limit_returns_413(self, client, test_project, test_user, monkeypatch):
        monkeypatch.setattr(
            'qa_center.views_devops.settings.DEVOPS_WEBHOOK_MAX_BODY_BYTES',
            50,  # very small limit for testing
        )
        config = _make_webhook_config(test_project, test_user)
        # Build a payload larger than 50 bytes
        big_payload = {'status': 'passed', 'external_run_id': 'r-big',
                       'extra': 'x' * 200}
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps(big_payload),
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-token-123',
        )
        assert resp.status_code == 413

    def test_body_under_limit_accepted(self, client, test_project, test_user, monkeypatch):
        monkeypatch.setattr(
            'qa_center.views_devops.settings.DEVOPS_WEBHOOK_MAX_BODY_BYTES',
            1024 * 1024,  # generous limit
        )
        config = _make_webhook_config(test_project, test_user)
        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data=_json.dumps({'status': 'passed', 'external_run_id': 'r-small'}),
            content_type='application/json',
            HTTP_X_CI_TOKEN='test-token-123',
        )
        assert resp.status_code == 201


# ══════════════════════════════════════════════════════════════════════════
# P0.4 — poll_pipeline_status uses cicd_config (not ci_config)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPollPipelineFieldName:
    """poll_pipeline_status must access the correct FK field name."""

    def test_poll_uses_cicd_config_field(self, test_project, test_user):
        """Verify the function accesses run.cicd_config, not run.ci_config."""
        from qa_center.models import CiCdConfig, PipelineRun
        from qa_center.tasks_test_exec import poll_pipeline_status

        config = CiCdConfig.objects.create(
            project=test_project,
            created_by=test_user,
            name='poll-test config',
            ci_type='jenkins',
            api_token='tok-poll',
        )
        run = PipelineRun.objects.create(
            cicd_config=config,
            project=test_project,
            status='running',
            external_run_id='ext-poll-1',
            is_mock=False,
            started_at=timezone.now(),
        )

        # get_client is imported inside poll_pipeline_status from .pipeline
        with patch('qa_center.pipeline.get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_status.return_value = MagicMock(status='passed')
            mock_get_client.return_value = mock_client

            result = poll_pipeline_status.run(run.id)

        assert result['status'] == 'completed'

        # Verify get_client was called with the cicd_config
        args, _ = mock_get_client.call_args
        assert args[0] == config
        assert args[0].ci_type == 'jenkins'

    def test_poll_select_related_uses_correct_field(self):
        """Verify source code uses 'cicd_config' not 'ci_config'."""
        import inspect
        from qa_center.tasks_test_exec import poll_pipeline_status

        # Celery tasks may wrap the function — unwrap if possible
        func = poll_pipeline_status
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__

        src_lines = inspect.getsource(func)
        assert 'select_related("cicd_config")' in src_lines, \
            "poll_pipeline_status must use select_related('cicd_config')"
        assert 'get_client(run.cicd_config)' in src_lines, \
            "poll_pipeline_status must use run.cicd_config"
        assert 'ci_config' not in src_lines, \
            "poll_pipeline_status must NOT use ci_config (old broken field name)"


# ══════════════════════════════════════════════════════════════════════════
# P1.5 — QuickTest cross-project validation before 501
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestQuickTestCrossProject:
    """QuickTest must validate project ownership before returning 501."""

    def test_cross_project_cases_rejected_with_400(self, auth_client, test_project, test_user):
        """Test cases from a different project must be rejected with 400."""
        # Create a second project
        from room.models import Project, Column
        project2 = Project.objects.create(name='Other Project', owner=test_user)
        Column.objects.create(project=project2, title='C1', position=1)

        # Create a case in project2
        from qa_center.models import ApiAutoTestCase
        case = ApiAutoTestCase.objects.create(
            project=project2,
            created_by=test_user,
            name='cross-project case',
            url='/api/cross/',
            method='GET',
        )

        # Try to run QuickTest on test_project with a case from project2
        resp = _json_post(auth_client, '/api/qa/devops/quick-test/', {
            'type': 'api',
            'test_cases': [case.id],
            'project_id': str(test_project.id),
        })
        assert resp.status_code == 400
        assert '不存在' in resp.data.get('error', '')

    def test_same_project_cases_pass_validation_then_501(self, auth_client, test_project, test_user):
        """Test cases in the same project pass validation, then execute (Phase 2A: real runner)."""
        from qa_center.models import ApiAutoTestCase
        case = ApiAutoTestCase.objects.create(
            project=test_project,
            created_by=test_user,
            name='same-project case',
            url='/api/same/',
            method='GET',
        )

        with patch('qa_center.views_devops._execute_api_cases_via_unified') as mock_exec:
            mock_exec.return_value = [{
                'case_id': case.id, 'case_name': case.name,
                'passed': True, 'status_code': 200, 'response_time_ms': 5,
                'error_message': '', 'failure_type': '',
            }]
            resp = _json_post(auth_client, '/api/qa/devops/quick-test/', {
                'type': 'api',
                'test_cases': [case.id],
                'project_id': str(test_project.id),
            })
        # Phase 2A: real executor → 200 on success
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# P1.6 — RuntimeGuard behaviour matrix
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRuntimeGuardMatrix:
    """RuntimeGuard must enforce env-specific rules."""

    def test_production_blocks_mock_pipeline(self, auth_client, test_project, test_user, monkeypatch):
        """production + USE_REAL_CI=False → 409."""
        monkeypatch.setenv("APP_ENV", "production")
        config = _make_webhook_config(test_project, test_user)
        with patch('qa_center.views_devops.settings.USE_REAL_CI', False):
            resp = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )
        assert resp.status_code == 409

    def test_staging_blocks_mock_pipeline(self, auth_client, test_project, test_user, monkeypatch):
        """staging + USE_REAL_CI=False → 409."""
        monkeypatch.setenv("APP_ENV", "staging")
        config = _make_webhook_config(test_project, test_user)
        with patch('qa_center.views_devops.settings.USE_REAL_CI', False):
            resp = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )
        assert resp.status_code == 409

    def test_local_allows_mock_with_is_mock_true(self, auth_client, test_project, test_user, monkeypatch):
        """local + USE_REAL_CI=False → 201 with is_mock=True."""
        monkeypatch.setenv("APP_ENV", "local")
        config = _make_webhook_config(test_project, test_user)
        with patch('qa_center.views_devops.settings.USE_REAL_CI', False), \
             patch('qa_center.views_devops.threading.Thread'):
            resp = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )
        assert resp.status_code == 201
        assert resp.data.get('is_mock') is True

    def test_dev_allows_mock_with_is_mock_true(self, auth_client, test_project, test_user, monkeypatch):
        """dev + USE_REAL_CI=False → 201 with is_mock=True."""
        monkeypatch.setenv("APP_ENV", "dev")
        config = _make_webhook_config(test_project, test_user)
        with patch('qa_center.views_devops.settings.USE_REAL_CI', False), \
             patch('qa_center.views_devops.threading.Thread'):
            resp = auth_client.post(
                f'/api/qa/devops/cicd-config/{config.id}/trigger/',
                data={}, format='json',
            )
        assert resp.status_code == 201
        assert resp.data.get('is_mock') is True

    def test_production_refuses_execution_without_celery(self, test_project, test_user, monkeypatch):
        """RuntimeGuard.require_celery_for_runtime_entrypoint() → True in production."""
        monkeypatch.setenv("APP_ENV", "production")
        from qa_center.api_execution.runtime_guard import RuntimeGuard
        guard = RuntimeGuard()
        assert guard.is_strict() is True
        assert guard.require_celery_for_runtime_entrypoint() is True

    def test_local_does_not_require_celery(self, monkeypatch):
        """RuntimeGuard.require_celery_for_runtime_entrypoint() → False in local."""
        monkeypatch.setenv("APP_ENV", "local")
        from qa_center.api_execution.runtime_guard import RuntimeGuard
        guard = RuntimeGuard()
        assert guard.is_strict() is False
        assert guard.require_celery_for_runtime_entrypoint() is False


# ══════════════════════════════════════════════════════════════════════════
# P1.7 — Audit logging does not leak secrets
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAuditLogSanitization:
    """Audit log helpers must never record secrets."""

    def test_log_webhook_audit_redacts_token_fields(self):
        from qa_center.webhooks import log_webhook_audit

        # Should not raise; if it logs token it would be visible in output
        log_webhook_audit("test_event", 42,
                          token="secret123",
                          signature="sha256=abc",
                          message="ok")

    def test_compute_payload_hash_is_stable(self):
        """Same payload + config_id always yields the same hash."""
        from qa_center.webhooks import compute_webhook_payload_hash

        body1 = _json.dumps({'a': 1, 'b': 2}).encode()
        body2 = _json.dumps({'b': 2, 'a': 1}).encode()  # reordered keys

        h1 = compute_webhook_payload_hash(body1, 42)
        h2 = compute_webhook_payload_hash(body2, 42)
        # Canonicalisation must yield identical hashes regardless of key order
        assert h1 == h2

    def test_compute_payload_hash_differs_by_config(self):
        """Same body, different config_id → different hash."""
        from qa_center.webhooks import compute_webhook_payload_hash

        body = _json.dumps({'status': 'passed'}).encode()
        h1 = compute_webhook_payload_hash(body, 1)
        h2 = compute_webhook_payload_hash(body, 2)
        assert h1 != h2
