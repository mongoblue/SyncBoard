# QA Dashboard Project Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent authenticated users from receiving other projects' QA dashboard progress events through the global `qa_dashboard` WebSocket group.

**Architecture:** Add a project-scoped QA dashboard WebSocket route that joins `qa_dashboard_<project_id>` only after owner/member authorization. Move run-plan progress broadcasts to the same project-scoped group, while leaving the legacy `/ws/qa/dashboard/` route authenticated-only for compatibility and not using it for project-scoped events.

**Tech Stack:** Django 6, Channels, pytest-django, pytest-anyio, asgiref test communicator, unittest.mock.

---

## Files

- Modify: `backend/qa_center/routing.py`
  - Add `/ws/qa/dashboard/<project_id>/` before the legacy `/ws/qa/dashboard/` route.
- Modify: `backend/qa_center/consumers.py`
  - Add project lookup helper for dashboard project IDs.
  - Update `QAConsumer.connect()` to authorize project-scoped dashboard subscriptions and join `qa_dashboard_<project_id>`.
  - Keep legacy dashboard route authenticated and connected, but without claiming project isolation for it.
- Modify: `backend/qa_center/run_plan_executor.py`
  - Change `_broadcast()` to accept `project_id` and send to `qa_dashboard_<project_id>`.
  - Pass `self.plan.project_id` for started, case_done, and finished run-plan progress events.
- Modify: `backend/tests/test_qa_websocket_security.py`
  - Add tests for project-scoped dashboard outsider rejection, member acceptance, owner acceptance, invalid project ID rejection, and legacy route compatibility.
- Modify: `backend/tests/test_run_plan.py`
  - Add/adjust tests proving run-plan executor broadcasts to `qa_dashboard_<project_id>` and no longer uses the global `qa_dashboard` group for run-plan progress.

---

### Task 1: Add RED tests for project-scoped QA dashboard subscriptions

**Files:**
- Modify: `backend/tests/test_qa_websocket_security.py`

- [ ] **Step 1: Add project-scoped dashboard WebSocket tests**

Insert these tests after `test_qa_dashboard_accepts_authenticated_user` in `backend/tests/test_qa_websocket_security.py`:

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_project_dashboard_rejects_outsider():
    owner = await _create_user('qa-project-dashboard-owner')
    outsider = await _create_user('qa-project-dashboard-outsider')
    project = await _create_project(owner, name='QA Project Dashboard')

    communicator = await _communicator(f'/ws/qa/dashboard/{project.id}/', outsider)
    connected, code = await communicator.connect()

    assert connected is False
    assert code == 4003


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_project_dashboard_accepts_project_member():
    owner = await _create_user('qa-project-dashboard-owner-member')
    member = await _create_user('qa-project-dashboard-member')
    project = await _create_project(owner, member=member, name='QA Project Dashboard Member')

    communicator = await _communicator(f'/ws/qa/dashboard/{project.id}/', member)
    connected, _ = await communicator.connect()

    assert connected is True
    message = await communicator.receive_json_from()
    assert message['type'] == 'connected'
    assert message['project_id'] == str(project.id)
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_project_dashboard_accepts_project_owner():
    owner = await _create_user('qa-project-dashboard-owner-access')
    project = await _create_project(owner, name='QA Project Dashboard Owner')

    communicator = await _communicator(f'/ws/qa/dashboard/{project.id}/', owner)
    connected, _ = await communicator.connect()

    assert connected is True
    message = await communicator.receive_json_from()
    assert message['type'] == 'connected'
    assert message['project_id'] == str(project.id)
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.anyio
async def test_project_dashboard_rejects_invalid_project_id():
    user = await _create_user('qa-project-dashboard-invalid')

    communicator = await _communicator('/ws/qa/dashboard/abc/', user)
    connected, code = await communicator.connect()

    assert connected is False
    assert code == 4003
```

- [ ] **Step 2: Run RED for the new dashboard tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py::test_project_dashboard_rejects_outsider tests/test_qa_websocket_security.py::test_project_dashboard_accepts_project_member tests/test_qa_websocket_security.py::test_project_dashboard_accepts_project_owner tests/test_qa_websocket_security.py::test_project_dashboard_rejects_invalid_project_id -v
```

Expected: tests fail before implementation because `/ws/qa/dashboard/<project_id>/` is not routed.

---

### Task 2: Implement project-scoped QA dashboard route and authorization

**Files:**
- Modify: `backend/qa_center/routing.py`
- Modify: `backend/qa_center/consumers.py`
- Test: `backend/tests/test_qa_websocket_security.py`

- [ ] **Step 1: Add the project-scoped dashboard route**

In `backend/qa_center/routing.py`, update the route list to place the new project route before the legacy route:

