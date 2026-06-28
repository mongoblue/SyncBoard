import json
from urllib.parse import unquote, urlparse

import pytest
from asgiref.testing import ApplicationCommunicator
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from django.contrib.auth.models import AnonymousUser, User
from django.utils import timezone

from qa_center import consumers
from qa_center.models import (
    PerformanceTestCase,
    PerformanceTestResult,
    TestResult as QaTestResult,
    TestRun as QaTestRun,
)
from qa_center.routing import websocket_urlpatterns
from room.models import Project


class WebsocketCommunicator(ApplicationCommunicator):
    def __init__(self, application, path, headers=None, subprotocols=None):
        parsed = urlparse(path)
        self.scope = {
            'type': 'websocket',
            'path': unquote(parsed.path),
            'query_string': parsed.query.encode('utf-8'),
            'headers': headers or [],
            'subprotocols': subprotocols or [],
        }
        super().__init__(application, self.scope)

    async def connect(self, timeout=1):
        await self.send_input({'type': 'websocket.connect'})
        response = await self.receive_output(timeout)
        if response['type'] == 'websocket.close':
            return False, response.get('code', 1000)
        assert response['type'] == 'websocket.accept'
        return True, response.get('subprotocol', None)

    async def receive_json_from(self, timeout=1):
        response = await self.receive_output(timeout)
        assert response['type'] == 'websocket.send'
        return json.loads(response['text'])

    async def disconnect(self, code=1000, timeout=1):
        await self.send_input({'type': 'websocket.disconnect', 'code': code})
        await self.wait(timeout)


class _DiscardRecorder:
    def __init__(self):
        self.discarded = []

    async def group_discard(self, group_name, channel_name):
        self.discarded.append((group_name, channel_name))


application = URLRouter(websocket_urlpatterns)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


async def _communicator(path, user):
    communicator = WebsocketCommunicator(application, path)
    communicator.scope['user'] = user
    return communicator


@database_sync_to_async
def _create_user(username):
    return User.objects.create_user(username=username, password='pass')


@database_sync_to_async
def _create_project(owner, member=None, name='Project'):
    project = Project.objects.create(name=name, owner=owner)
    if member is not None:
        project.members.add(member)
    return project


@database_sync_to_async
def _create_test_run(project, user):
    return QaTestRun.objects.create(
        project=project,
        name='Run',
        trigger='manual',
        test_type='api',
        status='running',
        total_count=1,
        triggered_by=user,
        started_at=timezone.now(),
    )


@database_sync_to_async
def _create_performance_result(project, user):
    case = PerformanceTestCase.objects.create(
        project=project,
        name='Perf',
        url='https://example.com',
        method='GET',
        created_by=user,
    )
    result = QaTestResult.objects.create(
        test_type='performance',
        name='Perf Result',
        status='running',
        started_at=timezone.now(),
    )
    PerformanceTestResult.objects.create(
        test_case=case,
        test_result=result,
        executed_by=user,
        total_requests=1,
        successful_requests=1,
        failed_requests=0,
        avg_response_time_ms=10,
        min_response_time_ms=10,
        max_response_time_ms=10,
        p50_response_time_ms=10,
        p90_response_time_ms=10,
        p95_response_time_ms=10,
        p99_response_time_ms=10,
        throughput=1,
        error_rate=0,
    )
    return result


@database_sync_to_async
def _create_ui_result(project, task_id):
    return QaTestResult.objects.create(
        test_type='ui',
        name='UI Result',
        status='running',
        task_id=task_id,
        started_at=timezone.now(),
        test_params={'project_id': str(project.id)},
    )


@database_sync_to_async
def _create_duplicate_ui_results(project, other_project, task_id):
    QaTestResult.objects.create(
        test_type='ui',
        name='UI Result One',
        status='running',
        task_id=task_id,
        started_at=timezone.now(),
        test_params={'project_id': str(project.id)},
    )
    QaTestResult.objects.create(
        test_type='ui',
        name='UI Result Two',
        status='running',
        task_id=task_id,
        started_at=timezone.now(),
        test_params={'project_id': str(other_project.id)},
    )


