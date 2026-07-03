from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qa_center.pipeline import CiJobResult
from qa_center.pipeline.gitlab import GitLabClient
from qa_center.pipeline.jenkins import JenkinsClient


@pytest.mark.django_db
def test_gitlab_client_status_mapping_from_api_payload(cicd_config):
    cicd_config.ci_type = "gitlab"
    cicd_config.save(update_fields=["ci_type"])
    client = GitLabClient(cicd_config)

    run = MagicMock(external_run_id="123", external_url="https://ci.example.test/123", status="running")
    with pytest.MonkeyPatch.context() as mp:
        fake_resp = MagicMock()
        fake_resp.raise_for_status.return_value = None
        fake_resp.json.return_value = {"status": "success", "web_url": "https://ci.example.test/123", "duration": 12}
        mp.setattr(client, "_get_session", lambda: MagicMock(get=lambda *a, **k: fake_resp))
        status = client.get_status(run)

    assert status.status == "passed"


@pytest.mark.django_db
def test_jenkins_client_status_mapping_from_api_payload(cicd_config):
    cicd_config.ci_type = "jenkins"
    cicd_config.save(update_fields=["ci_type"])
    client = JenkinsClient(cicd_config)

    run = MagicMock(external_run_id="55", external_url="https://ci.example.test/55", status="running")
    with pytest.MonkeyPatch.context() as mp:
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"state": "FINISHED", "result": "SUCCESS", "durationInMillis": 18}
        session = MagicMock(get=lambda *a, **k: fake_resp)
        mp.setattr(client, "_get_session", lambda: session)
        status = client.get_status(run)

    assert status.status == "passed"


@pytest.mark.django_db
def test_gitlab_client_get_jobs_maps_statuses(cicd_config):
    cicd_config.ci_type = "gitlab"
    cicd_config.save(update_fields=["ci_type"])
    client = GitLabClient(cicd_config)
    run = MagicMock(external_run_id="123")

    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = [
        {"name": "test", "stage": "qa", "status": "failed", "duration": 2, "id": 77, "web_url": "https://ci/job/77"}
    ]
    fake_resp.links = {}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(client, "_get_session", lambda: MagicMock(get=lambda *a, **k: fake_resp))
        jobs = client.get_jobs(run)

    assert jobs[0].status == "failed"

