# QA WebSocket Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent anonymous and cross-project access to QA WebSocket streams and add standard origin validation at the ASGI boundary.

**Architecture:** Keep the current Channels consumers but add small async authorization helpers inside `backend/qa_center/consumers.py`. Each consumer rejects unauthenticated users with close code `4003`; ID-scoped consumers load the backing model and verify project owner/member before joining a group. ASGI wraps the existing WebSocket router with Channels' `AllowedHostsOriginValidator`.

**Tech Stack:** Django 6, Channels, pytest-django, channels.testing.WebsocketCommunicator.

---

## Files

- Modify: `backend/backend/asgi.py`
  - Wrap WebSocket application with `AllowedHostsOriginValidator`.
- Modify: `backend/qa_center/consumers.py`
  - Add async auth/project-access helpers.
  - Guard QA dashboard, recorder, performance, TestRun, and UI-run sockets.
- Modify: `backend/qa_center/routing.py`
  - Allow hyphenated UI run `task_id` values.
- Create: `backend/tests/test_qa_websocket_security.py`
  - Regression tests for anonymous rejection, member access, outsider rejection, and hyphenated task IDs.

---

### Task 1: Add WebSocket regression test scaffolding

- [ ] **Step 1: Create `backend/tests/test_qa_websocket_security.py`**

Use this structure:

```python
import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.utils import timezone

from qa_center.models import PerformanceTestCase, PerformanceTestResult, TestResult, TestRun
from qa_center.routing import websocket_urlpatterns
from room.models import Project


application = URLRouter(websocket_urlpatterns)


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
```

- [ ] **Step 2: Run import/collection check**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py --collect-only -q
```

Expected: collection succeeds with zero or listed tests depending on current file content.

---

### Task 2: Dashboard and recorder require authentication

- [ ] **Step 1: Add failing tests**

Append:

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_qa_dashboard_rejects_anonymous_user():
    communicator = await _communicator('/ws/qa/dashboard/', AnonymousUser())
    connected, _ = await communicator.connect()
    assert connected is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_qa_dashboard_accepts_authenticated_user():
    user = await _create_user('qa-dashboard-member')
    communicator = await _communicator('/ws/qa/dashboard/', user)
    connected, _ = await communicator.connect()
    assert connected is True
    message = await communicator.receive_json_from()
    assert message['type'] == 'connected'
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_recorder_rejects_anonymous_user():
    communicator = await _communicator('/ws/qa/recorder/', AnonymousUser())
    connected, _ = await communicator.connect()
    assert connected is False
```

- [ ] **Step 2: Run RED**

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py::test_qa_dashboard_rejects_anonymous_user tests/test_qa_websocket_security.py::test_qa_dashboard_accepts_authenticated_user tests/test_qa_websocket_security.py::test_recorder_rejects_anonymous_user -v
```

Expected: anonymous rejection tests fail because consumers currently accept them; authenticated dashboard may fail until a connected message is added.

- [ ] **Step 3: Implement minimal consumer auth in `backend/qa_center/consumers.py`**

Add helper:

```python
async def _close_if_anonymous(consumer):
    user = consumer.scope.get('user')
    if not user or not user.is_authenticated:
        await consumer.close(code=4003)
        return True
    return False
```

At the start of `QAConsumer.connect` and `RecorderConsumer.connect`:

```python
if await _close_if_anonymous(self):
    return
