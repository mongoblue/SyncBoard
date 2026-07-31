"""TestTask 定时调度接线测试：创建/更新/删除时同步 celery-beat PeriodicTask。"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from qa_center.models import TestTask


def _auth_client(mock_user):
    client = APIClient()
    client.force_authenticate(user=mock_user)
    return client


@pytest.fixture
def beat_available(monkeypatch):
    """模拟 django-celery-beat 已安装且可用。"""
    monkeypatch.setattr(
        'qa_center.services.devops.test_execution_service.TestExecutionService'
        '._celery_beat_available',
        lambda self: True,
    )


@pytest.fixture
def periodic_task_mocks():
    """Mock django_celery_beat 的 CrontabSchedule / PeriodicTask。"""
    crontab_schedule = patch(
        'django_celery_beat.models.CrontabSchedule'
    ).start()
    periodic_task = patch(
        'django_celery_beat.models.PeriodicTask'
    ).start()
    # get_or_create / update_or_create 都返回 (obj, created) 元组
    crontab_schedule.objects.get_or_create.return_value = (
        crontab_schedule.objects.get_or_create.return_value,
        False,
    )
    periodic_task.objects.update_or_create.return_value = (
        periodic_task.objects.update_or_create.return_value,
        True,
    )
    yield crontab_schedule, periodic_task
    patch.stopall()


def _task_payload(project_id, **overrides):
    payload = {
        'name': 'Scheduled Task',
        'test_type': 'api',
        'project': project_id,
        'trigger_type': 'scheduled',
        'cron_expression': '0 2 * * *',
        'test_config': {'api_cases': []},
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_create_scheduled_task_registers_periodic_task(
    mock_user, mock_project, beat_available, periodic_task_mocks,
):
    _, periodic_task = periodic_task_mocks
    client = _auth_client(mock_user)
    resp = client.post(
        '/api/qa/devops/tasks/',
        _task_payload(mock_project.id),
        content_type='application/json',
    )
    assert resp.status_code == 201, resp.content

    task = TestTask.objects.get(id=resp.data['id'])
    assert task.trigger_type == 'scheduled'

    pt = periodic_task.objects.update_or_create
    assert pt.call_count == 1
    name = pt.call_args.kwargs['name']
    defaults = pt.call_args.kwargs['defaults']
    assert name == f"qa_center.test_task.{task.id}"
    assert defaults['task'] == 'qa_center.execute_test_task'
    assert defaults['args'] == f'[{task.id}]'
    assert defaults['enabled'] is True


@pytest.mark.django_db
def test_create_scheduled_task_with_invalid_cron_rejected(
    mock_user, mock_project, beat_available, periodic_task_mocks,
):
    _, periodic_task = periodic_task_mocks
    client = _auth_client(mock_user)
    resp = client.post(
        '/api/qa/devops/tasks/',
        _task_payload(mock_project.id, cron_expression='not-a-cron'),
        content_type='application/json',
    )
    assert resp.status_code == 400, resp.content
    assert not TestTask.objects.filter(name='Scheduled Task').exists()
    periodic_task.objects.update_or_create.assert_not_called()


@pytest.mark.django_db
def test_update_scheduled_task_resyncs_periodic_task(
    mock_user, mock_project, beat_available, periodic_task_mocks,
):
    _, periodic_task = periodic_task_mocks
    task = TestTask.objects.create(
        name='Scheduled Task',
        test_type='api',
        project=mock_project,
        created_by=mock_user,
        trigger_type='scheduled',
        cron_expression='0 2 * * *',
        test_config={'api_cases': []},
    )
    periodic_task.objects.update_or_create.reset_mock()

    client = _auth_client(mock_user)
    resp = client.put(
        f'/api/qa/devops/tasks/{task.id}/',
        {'name': 'Renamed Task', 'is_active': False},
        content_type='application/json',
    )
    assert resp.status_code == 200, resp.content

    pt = periodic_task.objects.update_or_create
    assert pt.call_count == 1
    defaults = pt.call_args.kwargs['defaults']
    assert defaults['enabled'] is False  # is_active=False 同步到 PeriodicTask
    assert defaults['description'] == 'Scheduled TestTask: Renamed Task'


@pytest.mark.django_db
def test_update_scheduled_task_to_manual_unregisters(
    mock_user, mock_project, beat_available, periodic_task_mocks,
):
    _, periodic_task = periodic_task_mocks
    task = TestTask.objects.create(
        name='Scheduled Task',
        test_type='api',
        project=mock_project,
        created_by=mock_user,
        trigger_type='scheduled',
        cron_expression='0 2 * * *',
        test_config={'api_cases': []},
    )

    client = _auth_client(mock_user)
    resp = client.put(
        f'/api/qa/devops/tasks/{task.id}/',
        {'trigger_type': 'manual', 'cron_expression': ''},
        content_type='application/json',
    )
    assert resp.status_code == 200, resp.content

    periodic_task.objects.filter.return_value.delete.assert_called_once()


@pytest.mark.django_db
def test_delete_scheduled_task_unregisters(
    mock_user, mock_project, beat_available, periodic_task_mocks,
):
    _, periodic_task = periodic_task_mocks
    task = TestTask.objects.create(
        name='Scheduled Task',
        test_type='api',
        project=mock_project,
        created_by=mock_user,
        trigger_type='scheduled',
        cron_expression='0 2 * * *',
        test_config={'api_cases': []},
    )

    client = _auth_client(mock_user)
    resp = client.delete(f'/api/qa/devops/tasks/{task.id}/')
    assert resp.status_code == 200, resp.content
    assert not TestTask.objects.filter(id=task.id).exists()
    periodic_task.objects.filter.return_value.delete.assert_called_once()
