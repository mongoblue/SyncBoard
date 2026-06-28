# Agent Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working SyncBoard Agent Orchestrator: permission-safe Agent runs, generated plans, approvals, dry-run diffs, and approved edits for projects, columns, and tasks.

**Architecture:** Add a new Django `agent` app that owns Agent run state, approval state, tool-call audit, orchestration, and WebSocket progress. Keep the existing `room` app as the domain model owner; Agent tools call `room` models through a permission-checked registry instead of letting LLM tool calls mutate records directly. Reuse the existing frontend AI page as the entry point and add Agent run UI beside the current chat flow.

**Tech Stack:** Django REST Framework, Django Channels, pytest-django, Vue 3, TypeScript, Element Plus, existing session auth and CSRF setup.

---

## Scope

This plan implements P0-P2 from `docs/superpowers/specs/2026-06-27-agent-platform-design.md`:

- P0: close permission and safety gaps that affect Agent access.
- P1: add Agent data model, REST API, mock planner, approval lifecycle, and WebSocket status updates.
- P2: add a controlled tool registry with read/edit tools, dry-run diffs, execution audit, and frontend approval flow.
  - `POST /api/agent/runs/:id/dry-run/` runs approved tools in dry-run mode and returns diffs without writing.
  - `POST /api/agent/runs/:id/confirm-diff/` executes only after a successful dry-run preview.

This plan does not implement P3/P4 real LLM orchestration, RAG retrieval, multi-Agent routing, long-running background workers, rollback, delete tools, permission-editing tools, shell execution, or source-code editing from the web Agent.

## File Structure

### Backend files to create

- `backend/agent/__init__.py` — package marker.
- `backend/agent/apps.py` — Django app config.
- `backend/agent/models.py` — `AgentSession`, `AgentMessage`, `AgentRun`, `AgentPlan`, `AgentStep`, `AgentToolCall`, `AgentApproval`.
- `backend/agent/serializers.py` — DRF serializers for sessions, runs, plans, steps, tool calls, approvals, and tool metadata.
- `backend/agent/permissions.py` — project access helpers reused by views and tools.
- `backend/agent/planner.py` — deterministic mock planner for P1/P2.
- `backend/agent/orchestrator.py` — run lifecycle transitions, planning, approval, dry-run, execution, cancellation, and WebSocket events.
- `backend/agent/urls.py` — `/api/agent/*` route definitions.
- `backend/agent/views.py` — Agent REST endpoints, including separate dry-run and confirm-execute actions.
- `backend/agent/consumers.py` — Agent WebSocket consumer.
- `backend/agent/routing.py` — `ws/agent/runs/<run_id>/` route.
- `backend/agent/tools/__init__.py` — tool package exports.
- `backend/agent/tools/base.py` — dataclasses and base types for tool definitions and results.
- `backend/agent/tools/registry.py` — `ToolRegistry` and default registry.
- `backend/agent/tools/project_tools.py` — `project.read`, `project.update`.
- `backend/agent/tools/column_tools.py` — `column.list`, `column.create`, `column.update`, `column.reorder`.
- `backend/agent/tools/task_tools.py` — `task.list`, `task.create`, `task.update`, `task.move`, `task.bulk_update`.
- `backend/agent/tools/chat_tools.py` — `chat.history.read`, `chat.summarize`.
- `backend/agent/tools/module_tools.py` — `module.list`, `module.capability_map`, `module.plan_changes`.
- `backend/tests/test_agent_models.py` — model defaults and relationships.
- `backend/tests/test_agent_api.py` — session/run/approval/cancel API tests.
- `backend/tests/test_agent_tools.py` — registry, read tools, edit tools, dry-run and execute tests.
- `backend/tests/test_agent_permissions.py` — project access and WebSocket permission tests.

### Backend files to modify

- `backend/backend/settings.py` — add `agent` to `INSTALLED_APPS`.
- `backend/backend/urls.py` — mount `path('api/agent/', include('agent.urls'))`.
- `backend/backend/asgi.py` — include `agent.routing.websocket_urlpatterns` beside existing room routes.
- `backend/room/consumers_chat.py` — remove the unreachable anonymous fallback from `receive()` and return immediately if unauthenticated.
- `backend/room/views/ai.py` — make existing direct tool-calling opt out of edit tools after Agent tools exist; keep current chat and analysis endpoints.
- `backend/room/ai_utils.py` — preserve current chat helpers, but do not route new Agent edit flow through `execute_tool`.

### Frontend files to create

- `frontend/src/types/agent.ts` — Agent TypeScript interfaces.
- `frontend/src/api/agent.ts` — API wrapper for Agent endpoints.
- `frontend/src/components/agent/AgentRunPanel.vue` — displays run state, plan, steps, tool calls, diffs, approve, confirm, cancel.
- `frontend/src/components/agent/AgentToolDiff.vue` — renders tool dry-run diff JSON in a readable format.
- `frontend/src/__tests__/AgentRunPanel.test.ts` — component behavior tests.

### Frontend files to modify

- `frontend/src/views/AIChat.vue` — add an Agent mode panel that starts Agent runs from the current project and request text.
- `frontend/src/router/index.ts` — keep the existing `/projects/:projectId/ai-chat` route; no new route is required.

---

## Task 1: Lock Existing Permission Boundaries

**Files:**
- Modify: `backend/room/consumers_chat.py:79-88`
- Modify: `backend/room/views/ai.py:32-52`
- Test: `backend/tests/test_agent_permissions.py`

- [ ] **Step 1: Write permission regression tests**

Create `backend/tests/test_agent_permissions.py`:

```python
import pytest
from django.contrib.auth.models import User
from room.models import AIConversation, Project


@pytest.mark.django_db
class TestExistingAiPermissionBoundaries:
    def setup_method(self):
        self.owner = User.objects.create_user(username='agent_owner', password='pass')
        self.outsider = User.objects.create_user(username='agent_outsider', password='pass')
        self.project = Project.objects.create(name='Agent Project', owner=self.owner)

    def test_outsider_cannot_create_ai_conversation_for_project(self, client):
        client.force_login(self.outsider)
        response = client.post('/api/ai/conversations/', {
            'project': str(self.project.id),
            'title': 'Outsider conversation',
        }, content_type='application/json')
        assert response.status_code == 403
        assert AIConversation.objects.count() == 0

    def test_owner_can_create_ai_conversation_for_project(self, client):
        client.force_login(self.owner)
        response = client.post('/api/ai/conversations/', {
            'project': str(self.project.id),
            'title': 'Owner conversation',
        }, content_type='application/json')
        assert response.status_code == 201
        assert AIConversation.objects.filter(user=self.owner, project=self.project).exists()
```

- [ ] **Step 2: Run the new tests and verify the first test fails**

Run:

```bash
cd backend && pytest tests/test_agent_permissions.py -q
```

Expected: `test_outsider_cannot_create_ai_conversation_for_project` fails because `AIConversationListView.post()` does not verify project membership before saving.

- [ ] **Step 3: Add project access validation to AI conversation creation**

Modify `backend/room/views/ai.py` inside `AIConversationListView.post()`:

```python
    def post(self, request):
        data = request.data.copy()
        data['user'] = request.user.id

        project_id = data.get('project') or data.get('project_id')
        if project_id:
            project = get_object_or_404(Project, pk=project_id)
            if not _check_project_member(project, request.user):
                return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)
            data['project'] = str(project.id)

        serializer = AIConversationSerializer(data=data)
        if serializer.is_valid():
            conv = serializer.save()
            return Response(AIConversationSerializer(conv).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 4: Remove anonymous fallback in chat receive path**

Modify `backend/room/consumers_chat.py` in `receive()`:

```python
    async def receive(self, text_data):
        if not self.scope['user'].is_authenticated:
            await self.close(code=4003)
            return

        data = json.loads(text_data)
        message = data.get('message')
        username = self.scope['user'].username

        safe_message = sanitize_html(message)
        safe_username = sanitize_html(username)

        msg_id = self.redis.xadd(self.stream_key, {
            'user': safe_username,
            'content': safe_message,
            'time': str(data.get('time', ''))
        })

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'id': msg_id,
                'user': safe_username,
                'content': safe_message,
                'time': data.get('time', '')
            }
        )
```

- [ ] **Step 5: Run permission tests**

Run:

```bash
cd backend && pytest tests/test_permissions.py tests/test_agent_permissions.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/room/views/ai.py backend/room/consumers_chat.py backend/tests/test_agent_permissions.py
git commit -m "fix: tighten ai project access boundaries"
```

---

## Task 2: Add Agent App and Core Models

**Files:**
- Create: `backend/agent/__init__.py`
- Create: `backend/agent/apps.py`
- Create: `backend/agent/models.py`
- Modify: `backend/backend/settings.py:35-50`
- Test: `backend/tests/test_agent_models.py`

- [ ] **Step 1: Write model tests**

Create `backend/tests/test_agent_models.py`:

```python
import pytest
from django.contrib.auth.models import User
from room.models import Project
from agent.models import (
    AgentApproval,
    AgentMessage,
    AgentPlan,
    AgentRun,
    AgentSession,
    AgentStep,
    AgentToolCall,
)


@pytest.mark.django_db
class TestAgentModels:
    def setup_method(self):
        self.user = User.objects.create_user(username='planner', password='pass')
        self.project = Project.objects.create(name='Agent Models', owner=self.user)

    def test_run_plan_step_tool_call_relationships(self):
        session = AgentSession.objects.create(user=self.user, project=self.project, title='Plan project')
        message = AgentMessage.objects.create(session=session, role='user', content='Plan the work')
        run = AgentRun.objects.create(
            session=session,
            user=self.user,
            project=self.project,
            original_request=message.content,
        )
        plan = AgentPlan.objects.create(
            run=run,
            goal='Plan the work',
            scope='project',
            affected_modules=['tasks'],
            risk_summary='medium risk edits require approval',
            plan_json={'steps': []},
        )
        step = AgentStep.objects.create(
            plan=plan,
            order=1,
            title='Create task',
            description='Create one task after approval',
            risk_level='medium',
            requires_approval=True,
        )
        tool_call = AgentToolCall.objects.create(
            run=run,
            step=step,
            tool_name='task.create',
            input_json={'title': 'New task'},
            risk_level='medium',
        )
        approval = AgentApproval.objects.create(run=run, step=step, user=self.user, decision='approved')

        assert session.messages.get() == message
        assert run.status == 'queued'
        assert plan.status == 'draft'
        assert step.status == 'pending'
        assert tool_call.execution_status == 'pending'
        assert tool_call.approval_status == 'pending'
        assert approval.decision == 'approved'

    def test_global_session_allowed_but_project_run_required_for_project_edit(self):
        session = AgentSession.objects.create(user=self.user, title='Global')
        run = AgentRun.objects.create(session=session, user=self.user, original_request='Explain system')
        assert session.project is None
        assert run.project is None
```

- [ ] **Step 2: Run model tests and verify import failure**

Run:

```bash
cd backend && pytest tests/test_agent_models.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'agent'`.

- [ ] **Step 3: Create Agent package and app config**

Create `backend/agent/__init__.py` as an empty file.

Create `backend/agent/apps.py`:

```python
from django.apps import AppConfig


class AgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'
```

- [ ] **Step 4: Add `agent` to installed apps**

Modify `backend/backend/settings.py`:

```python
INSTALLED_APPS = [
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'room',
    'agent',
    'qa_center',
    'system',
    'bug_tracker',
    'corsheaders',
    'haystack',
]
```

- [ ] **Step 5: Create core models**

Create `backend/agent/models.py`:

```python
from django.conf import settings
from django.db import models


class AgentSession(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('archived', 'Archived')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='agent_sessions')
    project = models.ForeignKey('room.Project', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_sessions')
    title = models.CharField(max_length=255, default='新 Agent 会话')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_session'
        ordering = ['-updated_at']


class AgentMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant'), ('system', 'System'), ('tool', 'Tool')]

    session = models.ForeignKey(AgentSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'agent_message'
        ordering = ['created_at']


class AgentRun(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('planning', 'Planning'),
        ('waiting_approval', 'Waiting Approval'),
        ('dry_running', 'Dry Running'),
        ('waiting_diff_confirmation', 'Waiting Diff Confirmation'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    session = models.ForeignKey(AgentSession, on_delete=models.CASCADE, related_name='runs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='agent_runs')
    project = models.ForeignKey('room.Project', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_runs')
    original_request = models.TextField()
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default='queued')
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_run'
        ordering = ['-created_at']


class AgentPlan(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('approved', 'Approved'), ('rejected', 'Rejected')]

    run = models.OneToOneField(AgentRun, on_delete=models.CASCADE, related_name='plan')
    goal = models.CharField(max_length=500)
    scope = models.CharField(max_length=100, default='project')
    affected_modules = models.JSONField(default=list)
    risk_summary = models.TextField(blank=True)
    plan_json = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_plan'


class AgentStep(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('dry_run_ready', 'Dry Run Ready'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    RISK_CHOICES = [('read', 'Read'), ('low', 'Low'), ('medium', 'Medium'), ('high', 'High')]

    plan = models.ForeignKey(AgentPlan, on_delete=models.CASCADE, related_name='steps')
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default='read')
    requires_approval = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_step'
        ordering = ['order']
        unique_together = ['plan', 'order']


class AgentToolCall(models.Model):
    APPROVAL_CHOICES = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    EXECUTION_CHOICES = [
        ('pending', 'Pending'),
        ('dry_run_succeeded', 'Dry Run Succeeded'),
        ('dry_run_failed', 'Dry Run Failed'),
        ('running', 'Running'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    RISK_CHOICES = AgentStep.RISK_CHOICES

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='tool_calls')
    step = models.ForeignKey(AgentStep, on_delete=models.CASCADE, related_name='tool_calls')
    tool_name = models.CharField(max_length=120)
    input_json = models.JSONField(default=dict)
    output_json = models.JSONField(default=dict, blank=True)
    diff_json = models.JSONField(default=dict, blank=True)
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default='read')
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='pending')
    execution_status = models.CharField(max_length=30, choices=EXECUTION_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_tool_call'
        ordering = ['created_at']


class AgentApproval(models.Model):
    DECISION_CHOICES = [('approved', 'Approved'), ('rejected', 'Rejected')]

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='approvals')
    step = models.ForeignKey(AgentStep, on_delete=models.CASCADE, null=True, blank=True, related_name='approvals')
    tool_call = models.ForeignKey(AgentToolCall, on_delete=models.CASCADE, null=True, blank=True, related_name='approvals')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='agent_approvals')
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'agent_approval'
        ordering = ['-created_at']
```

- [ ] **Step 6: Create migrations**

Run:

```bash
cd backend && python manage.py makemigrations agent
```

Expected: Django creates `backend/agent/migrations/0001_initial.py`.

- [ ] **Step 7: Run model tests**

Run:

```bash
cd backend && pytest tests/test_agent_models.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/backend/settings.py backend/agent backend/tests/test_agent_models.py
git commit -m "feat: add agent orchestration models"
```

---

## Task 3: Add Agent Serializers and Session API

**Files:**
- Create: `backend/agent/permissions.py`
- Create: `backend/agent/serializers.py`
- Create: `backend/agent/views.py`
- Create: `backend/agent/urls.py`
- Modify: `backend/backend/urls.py:24-30`
- Test: `backend/tests/test_agent_api.py`

- [ ] **Step 1: Write session API tests**

Create `backend/tests/test_agent_api.py`:

```python
import pytest
from django.contrib.auth.models import User
from room.models import Project
from agent.models import AgentSession


@pytest.mark.django_db
class TestAgentSessionApi:
    def setup_method(self):
        self.owner = User.objects.create_user(username='session_owner', password='pass')
        self.member = User.objects.create_user(username='session_member', password='pass')
        self.outsider = User.objects.create_user(username='session_outsider', password='pass')
        self.project = Project.objects.create(name='Session Project', owner=self.owner)
        self.project.members.add(self.member)

    def test_auth_required_for_sessions(self, client):
        response = client.get('/api/agent/sessions/')
        assert response.status_code in (401, 403)

    def test_create_project_session_requires_membership(self, client):
        client.force_login(self.outsider)
        response = client.post('/api/agent/sessions/', {
            'project_id': str(self.project.id),
            'title': 'Forbidden',
        }, content_type='application/json')
        assert response.status_code == 403
        assert AgentSession.objects.count() == 0

    def test_create_project_session_for_member(self, client):
        client.force_login(self.member)
        response = client.post('/api/agent/sessions/', {
            'project_id': str(self.project.id),
            'title': 'Allowed',
        }, content_type='application/json')
        assert response.status_code == 201
        assert response.json()['project'] == str(self.project.id)

    def test_list_only_own_sessions(self, client):
        AgentSession.objects.create(user=self.owner, project=self.project, title='Owner')
        AgentSession.objects.create(user=self.member, project=self.project, title='Member')
        client.force_login(self.member)
        response = client.get('/api/agent/sessions/')
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]['title'] == 'Member'
```

- [ ] **Step 2: Run tests and verify URL failure**

Run:

```bash
cd backend && pytest tests/test_agent_api.py::TestAgentSessionApi -q
```

Expected: fails with 404 for `/api/agent/sessions/`.

- [ ] **Step 3: Create permission helper**

Create `backend/agent/permissions.py`:

```python
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from room.models import Project


def user_can_access_project(user, project):
    if not user or not user.is_authenticated:
        return False
    return project.owner_id == user.id or project.members.filter(pk=user.pk).exists()


def get_project_for_user_or_response(user, project_id):
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return None, Response({'detail': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

    if not user_can_access_project(user, project):
        return None, Response({'detail': '无权访问此项目'}, status=status.HTTP_403_FORBIDDEN)

    return project, None


def project_queryset_for_user(user):
    return Project.objects.filter(Q(owner=user) | Q(members=user)).distinct()
```

- [ ] **Step 4: Create serializers**

Create `backend/agent/serializers.py`:

```python
from rest_framework import serializers
from .models import AgentApproval, AgentMessage, AgentPlan, AgentRun, AgentSession, AgentStep, AgentToolCall


class AgentMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMessage
        fields = ['id', 'session', 'role', 'content', 'metadata', 'created_at']
        read_only_fields = ['id', 'session', 'created_at']


class AgentSessionSerializer(serializers.ModelSerializer):
    project_id = serializers.CharField(write_only=True, required=False, allow_blank=True)
    project = serializers.CharField(source='project_id', read_only=True)

    class Meta:
        model = AgentSession
        fields = ['id', 'user', 'project', 'project_id', 'title', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'project', 'status', 'created_at', 'updated_at']


class AgentToolCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentToolCall
        fields = [
            'id', 'run', 'step', 'tool_name', 'input_json', 'output_json', 'diff_json',
            'risk_level', 'approval_status', 'execution_status', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class AgentStepSerializer(serializers.ModelSerializer):
    tool_calls = AgentToolCallSerializer(many=True, read_only=True)

    class Meta:
        model = AgentStep
        fields = [
            'id', 'plan', 'order', 'title', 'description', 'status', 'risk_level',
            'requires_approval', 'tool_calls', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class AgentPlanSerializer(serializers.ModelSerializer):
    steps = AgentStepSerializer(many=True, read_only=True)

    class Meta:
        model = AgentPlan
        fields = [
            'id', 'run', 'goal', 'scope', 'affected_modules', 'risk_summary',
            'plan_json', 'status', 'steps', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class AgentApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentApproval
        fields = ['id', 'run', 'step', 'tool_call', 'user', 'decision', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class AgentRunSerializer(serializers.ModelSerializer):
    plan = AgentPlanSerializer(read_only=True)
    tool_calls = AgentToolCallSerializer(many=True, read_only=True)
    approvals = AgentApprovalSerializer(many=True, read_only=True)
    project = serializers.CharField(source='project_id', read_only=True)

    class Meta:
        model = AgentRun
        fields = [
            'id', 'session', 'user', 'project', 'original_request', 'status', 'error_message',
            'started_at', 'completed_at', 'plan', 'tool_calls', 'approvals', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
```

- [ ] **Step 5: Create session views and URLs**

Create `backend/agent/views.py`:

```python
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import AgentMessage, AgentRun, AgentSession
from .permissions import get_project_for_user_or_response
from .serializers import AgentMessageSerializer, AgentRunSerializer, AgentSessionSerializer


class AgentSessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = AgentSession.objects.filter(user=request.user).select_related('project')
        project_id = request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        serializer = AgentSessionSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        project = None
        project_id = request.data.get('project_id') or request.data.get('project')
        if project_id:
            project, error_response = get_project_for_user_or_response(request.user, project_id)
            if error_response:
                return error_response

        session = AgentSession.objects.create(
            user=request.user,
            project=project,
            title=request.data.get('title') or '新 Agent 会话',
        )
        return Response(AgentSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class AgentSessionMessagesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(AgentSession, pk=session_id, user=request.user)
        messages = AgentMessage.objects.filter(session=session)
        return Response(AgentMessageSerializer(messages, many=True).data)
```

Create `backend/agent/urls.py`:

```python
from django.urls import path
from .views import AgentSessionListView, AgentSessionMessagesView

urlpatterns = [
    path('sessions/', AgentSessionListView.as_view(), name='agent-session-list'),
    path('sessions/<int:session_id>/messages/', AgentSessionMessagesView.as_view(), name='agent-session-messages'),
]
```

- [ ] **Step 6: Mount Agent API**

Modify `backend/backend/urls.py`:

```python
urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('admin/', admin.site.urls),
    path('api/', include('room.urls')),
    path('api/agent/', include('agent.urls')),
    path('api/qa/', include('qa_center.urls')),
    path('api/system/', include('system.urls')),
    path('api/', include('bug_tracker.urls')),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
```

- [ ] **Step 7: Run session API tests**

Run:

```bash
cd backend && pytest tests/test_agent_api.py::TestAgentSessionApi -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/backend/urls.py backend/agent/permissions.py backend/agent/serializers.py backend/agent/views.py backend/agent/urls.py backend/tests/test_agent_api.py
git commit -m "feat: add agent session api"
```

---

## Task 4: Add Mock Planner and Run Lifecycle API

**Files:**
- Create: `backend/agent/planner.py`
- Create: `backend/agent/orchestrator.py`
- Modify: `backend/agent/views.py`
- Modify: `backend/agent/urls.py`
- Test: `backend/tests/test_agent_api.py`

- [ ] **Step 1: Add run lifecycle tests**

Append to `backend/tests/test_agent_api.py`:

```python
from room.models import Column, Project, Task
from agent.models import AgentApproval, AgentPlan, AgentRun, AgentSession, AgentStep, AgentToolCall


@pytest.mark.django_db
class TestAgentRunApi:
    def setup_method(self):
        self.owner = User.objects.create_user(username='run_owner', password='pass')
        self.outsider = User.objects.create_user(username='run_outsider', password='pass')
        self.project = Project.objects.create(name='Run Project', owner=self.owner)
        self.session = AgentSession.objects.create(user=self.owner, project=self.project, title='Run Session')

    def test_create_run_generates_plan_and_waits_for_approval(self, client):
        client.force_login(self.owner)
        response = client.post('/api/agent/runs/', {
            'session_id': self.session.id,
            'project_id': str(self.project.id),
            'message': '帮我整理项目任务',
        }, content_type='application/json')
        assert response.status_code == 201
        payload = response.json()
        assert payload['status'] == 'waiting_approval'
        assert payload['plan']['goal'] == '帮我整理项目任务'
        assert len(payload['plan']['steps']) >= 2
        assert AgentRun.objects.count() == 1
        assert AgentPlan.objects.count() == 1
        assert AgentStep.objects.count() >= 2

    def test_outsider_cannot_create_project_run(self, client):
        outsider_session = AgentSession.objects.create(user=self.outsider, title='Outsider')
        client.force_login(self.outsider)
        response = client.post('/api/agent/runs/', {
            'session_id': outsider_session.id,
            'project_id': str(self.project.id),
            'message': '越权计划',
        }, content_type='application/json')
        assert response.status_code == 403
        assert AgentRun.objects.count() == 0

    def test_owner_can_approve_run_plan(self, client):
        run = AgentRun.objects.create(session=self.session, user=self.owner, project=self.project, original_request='Create plan', status='waiting_approval')
        plan = AgentPlan.objects.create(run=run, goal='Create plan', scope='project', affected_modules=['tasks'], risk_summary='medium', plan_json={})
        AgentStep.objects.create(plan=plan, order=1, title='Read tasks', description='Read tasks', risk_level='read')

        client.force_login(self.owner)
        response = client.post(f'/api/agent/runs/{run.id}/approve/', {
            'decision': 'approved',
            'comment': 'Looks good',
        }, content_type='application/json')
        assert response.status_code == 200
        run.refresh_from_db()
        plan.refresh_from_db()
        assert run.status == 'dry_running'
        assert plan.status == 'approved'
        assert AgentApproval.objects.filter(run=run, decision='approved').exists()

    def test_owner_can_cancel_waiting_run(self, client):
        run = AgentRun.objects.create(session=self.session, user=self.owner, project=self.project, original_request='Cancel me', status='waiting_approval')
        client.force_login(self.owner)
        response = client.post(f'/api/agent/runs/{run.id}/cancel/')
        assert response.status_code == 200
        run.refresh_from_db()
        assert run.status == 'cancelled'
```

- [ ] **Step 2: Run run API tests and verify failures**

Run:

```bash
cd backend && pytest tests/test_agent_api.py::TestAgentRunApi -q
```

Expected: fails because run endpoints and planner do not exist.

- [ ] **Step 3: Create mock planner**

Create `backend/agent/planner.py`:

```python
class MockAgentPlanner:
    def build_plan(self, *, request_text, project):
        affected_modules = ['project', 'columns', 'tasks'] if project else ['system']
        steps = [
            {
                'order': 1,
                'title': '读取项目上下文',
                'description': '读取项目、看板列和任务数据，确认当前状态。',
                'risk_level': 'read',
                'requires_approval': False,
                'tool_calls': [
                    {'tool_name': 'project.read', 'input_json': {'project_id': str(project.id)} if project else {}, 'risk_level': 'read'},
                    {'tool_name': 'column.list', 'input_json': {'project_id': str(project.id)} if project else {}, 'risk_level': 'read'},
                    {'tool_name': 'task.list', 'input_json': {'project_id': str(project.id)} if project else {}, 'risk_level': 'read'},
                ] if project else [
                    {'tool_name': 'module.capability_map', 'input_json': {}, 'risk_level': 'read'},
                ],
            },
            {
                'order': 2,
                'title': '生成执行计划',
                'description': '根据用户请求生成可审批的系统修改计划。',
                'risk_level': 'low',
                'requires_approval': True,
                'tool_calls': [
                    {'tool_name': 'module.plan_changes', 'input_json': {'request': request_text}, 'risk_level': 'low'},
                ],
            },
        ]
        if project and any(word in request_text for word in ['任务', '拆分', '计划', '创建']):
            steps.append({
                'order': 3,
                'title': '创建计划任务',
                'description': '在用户确认差异后创建一张任务卡片记录 Agent 建议。',
                'risk_level': 'medium',
                'requires_approval': True,
                'tool_calls': [
                    {
                        'tool_name': 'task.create',
                        'input_json': {
                            'project_id': str(project.id),
                            'title': f'Agent 计划：{request_text[:40]}',
                            'content': request_text,
                        },
                        'risk_level': 'medium',
                    }
                ],
            })
        return {
            'goal': request_text,
            'scope': 'project' if project else 'global',
            'affected_modules': affected_modules,
            'risk_summary': '读操作自动执行，编辑操作需要计划审批和 diff 确认。',
            'steps': steps,
        }
```

- [ ] **Step 4: Create orchestrator lifecycle methods**

Create `backend/agent/orchestrator.py`:

```python
from django.db import transaction
from django.utils import timezone
from .models import AgentApproval, AgentMessage, AgentPlan, AgentRun, AgentSession, AgentStep, AgentToolCall
from .planner import MockAgentPlanner


class AgentOrchestrator:
    def __init__(self, planner=None):
        self.planner = planner or MockAgentPlanner()

    @transaction.atomic
    def create_run(self, *, user, session, project, request_text):
        AgentMessage.objects.create(session=session, role='user', content=request_text)
        run = AgentRun.objects.create(
            session=session,
            user=user,
            project=project,
            original_request=request_text,
            status='planning',
            started_at=timezone.now(),
        )
        plan_data = self.planner.build_plan(request_text=request_text, project=project)
        plan = AgentPlan.objects.create(
            run=run,
            goal=plan_data['goal'],
            scope=plan_data['scope'],
            affected_modules=plan_data['affected_modules'],
            risk_summary=plan_data['risk_summary'],
            plan_json=plan_data,
        )
        for step_data in plan_data['steps']:
            step = AgentStep.objects.create(
                plan=plan,
                order=step_data['order'],
                title=step_data['title'],
                description=step_data['description'],
                risk_level=step_data['risk_level'],
                requires_approval=step_data['requires_approval'],
            )
            for tool_data in step_data.get('tool_calls', []):
                AgentToolCall.objects.create(
                    run=run,
                    step=step,
                    tool_name=tool_data['tool_name'],
                    input_json=tool_data.get('input_json', {}),
                    risk_level=tool_data.get('risk_level', step.risk_level),
                    approval_status='pending' if step.requires_approval else 'approved',
                )
        run.status = 'waiting_approval'
        run.save(update_fields=['status', 'updated_at'])
        return run

    @transaction.atomic
    def approve_run(self, *, run, user, decision, comment=''):
        plan = run.plan
        AgentApproval.objects.create(run=run, user=user, decision=decision, comment=comment)
        if decision == 'rejected':
            plan.status = 'rejected'
            run.status = 'cancelled'
            plan.save(update_fields=['status', 'updated_at'])
            run.save(update_fields=['status', 'updated_at'])
            return run

        plan.status = 'approved'
        plan.steps.filter(requires_approval=True).update(status='approved')
        run.tool_calls.filter(approval_status='pending').update(approval_status='approved')
        run.status = 'dry_running'
        plan.save(update_fields=['status', 'updated_at'])
        run.save(update_fields=['status', 'updated_at'])
        return run

    @transaction.atomic
    def cancel_run(self, *, run):
        run.status = 'cancelled'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'completed_at', 'updated_at'])
        run.tool_calls.filter(execution_status='pending').update(execution_status='skipped')
        return run
```

- [ ] **Step 5: Add run views**

Append to `backend/agent/views.py`:

```python
from .orchestrator import AgentOrchestrator


class AgentRunListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session = get_object_or_404(AgentSession, pk=request.data.get('session_id'), user=request.user)
        message = (request.data.get('message') or request.data.get('request') or '').strip()
        if not message:
            return Response({'detail': '请求内容不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        project = None
        project_id = request.data.get('project_id') or session.project_id
        if project_id:
            project, error_response = get_project_for_user_or_response(request.user, project_id)
            if error_response:
                return error_response

        run = AgentOrchestrator().create_run(user=request.user, session=session, project=project, request_text=message)
        return Response(AgentRunSerializer(run).data, status=status.HTTP_201_CREATED)


class AgentRunDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, run_id):
        run = get_object_or_404(AgentRun, pk=run_id, user=request.user)
        return Response(AgentRunSerializer(run).data)


class AgentRunApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, run_id):
        run = get_object_or_404(AgentRun, pk=run_id, user=request.user)
        if run.status != 'waiting_approval':
            return Response({'detail': '当前状态不能审批'}, status=status.HTTP_400_BAD_REQUEST)
        decision = request.data.get('decision', 'approved')
        if decision not in ('approved', 'rejected'):
            return Response({'detail': '审批结果无效'}, status=status.HTTP_400_BAD_REQUEST)
        run = AgentOrchestrator().approve_run(
            run=run,
            user=request.user,
            decision=decision,
            comment=request.data.get('comment', ''),
        )
        return Response(AgentRunSerializer(run).data)


class AgentRunCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, run_id):
        run = get_object_or_404(AgentRun, pk=run_id, user=request.user)
        if run.status in ('completed', 'failed', 'cancelled'):
            return Response({'detail': '当前状态不能取消'}, status=status.HTTP_400_BAD_REQUEST)
        run = AgentOrchestrator().cancel_run(run=run)
        return Response(AgentRunSerializer(run).data)
```

Modify `backend/agent/urls.py`:

```python
from django.urls import path
from .views import (
    AgentRunApproveView,
    AgentRunCancelView,
    AgentRunDetailView,
    AgentRunListView,
    AgentSessionListView,
    AgentSessionMessagesView,
)

urlpatterns = [
    path('sessions/', AgentSessionListView.as_view(), name='agent-session-list'),
    path('sessions/<int:session_id>/messages/', AgentSessionMessagesView.as_view(), name='agent-session-messages'),
    path('runs/', AgentRunListView.as_view(), name='agent-run-list'),
    path('runs/<int:run_id>/', AgentRunDetailView.as_view(), name='agent-run-detail'),
    path('runs/<int:run_id>/approve/', AgentRunApproveView.as_view(), name='agent-run-approve'),
    path('runs/<int:run_id>/cancel/', AgentRunCancelView.as_view(), name='agent-run-cancel'),
]
```

- [ ] **Step 6: Run Agent API tests**

Run:

```bash
cd backend && pytest tests/test_agent_api.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/agent/planner.py backend/agent/orchestrator.py backend/agent/views.py backend/agent/urls.py backend/tests/test_agent_api.py
git commit -m "feat: add agent run planning lifecycle"
```

---

## Task 5: Add Tool Registry and Read Tools

**Files:**
- Create: `backend/agent/tools/__init__.py`
- Create: `backend/agent/tools/base.py`
- Create: `backend/agent/tools/registry.py`
- Create: `backend/agent/tools/project_tools.py`
- Create: `backend/agent/tools/column_tools.py`
- Create: `backend/agent/tools/task_tools.py`
- Create: `backend/agent/tools/chat_tools.py`
- Create: `backend/agent/tools/module_tools.py`
- Modify: `backend/agent/views.py`
- Modify: `backend/agent/urls.py`
- Test: `backend/tests/test_agent_tools.py`

- [ ] **Step 1: Write read tool tests**

Create `backend/tests/test_agent_tools.py`:

```python
import pytest
from django.contrib.auth.models import User
from room.models import Column, Project, Task
from agent.tools.registry import default_registry


@pytest.mark.django_db
class TestAgentReadTools:
    def setup_method(self):
        self.owner = User.objects.create_user(username='tool_owner', password='pass')
        self.outsider = User.objects.create_user(username='tool_outsider', password='pass')
        self.project = Project.objects.create(name='Tool Project', owner=self.owner)
        self.todo = Column.objects.create(project=self.project, title='To Do', position=1)
        self.done = Column.objects.create(project=self.project, title='Done', position=2)
        self.task = Task.objects.create(column=self.todo, title='Read me', content='Context')

    def test_registry_exposes_read_tools(self):
        names = default_registry.names()
        assert 'project.read' in names
        assert 'column.list' in names
        assert 'task.list' in names
        assert 'module.capability_map' in names

    def test_project_read_requires_membership(self):
        result = default_registry.execute('project.read', {'project_id': str(self.project.id)}, self.outsider, dry_run=True)
        assert result.ok is False
        assert result.error == '无权访问此项目'

    def test_task_list_returns_project_tasks_for_owner(self):
        result = default_registry.execute('task.list', {'project_id': str(self.project.id)}, self.owner, dry_run=True)
        assert result.ok is True
        assert result.output['tasks'][0]['title'] == 'Read me'

    def test_tool_metadata_contains_risk_and_schema(self):
        metadata = default_registry.metadata_for_user(self.owner, project_id=str(self.project.id))
        task_list = next(item for item in metadata if item['name'] == 'task.list')
        assert task_list['risk_level'] == 'read'
        assert task_list['input_schema']['required'] == ['project_id']
```

- [ ] **Step 2: Run read tool tests and verify import failure**

Run:

```bash
cd backend && pytest tests/test_agent_tools.py::TestAgentReadTools -q
```

Expected: fails because `agent.tools.registry` does not exist.

- [ ] **Step 3: Create tool base types**

Create `backend/agent/tools/__init__.py`:

```python
from .registry import default_registry

__all__ = ['default_registry']
```

Create `backend/agent/tools/base.py`:

```python
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: dict = field(default_factory=dict)
    diff: dict = field(default_factory=dict)
    error: str = ''


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict
    risk_level: str
    permission: str
    handler: Callable

    def to_metadata(self):
        return {
            'name': self.name,
            'description': self.description,
            'input_schema': self.input_schema,
            'risk_level': self.risk_level,
            'permission': self.permission,
        }
```

- [ ] **Step 4: Create registry**

Create `backend/agent/tools/registry.py`:

```python
from .base import ToolDefinition, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, definition: ToolDefinition):
        self._tools[definition.name] = definition

    def get(self, name):
        return self._tools[name]

    def names(self):
        return sorted(self._tools.keys())

    def execute(self, name, input_json, user, dry_run=True):
        definition = self.get(name)
        return definition.handler(input_json or {}, user, dry_run=dry_run)

    def metadata_for_user(self, user, project_id=None):
        return [self._tools[name].to_metadata() for name in self.names()]


def build_default_registry():
    from .chat_tools import register_chat_tools
    from .column_tools import register_column_tools
    from .module_tools import register_module_tools
    from .project_tools import register_project_tools
    from .task_tools import register_task_tools

    registry = ToolRegistry()
    register_project_tools(registry)
    register_column_tools(registry)
    register_task_tools(registry)
    register_chat_tools(registry)
    register_module_tools(registry)
    return registry


def forbidden(message):
    return ToolResult(ok=False, error=message)


def missing(message):
    return ToolResult(ok=False, error=message)


def success(output=None, diff=None):
    return ToolResult(ok=True, output=output or {}, diff=diff or {})


default_registry = build_default_registry()
```

- [ ] **Step 5: Create project and module read tools**

Create `backend/agent/tools/project_tools.py`:

```python
from room.models import Project
from agent.permissions import user_can_access_project
from .base import ToolDefinition
from .registry import forbidden, missing, success

PROJECT_ID_SCHEMA = {
    'type': 'object',
    'properties': {'project_id': {'type': 'string'}},
    'required': ['project_id'],
}


def _get_project(input_json, user):
    try:
        project = Project.objects.get(pk=input_json.get('project_id'))
    except Project.DoesNotExist:
        return None, missing('项目不存在')
    if not user_can_access_project(user, project):
        return None, forbidden('无权访问此项目')
    return project, None


def project_read(input_json, user, dry_run=True):
    project, error = _get_project(input_json, user)
    if error:
        return error
    return success({
        'project': {
            'id': str(project.id),
            'name': project.name,
            'owner': project.owner.username,
            'members': list(project.members.values_list('username', flat=True)),
        }
    })


def project_update(input_json, user, dry_run=True):
    project, error = _get_project(input_json, user)
    if error:
        return error
    new_name = (input_json.get('name') or '').strip()
    if not new_name:
        return missing('项目名称不能为空')
    diff = {'project': {'id': str(project.id), 'before': {'name': project.name}, 'after': {'name': new_name}}}
    if dry_run:
        return success({'message': 'dry_run'}, diff)
    project.name = new_name
    project.save(update_fields=['name'])
    return success({'project': {'id': str(project.id), 'name': project.name}}, diff)


def register_project_tools(registry):
    registry.register(ToolDefinition('project.read', '读取项目信息', PROJECT_ID_SCHEMA, 'read', 'project:read', project_read))
    registry.register(ToolDefinition(
        'project.update',
        '更新项目基础信息',
        {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'name': {'type': 'string'}}, 'required': ['project_id', 'name']},
        'medium',
        'project:update',
        project_update,
    ))
```

Create `backend/agent/tools/module_tools.py`:

```python
from .base import ToolDefinition
from .registry import success


def module_list(input_json, user, dry_run=True):
    return success({'modules': ['project', 'column', 'task', 'chat', 'qa', 'bug_tracker', 'system']})


def module_capability_map(input_json, user, dry_run=True):
    return success({'capabilities': {
        'project': ['project.read', 'project.update'],
        'column': ['column.list', 'column.create', 'column.update', 'column.reorder'],
        'task': ['task.list', 'task.create', 'task.update', 'task.move', 'task.bulk_update'],
        'chat': ['chat.history.read', 'chat.summarize'],
    }})


def module_plan_changes(input_json, user, dry_run=True):
    request_text = input_json.get('request', '')
    return success({'plan': {'request': request_text, 'summary': f'已生成「{request_text}」的执行计划草案'}})


def register_module_tools(registry):
    registry.register(ToolDefinition('module.list', '列出系统模块', {'type': 'object', 'properties': {}, 'required': []}, 'read', 'module:read', module_list))
    registry.register(ToolDefinition('module.capability_map', '列出模块工具能力', {'type': 'object', 'properties': {}, 'required': []}, 'read', 'module:read', module_capability_map))
    registry.register(ToolDefinition(
        'module.plan_changes',
        '生成模块修改计划',
        {'type': 'object', 'properties': {'request': {'type': 'string'}}, 'required': ['request']},
        'low',
        'module:plan',
        module_plan_changes,
    ))
```

- [ ] **Step 6: Create column, task, and chat read tools**

Create `backend/agent/tools/column_tools.py`:

```python
from room.models import Column, Project
from agent.permissions import user_can_access_project
from .base import ToolDefinition
from .registry import forbidden, missing, success

PROJECT_ID_SCHEMA = {'type': 'object', 'properties': {'project_id': {'type': 'string'}}, 'required': ['project_id']}


def _project(input_json, user):
    try:
        project = Project.objects.get(pk=input_json.get('project_id'))
    except Project.DoesNotExist:
        return None, missing('项目不存在')
    if not user_can_access_project(user, project):
        return None, forbidden('无权访问此项目')
    return project, None


def column_list(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    columns = Column.objects.filter(project=project).order_by('position')
    return success({'columns': [{'id': str(c.id), 'title': c.title, 'position': c.position} for c in columns]})


def register_column_tools(registry):
    registry.register(ToolDefinition('column.list', '读取项目看板列', PROJECT_ID_SCHEMA, 'read', 'column:read', column_list))
```

Create `backend/agent/tools/task_tools.py`:

```python
from room.models import Project, Task
from agent.permissions import user_can_access_project
from .base import ToolDefinition
from .registry import forbidden, missing, success

PROJECT_ID_SCHEMA = {'type': 'object', 'properties': {'project_id': {'type': 'string'}}, 'required': ['project_id']}


def _project(input_json, user):
    try:
        project = Project.objects.get(pk=input_json.get('project_id'))
    except Project.DoesNotExist:
        return None, missing('项目不存在')
    if not user_can_access_project(user, project):
        return None, forbidden('无权访问此项目')
    return project, None


def task_list(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    tasks = Task.objects.filter(column__project=project).select_related('column', 'assignee').order_by('position')[:100]
    return success({'tasks': [{
        'id': str(t.id),
        'title': t.title,
        'content': t.content,
        'column_id': str(t.column_id),
        'column_title': t.column.title,
        'assignee': t.assignee.username if t.assignee else None,
        'position': t.position,
    } for t in tasks]})


def register_task_tools(registry):
    registry.register(ToolDefinition('task.list', '读取项目任务', PROJECT_ID_SCHEMA, 'read', 'task:read', task_list))
```

Create `backend/agent/tools/chat_tools.py`:

```python
from .base import ToolDefinition
from .registry import success

PROJECT_ID_SCHEMA = {'type': 'object', 'properties': {'project_id': {'type': 'string'}}, 'required': ['project_id']}


def chat_history_read(input_json, user, dry_run=True):
    return success({'messages': []})


def chat_summarize(input_json, user, dry_run=True):
    return success({'summary': '当前版本未接入 Redis 聊天记录摘要，返回空摘要。'})


def register_chat_tools(registry):
    registry.register(ToolDefinition('chat.history.read', '读取项目聊天历史', PROJECT_ID_SCHEMA, 'read', 'chat:read', chat_history_read))
    registry.register(ToolDefinition('chat.summarize', '总结项目聊天历史', PROJECT_ID_SCHEMA, 'read', 'chat:read', chat_summarize))
```

- [ ] **Step 7: Add tools metadata endpoint**

Append to `backend/agent/views.py`:

```python
from .tools.registry import default_registry


class AgentToolListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(default_registry.metadata_for_user(
            request.user,
            project_id=request.query_params.get('project_id'),
        ))
```

Modify `backend/agent/urls.py`:

```python
from django.urls import path
from .views import (
    AgentRunApproveView,
    AgentRunCancelView,
    AgentRunDetailView,
    AgentRunListView,
    AgentSessionListView,
    AgentSessionMessagesView,
    AgentToolListView,
)

urlpatterns = [
    path('sessions/', AgentSessionListView.as_view(), name='agent-session-list'),
    path('sessions/<int:session_id>/messages/', AgentSessionMessagesView.as_view(), name='agent-session-messages'),
    path('runs/', AgentRunListView.as_view(), name='agent-run-list'),
    path('runs/<int:run_id>/', AgentRunDetailView.as_view(), name='agent-run-detail'),
    path('runs/<int:run_id>/approve/', AgentRunApproveView.as_view(), name='agent-run-approve'),
    path('runs/<int:run_id>/cancel/', AgentRunCancelView.as_view(), name='agent-run-cancel'),
    path('tools/', AgentToolListView.as_view(), name='agent-tool-list'),
]
```

- [ ] **Step 8: Run read tool tests**

Run:

```bash
cd backend && pytest tests/test_agent_tools.py::TestAgentReadTools -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/agent/tools backend/agent/views.py backend/agent/urls.py backend/tests/test_agent_tools.py
git commit -m "feat: add agent tool registry and read tools"
```

---

## Task 6: Add Editable Tools, Dry-Run, Confirm Diff, and Execute

**Files:**
- Modify: `backend/agent/tools/column_tools.py`
- Modify: `backend/agent/tools/task_tools.py`
- Modify: `backend/agent/orchestrator.py`
- Modify: `backend/agent/views.py`
- Modify: `backend/agent/urls.py`
- Test: `backend/tests/test_agent_tools.py`
- Test: `backend/tests/test_agent_api.py`

- [ ] **Step 1: Add editable tool tests**

Append to `backend/tests/test_agent_tools.py`:

```python
from agent.models import AgentPlan, AgentRun, AgentSession, AgentStep, AgentToolCall
from agent.orchestrator import AgentOrchestrator


@pytest.mark.django_db
class TestAgentEditableTools:
    def setup_method(self):
        self.owner = User.objects.create_user(username='edit_owner', password='pass')
        self.project = Project.objects.create(name='Edit Project', owner=self.owner)
        self.todo = Column.objects.create(project=self.project, title='To Do', position=1)
        self.done = Column.objects.create(project=self.project, title='Done', position=2)
        self.task = Task.objects.create(column=self.todo, title='Move me', content='Before')

    def test_task_create_dry_run_does_not_write(self):
        result = default_registry.execute('task.create', {
            'project_id': str(self.project.id),
            'title': 'Created by Agent',
            'content': 'Draft',
        }, self.owner, dry_run=True)
        assert result.ok is True
        assert result.diff['task']['after']['title'] == 'Created by Agent'
        assert Task.objects.filter(title='Created by Agent').exists() is False

    def test_task_create_execute_writes(self):
        result = default_registry.execute('task.create', {
            'project_id': str(self.project.id),
            'title': 'Created by Agent',
            'content': 'Draft',
        }, self.owner, dry_run=False)
        assert result.ok is True
        assert Task.objects.filter(title='Created by Agent', column=self.todo).exists()

    def test_task_move_dry_run_has_before_after(self):
        result = default_registry.execute('task.move', {
            'project_id': str(self.project.id),
            'task_id': str(self.task.id),
            'column_id': str(self.done.id),
        }, self.owner, dry_run=True)
        assert result.ok is True
        assert result.diff['task']['before']['column_id'] == str(self.todo.id)
        assert result.diff['task']['after']['column_id'] == str(self.done.id)
        self.task.refresh_from_db()
        assert self.task.column_id == self.todo.id

    def test_orchestrator_dry_run_and_confirm_execute(self):
        session = AgentSession.objects.create(user=self.owner, project=self.project)
        run = AgentRun.objects.create(session=session, user=self.owner, project=self.project, original_request='Create task', status='dry_running')
        plan = AgentPlan.objects.create(run=run, goal='Create task', scope='project', affected_modules=['tasks'], risk_summary='medium', plan_json={})
        step = AgentStep.objects.create(plan=plan, order=1, title='Create task', description='Create task', risk_level='medium', requires_approval=True, status='approved')
        AgentToolCall.objects.create(
            run=run,
            step=step,
            tool_name='task.create',
            input_json={'project_id': str(self.project.id), 'title': 'Confirmed task', 'content': 'After approval'},
            risk_level='medium',
            approval_status='approved',
        )

        orchestrator = AgentOrchestrator()
        orchestrator.run_dry_run(run=run)
        run.refresh_from_db()
        call = run.tool_calls.get()
        assert run.status == 'waiting_diff_confirmation'
        assert call.execution_status == 'dry_run_succeeded'
        assert Task.objects.filter(title='Confirmed task').exists() is False

        orchestrator.confirm_and_execute(run=run)
        run.refresh_from_db()
        call.refresh_from_db()
        assert run.status == 'completed'
        assert call.execution_status == 'succeeded'
        assert Task.objects.filter(title='Confirmed task').exists()
```

- [ ] **Step 2: Run editable tool tests and verify missing tool failure**

Run:

```bash
cd backend && pytest tests/test_agent_tools.py::TestAgentEditableTools -q
```

Expected: fails with `KeyError` for edit tools or missing orchestrator methods.

- [ ] **Step 3: Implement column edit tools**

Replace `backend/agent/tools/column_tools.py` with:

```python
from room.models import Column, Project
from agent.permissions import user_can_access_project
from .base import ToolDefinition
from .registry import forbidden, missing, success

PROJECT_ID_SCHEMA = {'type': 'object', 'properties': {'project_id': {'type': 'string'}}, 'required': ['project_id']}


def _project(input_json, user):
    try:
        project = Project.objects.get(pk=input_json.get('project_id'))
    except Project.DoesNotExist:
        return None, missing('项目不存在')
    if not user_can_access_project(user, project):
        return None, forbidden('无权访问此项目')
    return project, None


def _column(project, column_id):
    try:
        return Column.objects.get(pk=column_id, project=project), None
    except Column.DoesNotExist:
        return None, missing('列不存在')


def column_list(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    columns = Column.objects.filter(project=project).order_by('position')
    return success({'columns': [{'id': str(c.id), 'title': c.title, 'position': c.position} for c in columns]})


def column_create(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    title = (input_json.get('title') or '').strip()
    if not title:
        return missing('列标题不能为空')
    position = input_json.get('position') or 65535
    diff = {'column': {'before': None, 'after': {'project_id': str(project.id), 'title': title, 'position': float(position)}}}
    if dry_run:
        return success({'message': 'dry_run'}, diff)
    column = Column.objects.create(project=project, title=title, position=position)
    return success({'column': {'id': str(column.id), 'title': column.title, 'position': column.position}}, diff)


def column_update(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    column, error = _column(project, input_json.get('column_id'))
    if error:
        return error
    title = (input_json.get('title') or column.title).strip()
    position = float(input_json.get('position', column.position))
    diff = {'column': {'id': str(column.id), 'before': {'title': column.title, 'position': column.position}, 'after': {'title': title, 'position': position}}}
    if dry_run:
        return success({'message': 'dry_run'}, diff)
    column.title = title
    column.position = position
    column.save(update_fields=['title', 'position'])
    return success({'column': {'id': str(column.id), 'title': column.title, 'position': column.position}}, diff)


def column_reorder(input_json, user, dry_run=True):
    return column_update(input_json, user, dry_run=dry_run)


def register_column_tools(registry):
    registry.register(ToolDefinition('column.list', '读取项目看板列', PROJECT_ID_SCHEMA, 'read', 'column:read', column_list))
    registry.register(ToolDefinition('column.create', '创建看板列', {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'title': {'type': 'string'}, 'position': {'type': 'number'}}, 'required': ['project_id', 'title']}, 'medium', 'column:create', column_create))
    registry.register(ToolDefinition('column.update', '更新看板列', {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'column_id': {'type': 'string'}, 'title': {'type': 'string'}, 'position': {'type': 'number'}}, 'required': ['project_id', 'column_id']}, 'medium', 'column:update', column_update))
    registry.register(ToolDefinition('column.reorder', '调整看板列顺序', {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'column_id': {'type': 'string'}, 'position': {'type': 'number'}}, 'required': ['project_id', 'column_id', 'position']}, 'medium', 'column:reorder', column_reorder))
```

- [ ] **Step 4: Implement task edit tools**

Replace `backend/agent/tools/task_tools.py` with:

```python
from django.contrib.auth.models import User
from room.models import Column, Project, Task
from agent.permissions import user_can_access_project
from .base import ToolDefinition
from .registry import forbidden, missing, success

PROJECT_ID_SCHEMA = {'type': 'object', 'properties': {'project_id': {'type': 'string'}}, 'required': ['project_id']}


def _project(input_json, user):
    try:
        project = Project.objects.get(pk=input_json.get('project_id'))
    except Project.DoesNotExist:
        return None, missing('项目不存在')
    if not user_can_access_project(user, project):
        return None, forbidden('无权访问此项目')
    return project, None


def _task(project, task_id):
    try:
        return Task.objects.select_related('column').get(pk=task_id, column__project=project), None
    except Task.DoesNotExist:
        return None, missing('任务不存在')


def _default_column(project):
    return Column.objects.filter(project=project).order_by('position').first()


def _column(project, column_id):
    if column_id:
        try:
            return Column.objects.get(pk=column_id, project=project), None
        except Column.DoesNotExist:
            return None, missing('列不存在')
    column = _default_column(project)
    if not column:
        return None, missing('项目没有可用列')
    return column, None


def task_list(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    tasks = Task.objects.filter(column__project=project).select_related('column', 'assignee').order_by('position')[:100]
    return success({'tasks': [{
        'id': str(t.id),
        'title': t.title,
        'content': t.content,
        'column_id': str(t.column_id),
        'column_title': t.column.title,
        'assignee': t.assignee.username if t.assignee else None,
        'position': t.position,
    } for t in tasks]})


def task_create(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    title = (input_json.get('title') or '').strip()
    if not title:
        return missing('任务标题不能为空')
    column, error = _column(project, input_json.get('column_id'))
    if error:
        return error
    assignee = None
    assignee_id = input_json.get('assignee_id')
    if assignee_id:
        assignee = User.objects.filter(pk=assignee_id).first()
        if assignee is None:
            return missing('负责人不存在')
    content = input_json.get('content') or ''
    position = float(input_json.get('position', 65535))
    diff = {'task': {'before': None, 'after': {'title': title, 'content': content, 'column_id': str(column.id), 'assignee_id': assignee.id if assignee else None, 'position': position}}}
    if dry_run:
        return success({'message': 'dry_run'}, diff)
    task = Task.objects.create(column=column, title=title, content=content, assignee=assignee, position=position)
    return success({'task': {'id': str(task.id), 'title': task.title}}, diff)


def task_update(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    task, error = _task(project, input_json.get('task_id'))
    if error:
        return error
    title = (input_json.get('title') or task.title).strip()
    content = input_json.get('content', task.content)
    diff = {'task': {'id': str(task.id), 'before': {'title': task.title, 'content': task.content}, 'after': {'title': title, 'content': content}}}
    if dry_run:
        return success({'message': 'dry_run'}, diff)
    task.title = title
    task.content = content
    task.save(update_fields=['title', 'content'])
    return success({'task': {'id': str(task.id), 'title': task.title, 'content': task.content}}, diff)


def task_move(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    task, error = _task(project, input_json.get('task_id'))
    if error:
        return error
    column, error = _column(project, input_json.get('column_id'))
    if error:
        return error
    diff = {'task': {'id': str(task.id), 'before': {'column_id': str(task.column_id)}, 'after': {'column_id': str(column.id)}}}
    if dry_run:
        return success({'message': 'dry_run'}, diff)
    task.column = column
    task.save(update_fields=['column'])
    return success({'task': {'id': str(task.id), 'column_id': str(task.column_id)}}, diff)


def task_bulk_update(input_json, user, dry_run=True):
    project, error = _project(input_json, user)
    if error:
        return error
    updates = input_json.get('updates') or []
    diffs = []
    for item in updates:
        task, error = _task(project, item.get('task_id'))
        if error:
            return error
        before = {'title': task.title, 'content': task.content}
        after = {'title': (item.get('title') or task.title).strip(), 'content': item.get('content', task.content)}
        diffs.append({'id': str(task.id), 'before': before, 'after': after})
    if dry_run:
        return success({'message': 'dry_run'}, {'tasks': diffs})
    for item in updates:
        task = Task.objects.get(pk=item.get('task_id'), column__project=project)
        task.title = (item.get('title') or task.title).strip()
        task.content = item.get('content', task.content)
        task.save(update_fields=['title', 'content'])
    return success({'updated_count': len(updates)}, {'tasks': diffs})


def register_task_tools(registry):
    registry.register(ToolDefinition('task.list', '读取项目任务', PROJECT_ID_SCHEMA, 'read', 'task:read', task_list))
    registry.register(ToolDefinition('task.create', '创建任务', {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'column_id': {'type': 'string'}, 'title': {'type': 'string'}, 'content': {'type': 'string'}, 'assignee_id': {'type': 'integer'}, 'position': {'type': 'number'}}, 'required': ['project_id', 'title']}, 'medium', 'task:create', task_create))
    registry.register(ToolDefinition('task.update', '更新任务', {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'task_id': {'type': 'string'}, 'title': {'type': 'string'}, 'content': {'type': 'string'}}, 'required': ['project_id', 'task_id']}, 'medium', 'task:update', task_update))
    registry.register(ToolDefinition('task.move', '移动任务', {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'task_id': {'type': 'string'}, 'column_id': {'type': 'string'}}, 'required': ['project_id', 'task_id', 'column_id']}, 'medium', 'task:move', task_move))
    registry.register(ToolDefinition('task.bulk_update', '批量更新任务', {'type': 'object', 'properties': {'project_id': {'type': 'string'}, 'updates': {'type': 'array'}}, 'required': ['project_id', 'updates']}, 'medium', 'task:bulk_update', task_bulk_update))
```

- [ ] **Step 5: Add dry-run and execute methods to orchestrator**

Append to `AgentOrchestrator` in `backend/agent/orchestrator.py`:

```python
    @transaction.atomic
    def run_dry_run(self, *, run):
        from .tools.registry import default_registry

        failed = False
        for call in run.tool_calls.filter(approval_status='approved').order_by('created_at'):
            result = default_registry.execute(call.tool_name, call.input_json, run.user, dry_run=True)
            if result.ok:
                call.output_json = result.output
                call.diff_json = result.diff
                call.execution_status = 'dry_run_succeeded'
                call.error_message = ''
            else:
                failed = True
                call.execution_status = 'dry_run_failed'
                call.error_message = result.error
            call.save(update_fields=['output_json', 'diff_json', 'execution_status', 'error_message', 'updated_at'])

        run.status = 'failed' if failed else 'waiting_diff_confirmation'
        run.save(update_fields=['status', 'updated_at'])
        return run

    @transaction.atomic
    def confirm_and_execute(self, *, run):
        from .tools.registry import default_registry

        failed = False
        for call in run.tool_calls.filter(approval_status='approved', execution_status='dry_run_succeeded').order_by('created_at'):
            call.execution_status = 'running'
            call.save(update_fields=['execution_status', 'updated_at'])
            result = default_registry.execute(call.tool_name, call.input_json, run.user, dry_run=False)
            if result.ok:
                call.output_json = result.output
                call.diff_json = result.diff or call.diff_json
                call.execution_status = 'succeeded'
                call.error_message = ''
            else:
                failed = True
                call.execution_status = 'failed'
                call.error_message = result.error
            call.save(update_fields=['output_json', 'diff_json', 'execution_status', 'error_message', 'updated_at'])
            if failed:
                break

        run.status = 'failed' if failed else 'completed'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'completed_at', 'updated_at'])
        AgentMessage.objects.create(
            session=run.session,
            role='assistant',
            content='Agent 执行完成。' if not failed else 'Agent 执行失败，请查看工具调用错误。',
            metadata={'run_id': run.id},
        )
        return run
```

- [ ] **Step 6: Add dry-run and confirm diff endpoints**

Append to `backend/agent/views.py`:

```python
class AgentRunDryRunView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, run_id):
        run = get_object_or_404(AgentRun, pk=run_id, user=request.user)
        if run.status != 'dry_running':
            return Response({'detail': '当前状态不能预演执行'}, status=status.HTTP_400_BAD_REQUEST)
        run = AgentOrchestrator().run_dry_run(run=run)
        return Response(AgentRunSerializer(run).data)


class AgentRunConfirmDiffView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, run_id):
        run = get_object_or_404(AgentRun, pk=run_id, user=request.user)
        if run.status != 'waiting_diff_confirmation':
            return Response({'detail': '请先完成 dry-run 并预览 diff'}, status=status.HTTP_400_BAD_REQUEST)
        run = AgentOrchestrator().confirm_and_execute(run=run)
        return Response(AgentRunSerializer(run).data)
```

Modify `backend/agent/urls.py` imports and routes:

```python
from .views import (
    AgentRunApproveView,
    AgentRunCancelView,
    AgentRunConfirmDiffView,
    AgentRunDetailView,
    AgentRunDryRunView,
    AgentRunListView,
    AgentSessionListView,
    AgentSessionMessagesView,
    AgentToolListView,
)
```

```python
    path('runs/<int:run_id>/dry-run/', AgentRunDryRunView.as_view(), name='agent-run-dry-run'),
    path('runs/<int:run_id>/confirm-diff/', AgentRunConfirmDiffView.as_view(), name='agent-run-confirm-diff'),
```

- [ ] **Step 7: Add API tests for dry-run and confirm diff**

Append to `TestAgentRunApi` in `backend/tests/test_agent_api.py`:

```python
    def test_dry_run_previews_diff_without_executing(self, client):
        run = AgentRun.objects.create(session=self.session, user=self.owner, project=self.project, original_request='Create task', status='dry_running')
        plan = AgentPlan.objects.create(run=run, goal='Create task', scope='project', affected_modules=['tasks'], risk_summary='medium', plan_json={})
        step = AgentStep.objects.create(plan=plan, order=1, title='Create task', description='Create task', risk_level='medium', requires_approval=True, status='approved')
        column = Column.objects.create(project=self.project, title='To Do', position=1)
        AgentToolCall.objects.create(
            run=run,
            step=step,
            tool_name='task.create',
            input_json={'project_id': str(self.project.id), 'column_id': str(column.id), 'title': 'API dry-run task'},
            risk_level='medium',
            approval_status='approved',
        )
        client.force_login(self.owner)
        response = client.post(f'/api/agent/runs/{run.id}/dry-run/')
        assert response.status_code == 200
        assert response.json()['status'] == 'waiting_diff_confirmation'
        assert Task.objects.filter(title='API dry-run task').exists() is False
        tool_call = response.json()['tool_calls'][0]
        assert tool_call['execution_status'] == 'dry_run_succeeded'
        assert tool_call['diff_json']['task']['after']['title'] == 'API dry-run task'

    def test_confirm_diff_requires_successful_dry_run(self, client):
        run = AgentRun.objects.create(session=self.session, user=self.owner, project=self.project, original_request='Create task', status='dry_running')
        client.force_login(self.owner)
        response = client.post(f'/api/agent/runs/{run.id}/confirm-diff/')
        assert response.status_code == 400
        assert Task.objects.count() == 0

    def test_confirm_diff_executes_dry_run_ready_tools(self, client):
        run = AgentRun.objects.create(session=self.session, user=self.owner, project=self.project, original_request='Create task', status='dry_running')
        plan = AgentPlan.objects.create(run=run, goal='Create task', scope='project', affected_modules=['tasks'], risk_summary='medium', plan_json={})
        step = AgentStep.objects.create(plan=plan, order=1, title='Create task', description='Create task', risk_level='medium', requires_approval=True, status='approved')
        column = Column.objects.create(project=self.project, title='To Do', position=1)
        AgentToolCall.objects.create(
            run=run,
            step=step,
            tool_name='task.create',
            input_json={'project_id': str(self.project.id), 'column_id': str(column.id), 'title': 'API confirmed task'},
            risk_level='medium',
            approval_status='approved',
        )
        client.force_login(self.owner)
        dry_run_response = client.post(f'/api/agent/runs/{run.id}/dry-run/')
        assert dry_run_response.status_code == 200
        response = client.post(f'/api/agent/runs/{run.id}/confirm-diff/')
        assert response.status_code == 200
        assert response.json()['status'] == 'completed'
        assert Task.objects.filter(title='API confirmed task').exists()
```

- [ ] **Step 8: Run editable tool and API tests**

Run:

```bash
cd backend && pytest tests/test_agent_tools.py tests/test_agent_api.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/agent/tools backend/agent/orchestrator.py backend/agent/views.py backend/agent/urls.py backend/tests/test_agent_tools.py backend/tests/test_agent_api.py
git commit -m "feat: execute approved agent tool calls"
```

---

## Task 7: Add Agent WebSocket Progress Route

**Files:**
- Create: `backend/agent/consumers.py`
- Create: `backend/agent/routing.py`
- Modify: `backend/backend/asgi.py:23-38`
- Test: `backend/tests/test_agent_permissions.py`

- [ ] **Step 1: Add WebSocket permission tests**

Append to `backend/tests/test_agent_permissions.py`:

```python
from channels.testing import WebsocketCommunicator
from backend.asgi import application
from agent.models import AgentRun, AgentSession


@pytest.mark.django_db(transaction=True)
class TestAgentRunWebSocket:
    def setup_method(self):
        self.owner = User.objects.create_user(username='ws_owner', password='pass')
        self.project = Project.objects.create(name='WS Project', owner=self.owner)
        self.session = AgentSession.objects.create(user=self.owner, project=self.project)
        self.run = AgentRun.objects.create(session=self.session, user=self.owner, project=self.project, original_request='Watch')

    async def test_anonymous_agent_ws_rejected(self):
        communicator = WebsocketCommunicator(application, f'/ws/agent/runs/{self.run.id}/')
        connected, _ = await communicator.connect()
        assert connected is False
```

- [ ] **Step 2: Run WebSocket test and verify route failure**

Run:

```bash
cd backend && pytest tests/test_agent_permissions.py::TestAgentRunWebSocket -q
```

Expected: fails because the Agent WebSocket route does not exist.

- [ ] **Step 3: Create Agent WebSocket consumer**

Create `backend/agent/consumers.py`:

```python
import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import AgentRun


class AgentRunConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def _can_access_run(self, user, run_id):
        if not user.is_authenticated:
            return False
        return AgentRun.objects.filter(pk=run_id, user=user).exists()

    async def connect(self):
        self.run_id = self.scope['url_route']['kwargs']['run_id']
        self.group_name = f'agent_run_{self.run_id}'
        if not await self._can_access_run(self.scope['user'], self.run_id):
            await self.close(code=4003)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def agent_run_update(self, event):
        await self.send(text_data=json.dumps(event['message'], ensure_ascii=False))
```

Create `backend/agent/routing.py`:

```python
from django.urls import re_path
from .consumers import AgentRunConsumer

websocket_urlpatterns = [
    re_path(r'ws/agent/runs/(?P<run_id>\d+)/$', AgentRunConsumer.as_asgi()),
]
```

- [ ] **Step 4: Include Agent routing in ASGI**

Modify `backend/backend/asgi.py`:

```python
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import room.routing
import agent.routing

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            room.routing.websocket_urlpatterns + agent.routing.websocket_urlpatterns
        )
    ),
})
```

- [ ] **Step 5: Add event emitter to orchestrator**

Append helper methods to `AgentOrchestrator` in `backend/agent/orchestrator.py`:

```python
    def emit_run_update(self, run):
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        async_to_sync(channel_layer.group_send)(
            f'agent_run_{run.id}',
            {
                'type': 'agent_run_update',
                'message': {
                    'run_id': run.id,
                    'status': run.status,
                    'updated_at': run.updated_at.isoformat(),
                },
            },
        )
```

Call `self.emit_run_update(run)` before each `return run` in `create_run`, `approve_run`, `cancel_run`, `run_dry_run`, and `confirm_and_execute`.

- [ ] **Step 6: Run WebSocket tests**

Run:

```bash
cd backend && pytest tests/test_agent_permissions.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/backend/asgi.py backend/agent/consumers.py backend/agent/routing.py backend/agent/orchestrator.py backend/tests/test_agent_permissions.py
git commit -m "feat: stream agent run status over websocket"
```

---

## Task 8: Add Frontend Agent API and Types

**Files:**
- Create: `frontend/src/types/agent.ts`
- Create: `frontend/src/api/agent.ts`

- [ ] **Step 1: Create Agent types**

Create `frontend/src/types/agent.ts`:

```ts
export type AgentRunStatus =
  | 'queued'
  | 'planning'
  | 'waiting_approval'
  | 'dry_running'
  | 'waiting_diff_confirmation'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface AgentSession {
  id: number
  user: number
  project: string | null
  title: string
  status: string
  created_at: string
  updated_at: string
}

export interface AgentToolCall {
  id: number
  run: number
  step: number
  tool_name: string
  input_json: Record<string, unknown>
  output_json: Record<string, unknown>
  diff_json: Record<string, unknown>
  risk_level: 'read' | 'low' | 'medium' | 'high'
  approval_status: 'pending' | 'approved' | 'rejected'
  execution_status: string
  error_message: string
}

export interface AgentStep {
  id: number
  order: number
  title: string
  description: string
  status: string
  risk_level: 'read' | 'low' | 'medium' | 'high'
  requires_approval: boolean
  tool_calls: AgentToolCall[]
}

export interface AgentPlan {
  id: number
  goal: string
  scope: string
  affected_modules: string[]
  risk_summary: string
  plan_json: Record<string, unknown>
  status: string
  steps: AgentStep[]
}

export interface AgentRun {
  id: number
  session: number
  project: string | null
  original_request: string
  status: AgentRunStatus
  error_message: string
  plan?: AgentPlan
  tool_calls: AgentToolCall[]
  created_at: string
  updated_at: string
}
```

- [ ] **Step 2: Create Agent API wrapper**

Create `frontend/src/api/agent.ts`:

```ts
import service from '@/utils/request'
import type { AgentRun, AgentSession } from '@/types/agent'

export const createAgentSession = (payload: { project_id?: string; title?: string }) => {
  return service.post<AgentSession>('/agent/sessions/', payload)
}

export const createAgentRun = (payload: { session_id: number; project_id?: string; message: string }) => {
  return service.post<AgentRun>('/agent/runs/', payload)
}

export const getAgentRun = (runId: number) => {
  return service.get<AgentRun>(`/agent/runs/${runId}/`)
}

export const approveAgentRun = (runId: number, payload: { decision: 'approved' | 'rejected'; comment?: string }) => {
  return service.post<AgentRun>(`/agent/runs/${runId}/approve/`, payload)
}

export const runAgentDryRun = (runId: number) => {
  return service.post<AgentRun>(`/agent/runs/${runId}/dry-run/`)
}

export const confirmAgentDiff = (runId: number) => {
  return service.post<AgentRun>(`/agent/runs/${runId}/confirm-diff/`)
}

export const cancelAgentRun = (runId: number) => {
  return service.post<AgentRun>(`/agent/runs/${runId}/cancel/`)
}
```

- [ ] **Step 3: Run frontend type check**

Run:

```bash
cd frontend && npm run type-check
```

Expected: type check passes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/agent.ts frontend/src/api/agent.ts
git commit -m "feat: add frontend agent api client"
```

---

## Task 9: Add Agent Run Panel UI

**Files:**
- Create: `frontend/src/components/agent/AgentToolDiff.vue`
- Create: `frontend/src/components/agent/AgentRunPanel.vue`
- Create: `frontend/src/__tests__/AgentRunPanel.test.ts`

- [ ] **Step 1: Write component test**

Create `frontend/src/__tests__/AgentRunPanel.test.ts`:

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AgentRunPanel from '@/components/agent/AgentRunPanel.vue'

const run = {
  id: 1,
  session: 1,
  project: 'project-1',
  original_request: '整理任务',
  status: 'waiting_approval',
  error_message: '',
  created_at: '2026-06-27T00:00:00Z',
  updated_at: '2026-06-27T00:00:00Z',
  tool_calls: [],
  plan: {
    id: 1,
    goal: '整理任务',
    scope: 'project',
    affected_modules: ['tasks'],
    risk_summary: '需要审批',
    plan_json: {},
    status: 'draft',
    steps: [
      {
        id: 1,
        order: 1,
        title: '读取项目上下文',
        description: '读取任务',
        status: 'pending',
        risk_level: 'read',
        requires_approval: false,
        tool_calls: [],
      },
    ],
  },
} as any

describe('AgentRunPanel', () => {
  it('renders plan and emits approve', async () => {
    const wrapper = mount(AgentRunPanel, {
      props: { run },
      global: { stubs: ['el-card', 'el-tag', 'el-button', 'el-timeline', 'el-timeline-item', 'el-empty'] },
    })
    expect(wrapper.text()).toContain('整理任务')
    expect(wrapper.text()).toContain('读取项目上下文')
    await wrapper.get('[data-test="approve-run"]').trigger('click')
    expect(wrapper.emitted('approve')).toHaveLength(1)
  })

  it('renders confirm button for diff confirmation state', () => {
    const wrapper = mount(AgentRunPanel, {
      props: { run: { ...run, status: 'waiting_diff_confirmation' } },
      global: { stubs: ['el-card', 'el-tag', 'el-button', 'el-timeline', 'el-timeline-item', 'el-empty'] },
    })
    expect(wrapper.find('[data-test="confirm-diff"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run component test and verify missing component failure**

Run:

```bash
cd frontend && npm run test:run -- AgentRunPanel
```

Expected: fails because `AgentRunPanel.vue` does not exist.

- [ ] **Step 3: Create diff component**

Create `frontend/src/components/agent/AgentToolDiff.vue`:

```vue
<template>
  <div class="agent-tool-diff">
    <pre>{{ formatted }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ diff: Record<string, unknown> }>()

const formatted = computed(() => JSON.stringify(props.diff || {}, null, 2))
</script>

<style scoped>
.agent-tool-diff pre {
  margin: 0;
  padding: 10px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: 6px;
  overflow: auto;
  font: 12px/1.5 var(--font-mono);
}
</style>
```

- [ ] **Step 4: Create run panel component**

Create `frontend/src/components/agent/AgentRunPanel.vue`:

```vue
<template>
  <el-card v-if="run" class="agent-run-panel" shadow="never">
    <template #header>
      <div class="panel-header">
        <div>
          <div class="title">Agent Plan</div>
          <div class="subtitle">{{ run.original_request }}</div>
        </div>
        <el-tag>{{ run.status }}</el-tag>
      </div>
    </template>

    <div v-if="run.plan" class="plan-body">
      <h3>{{ run.plan.goal }}</h3>
      <p class="risk">{{ run.plan.risk_summary }}</p>
      <el-timeline>
        <el-timeline-item v-for="step in run.plan.steps" :key="step.id" :timestamp="step.risk_level">
          <div class="step-title">{{ step.order }}. {{ step.title }}</div>
          <div class="step-desc">{{ step.description }}</div>
          <div v-for="call in step.tool_calls" :key="call.id" class="tool-call">
            <div class="tool-line">
              <span>{{ call.tool_name }}</span>
              <el-tag size="small">{{ call.execution_status }}</el-tag>
            </div>
            <AgentToolDiff v-if="Object.keys(call.diff_json || {}).length" :diff="call.diff_json" />
            <div v-if="call.error_message" class="error">{{ call.error_message }}</div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>
    <el-empty v-else description="暂无计划" />

    <div class="actions">
      <el-button
        v-if="run.status === 'waiting_approval'"
        data-test="approve-run"
        type="primary"
        @click="$emit('approve')"
      >批准计划</el-button>
      <el-button
        v-if="run.status === 'waiting_approval'"
        data-test="reject-run"
        @click="$emit('reject')"
      >拒绝</el-button>
      <el-button
        v-if="run.status === 'waiting_diff_confirmation'"
        data-test="confirm-diff"
        type="primary"
        @click="$emit('confirm')"
      >确认执行</el-button>
      <el-button
        v-if="!['completed', 'failed', 'cancelled'].includes(run.status)"
        data-test="cancel-run"
        @click="$emit('cancel')"
      >取消</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { AgentRun } from '@/types/agent'
import AgentToolDiff from './AgentToolDiff.vue'

defineProps<{ run: AgentRun | null }>()
defineEmits<{
  approve: []
  reject: []
  confirm: []
  cancel: []
}>()
</script>

<style scoped>
.agent-run-panel { margin-top: 12px; }
.panel-header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.title { font-weight: 600; }
.subtitle { margin-top: 4px; color: var(--color-text-secondary); font-size: 13px; }
.plan-body h3 { margin: 0 0 8px; }
.risk { color: var(--color-text-secondary); margin: 0 0 12px; }
.step-title { font-weight: 600; }
.step-desc { color: var(--color-text-secondary); margin-top: 4px; }
.tool-call { margin-top: 8px; padding: 8px; border: 1px solid var(--color-border-light); border-radius: 6px; }
.tool-line { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.error { margin-top: 6px; color: var(--color-danger); }
.actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
</style>
```

- [ ] **Step 5: Run component test**

Run:

```bash
cd frontend && npm run test:run -- AgentRunPanel
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/agent frontend/src/__tests__/AgentRunPanel.test.ts
git commit -m "feat: add agent run approval panel"
```

---

## Task 10: Integrate Agent Panel Into Existing AI Chat Page

**Files:**
- Modify: `frontend/src/views/AIChat.vue`

- [ ] **Step 1: Add Agent imports and state**

Modify the script section of `frontend/src/views/AIChat.vue`:

```ts
import AgentRunPanel from '@/components/agent/AgentRunPanel.vue';
import { approveAgentRun, cancelAgentRun, confirmAgentDiff, createAgentRun, createAgentSession, getAgentRun, runAgentDryRun } from '@/api/agent';
import type { AgentRun } from '@/types/agent';
```

Add state after the existing `analyzing` ref:

```ts
const agentMode = ref(false);
const agentSessionId = ref<number | null>(null);
const activeAgentRun = ref<AgentRun | null>(null);
const agentLoading = ref(false);
let agentSocket: WebSocket | null = null;
```

- [ ] **Step 2: Add Agent UI controls**

Modify the template quick-bar area in `AIChat.vue` after the streaming switch:

```vue
<el-divider direction="vertical" />
<el-switch v-model="agentMode" size="small" active-text="Agent" />
```

Add the panel below the quick-bar:

```vue
<AgentRunPanel
  :run="activeAgentRun"
  @approve="approveCurrentAgentRun"
  @reject="rejectCurrentAgentRun"
  @confirm="confirmCurrentAgentDiff"
  @cancel="cancelCurrentAgentRun"
/>
```

- [ ] **Step 3: Route send action to Agent mode**

Modify `sendMessage()` in `AIChat.vue`:

```ts
const sendMessage = async () => {
  const msg = inputMessage.value.trim();
  if (!msg || isLoading.value || isSending.value || agentLoading.value) return;

  messages.value.push({ role: 'user', content: msg, timestamp: Date.now() });
  inputMessage.value = '';
  scrollToBottom();

  if (agentMode.value) {
    await startAgentRun(msg);
    return;
  }

  if (streamingPref.value) {
    await sendMessageStream(msg);
  } else {
    await sendMessageNormal(msg);
  }
};
```

Add Agent methods:

```ts
const ensureAgentSession = async () => {
  if (agentSessionId.value) return agentSessionId.value;
  const session = await createAgentSession({ project_id: projectId.value, title: 'Agent 会话' });
  agentSessionId.value = session.id;
  return session.id;
};

const connectAgentSocket = (runId: number) => {
  if (agentSocket) agentSocket.close();
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  agentSocket = new WebSocket(`${protocol}://${window.location.host}/ws/agent/runs/${runId}/`);
  agentSocket.onmessage = async () => {
    activeAgentRun.value = await getAgentRun(runId);
  };
};

const startAgentRun = async (msg: string) => {
  agentLoading.value = true;
  try {
    const sessionId = await ensureAgentSession();
    activeAgentRun.value = await createAgentRun({ session_id: sessionId, project_id: projectId.value, message: msg });
    connectAgentSocket(activeAgentRun.value.id);
    messages.value.push({
      role: 'assistant',
      content: '已生成 Agent 计划，请在下方审批。',
      timestamp: Date.now(),
    });
  } catch {
    ElMessage.error('Agent 请求失败');
  } finally {
    agentLoading.value = false;
  }
};

const approveCurrentAgentRun = async () => {
  if (!activeAgentRun.value) return;
  activeAgentRun.value = await approveAgentRun(activeAgentRun.value.id, { decision: 'approved' });
  activeAgentRun.value = await runAgentDryRun(activeAgentRun.value.id);
};

const rejectCurrentAgentRun = async () => {
  if (!activeAgentRun.value) return;
  activeAgentRun.value = await approveAgentRun(activeAgentRun.value.id, { decision: 'rejected' });
};

const confirmCurrentAgentDiff = async () => {
  if (!activeAgentRun.value) return;
  activeAgentRun.value = await confirmAgentDiff(activeAgentRun.value.id);
  messages.value.push({ role: 'assistant', content: 'Agent 执行完成，请查看执行结果。', timestamp: Date.now() });
};

const cancelCurrentAgentRun = async () => {
  if (!activeAgentRun.value) return;
  activeAgentRun.value = await cancelAgentRun(activeAgentRun.value.id);
};
```

- [ ] **Step 4: Close Agent WebSocket on unmount**

Modify `onBeforeUnmount()`:

```ts
onBeforeUnmount(() => {
  cancelActiveTimers();
  if (agentSocket) agentSocket.close();
});
```

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd frontend && npm run type-check && npm run test:run -- AgentRunPanel
```

Expected: type check and component tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/AIChat.vue
git commit -m "feat: integrate agent runs into ai chat"
```

---

## Task 11: Disable Direct AI Edit Tools Until They Use Approval Flow

**Files:**
- Modify: `backend/room/views/ai.py`
- Modify: `backend/room/ai_utils.py`
- Test: `backend/tests/test_permissions.py`

- [ ] **Step 1: Add regression test for existing AI chat edit behavior**

Append to `backend/tests/test_permissions.py`:

```python
@pytest.mark.django_db
class TestAiDirectEditToolsDisabled:
    def setup_method(self):
        self.owner = User.objects.create_user(username='direct_ai_owner', password='pass')
        self.project = Project.objects.create(name='Direct AI Project', owner=self.owner)
        self.column = Column.objects.create(project=self.project, title='To Do', position=1)

    def test_execute_tool_does_not_create_task_directly(self):
        from room.ai_utils import execute_tool
        result = execute_tool('create_task', {
            'title': 'Direct edit should not happen',
            'column_title': 'To Do',
        }, str(self.project.id), self.owner)
        assert '请使用 Agent 审批流程' in result
        assert Task.objects.filter(title='Direct edit should not happen').exists() is False
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd backend && pytest tests/test_permissions.py::TestAiDirectEditToolsDisabled -q
```

Expected: fails because `execute_tool('create_task')` currently creates a task directly.

- [ ] **Step 3: Block mutating tools in legacy AI tool executor**

Modify `backend/room/ai_utils.py` at the start of `execute_tool()` after project lookup:

```python
    mutating_tools = {
        'create_task',
        'update_task_assignee',
        'move_task',
        'create_api_test_case',
        'create_ui_test_case',
        'create_test_task',
        'execute_test_task',
        'trigger_pipeline',
    }
    if tool_name in mutating_tools:
        return '该操作需要审批。请使用 Agent 审批流程生成计划、预览 diff，并确认后执行。'
```

- [ ] **Step 4: Run AI and permission tests**

Run:

```bash
cd backend && pytest tests/test_permissions.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/room/ai_utils.py backend/tests/test_permissions.py
git commit -m "fix: route ai edits through agent approval flow"
```

---

## Task 12: End-to-End Verification

**Files:**
- Verification uses the files changed by Tasks 1-11; this task adds no new source file.

- [ ] **Step 1: Run backend Agent test slice**

Run:

```bash
cd backend && pytest tests/test_agent_models.py tests/test_agent_api.py tests/test_agent_tools.py tests/test_agent_permissions.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run existing permission and AI tests**

Run:

```bash
cd backend && pytest tests/test_permissions.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend tests and type check**

Run:

```bash
cd frontend && npm run type-check && npm run test:run -- AgentRunPanel
```

Expected: type check passes and `AgentRunPanel` tests pass.

- [ ] **Step 4: Run migrations locally**

Run:

```bash
cd backend && python manage.py migrate
```

Expected: `agent.0001_initial` applies successfully.

- [ ] **Step 5: Start backend server**

Run:

```bash
cd backend && python manage.py runserver 127.0.0.1:8000
```

Expected: server starts without import errors.

- [ ] **Step 6: Start frontend dev server**

Run in a second terminal:

```bash
cd frontend && npm run dev
```

Expected: Vite starts and serves the app.

- [ ] **Step 7: Manually verify Agent flow in browser**

Use the existing project UI:

1. Log in.
2. Open a project.
3. Navigate to `AIChat` from the project menu.
4. Toggle `Agent` mode on.
5. Submit: `帮我把当前项目拆成一张计划任务`.
6. Verify an Agent plan appears.
7. Approve the plan.
8. Verify a dry-run diff preview appears.
9. Confirm execution.
10. Verify a new task appears on the board.
11. Verify the run detail endpoint returns completed status at `/api/agent/runs/<run_id>/`.

- [ ] **Step 8: Commit verification-only fixes if any were needed**

If verification required code changes, commit only those changed files:

```bash
git add <changed-files>
git commit -m "fix: stabilize agent platform verification"
```

---

## Self-Review Notes

Spec coverage:

- Agent conversation layer: Task 10 integrates Agent mode into existing AI chat.
- Orchestrator layer: Tasks 2, 4, 6, and 7 add models, lifecycle, execution, and WebSocket events.
- Module tool layer: Tasks 5 and 6 add registry, metadata, read tools, edit tools, dry-run, and execute.
- Approval and permission layer: Tasks 1, 3, 4, 6, and 11 enforce membership, approval, and diff confirmation.
- Audit and recovery layer: Tasks 2 and 6 persist tool call input, output, diff, status, and errors.
- P0-P2 roadmap: fully covered.
- P3/P4: intentionally excluded and called out as future plans.

Naming consistency:

- REST endpoints use `/api/agent/...` because `backend/backend/urls.py` mounts `agent.urls` at `api/agent/`.
- WebSocket endpoint uses `/ws/agent/runs/<run_id>/`.
- Model names use `AgentSession`, `AgentMessage`, `AgentRun`, `AgentPlan`, `AgentStep`, `AgentToolCall`, `AgentApproval` consistently.
- Frontend types mirror serializer field names.