```python
websocket_urlpatterns = [
    re_path(r'ws/qa/dashboard/(?P<project_id>[-\w]+)/$', consumers.QAConsumer.as_asgi()),
    re_path(r'ws/qa/dashboard/$', consumers.QAConsumer.as_asgi()),
    re_path(r'ws/qa/recorder/$', consumers.RecorderConsumer.as_asgi()),
    re_path(r'ws/qa/performance/(?P<execution_id>\d+)/$', consumers.PerformanceTestConsumer.as_asgi()),
    re_path(r'ws/qa/test-run/(?P<run_id>\w+)/$', consumers.TestRunProgressConsumer.as_asgi()),
    re_path(r'ws/qa/run/(?P<task_id>[-\w]+)/$', consumers.UiRunConsumer.as_asgi()),
]
```

- [ ] **Step 2: Add a dashboard project lookup helper**

In `backend/qa_center/consumers.py`, insert this helper after `_user_can_access_project()`:

```python
@database_sync_to_async
def _get_dashboard_project(project_id):
    try:
        return Project.objects.select_related('owner').prefetch_related('members').get(id=project_id)
    except (Project.DoesNotExist, ValueError, TypeError, ValidationError):
        return None
```

- [ ] **Step 3: Update `QAConsumer.connect()`**

Replace `QAConsumer.connect()` with:

```python
    async def connect(self):
        if await _close_if_anonymous(self):
            return

        self.project_id = self.scope.get('url_route', {}).get('kwargs', {}).get('project_id')
        if self.project_id:
            project = await _get_dashboard_project(self.project_id)
            if project is None or not await _user_can_access_project(self.scope['user'], project):
                await self.close(code=4003)
                return
            self.group_name = f"qa_dashboard_{project.id}"
        else:
            self.group_name = "qa_dashboard"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        message = {'type': 'connected'}
        if self.project_id:
            message['project_id'] = str(self.project_id)
        await self.send(text_data=json.dumps(message))
```

- [ ] **Step 4: Run GREEN for project-scoped dashboard tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py::test_project_dashboard_rejects_outsider tests/test_qa_websocket_security.py::test_project_dashboard_accepts_project_member tests/test_qa_websocket_security.py::test_project_dashboard_accepts_project_owner tests/test_qa_websocket_security.py::test_project_dashboard_rejects_invalid_project_id -v
```

Expected: all four tests pass.

- [ ] **Step 5: Run legacy dashboard compatibility tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py::test_qa_dashboard_rejects_anonymous_user tests/test_qa_websocket_security.py::test_qa_dashboard_accepts_authenticated_user -v
```

Expected: both tests pass. The legacy route remains authenticated-only and returns `{'type': 'connected'}` without `project_id`.

---

### Task 3: Add RED tests for project-scoped run-plan broadcasting

**Files:**
- Modify: `backend/tests/test_run_plan.py`

- [ ] **Step 1: Import `call` for group-send assertions**

Change the import at the top of `backend/tests/test_run_plan.py` from:

```python
from unittest.mock import patch, MagicMock
```

to:

```python
from unittest.mock import call, patch, MagicMock
```

- [ ] **Step 2: Add a direct `_broadcast()` group-name regression test**

Inside `class TestRunPlanExecutor`, after `test_progress_broadcast_called`, add:

```python
    def test_broadcast_sends_run_plan_progress_to_project_dashboard_group(self, test_project):
        from qa_center.run_plan_executor import _broadcast

        with patch('qa_center.run_plan_executor.get_channel_layer') as get_layer, \
             patch('qa_center.run_plan_executor.async_to_sync') as to_sync:
            layer = MagicMock()
            get_layer.return_value = layer
            sender = MagicMock()
            to_sync.return_value = sender

            _broadcast({'type': 'run_plan_progress', 'phase': 'started'}, project_id=test_project.id)

        to_sync.assert_called_once_with(layer.group_send)
        sender.assert_called_once_with(
            f'qa_dashboard_{test_project.id}',
            {'type': 'run_plan_progress', 'phase': 'started'},
        )
```

- [ ] **Step 3: Add executor progress project-id propagation test**

Inside `class TestRunPlanExecutor`, after the new direct `_broadcast()` test, add:

```python
    def test_progress_broadcast_includes_plan_project_id(self, test_project, test_user, cases):
        from qa_center.run_plan_executor import TestRunPlanExecutor

        plan = self._make_plan(test_project, test_user, [c.id for c in cases])
        with patch('qa_center.run_plan_executor._broadcast') as bc, \
             patch('requests.Session.request', return_value=_mock_response()):
            TestRunPlanExecutor(plan, user=test_user).execute()

        assert bc.call_count == 5
        assert all(call.kwargs['project_id'] == test_project.id for call in bc.call_args_list)
```

- [ ] **Step 4: Run RED for broadcasting tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_run_plan.py::TestRunPlanExecutor::test_broadcast_sends_run_plan_progress_to_project_dashboard_group tests/test_run_plan.py::TestRunPlanExecutor::test_progress_broadcast_includes_plan_project_id -v
```

Expected: tests fail because `_broadcast()` does not accept `project_id`, imports `get_channel_layer` inside the function, and the executor calls `_broadcast(event)` without keyword arguments.

---

### Task 4: Implement project-scoped run-plan broadcasting

**Files:**
- Modify: `backend/qa_center/run_plan_executor.py`
- Test: `backend/tests/test_run_plan.py`

- [ ] **Step 1: Add module-level Channels imports**

In `backend/qa_center/run_plan_executor.py`, add these imports near the other imports:

```python
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
```

- [ ] **Step 2: Replace `_broadcast()` with project-scoped implementation**

Replace the current `_broadcast(event: dict)` function with:

```python
def _broadcast(event: dict, *, project_id: int) -> None:
    """向项目作用域 QA dashboard 组广播一条进度事件。channels 不可用时静默忽略。"""
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(f'qa_dashboard_{project_id}', event)
    except Exception as e:  # pragma: no cover
        logger.debug('[RunPlan] broadcast failed: %s', e)
