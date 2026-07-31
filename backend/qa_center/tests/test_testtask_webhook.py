"""TestTask Webhook 触发端点测试：token 鉴权、触发执行、限流、错误路径。"""
import time
from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from qa_center.models import TestResult, TestTask


def _make_task(mock_project, mock_user, **kwargs):
    return TestTask.objects.create(
        name=kwargs.pop('name', 'Webhook Task'),
        test_type=kwargs.pop('test_type', 'api'),
        project=mock_project,
        created_by=mock_user,
        trigger_type=kwargs.pop('trigger_type', 'webhook'),
        test_config=kwargs.pop('test_config', {'api_cases': []}),
        **kwargs,
    )


def _client():
    return APIClient()  # webhook 端点不要求 session 认证


@pytest.mark.django_db
def test_webhook_trigger_starts_execution(mock_project, mock_user):
    from qa_center.models import ApiAutoTestCase

    case = ApiAutoTestCase.objects.create(
        project=mock_project, name='wh-case', url='/wh', method='GET',
        created_by=mock_user,
    )
    task = _make_task(mock_project, mock_user, test_config={'api_cases': [case.id]})

    client = _client()
    with patch('qa_center.views_devops.threading.Thread'):
        resp = client.post(
            f'/api/qa/devops/tasks/{task.id}/webhook/{task.webhook_token}/',
            data={},
            content_type='application/json',
        )

    assert resp.status_code == 200, resp.content
    assert resp.data['runtime_mode'] in ('thread_fallback',)
    assert resp.data['execution_id'] is not None
    tr = TestResult.objects.get(id=resp.data['execution_id'])
    assert tr.status == 'running'
    assert tr.task_id == str(task.id)
    # 任务状态已更新
    task.refresh_from_db()
    assert task.status == 'running'
    assert task.execution_count == 1


@pytest.mark.django_db
def test_webhook_trigger_rejects_wrong_token(mock_project, mock_user):
    task = _make_task(mock_project, mock_user)

    client = _client()
    resp = client.post(
        f'/api/qa/devops/tasks/{task.id}/webhook/wrong-token/',
        data={},
        content_type='application/json',
    )
    assert resp.status_code == 403
    task.refresh_from_db()
    assert task.execution_count == 0


@pytest.mark.django_db
def test_webhook_trigger_rejects_non_webhook_task(mock_project, mock_user):
    task = _make_task(mock_project, mock_user, trigger_type='manual')

    client = _client()
    resp = client.post(
        f'/api/qa/devops/tasks/{task.id}/webhook/{task.webhook_token}/',
        data={},
        content_type='application/json',
    )
    assert resp.status_code == 403
    task.refresh_from_db()
    assert task.execution_count == 0


@pytest.mark.django_db
def test_webhook_trigger_404_for_inactive_task(mock_project, mock_user):
    task = _make_task(mock_project, mock_user, is_active=False)

    client = _client()
    resp = client.post(
        f'/api/qa/devops/tasks/{task.id}/webhook/{task.webhook_token}/',
        data={},
        content_type='application/json',
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_webhook_trigger_rejects_running_task(mock_project, mock_user):
    task = _make_task(mock_project, mock_user, status='running')

    client = _client()
    resp = client.post(
        f'/api/qa/devops/tasks/{task.id}/webhook/{task.webhook_token}/',
        data={},
        content_type='application/json',
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_webhook_trigger_rate_limited(mock_project, mock_user):
    task = _make_task(mock_project, mock_user)
    client = APIClient()

    # 打满 5 次窗口计数
    cache.clear()
    window = int(time.time()) // 60
    cache.set(f'testtask:webhook:{task.id}:{window}', 5, 120)

    resp = client.post(
        f'/api/qa/devops/tasks/{task.id}/webhook/{task.webhook_token}/',
        data={},
        content_type='application/json',
    )
    assert resp.status_code == 429
    task.refresh_from_db()
    assert task.execution_count == 0


@pytest.mark.django_db
def test_webhook_token_exposed_in_detail_serializer(
    mock_user, mock_project,
):
    from django.contrib.auth.models import User
    task = _make_task(mock_project, mock_user)
    other = User.objects.create_user(username='wh-viewer', password='x')
    mock_project.members.add(other)
    client = APIClient()
    client.force_authenticate(user=other)
    resp = client.get(f'/api/qa/devops/tasks/{task.id}/')
    assert resp.status_code == 200
    assert str(resp.data['webhook_token']) == str(task.webhook_token)