@database_sync_to_async
def _create_ui_result_without_project(task_id):
    return QaTestResult.objects.create(
        test_type='ui',
        name='UI Result Without Project',
        status='running',
        task_id=task_id,
        started_at=timezone.now(),
        test_params={},
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_qa_dashboard_rejects_anonymous_user():
    communicator = await _communicator('/ws/qa/dashboard/', AnonymousUser())
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_qa_dashboard_accepts_authenticated_user():
    user = await _create_user('qa-dashboard-member')
    communicator = await _communicator('/ws/qa/dashboard/', user)
    connected, _ = await communicator.connect()
    assert connected is True
    message = await communicator.receive_json_from()
    assert message['type'] == 'connected'
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_recorder_rejects_anonymous_user():
    communicator = await _communicator('/ws/qa/recorder/', AnonymousUser())
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_test_run_progress_rejects_anonymous_user():
    owner = await _create_user('run-anonymous-owner')
    project = await _create_project(owner, name='Run Anonymous Project')
    run = await _create_test_run(project, owner)

    communicator = await _communicator(f'/ws/qa/test-run/{run.id}/', AnonymousUser())
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_test_run_progress_rejects_invalid_run_id():
    user = await _create_user('run-invalid-user')

    communicator = await _communicator('/ws/qa/test-run/abc/', user)
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_test_run_progress_rejects_outsider():
    owner = await _create_user('run-owner')
    outsider = await _create_user('run-outsider')
    project = await _create_project(owner, name='Run Project')
    run = await _create_test_run(project, owner)

    communicator = await _communicator(f'/ws/qa/test-run/{run.id}/', outsider)
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_test_run_progress_accepts_project_member():
    owner = await _create_user('run-owner-member')
    member = await _create_user('run-member')
    project = await _create_project(owner, member=member, name='Run Member Project')
    run = await _create_test_run(project, owner)

    communicator = await _communicator(f'/ws/qa/test-run/{run.id}/', member)
    connected, _ = await communicator.connect()
    assert connected is True
    message = await communicator.receive_json_from()
    assert message['type'] == 'connected'
    assert message['run_id'] == str(run.id)
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_performance_socket_rejects_anonymous_user():
    owner = await _create_user('perf-anonymous-owner')
    project = await _create_project(owner, name='Perf Anonymous Project')
    result = await _create_performance_result(project, owner)

    communicator = await _communicator(f'/ws/qa/performance/{result.id}/', AnonymousUser())
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_performance_socket_rejects_outsider():
    owner = await _create_user('perf-owner')
    outsider = await _create_user('perf-outsider')
    project = await _create_project(owner, name='Perf Project')
    result = await _create_performance_result(project, owner)

    communicator = await _communicator(f'/ws/qa/performance/{result.id}/', outsider)
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_performance_socket_accepts_project_member():
    owner = await _create_user('perf-owner-member')
    member = await _create_user('perf-member')
    project = await _create_project(owner, member=member, name='Perf Member Project')
    result = await _create_performance_result(project, owner)

    communicator = await _communicator(f'/ws/qa/performance/{result.id}/', member)
    connected, _ = await communicator.connect()
    assert connected is True
    message = await communicator.receive_json_from()
    assert message['type'] == 'connected'
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_ui_run_socket_rejects_anonymous_user():
    owner = await _create_user('ui-anonymous-owner')
    project = await _create_project(owner, name='UI Anonymous Project')
    await _create_ui_result(project, 'abc-anonymous')

    communicator = await _communicator('/ws/qa/run/abc-anonymous/', AnonymousUser())
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_ui_run_socket_rejects_outsider_for_hyphenated_task_id():
    owner = await _create_user('ui-owner')
    outsider = await _create_user('ui-outsider')
    project = await _create_project(owner, name='UI Project')
    await _create_ui_result(project, 'abc-123')

    communicator = await _communicator('/ws/qa/run/abc-123/', outsider)
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_ui_run_socket_accepts_member_for_hyphenated_task_id():
    owner = await _create_user('ui-owner-member')
    member = await _create_user('ui-member')
    project = await _create_project(owner, member=member, name='UI Member Project')
    await _create_ui_result(project, 'abc-456')

    communicator = await _communicator('/ws/qa/run/abc-456/', member)
    connected, _ = await communicator.connect()
    assert connected is True
    message = await communicator.receive_json_from()
    assert message['type'] == 'connected'
    assert message['task_id'] == 'abc-456'
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_ui_run_socket_rejects_result_without_project_scope():
    user = await _create_user('ui-noscope-user')
    await _create_ui_result_without_project('abc-noscope')

    communicator = await _communicator('/ws/qa/run/abc-noscope/', user)
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_ui_run_socket_rejects_duplicate_task_id():
    owner = await _create_user('ui-duplicate-owner')
    other_owner = await _create_user('ui-duplicate-other-owner')
    project = await _create_project(owner, name='UI Duplicate Project')
    other_project = await _create_project(other_owner, name='UI Duplicate Other Project')
    await _create_duplicate_ui_results(project, other_project, 'abc-duplicate')

    communicator = await _communicator('/ws/qa/run/abc-duplicate/', owner)
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4003


@pytest.mark.anyio
async def test_denied_consumers_disconnect_without_initialized_group_name():
    for consumer_class in (
        consumers.QAConsumer,
        consumers.RecorderConsumer,
        consumers.PerformanceTestConsumer,
        consumers.TestRunProgressConsumer,
        consumers.UiRunConsumer,
    ):
        consumer = consumer_class()
        consumer.channel_layer = _DiscardRecorder()
        consumer.channel_name = 'test-channel'

        await consumer.disconnect(4003)

        assert consumer.channel_layer.discarded == []


def test_asgi_websocket_uses_allowed_hosts_origin_validator():
    from django.conf import settings

    from backend.asgi import application as asgi_application

    websocket_app = asgi_application.application_mapping['websocket']
    assert websocket_app.__class__.__name__ == 'OriginValidator'
    assert websocket_app.allowed_origins == settings.ALLOWED_HOSTS
