# Room Permission Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Room/Board/Search project-boundary bugs that allow global search leakage, cross-project task/column mutation, invalid task relationships, and partial batch deletes.

**Architecture:** Keep the existing DRF APIView structure and `ProjectAccessMixin`. Add focused validation helpers in `backend/room/views/board.py` so views validate the effective project before saving. Keep serializers mostly structural; enforce authorization and project consistency at view boundaries where `request.user` and the effective project are available.

**Tech Stack:** Django 6, Django REST Framework, pytest-django, Haystack search API.

---

## Files

- Modify: `backend/tests/test_permissions.py`
  - Add regression tests for search scoping, column project validation, task cross-project relationships, assignee membership, and batch delete atomicity.
- Modify: `backend/room/views_search.py`
  - Require project scope for search, accept both `project` and `project_id`, and reuse `ProjectAccessMixin` authorization.
- Modify: `backend/room/views/board.py`
  - Validate column create project access.
  - Disallow column project changes.
  - Validate task create/update relationships before serializer save.
  - Make batch delete reject missing IDs and execute atomically.

---

### Task 1: Search must be project-scoped

- [ ] **Step 1: Write failing tests in `backend/tests/test_permissions.py`**

Add tests under `TestProjectMemberGate`:

```python
def test_outsider_cannot_search_with_project_param(self, client):
    client.force_login(self.outsider)
    resp = client.get(f'/api/tasks/search/?q=Secret&project={self.project.id}')
    assert resp.status_code == 403


def test_search_requires_project_scope(self, client):
    client.force_login(self.member)
    resp = client.get('/api/tasks/search/?q=Secret')
    assert resp.status_code == 400
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_permissions.py::TestProjectMemberGate::test_outsider_cannot_search_with_project_param tests/test_permissions.py::TestProjectMemberGate::test_search_requires_project_scope -v
```

Expected: at least one test fails because search ignores `project` and permits unscoped search.

- [ ] **Step 3: Implement minimal search fix in `backend/room/views_search.py`**

Use:

```python
project_id = request.GET.get('project_id') or request.GET.get('project')
if not project_id:
    return Response({'detail': '缺少 project 参数'}, status=400)
project, error_response = self.get_project_with_access(request, project_id)
if error_response:
    return error_response
results = SearchQuerySet().filter(project_id=project_id).auto_query(query).models(Task)
```

- [ ] **Step 4: Run GREEN**

Run the same two tests and expect PASS.

---

### Task 2: Column create/update must not cross project boundaries

- [ ] **Step 1: Write failing tests in `backend/tests/test_permissions.py`**

Add tests:

```python
def test_outsider_cannot_create_column_in_project(self, client):
    client.force_login(self.outsider)
    resp = client.post('/api/columns/', {
        'project': str(self.project.id),
        'title': 'Injected',
        'position': 9,
    }, content_type='application/json')
    assert resp.status_code == 403
    assert not Column.objects.filter(project=self.project, title='Injected').exists()


def test_column_project_cannot_be_changed(self, client):
    other = Project.objects.create(name='Other', owner=self.member)
    client.force_login(self.owner)
    resp = client.patch(f'/api/columns/{self.col.id}/', {
        'project': str(other.id),
    }, content_type='application/json')
    assert resp.status_code == 400
    self.col.refresh_from_db()
    assert self.col.project_id == self.project.id
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_permissions.py::TestProjectMemberGate::test_outsider_cannot_create_column_in_project tests/test_permissions.py::TestProjectMemberGate::test_column_project_cannot_be_changed -v
```

Expected: tests fail because column create lacks project authorization and patch permits project field.

- [ ] **Step 3: Implement minimal column validation in `backend/room/views/board.py`**

In `ColumnListView.post`, validate `project` instead of `id` before save.

In `ColumnDetailView.patch`, reject `project` if supplied and different from current project.

- [ ] **Step 4: Run GREEN**

Run the same two tests and expect PASS.

---

### Task 3: Task create/update relationships must stay inside the effective project

- [ ] **Step 1: Write failing tests in `backend/tests/test_permissions.py`**

Add tests for cross-project column move, cross-project tags, and outsider assignee:

