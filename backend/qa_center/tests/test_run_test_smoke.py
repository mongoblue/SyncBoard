"""RunTestView 冒烟入口落库测试：执行结果进入 TestResult。"""
from unittest.mock import patch, MagicMock

import pytest
from rest_framework.test import APIClient

from qa_center.models import TestResult


def _make_client(mock_user):
    client = APIClient()
    client.force_authenticate(user=mock_user)
    return client


@pytest.mark.django_db
def test_run_test_creates_running_result(mock_user, mock_project):
    client = _make_client(mock_user)

    with patch('qa_center.views.threading.Thread') as thread_cls:
        resp = client.post(
            '/api/qa/run-test/',
            data={'test_type': 'api', 'project_id': mock_project.id},
            content_type='application/json',
        )

    assert resp.status_code == 200
    assert resp.data['result_id'] is not None
    tr = TestResult.objects.get(id=resp.data['result_id'])
    assert tr.status == 'running'
    assert tr.project_id == mock_project.id
    assert tr.executed_by_id == mock_user.id
    assert tr.source == 'manual'
    thread_cls.assert_called_once()


@pytest.mark.django_db
def test_run_test_persists_success(mock_user, mock_project):
    from qa_center.views import RunTestView

    tr = TestResult.objects.create(
        test_type='api', name='smoke', project=mock_project,
        status='running', executed_by=mock_user, source='manual',
    )

    view = RunTestView()
    view._persist_smoke_result(tr.id, 0, ['python', '-m', 'pytest'])

    tr.refresh_from_db()
    assert tr.status == 'passed'
    assert tr.completed_at is not None
    assert '冒烟执行' in tr.test_log


@pytest.mark.django_db
def test_run_test_persists_failure(mock_user, mock_project):
    from qa_center.views import RunTestView

    tr = TestResult.objects.create(
        test_type='api', name='smoke', project=mock_project,
        status='running', executed_by=mock_user, source='manual',
    )

    view = RunTestView()
    view._persist_smoke_result(tr.id, 1, ['python', '-m', 'pytest'], error='boom')

    tr.refresh_from_db()
    assert tr.status == 'failed'
    assert tr.error_message == 'boom'  # 异常信息优先
    assert tr.test_log is not None