```

- [ ] **Step 3: Update started event broadcast**

In `TestRunPlanExecutor.execute()`, replace:

```python
        _broadcast({
            'type': 'run_plan_progress',
            'plan_id': self.plan.id,
            'result_id': self.test_result.id,
            'phase': 'started',
            'total': total,
            'completed': 0,
            'passed': 0,
            'failed': 0,
            'error': 0,
        })
```

with:

```python
        _broadcast({
            'type': 'run_plan_progress',
            'plan_id': self.plan.id,
            'result_id': self.test_result.id,
            'phase': 'started',
            'total': total,
            'completed': 0,
            'passed': 0,
            'failed': 0,
            'error': 0,
        }, project_id=self.plan.project_id)
```

- [ ] **Step 4: Update case_done and finished broadcasts**

Search inside `backend/qa_center/run_plan_executor.py` for the remaining `_broadcast({` calls and add the same keyword argument:

```python
        }, project_id=self.plan.project_id)
```

The final file must have exactly three `_broadcast(` call sites in `TestRunPlanExecutor`: started, case_done, and finished. All three must pass `project_id=self.plan.project_id`.

- [ ] **Step 5: Run GREEN for broadcasting tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_run_plan.py::TestRunPlanExecutor::test_broadcast_sends_run_plan_progress_to_project_dashboard_group tests/test_run_plan.py::TestRunPlanExecutor::test_progress_broadcast_includes_plan_project_id tests/test_run_plan.py::TestRunPlanExecutor::test_progress_broadcast_called -v
```

Expected: all three tests pass.

---

### Task 5: Full verification and commit

**Files:**
- Verify staged files only:
  - `backend/qa_center/consumers.py`
  - `backend/qa_center/routing.py`
  - `backend/qa_center/run_plan_executor.py`
  - `backend/tests/test_qa_websocket_security.py`
  - `backend/tests/test_run_plan.py`
  - `docs/superpowers/plans/2026-06-28-qa-dashboard-project-scope.md`

- [ ] **Step 1: Run full WebSocket security tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run run-plan regression tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_run_plan.py::TestRunPlanExecutor -v
```

Expected: all `TestRunPlanExecutor` tests pass.

- [ ] **Step 3: Run combined regression tests**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_qa_websocket_security.py tests/test_run_plan.py::TestRunPlanExecutor tests/test_permissions.py -v
```

Expected: all selected tests pass.

- [ ] **Step 4: Compile changed backend modules**

Run:

```bash
cd D:/Projects/SyncBoard/backend && python -m compileall qa_center
```

Expected: exit code 0.

- [ ] **Step 5: Check whitespace for this batch**

Run:

```bash
git -C D:/Projects/SyncBoard diff --check -- backend/qa_center/consumers.py backend/qa_center/routing.py backend/qa_center/run_plan_executor.py backend/tests/test_qa_websocket_security.py backend/tests/test_run_plan.py docs/superpowers/plans/2026-06-28-qa-dashboard-project-scope.md
```

Expected: no whitespace errors. Line-ending warnings are acceptable if there are no diff-check errors.

- [ ] **Step 6: Stage explicit files only**

Run:

```bash
git -C D:/Projects/SyncBoard add -- backend/qa_center/consumers.py backend/qa_center/routing.py backend/qa_center/run_plan_executor.py backend/tests/test_qa_websocket_security.py backend/tests/test_run_plan.py docs/superpowers/plans/2026-06-28-qa-dashboard-project-scope.md
```

Do not use `git add .`.

- [ ] **Step 7: Verify staged files**

Run:

```bash
git -C D:/Projects/SyncBoard diff --cached --check
git -C D:/Projects/SyncBoard diff --cached --name-status
```

Expected staged files only:

```text
M	backend/qa_center/consumers.py
M	backend/qa_center/routing.py
M	backend/qa_center/run_plan_executor.py
M	backend/tests/test_qa_websocket_security.py
M	backend/tests/test_run_plan.py
A	docs/superpowers/plans/2026-06-28-qa-dashboard-project-scope.md
```

- [ ] **Step 8: Commit**

Run:

```bash
git -C D:/Projects/SyncBoard commit -m "fix(qa): scope dashboard websocket by project"
```

- [ ] **Step 9: Confirm post-commit status**

Run:

```bash
git -C D:/Projects/SyncBoard status --short
```

Expected: the five batch code/test files and plan file are no longer listed. Pre-existing unrelated modified/untracked files may remain.