```

In `QAConsumer.connect`, after `accept()`, send:

```python
await self.send(text_data=json.dumps({'type': 'connected'}))
```

- [ ] **Step 4: Run GREEN**

Run the same three tests and expect PASS.

---

### Task 3: TestRun progress socket requires project membership

- [ ] **Step 1: Add failing tests**

Append:

```python
@database_sync_to_async
def _create_test_run(project, user):
    return TestRun.objects.create(
        project=project,
        name='Run',
        trigger='manual',
        test_type='api',
        status='running',
        total_count=1,
        triggered_by=user,
        started_at=timezone.now(),
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_test_run_progress_rejects_outsider():
    owner = await _create_user('run-owner')
    outsider = await _create_user('run-outsider')
    project = await _create_project(owner, name='Run Project')
    run = await _create_test_run(project, owner)

    communicator = await _communicator(f'/ws/qa/test-run/{run.id}/', outsider)
    connected, _ = await communicator.connect()
    assert connected is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
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
```

- [ ] **Step 2: Run RED**

Run the two tests. Expected: outsider test fails because current consumer accepts all.

- [ ] **Step 3: Implement TestRun authorization**

Add imports:

```python
from channels.db import database_sync_to_async
from .models import PerformanceTestResult, TestResult, TestRun
```

Add helpers:

```python
@database_sync_to_async

def _user_can_access_project(user, project):
    return user == project.owner or project.members.filter(id=user.id).exists()


@database_sync_to_async

def _get_test_run_project(run_id):
    try:
        return TestRun.objects.select_related('project__owner').prefetch_related('project__members').get(id=run_id).project
    except TestRun.DoesNotExist:
        return None
```

In `TestRunProgressConsumer.connect`, reject if anonymous, missing run, or no project access before group join.

- [ ] **Step 4: Run GREEN**

Run both tests and expect PASS.

---

### Task 4: Performance socket requires project membership

- [ ] **Step 1: Add failing tests**

Append helpers/tests:

```python
@database_sync_to_async
def _create_performance_result(project, user):
    case = PerformanceTestCase.objects.create(
        project=project,
        name='Perf',
        url='https://example.com',
        method='GET',
        created_by=user,
    )
    result = TestResult.objects.create(
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_performance_socket_rejects_outsider():
    owner = await _create_user('perf-owner')
    outsider = await _create_user('perf-outsider')
    project = await _create_project(owner, name='Perf Project')
    result = await _create_performance_result(project, owner)

    communicator = await _communicator(f'/ws/qa/performance/{result.id}/', outsider)
    connected, _ = await communicator.connect()
    assert connected is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
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
```

- [ ] **Step 2: Run RED**

Run the two tests. Expected: outsider test fails because current consumer accepts all.

- [ ] **Step 3: Implement Performance authorization**

Add helper to load `PerformanceTestResult.objects.select_related('test_case__project__owner')` by `test_result_id=execution_id`; return project or `None`. In `PerformanceTestConsumer.connect`, reject anonymous, missing execution, or no project access before group join.

- [ ] **Step 4: Run GREEN**

Run both tests and expect PASS.

---

### Task 5: UI run socket supports hyphenated task IDs and requires membership

- [ ] **Step 1: Add failing tests**

Append:

```python
@database_sync_to_async
def _create_ui_result(project, task_id):
    return TestResult.objects.create(
        test_type='ui',
        name='UI Result',
        status='running',
        task_id=task_id,
        started_at=timezone.now(),
        test_params={'project_id': str(project.id)},
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ui_run_socket_rejects_outsider_for_hyphenated_task_id():
    owner = await _create_user('ui-owner')
    outsider = await _create_user('ui-outsider')
    project = await _create_project(owner, name='UI Project')
    await _create_ui_result(project, 'abc-123')

    communicator = await _communicator('/ws/qa/run/abc-123/', outsider)
    connected, _ = await communicator.connect()
    assert connected is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
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
```

- [ ] **Step 2: Run RED**

Run the two tests. Expected: route or authorization fails because current regex does not accept hyphens and consumer accepts all matched routes.

- [ ] **Step 3: Implement route and UI authorization**

In `backend/qa_center/routing.py`, change:

```python
re_path(r'ws/qa/run/(?P<task_id>[-\\w]+)/$', consumers.UiRunConsumer.as_asgi()),
```

Add helper to load `TestResult` by `task_id`, read `test_params['project_id']`, load `Project`, and authorize user. In `UiRunConsumer.connect`, reject anonymous, missing result/project, or no project access before group join.

- [ ] **Step 4: Run GREEN**

Run both tests and expect PASS.

---

### Task 6: Add ASGI origin validator

- [ ] **Step 1: Add a static regression test**

Append:

```python
def test_asgi_websocket_uses_allowed_hosts_origin_validator():
    from backend.asgi import application as asgi_application

    websocket_app = asgi_application.application_mapping['websocket']
    assert websocket_app.__class__.__name__ == 'AllowedHostsOriginValidator'
```

- [ ] **Step 2: Run RED**

Run this test. Expected: fails because websocket app is currently `AuthMiddlewareStack`.

- [ ] **Step 3: Implement ASGI wrapper**

In `backend/backend/asgi.py`, import:

```python
from channels.security.websocket import AllowedHostsOriginValidator
```

Wrap websocket app:

```python
"websocket": AllowedHostsOriginValidator(
    AuthMiddlewareStack(
        URLRouter(room.routing.websocket_urlpatterns)
    )
),
```

- [ ] **Step 4: Run GREEN**

Run the static test and expect PASS.

---

### Task 7: Full verification and commit

- [ ] **Step 1: Run WebSocket security tests**

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run compile check**

```bash
cd D:/Projects/SyncBoard/backend && python -m compileall backend qa_center
```

Expected: exit code 0.

- [ ] **Step 3: Stage explicit paths**

```bash
git -C D:/Projects/SyncBoard add -- backend/backend/asgi.py backend/qa_center/consumers.py backend/qa_center/routing.py backend/tests/test_qa_websocket_security.py docs/superpowers/plans/2026-06-28-qa-websocket-security.md
```

- [ ] **Step 4: Verify staged files and commit**

```bash
git -C D:/Projects/SyncBoard diff --cached --check
git -C D:/Projects/SyncBoard diff --cached --name-status
git -C D:/Projects/SyncBoard commit -m "fix(qa): secure websocket subscriptions"
```
