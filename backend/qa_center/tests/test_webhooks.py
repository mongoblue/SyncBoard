from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


def test_correct_hmac_sha256_signature_passes():
    from qa_center.webhooks import verify_webhook_signature

    payload = b'{"status":"passed"}'
    secret = "shared-secret"
    signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(payload, f"sha256={signature}", secret) is True


def test_wrong_signature_rejected():
    from qa_center.webhooks import verify_webhook_signature

    payload = b'{"status":"passed"}'

    assert verify_webhook_signature(payload, "sha256=deadbeef", "shared-secret") is False


def test_missing_signature_rejected():
    from qa_center.webhooks import verify_webhook_signature

    assert verify_webhook_signature(b"{}", "", "shared-secret") is False


def test_webhook_dedup_rejects_replay():
    from qa_center.webhooks import check_webhook_dedup

    cache.clear()
    assert check_webhook_dedup(1, "ext-run-1") is False
    assert check_webhook_dedup(1, "ext-run-1") is True


def test_webhook_rate_limit_blocks_after_threshold():
    from qa_center.webhooks import check_webhook_rate_limit

    cache.clear()
    blocked = []
    for _ in range(6):
        blocked.append(check_webhook_rate_limit(123)[0])

    assert blocked[-1] is True


@pytest.mark.django_db
def test_pipeline_webhook_duplicate_external_run_id_returns_duplicate(cicd_config):
    client = APIClient()
    cicd_config.api_token = "token-123456"
    cicd_config.save(update_fields=["api_token"])
    payload = {
        "external_run_id": "dup-run-1",
        "status": "passed",
    }

    first = client.post(
        f"/api/qa/devops/cicd-config/{cicd_config.id}/webhook/",
        payload,
        format="json",
        HTTP_X_CI_TOKEN=cicd_config.api_token,
    )
    second = client.post(
        f"/api/qa/devops/cicd-config/{cicd_config.id}/webhook/",
        payload,
        format="json",
        HTTP_X_CI_TOKEN=cicd_config.api_token,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["message"] == "duplicate"