```python
def test_task_cannot_move_to_column_from_other_project(self, client):
    other = Project.objects.create(name='Other Move', owner=self.member)
    other_col = Column.objects.create(project=other, title='Other', position=1)
    client.force_login(self.owner)
    resp = client.patch(f'/api/tasks/{self.task.id}/', {
        'column': str(other_col.id),
    }, content_type='application/json')
    assert resp.status_code == 400
    self.task.refresh_from_db()
    assert self.task.column_id == self.col.id


def test_task_create_rejects_tag_from_other_project(self, client):
    from room.models import Tag
    other = Project.objects.create(name='Other Tag', owner=self.member)
    other_tag = Tag.objects.create(project=other, name='Foreign', color='#ff0000')
    client.force_login(self.owner)
    resp = client.post('/api/tasks/', {
        'title': 'With foreign tag',
        'column': str(self.col.id),
        'tags': [other_tag.id],
    }, content_type='application/json')
    assert resp.status_code == 400
    assert not Task.objects.filter(title='With foreign tag').exists()


def test_task_create_rejects_outsider_assignee(self, client):
    client.force_login(self.owner)
    resp = client.post('/api/tasks/', {
        'title': 'Bad assignee',
        'column': str(self.col.id),
        'assignee': self.outsider.id,
    }, content_type='application/json')
    assert resp.status_code == 400
    assert not Task.objects.filter(title='Bad assignee').exists()
```

- [ ] **Step 2: Run RED**

Run the three tests and expect failures.

- [ ] **Step 3: Implement task relationship validation in `backend/room/views/board.py`**

Add helper functions near the views:

```python
def _user_belongs_to_project(user, project):
    return user == project.owner or project.members.filter(id=user.id).exists()


def _validate_task_relationships(request, project, data):
    tags = data.get('tags')
    if tags is not None:
        tag_ids = [tag.get('id') if isinstance(tag, dict) else tag for tag in tags]
        if Tag.objects.filter(id__in=tag_ids).exclude(project=project).exists():
            return Response({'detail': '标签不属于当前项目'}, status=status.HTTP_400_BAD_REQUEST)

    assignee_id = data.get('assignee')
    if assignee_id:
        try:
            assignee = User.objects.get(pk=assignee_id)
        except User.DoesNotExist:
            return Response({'detail': '负责人不存在'}, status=status.HTTP_400_BAD_REQUEST)
        if not _user_belongs_to_project(assignee, project):
            return Response({'detail': '负责人不是项目成员'}, status=status.HTTP_400_BAD_REQUEST)

    return None
```

For task update, determine destination column if `column` is supplied; require it belongs to the current task project.

- [ ] **Step 4: Run GREEN**

Run the three tests and expect PASS.

---

### Task 4: Batch delete must reject partial/mixed requests before side effects

- [ ] **Step 1: Write failing tests in `backend/tests/test_permissions.py`**

Add tests:

```python
def test_batch_delete_rejects_missing_id_without_deleting_valid_task(self, client):
    client.force_login(self.owner)
    missing_id = '00000000-0000-0000-0000-000000000000'
    resp = client.post('/api/tasks/batch-delete/', {
        'task_ids': [str(self.task.id), missing_id],
    }, content_type='application/json')
    assert resp.status_code == 400
    assert Task.objects.filter(id=self.task.id).exists()


def test_batch_delete_rejects_mixed_project_ids_without_deleting_any(self, client):
    other = Project.objects.create(name='Other Batch', owner=self.member)
    other_col = Column.objects.create(project=other, title='Other', position=1)
    other_task = Task.objects.create(column=other_col, title='Other Secret')
    client.force_login(self.owner)
    resp = client.post('/api/tasks/batch-delete/', {
        'task_ids': [str(self.task.id), str(other_task.id)],
    }, content_type='application/json')
    assert resp.status_code == 400
    assert Task.objects.filter(id=self.task.id).exists()
    assert Task.objects.filter(id=other_task.id).exists()
```

- [ ] **Step 2: Run RED**

Run both tests and expect at least the missing-ID test to fail because current code deletes the valid task.

- [ ] **Step 3: Implement atomic validation in `TaskBatchDeleteView.post`**

Convert requested IDs to strings, load all matching tasks into a list, compare found IDs with requested IDs before deletion, verify exactly one project, authorize it, then create logs and delete inside `transaction.atomic()`.

- [ ] **Step 4: Run GREEN**

Run both tests and expect PASS.

---

### Task 5: Full targeted verification and commit

- [ ] **Step 1: Run targeted backend tests**

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_permissions.py -v
```

Expected: all tests in file PASS.

- [ ] **Step 2: Run related regression tests**

```bash
cd D:/Projects/SyncBoard/backend && pytest tests/test_permissions.py tests/test_project_isolation_regressions.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 3: Check staged diff only includes Room permission files and this plan**

```bash
git -C D:/Projects/SyncBoard status --short
git -C D:/Projects/SyncBoard diff --cached --name-status
```

- [ ] **Step 4: Commit explicit paths only**

```bash
git -C D:/Projects/SyncBoard add -- backend/tests/test_permissions.py backend/room/views_search.py backend/room/views/board.py docs/superpowers/plans/2026-06-28-room-permission-hardening.md
git -C D:/Projects/SyncBoard commit -m "fix(room): harden project permission boundaries"
```
