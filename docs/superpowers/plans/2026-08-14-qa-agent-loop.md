# AI QA Agent 增强闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SyncBoard 中实现事件触发的 AI QA Agent 闭环——自动生成并执行 API/UI 测试用例、失败智能分析（flaky/根因）、自动建 Bug、报告回写，并配套 Eval 评估集，作为 QA 工程师求职作品集核心。

**Architecture:** 新增独立 Django app `qa_agent` 承担编排职责（AgentRun 状态机 + Celery/线程执行 + 复用现有工具与执行引擎），编排层只经 `adapter.py` 调用 `room.ai_utils.execute_tool` 与 `qa_center` 公开入口，不直接操作业务模型。数据流：触发入口 → `create_run()` → `run_agent_pipeline()`（planning → executing → analyzing → reporting → done）→ AgentStep/AgentEvent 落库 + WebSocket 推送。

**Tech Stack:** Django 6 + DRF + Channels（WS 推送）+ Celery（`USE_CELERY_TASKS` 双模式分发）+ DeepSeek（OpenAI 兼容 client，复用 `room.ai_utils.client`）+ pytest（`backend/tests/`，`--reuse-db --nomigrations`）+ Vue 3 + Element Plus（前端两个页面改动）。

**设计文档:** `docs/superpowers/specs/2026-08-14-qa-agent-loop-design.md`

---

## 文件结构总览

```
backend/qa_agent/                     # 新建 app（编排层）
├── __init__.py
├── apps.py                           # QaAgentConfig，ready() 挂载 signals
├── config.py                         # 全部可调参数（env 可覆盖）
├── models.py                         # AgentRun / AgentStep / AgentEvent
├── serializers.py                    # AgentRun/Step/Event 序列化器 + PlanSchema + AnalysisItemSchema
├── llm.py                            # llm_json() 重试 + JSON 提取
├── services.py                       # create_run() 工厂 / dispatch_run() / build_context / build_plan / minimal_plan
├── adapter.py                        # 编排→业务能力适配器（API/UI 用例创建与执行）
├── analysis.py                       # 失败收集 / LLM 分析 / 规则 fallback / 聚类 / 自动建 Bug
├── reporting.py                      # Markdown 报告 / 评论回写 / 站内通知
├── orchestration.py                  # 状态机 + run_agent_pipeline() 主流程 + emit_event（含 WS 推送）
├── signals.py                        # Task post_save → 列移动触发 create_run
├── consumers.py                      # AgentRunConsumer（WS 实时事件）
├── routing.py                        # ws/qa-agent/<project_id>/
├── urls.py                           # /api/qa-agent/runs/...
├── views.py                          # AgentRunListCreateView / DetailView / CancelView
├── migrations/__init__.py
└── eval/
    ├── __init__.py
    ├── fixtures.py                   # 固定种子数据
    ├── golden.py                     # 人工标注金标准 + 期望指标
    ├── cache.py                      # LLM 响应 JSON 缓存（离线重放）
    └── run_eval.py                   # pytest -m eval 指标测试

backend/backend/settings.py           # INSTALLED_APPS + 'qa_agent'
backend/backend/urls.py               # + path('api/qa-agent/', include('qa_agent.urls'))
backend/room/routing.py               # + qa_agent WS 路由
backend/pytest.ini                    # + markers = eval
backend/tests/test_qa_agent_core.py       # 模型 + 状态机 + create_run/dispatch
backend/tests/test_qa_agent_planning.py   # llm.py + PlanSchema + context/plan
backend/tests/test_qa_agent_analysis.py   # analysis.py + reporting.py
backend/tests/test_qa_agent_api.py        # views/urls/权限
backend/tests/test_qa_agent_integration.py# 全流程闭环（stub LLM 与执行）
backend/tests/test_qa_agent_eval.py       # Eval 指标（-m eval）
frontend/src/api/qaAgent.ts           # 前端 API 模块
frontend/src/views/qa/AgentRunList.vue    # 执行记录列表 + 步骤时间线
frontend/src/router/index.ts          # + qa/agent-runs 路由
frontend/src/views/Board.vue          # 任务卡 AI-QA 状态徽标
scripts/demo_qa_agent.md              # 演示脚本
```

测试约定：所有测试放 `backend/tests/`，运行命令统一 `cd backend && pytest <file> -v`。conftest.py 提供 `test_user`、`auth_client`、`test_project` fixtures（已含 To Do/In Progress/Done 三列）。

---

# M1 骨架与数据层

## Task 1: 创建 qa_agent app 骨架并注册

**Files:**
- Create: `backend/qa_agent/__init__.py`
- Create: `backend/qa_agent/apps.py`
- Modify: `backend/backend/settings.py:37-53`

- [ ] **Step 1: 创建目录与基础文件**

创建 `backend/qa_agent/__init__.py`（空文件）与 `backend/qa_agent/migrations/__init__.py`（空文件）。

`backend/qa_agent/apps.py`：

```python
from django.apps import AppConfig


class QaAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'qa_agent'
    verbose_name = 'AI QA Agent'

    def ready(self):
        from . import signals  # noqa: F401
```

- [ ] **Step 2: 注册 app**

在 `backend/backend/settings.py` 的 `INSTALLED_APPS`（第 37-53 行）中 `'qa_center',` 之后加入 `'qa_agent',`。

- [ ] **Step 3: 验证加载**

Run: `cd backend && python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.settings'); import django; django.setup(); from qa_agent.apps import QaAgentConfig; print('OK', QaAgentConfig.name)"`

Expected: `OK qa_agent`

> 注：`ready()` 此时 import 的 `signals` 还不存在——Django 会忽略 ImportError 吗？不会。所以本步同时创建 `backend/qa_agent/signals.py` 占位空文件，Task 14 再填充内容。

- [ ] **Step 4: Commit**

```bash
git add backend/qa_agent backend/backend/settings.py
git commit -m "feat(qa_agent): app 骨架与注册"
```

## Task 2: 数据模型 AgentRun / AgentStep / AgentEvent

**Files:**
- Create: `backend/qa_agent/models.py`
- Test: `backend/tests/test_qa_agent_core.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_qa_agent_core.py`：

```python
"""qa_agent 模型与状态机测试"""
import pytest

from qa_agent.models import AgentRun, AgentEvent, AgentStep
from room.models import Column, Task


@pytest.mark.django_db
def test_agent_run_defaults(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    assert run.status == 'queued'
    assert run.trigger == 'manual'
    assert run.plan == {}
    assert run.summary == ''


@pytest.mark.django_db
def test_agent_run_task_column_trigger(test_user, test_project):
    col = Column.objects.create(project=test_project, title='待测试', position=4)
    task = Task.objects.create(column=col, title='登录功能')
    run = AgentRun.objects.create(
        project=test_project, source_task=task, trigger='task_column', created_by=test_user,
    )
    assert run.source_task == task
    assert run.trigger == 'task_column'


@pytest.mark.django_db
def test_agent_step_and_event_created(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    step = AgentStep.objects.create(
        run=run, step_type='generate_cases', tool_name='create_api_test_case',
        input={'name': 'x'}, output={'case_id': 1},
    )
    ev = AgentEvent.objects.create(run=run, level='info', message='开始')
    assert run.steps.count() == 1 and run.events.count() == 1
    assert step.step_type == 'generate_cases'
    assert ev.level == 'info'
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: FAIL（`ModuleNotFoundError: No module named 'qa_agent'` 或 `from qa_agent.models import AgentRun` 失败）

- [ ] **Step 3: 实现模型**

创建 `backend/qa_agent/models.py`：

```python
import uuid

from django.conf import settings
from django.db import models


class AgentRun(models.Model):
    """一次完整的 AI QA Agent 执行（状态机根记录）"""

    TRIGGER_CHOICES = [
        ('manual', '手动触发'),
        ('task_column', '看板列移动'),
        ('cicd', 'CI/CD 完成'),
    ]
    STATUS_CHOICES = [
        ('queued', '排队中'),
        ('planning', '制定计划'),
        ('executing', '执行测试'),
        ('analyzing', '失败分析'),
        ('reporting', '生成报告'),
        ('done', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        'room.Project', on_delete=models.CASCADE, related_name='agent_runs'
    )
    source_task = models.ForeignKey(
        'room.Task', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='agent_runs',
    )
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    plan = models.JSONField(default=dict, blank=True)
    summary = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_agent_runs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'qa_agent_run'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['project', 'status'])]

    def __str__(self):
        return f'[{self.status}] {self.trigger} run {self.id}'


class AgentStep(models.Model):
    """执行轨迹中的一步（前端时间线数据源）"""

    STEP_TYPE_CHOICES = [
        ('generate_cases', '生成用例'),
        ('execute', '执行测试'),
        ('analyze', '失败分析'),
        ('report', '生成报告'),
    ]

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='steps')
    step_type = models.CharField(max_length=30, choices=STEP_TYPE_CHOICES)
    status = models.CharField(max_length=20, default='done')  # done / error
    tool_name = models.CharField(max_length=100, blank=True, default='')
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(default=dict, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'qa_agent_step'
        ordering = ['created_at']


class AgentEvent(models.Model):
    """实时进度事件（WebSocket 推送内容）"""

    LEVEL_CHOICES = [
        ('info', '信息'),
        ('warn', '警告'),
        ('error', '错误'),
    ]

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='events')
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'qa_agent_event'
        ordering = ['created_at']
```

- [ ] **Step 4: 生成并应用迁移**

Run: `cd backend && python manage.py makemigrations qa_agent && python manage.py migrate qa_agent`

Expected: 生成 `qa_agent/migrations/0001_initial.py`，migrate 成功（`OK`）

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: 3 个测试 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/qa_agent backend/tests/test_qa_agent_core.py
git commit -m "feat(qa_agent): AgentRun/AgentStep/AgentEvent 模型与迁移"
```

## Task 3: 状态机 transition + emit_event

**Files:**
- Modify: `backend/qa_agent/orchestration.py`（新建）
- Test: `backend/tests/test_qa_agent_core.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_qa_agent_core.py` 末尾追加：

```python
from qa_agent.orchestration import InvalidTransition, transition, emit_event


@pytest.mark.django_db
def test_transition_valid_path(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    for status in ['planning', 'executing', 'analyzing', 'reporting', 'done']:
        transition(run, status)
        assert run.status == status


@pytest.mark.django_db
def test_transition_illegal_rejected(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    with pytest.raises(InvalidTransition):
        transition(run, 'done')  # queued 只能去 planning
    assert run.status == 'queued'


@pytest.mark.django_db
def test_transition_terminal_immutable(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    transition(run, 'planning')
    transition(run, 'executing')
    transition(run, 'analyzing')
    transition(run, 'reporting')
    transition(run, 'done')
    with pytest.raises(InvalidTransition):
        transition(run, 'executing')
    assert run.status == 'done'


@pytest.mark.django_db
def test_emit_event_creates_row(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    ev = emit_event(run, '开始', level='warn')
    assert ev.level == 'warn'
    assert ev.message == '开始'
    assert run.events.count() == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: 新增 4 个测试 FAIL（`ModuleNotFoundError: qa_agent.orchestration`）

- [ ] **Step 3: 实现状态机**

创建 `backend/qa_agent/orchestration.py`：

```python
"""AgentRun 状态机与主流程编排。

本模块是编排层核心：只允许按 STATUS_FLOW 线性推进，
终态（done/failed/cancelled）不可再转换。
"""
import logging

from .models import AgentEvent, AgentRun

logger = logging.getLogger(__name__)

STATUS_FLOW = {
    'queued': {'planning'},
    'planning': {'executing'},
    'executing': {'analyzing'},
    'analyzing': {'reporting'},
    'reporting': {'done'},
}
TERMINAL_STATUSES = {'done', 'failed', 'cancelled'}


class InvalidTransition(Exception):
    """非法状态转换（含对终态的再次转换）"""


def transition(run: AgentRun, new_status: str) -> AgentRun:
    """校验并执行状态转换，非法时抛出 InvalidTransition。"""
    if run.status in TERMINAL_STATUSES:
        raise InvalidTransition(f'终态 {run.status} 不可再转换')
    allowed = STATUS_FLOW.get(run.status, set())
    if new_status not in allowed:
        raise InvalidTransition(f'{run.status} -> {new_status} 非法')
    run.status = new_status
    run.save(update_fields=['status', 'updated_at'])
    return run


def emit_event(run: AgentRun, message: str, level: str = 'info') -> AgentEvent:
    """落库一条 AgentEvent，并尝试经 WebSocket 组推送（失败不影响主流程）。"""
    event = AgentEvent.objects.create(run=run, level=level, message=message)
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f'qa_agent_{run.project_id}',
                {
                    'type': 'agent_event',
                    'run_id': str(run.id),
                    'status': run.status,
                    'event': {'id': event.id, 'level': level, 'message': message},
                },
            )
    except Exception:  # noqa: BLE001
        logger.exception('AgentEvent WS 推送失败（不影响主流程）')
    return event
```

> 注：WS 推送逻辑在 Task 13 的 consumer 到位后生效；channel_layer 为 None 或推送异常时静默降级。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: 全部 PASS（7 个）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/orchestration.py backend/tests/test_qa_agent_core.py
git commit -m "feat(qa_agent): 状态机与事件落库"
```

## Task 4: config.py 可调参数

**Files:**
- Create: `backend/qa_agent/config.py`
- Test: `backend/tests/test_qa_agent_core.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_qa_agent_core.py` 末尾追加：

```python
from qa_agent import config


def test_config_defaults():
    assert config.RUN_TIMEOUT_SECONDS > 0
    assert config.POLL_INTERVAL_SECONDS > 0
    assert config.LLM_RETRIES >= 1
    assert '测试' in config.TEST_COLUMN_KEYWORDS
    assert config.MODEL
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: FAIL（`ModuleNotFoundError: qa_agent.config`）

- [ ] **Step 3: 实现 config**

创建 `backend/qa_agent/config.py`：

```python
"""qa_agent 可调参数（支持 env 覆盖，测试可直接改模块属性）"""
import os


def _int(name, default):
    return int(os.environ.get(name, str(default)))


def _float(name, default):
    return float(os.environ.get(name, str(default)))


RUN_TIMEOUT_SECONDS = _int('QA_AGENT_RUN_TIMEOUT_SECONDS', 1800)
POLL_INTERVAL_SECONDS = _int('QA_AGENT_POLL_INTERVAL_SECONDS', 2)
POLL_TIMEOUT_SECONDS = _int('QA_AGENT_POLL_TIMEOUT_SECONDS', 300)
LLM_RETRIES = _int('QA_AGENT_LLM_RETRIES', 3)
LLM_BACKOFF_BASE_SECONDS = _float('QA_AGENT_LLM_BACKOFF_BASE', 1.0)
MODEL = os.environ.get('QA_AGENT_MODEL', 'deepseek-chat')
TEST_COLUMN_KEYWORDS = ['测试', '待测', '待测试', 'QA']
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: 全部 PASS（8 个）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/config.py backend/tests/test_qa_agent_core.py
git commit -m "feat(qa_agent): 可调参数 config"
```

---

# M2 API 闭环

## Task 5: create_run 工厂 + Celery 任务 + 双模式分发

**Files:**
- Create: `backend/qa_agent/services.py`
- Create: `backend/qa_agent/tasks.py`
- Test: `backend/tests/test_qa_agent_core.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_qa_agent_core.py` 末尾追加：

```python
from qa_agent.services import create_run, dispatch_run


@pytest.mark.django_db
def test_create_run_basic(test_user, test_project):
    run = create_run(project=test_project, trigger='manual', created_by=test_user)
    assert run is not None
    assert run.status == 'queued'


@pytest.mark.django_db
def test_create_run_task_column_dedupe(test_user, test_project):
    col = Column.objects.create(project=test_project, title='待测试', position=4)
    task = Task.objects.create(column=col, title='登录功能')
    first = create_run(project=test_project, trigger='task_column', source_task=task, created_by=test_user)
    assert first is not None
    second = create_run(project=test_project, trigger='task_column', source_task=task, created_by=test_user)
    assert second is None  # 已有非终态 run，跳过


@pytest.mark.django_db
def test_dispatch_run_thread_mode(test_user, test_project, monkeypatch):
    captured = {}

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            captured['target'] = target
            captured['args'] = args

        def start(self):
            captured['started'] = True

    monkeypatch.setattr('qa_agent.services.threading.Thread', FakeThread)
    monkeypatch.setattr('qa_agent.services.settings.USE_CELERY_TASKS', False)
    run = create_run(project=test_project, created_by=test_user)
    dispatch_run(run.id)
    assert captured.get('started') is True
    assert captured['args'] == (run.id,)


@pytest.mark.django_db
def test_dispatch_run_celery_mode(test_user, test_project, monkeypatch):
    called = {}

    def fake_delay(run_id):
        called['run_id'] = run_id

    monkeypatch.setattr('qa_agent.services.settings.USE_CELERY_TASKS', True)
    monkeypatch.setattr('qa_agent.tasks.run_pipeline_task.delay', fake_delay)
    run = create_run(project=test_project, created_by=test_user)
    dispatch_run(run.id)
    assert called.get('run_id') == run.id
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: 新增 4 个 FAIL（`ModuleNotFoundError: qa_agent.services`）

- [ ] **Step 3: 实现 services.py 与 tasks.py**

创建 `backend/qa_agent/services.py`：

```python
"""AgentRun 工厂与调度入口"""
import logging
import threading

from django.conf import settings

from .models import AgentRun

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ['queued', 'planning', 'executing', 'analyzing', 'reporting']


def create_run(*, project, trigger='manual', source_task=None, created_by=None,
               skip_if_active=True):
    """统一创建 AgentRun 的工厂。

    - task_column 触发：同一源任务已有非终态 run 时返回 None（防重复触发）
    - 其他触发：直接创建
    """
    if trigger == 'task_column' and source_task is not None and skip_if_active:
        exists = AgentRun.objects.filter(
            source_task=source_task, status__in=ACTIVE_STATUSES,
        ).exists()
        if exists:
            logger.info('源任务 %s 已有进行中的 AgentRun，跳过', source_task.id)
            return None
    return AgentRun.objects.create(
        project=project, trigger=trigger,
        source_task=source_task, created_by=created_by,
    )


def dispatch_run(run_id):
    """按运行模式分发：生产走 Celery（USE_CELERY_TASKS=True），开发/测试走后台线程。"""
    if getattr(settings, 'USE_CELERY_TASKS', False):
        from .tasks import run_pipeline_task
        run_pipeline_task.delay(run_id)
    else:
        from .orchestration import run_agent_pipeline
        threading.Thread(target=run_agent_pipeline, args=(run_id,), daemon=True).start()
```

创建 `backend/qa_agent/tasks.py`：

```python
from celery import shared_task


@shared_task(bind=True, name='qa_agent.run_pipeline', max_retries=0)
def run_pipeline_task(self, run_id):
    from .orchestration import run_agent_pipeline
    return run_agent_pipeline(run_id)
```

> 注：`run_agent_pipeline` 在 Task 11 实现，在此之前本步的 `dispatch_run` 线程模式测试不实际启动（FakeThread 拦截了 start）。Celery 模式测试只验证 delay 被调用，同样不执行真实任务。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_core.py -v`

Expected: 全部 PASS（12 个）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/services.py backend/qa_agent/tasks.py backend/tests/test_qa_agent_core.py
git commit -m "feat(qa_agent): create_run 工厂与 Celery/线程双模式分发"
```

## Task 6: 序列化器 + API 视图 + 路由

**Files:**
- Create: `backend/qa_agent/serializers.py`
- Create: `backend/qa_agent/views.py`
- Create: `backend/qa_agent/urls.py`
- Modify: `backend/backend/urls.py`
- Test: `backend/tests/test_qa_agent_api.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_qa_agent_api.py`：

```python
"""qa_agent HTTP API 测试"""
import pytest

from qa_agent.models import AgentRun
from room.models import Column, Task


@pytest.mark.django_db
def test_api_requires_auth(client, test_project):
    resp = client.get('/api/qa-agent/runs/', {'project_id': test_project.id})
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_api_create_run(auth_client, test_project, monkeypatch):
    monkeypatch.setattr('qa_agent.views.dispatch_run', lambda run_id: None)
    resp = auth_client.post('/api/qa-agent/runs/', {'project_id': str(test_project.id)})
    assert resp.status_code == 201
    assert resp.json()['status'] == 'queued'
    assert AgentRun.objects.filter(project=test_project).count() == 1


@pytest.mark.django_db
def test_api_create_run_with_source_task(auth_client, test_project, monkeypatch):
    monkeypatch.setattr('qa_agent.views.dispatch_run', lambda run_id: None)
    col = Column.objects.create(project=test_project, title='待测试', position=4)
    task = Task.objects.create(column=col, title='登录功能')
    resp = auth_client.post('/api/qa-agent/runs/', {
        'project_id': str(test_project.id), 'source_task_id': str(task.id),
    })
    assert resp.status_code == 201
    assert resp.json()['source_task'] == str(task.id)
    assert resp.json()['source_task_title'] == '登录功能'


@pytest.mark.django_db
def test_api_non_member_forbidden(auth_client, test_project):
    from django.contrib.auth.models import User
    other = User.objects.create_user(username='outsider', password='x1234567')
    other_project = type(test_project).objects.create(name='Other', owner=other)
    resp = auth_client.post('/api/qa-agent/runs/', {'project_id': str(other_project.id)})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_api_detail_and_cancel(auth_client, test_project, test_user):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    detail = auth_client.get(f'/api/qa-agent/runs/{run.id}/')
    assert detail.status_code == 200
    assert detail.json()['status'] == 'queued'
    cancel = auth_client.post(f'/api/qa-agent/runs/{run.id}/cancel/')
    assert cancel.status_code == 200
    assert cancel.json()['status'] == 'cancelled'
    again = auth_client.post(f'/api/qa-agent/runs/{run.id}/cancel/')
    assert again.status_code == 400
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_api.py -v`

Expected: 全部 FAIL（404 路由不存在）

- [ ] **Step 3: 实现序列化器**

创建 `backend/qa_agent/serializers.py`：

```python
from rest_framework import serializers

from .models import AgentEvent, AgentRun, AgentStep


class AgentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentEvent
        fields = ['id', 'level', 'message', 'created_at']


class AgentStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentStep
        fields = ['id', 'step_type', 'status', 'tool_name', 'input', 'output',
                  'duration_ms', 'created_at']


class AgentRunSerializer(serializers.ModelSerializer):
    steps = AgentStepSerializer(many=True, read_only=True)
    events = AgentEventSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    trigger_display = serializers.CharField(source='get_trigger_display', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    source_task_title = serializers.CharField(
        source='source_task.title', read_only=True, default=None,
    )

    class Meta:
        model = AgentRun
        fields = [
            'id', 'project', 'project_name', 'source_task', 'source_task_title',
            'trigger', 'trigger_display', 'status', 'status_display', 'plan',
            'summary', 'created_by', 'created_at', 'updated_at', 'steps', 'events',
        ]
        read_only_fields = fields
```

- [ ] **Step 4: 实现视图**

创建 `backend/qa_agent/views.py`：

```python
"""qa_agent HTTP API"""
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from room.models import Project, Task
from room.views.ai import _check_project_member
from .models import AgentRun
from .serializers import AgentRunSerializer
from .services import create_run, dispatch_run


class AgentRunListCreateView(APIView):
    """GET /api/qa-agent/runs/?project_id=... | POST 手动创建并触发"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = AgentRun.objects.select_related('project', 'source_task', 'created_by')
        project_id = request.query_params.get('project_id', '').strip()
        if project_id:
            project = get_object_or_404(Project, pk=project_id)
            if not _check_project_member(project, request.user):
                return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)
            qs = qs.filter(project=project)
        serializer = AgentRunSerializer(qs[:50], many=True)
        return Response(serializer.data)

    def post(self, request):
        project_id = request.data.get('project_id', '').strip()
        source_task_id = request.data.get('source_task_id', '').strip()
        if not project_id:
            return Response({'detail': 'project_id 不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        project = get_object_or_404(Project, pk=project_id)
        if not _check_project_member(project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)
        source_task = None
        if source_task_id:
            source_task = get_object_or_404(
                Task, pk=source_task_id, column__project=project,
            )
        run = create_run(
            project=project, trigger='manual',
            source_task=source_task, created_by=request.user,
        )
        dispatch_run(run.id)
        return Response(AgentRunSerializer(run).data, status=status.HTTP_201_CREATED)


class AgentRunDetailView(APIView):
    """GET /api/qa-agent/runs/<id>/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, run_id):
        run = get_object_or_404(AgentRun, pk=run_id)
        if not _check_project_member(run.project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)
        return Response(AgentRunSerializer(run).data)


class AgentRunCancelView(APIView):
    """POST /api/qa-agent/runs/<id>/cancel/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, run_id):
        run = get_object_or_404(AgentRun, pk=run_id)
        if not _check_project_member(run.project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)
        if run.status not in ('queued', 'planning', 'executing', 'analyzing', 'reporting'):
            return Response(
                {'detail': f'当前状态 {run.status} 不可取消'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        run.status = 'cancelled'
        run.save(update_fields=['status', 'updated_at'])
        return Response(AgentRunSerializer(run).data)
```

- [ ] **Step 5: 实现 urls 并注册到根路由**

创建 `backend/qa_agent/urls.py`：

```python
from django.urls import path

from .views import AgentRunCancelView, AgentRunDetailView, AgentRunListCreateView

urlpatterns = [
    path('runs/', AgentRunListCreateView.as_view(), name='qa-agent-run-list'),
    path('runs/<str:run_id>/', AgentRunDetailView.as_view(), name='qa-agent-run-detail'),
    path('runs/<str:run_id>/cancel/', AgentRunCancelView.as_view(), name='qa-agent-run-cancel'),
]
```

在 `backend/backend/urls.py` 中 `path('api/', include('bug_tracker.urls')),` 之后追加：

```python
    path('api/qa-agent/', include('qa_agent.urls')),
```

（同时在文件顶部 import 区把 `include` 已在用，无需新增 import。）

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_api.py -v`

Expected: 全部 PASS（6 个）

- [ ] **Step 7: Commit**

```bash
git add backend/qa_agent/serializers.py backend/qa_agent/views.py backend/qa_agent/urls.py backend/backend/urls.py backend/tests/test_qa_agent_api.py
git commit -m "feat(qa_agent): 执行记录 API（列表/创建/详情/取消）"
```

## Task 7: llm.py — JSON 输出调用与重试

**Files:**
- Create: `backend/qa_agent/llm.py`
- Test: `backend/tests/test_qa_agent_planning.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_qa_agent_planning.py`：

```python
"""qa_agent LLM 与计划生成测试"""
import pytest

from qa_agent import llm
from qa_agent.llm import _extract_json, llm_json


def test_extract_json_fenced():
    text = '好的，以下是结果：\n```json\n{"a": 1}\n```'
    assert _extract_json(text) == {'a': 1}


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {'a': 1}


def test_extract_json_with_prefix_text():
    text = '开始{"a": 1}结束'
    assert _extract_json(text) == {'a': 1}


def test_extract_json_empty_raises():
    with pytest.raises(ValueError):
        _extract_json('   ')


class FakeChatCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raw = self._responses.pop(0)
        return _FakeResponse(raw)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeClient:
    def __init__(self, responses):
        self.chat = FakeChatCompletions(responses)


def test_llm_json_success(monkeypatch):
    fake = FakeClient(['```json\n{"ok": true}\n```'])
    monkeypatch.setattr('qa_agent.llm.client', fake)
    monkeypatch.setattr('qa_agent.llm.config.LLM_RETRIES', 3)
    assert llm_json([{'role': 'user', 'content': 'hi'}]) == {'ok': True}


def test_llm_json_retries_then_succeeds(monkeypatch):
    fake = FakeClient(['not json', '{"ok": true}'])
    monkeypatch.setattr('qa_agent.llm.client', fake)
    monkeypatch.setattr('qa_agent.llm.config.LLM_RETRIES', 3)
    monkeypatch.setattr('qa_agent.llm.config.LLM_BACKOFF_BASE_SECONDS', 0)
    assert llm_json([{'role': 'user', 'content': 'hi'}]) == {'ok': True}
    assert fake.chat.calls == 2


def test_llm_json_gives_up(monkeypatch):
    fake = FakeClient(['bad', 'bad', 'bad'])
    monkeypatch.setattr('qa_agent.llm.client', fake)
    monkeypatch.setattr('qa_agent.llm.config.LLM_RETRIES', 3)
    monkeypatch.setattr('qa_agent.llm.config.LLM_BACKOFF_BASE_SECONDS', 0)
    with pytest.raises(RuntimeError):
        llm_json([{'role': 'user', 'content': 'hi'}])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_planning.py -v`

Expected: 全部 FAIL（`ModuleNotFoundError: qa_agent.llm`）

- [ ] **Step 3: 实现 llm.py**

创建 `backend/qa_agent/llm.py`：

```python
"""LLM 结构化输出调用：JSON 提取 + 重试退避"""
import json
import logging
import re
import time

from room.ai_utils import client

from . import config

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON（容忍 ```json 围栏与前缀后缀文本）。"""
    if not text or not text.strip():
        raise ValueError('LLM 返回空内容')
    fence = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.S)
    candidate = fence.group(1) if fence else text.strip()
    start = candidate.find('{')
    end = candidate.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f'输出中未找到 JSON 对象: {candidate[:200]}')
    return json.loads(candidate[start:end + 1])


def llm_json(messages, *, temperature=0.2, max_tokens=2000, model=None) -> dict:
    """调用 LLM 并要求返回 JSON，带重试与指数退避；全部失败抛 RuntimeError。"""
    model = model or config.MODEL
    last_error = None
    for attempt in range(config.LLM_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens, timeout=60,
            )
            return _extract_json(resp.choices[0].message.content)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning('llm_json 第 %d 次尝试失败: %s', attempt + 1, exc)
            if attempt < config.LLM_RETRIES - 1:
                time.sleep(config.LLM_BACKOFF_BASE_SECONDS * (2 ** attempt))
    raise RuntimeError(f'llm_json 重试 {config.LLM_RETRIES} 次后失败: {last_error}')
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_planning.py -v`

Expected: 全部 PASS（6 个）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/llm.py backend/tests/test_qa_agent_planning.py
git commit -m "feat(qa_agent): LLM JSON 输出调用与重试"
```

## Task 8: PlanSchema + 上下文构建 + 计划生成（含最小计划降级）

**Files:**
- Modify: `backend/qa_agent/serializers.py`
- Modify: `backend/qa_agent/services.py`
- Test: `backend/tests/test_qa_agent_planning.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_qa_agent_planning.py` 末尾追加：

```python
from qa_agent.services import build_context, build_plan, minimal_plan
from qa_center.models import ApiAutoTestCase
from room.models import Column, Task, ProjectApiDoc


@pytest.mark.django_db
def test_build_context_contains_task_and_doc(test_user, test_project):
    col = Column.objects.create(project=test_project, title='待测试', position=4)
    task = Task.objects.create(column=col, title='登录功能', content='支持用户名密码登录')
    ProjectApiDoc.objects.create(
        project=test_project, name='auth_api', format='markdown',
        content='POST /api/auth/login/ 成功 200 失败 401',
    )
    from qa_agent.models import AgentRun
    run = AgentRun.objects.create(project=test_project, source_task=task, created_by=test_user)
    context = build_context(run)
    assert '登录功能' in context
    assert '/api/auth/login/' in context


@pytest.mark.django_db
def test_build_plan_valid_llm_output(test_user, test_project, monkeypatch):
    from qa_agent.models import AgentRun
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    monkeypatch.setattr('qa_agent.services.llm_json', lambda messages, **kw: {
        'api_cases': [{
            'name': '登录成功', 'url': 'http://testserver/api/auth/login/',
            'method': 'POST', 'expected_status': 200,
        }],
        'ui_cases': [],
        'regression_case_ids': [1, 2],
    })
    plan = build_plan(run)
    assert plan['api_cases'][0]['method'] == 'POST'
    assert plan['regression_case_ids'] == [1, 2]


@pytest.mark.django_db
def test_build_plan_fallback_to_minimal(test_user, test_project, monkeypatch):
    from qa_agent.models import AgentRun
    case = ApiAutoTestCase.objects.create(
        project=test_project, name='既有用例', url='http://testserver/api/projects/',
        method='GET', created_by=test_user,
    )
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    monkeypatch.setattr('qa_agent.services.llm_json', lambda messages, **kw: {'not': 'a plan'})
    plan = build_plan(run)
    assert plan['api_cases'] == []
    assert plan['regression_case_ids'] == [case.id]


@pytest.mark.django_db
def test_minimal_plan_reuses_existing_cases(test_user, test_project):
    from qa_agent.models import AgentRun
    ApiAutoTestCase.objects.create(
        project=test_project, name='用例A', url='http://testserver/api/a/',
        method='GET', created_by=test_user,
    )
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    plan = minimal_plan(run)
    assert len(plan['regression_case_ids']) == 1
    assert plan['api_cases'] == [] and plan['ui_cases'] == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_planning.py -v`

Expected: 新增 4 个 FAIL（`build_context`/`build_plan` 不存在）

- [ ] **Step 3: 在 serializers.py 追加 PlanSchema**

在 `backend/qa_agent/serializers.py` 末尾追加：

```python
# ---------- LLM 结构化输出校验 ----------

class PlanApiCaseSchema(serializers.Serializer):
    name = serializers.CharField()
    url = serializers.CharField()
    method = serializers.ChoiceField(choices=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    expected_status = serializers.IntegerField(required=False)
    assertions = serializers.CharField(required=False, allow_blank=True, default='')
    headers = serializers.CharField(required=False, allow_blank=True, default='')
    body = serializers.CharField(required=False, allow_blank=True, default='')


class PlanUiStepSchema(serializers.Serializer):
    action = serializers.CharField()
    selector = serializers.CharField(allow_blank=True, default='')
    value = serializers.CharField(allow_blank=True, default='')


class PlanUiCaseSchema(serializers.Serializer):
    name = serializers.CharField()
    url = serializers.CharField()
    steps = PlanUiStepSchema(many=True, required=False, default=list)


class PlanSchema(serializers.Serializer):
    api_cases = PlanApiCaseSchema(many=True, required=False, default=list)
    ui_cases = PlanUiCaseSchema(many=True, required=False, default=list)
    regression_case_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
    )


class AnalysisItemSchema(serializers.Serializer):
    flaky = serializers.ChoiceField(choices=['deterministic', 'flaky', 'unknown'])
    root_cause = serializers.ChoiceField(
        choices=['bug_in_app', 'test_case_issue', 'environment_issue', 'unknown'],
    )
    evidence = serializers.CharField(allow_blank=True, default='')
    fix_suggestion = serializers.CharField(allow_blank=True, default='')
```

- [ ] **Step 4: 在 services.py 追加上下文与计划生成**

在 `backend/qa_agent/services.py` 末尾追加：

```python
import logging as _logging

from .llm import llm_json
from .serializers import PlanSchema

logger = _logging.getLogger(__name__)

PLAN_PROMPT = """你是 QA 测试规划 Agent。根据提供的项目上下文，输出一份 JSON 测试计划。
计划必须只使用上下文中出现的真实资源（URL、ID），不得编造。
JSON 结构：
{
  "api_cases": [{"name": "用例名", "url": "http://...", "method": "GET|POST|PUT|PATCH|DELETE", "expected_status": 200, "assertions": "[{\\"type\\":\\"status_code\\",\\"operator\\":\\"==\\",\\"value\\":\\"200\\"}]"}],
  "ui_cases": [{"name": "用例名", "url": "http://...", "steps": [{"action": "click", "selector": "text=登录", "value": ""}]}],
  "regression_case_ids": [1, 2]
}
规则：
1. 只生成与源任务需求相关的用例
2. 没有 API 文档时 api_cases 为空列表；不适用 UI 时 ui_cases 为空列表
3. regression_case_ids 复用上下文中"已有 API 用例"的真实 ID，没有则空列表
4. expected_status 只填 200/400/401/403/404/500 等标准状态码
5. assertions 为可选的 JSON 数组字符串"""


def build_context(run) -> str:
    """构建 planning 阶段的上下文文本（源任务、评论、API 文档、已有用例）。"""
    from room.models import ProjectApiDoc
    from qa_center.models import ApiAutoTestCase

    parts = []
    if run.source_task:
        parts.append(
            f"## 源任务\n标题：{run.source_task.title}\n"
            f"内容：{run.source_task.content or '（无）'}"
        )
        comments = run.source_task.comments.order_by('created_at')[:10]
        if comments.exists():
            parts.append('## 任务评论\n' + '\n'.join(
                f'- {c.author.username}: {c.content[:200]}' for c in comments
            ))
    docs = ProjectApiDoc.objects.filter(project=run.project)[:3]
    if docs.exists():
        parts.append('## API 文档\n' + '\n'.join(
            f'- [{d.get_format_display()}] {d.name}: {d.content[:1500]}' for d in docs
        ))
    api_cases = ApiAutoTestCase.objects.filter(project=run.project)[:10]
    if api_cases.exists():
        parts.append('## 已有 API 用例\n' + '\n'.join(
            f'- ID={c.id} [{c.method}] {c.name} — {c.url}' for c in api_cases
        ))
    return '\n\n'.join(parts) or '（暂无项目上下文）'


def build_plan(run) -> dict:
    """生成测试计划；LLM 输出非法或调用失败时降级为最小计划，不阻断流程。"""
    context = build_context(run)
    try:
        raw = llm_json([
            {'role': 'system', 'content': PLAN_PROMPT},
            {'role': 'user', 'content': f'项目上下文：\n{context}'},
        ])
        plan = PlanSchema(data=raw)
        plan.is_valid(raise_exception=True)
        return plan.validated_data
    except Exception as exc:  # noqa: BLE001
        logger.warning('build_plan 降级为最小计划: %s', exc)
        return minimal_plan(run)


def minimal_plan(run) -> dict:
    """最小计划：不新建用例，回归执行项目已有 API 用例（最多 10 个）。"""
    from qa_center.models import ApiAutoTestCase

    return {
        'api_cases': [],
        'ui_cases': [],
        'regression_case_ids': list(
            ApiAutoTestCase.objects.filter(project=run.project)
            .values_list('id', flat=True)[:10]
        ),
    }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_planning.py -v`

Expected: 全部 PASS（10 个）

- [ ] **Step 6: Commit**

```bash
git add backend/qa_agent/serializers.py backend/qa_agent/services.py backend/tests/test_qa_agent_planning.py
git commit -m "feat(qa_agent): 计划 schema 校验与上下文/计划生成（含降级）"
```

## Task 9: analysis.py — 失败分析、聚类、自动建 Bug

**Files:**
- Create: `backend/qa_agent/analysis.py`
- Test: `backend/tests/test_qa_agent_analysis.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_qa_agent_analysis.py`：

```python
"""qa_agent 失败分析与报告测试"""
import pytest

from qa_agent.analysis import (
    analyze_failures, cluster_findings, collect_failures, fallback_analyze,
)
from qa_agent.models import AgentRun
from bug_tracker.models import Bug
from qa_center.models import TestResult
from room.models import Column, Task


def test_fallback_analyze_rules():
    assert fallback_analyze('预期 200，实际 401：未授权') == {
        'flaky': 'deterministic', 'root_cause': 'bug_in_app',
        'evidence': '关键词匹配: [\'401\', \'403\']', 'fix_suggestion': '',
    }
    assert fallback_analyze('TimeoutError: waiting for selector timed out')['flaky'] == 'flaky'
    assert fallback_analyze('Connection refused: 127.0.0.1:8000')['root_cause'] == 'environment_issue'
    assert fallback_analyze('locator.click: no such element #submit')['root_cause'] == 'test_case_issue'
    assert fallback_analyze('完全未知的错误')['root_cause'] == 'unknown'


@pytest.mark.django_db
def test_collect_failures_window(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    r = TestResult.objects.create(
        project=test_project, test_type='api', name='失败用例',
        status='failed', error_message='boom',
    )
    TestResult.objects.create(
        project=test_project, test_type='api', name='通过用例', status='passed',
    )
    assert [x.id for x in collect_failures(run)] == [r.id]


@pytest.mark.django_db
def test_analyze_failures_creates_bug_for_deterministic_bug(test_user, test_project, monkeypatch):
    col = Column.objects.create(project=test_project, title='待测试', position=4)
    task = Task.objects.create(column=col, title='登录功能')
    run = AgentRun.objects.create(
        project=test_project, source_task=task, trigger='task_column', created_by=test_user,
    )
    # 三条失败：两条错误文本相同（同聚类），一条不同
    TestResult.objects.create(
        project=test_project, test_type='api', name='登录成功',
        status='failed', error_message='预期 200，实际 401',
    )
    TestResult.objects.create(
        project=test_project, test_type='ui', name='登录成功-UI',
        status='failed', error_message='预期 200，实际 401',
    )
    TestResult.objects.create(
        project=test_project, test_type='ui', name='登录页打开',
        status='failed', error_message='locator.click: no such element',
    )
    monkeypatch.setattr('qa_agent.analysis.llm_json', lambda messages, **kw: {
        'flaky': 'deterministic', 'root_cause': 'bug_in_app',
        'evidence': '401 未授权', 'fix_suggestion': '检查鉴权',
    })
    findings = analyze_failures(run)
    assert len(findings) == 3
    bugs = list(Bug.objects.filter(project=test_project))
    # 聚类去重：同错误文本归为一簇 → 3 条失败 2 个聚类 → 2 张单
    assert len(bugs) == 2
    bug = bugs[0]
    assert bug.linked_task == task
    assert bug.source_test_type == 'api_auto'  # 取该簇首条失败的类型
    assert bug.reporter == test_user
    assert bug.title.startswith('[AI-QA]')


@pytest.mark.django_db
def test_analyze_failures_flaky_no_bug(test_user, test_project, monkeypatch):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    TestResult.objects.create(
        project=test_project, test_type='api', name='偶发超时',
        status='failed', error_message='TimeoutError',
    )
    monkeypatch.setattr('qa_agent.analysis.llm_json', lambda messages, **kw: {
        'flaky': 'flaky', 'root_cause': 'environment_issue',
        'evidence': '超时', 'fix_suggestion': '',
    })
    analyze_failures(run)
    assert Bug.objects.filter(project=test_project).count() == 0


@pytest.mark.django_db
def test_analyze_failures_llm_fallback_rules(test_user, test_project, monkeypatch):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    TestResult.objects.create(
        project=test_project, test_type='api', name='连接失败',
        status='error', error_message='Connection refused: 127.0.0.1:8000',
    )
    monkeypatch.setattr('qa_agent.analysis.llm_json', lambda messages, **kw: (_ for _ in ()).throw(RuntimeError('llm down')))
    findings = analyze_failures(run)
    assert findings[0]['root_cause'] == 'environment_issue'
    assert Bug.objects.filter(project=test_project).count() == 0


@pytest.mark.django_db
def test_cluster_findings_groups_by_root_cause(test_user, test_project):
    findings = [
        {'root_cause': 'bug_in_app', 'error_message': '预期 200，实际 401'},
        {'root_cause': 'bug_in_app', 'error_message': '预期 200，实际 401'},
        {'root_cause': 'test_case_issue', 'error_message': 'selector missing'},
    ]
    clusters = cluster_findings(findings)
    assert len(clusters) == 2
```

> 注：`TestScreenshot` 在此文件被 import 供后续 Task 12 使用前的存在性验证——实际截图断言在 Task 12 的集成测试中。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_analysis.py -v`

Expected: 全部 FAIL（`ModuleNotFoundError: qa_agent.analysis`）

- [ ] **Step 3: 实现 analysis.py**

创建 `backend/qa_agent/analysis.py`：

```python
"""失败分析：LLM 结构化分析 + 规则降级 + 聚类 + 自动建 Bug"""
import logging
import re

from bug_tracker.models import Bug
from qa_center.models import TestResult

from .llm import llm_json
from .orchestration import emit_event
from .serializers import AnalysisItemSchema

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """你是测试失败分析 Agent。根据失败用例信息，输出严格 JSON：
{
  "flaky": "deterministic|flaky|unknown",
  "root_cause": "bug_in_app|test_case_issue|environment_issue|unknown",
  "evidence": "判断依据（简述）",
  "fix_suggestion": "修复建议"
}
判定规则：
- flaky="flaky"：超时、偶发连接错误、选择器偶尔找不到等重试可能成功的迹象
- root_cause="bug_in_app"：稳定复现的功能断言失败（状态码/文本/元素不符）
- root_cause="test_case_issue"：用例自身错误（选择器失效、URL 错误、断言写错、测试数据缺失）
- root_cause="environment_issue"：环境问题（服务未启动、网络、依赖服务不可用）
- 无法判断用 "unknown"
只输出 JSON，不要任何解释文字。"""

FALLBACK_RULES = [
    (('flaky', 'unknown'), ['timeout', 'timed out', 'net::', 'retry']),
    (('deterministic', 'environment_issue'), ['connection refused', 'cannot connect', 'dns', '502', '503']),
    (('deterministic', 'test_case_issue'), ['selector', 'locator', 'no such element', 'not found']),
    (('deterministic', 'bug_in_app'), ['401', '403']),
]


def fallback_analyze(error_message: str) -> dict:
    """规则降级分析：关键词命中即返回，否则 unknown。"""
    text = (error_message or '').lower()
    for (flaky, root_cause), keywords in FALLBACK_RULES:
        if any(kw in text for kw in keywords):
            return {
                'flaky': flaky, 'root_cause': root_cause,
                'evidence': f'关键词匹配: {keywords}', 'fix_suggestion': '',
            }
    return {'flaky': 'unknown', 'root_cause': 'unknown',
            'evidence': '', 'fix_suggestion': ''}


def collect_failures(run):
    """收集本次 run 产生（created_at >= run.created_at）的失败/错误 TestResult。"""
    return list(TestResult.objects.filter(
        project=run.project,
        status__in=['failed', 'error'],
        created_at__gte=run.created_at,
    ).order_by('created_at'))


def analyze_failure(run, result: TestResult) -> dict:
    """单条失败分析：LLM 结构化输出，失败降级为规则分析。"""
    case_desc = (
        f'用例: {result.name} ({result.test_type})\n'
        f'错误信息: {result.error_message or ""}\n'
        f'日志: {(result.test_log or "")[:800]}\n'
        f'截图数: {result.screenshots.count()}'
    )
    try:
        raw = llm_json([
            {'role': 'system', 'content': ANALYSIS_PROMPT},
            {'role': 'user', 'content': case_desc},
        ])
        item = AnalysisItemSchema(data=raw)
        item.is_valid(raise_exception=True)
        return item.validated_data
    except Exception as exc:  # noqa: BLE001
        logger.warning('analyze_failure 降级为规则分析: %s', exc)
        return fallback_analyze(result.error_message or '')


def _normalize_error(text: str) -> str:
    """归一化错误信息：数字占位 + 折叠空白，用于聚类。"""
    text = re.sub(r'\d+', '#', text or '')
    return ' '.join(text.split())[:200]


def cluster_findings(findings):
    """按 (root_cause, 归一化错误) 聚类，返回 {key: [findings]}。"""
    clusters = {}
    for f in findings:
        key = (f['root_cause'], _normalize_error(f.get('error_message', '')))
        clusters.setdefault(key, []).append(f)
    return clusters


def create_bugs_for_findings(run, findings):
    """规则闸门：仅 bug_in_app + deterministic 的聚类建单，同根因去重。"""
    clusters = cluster_findings(findings)
    for (root_cause, _norm), items in clusters.items():
        if root_cause != 'bug_in_app':
            continue
        deterministic = [i for i in items if i.get('flaky') == 'deterministic']
        if not deterministic:
            continue
        first = deterministic[0]
        source = run.source_task
        Bug.objects.create(
            project=run.project,
            title=f'[AI-QA] {source.title if source else run.id} - {first["result_name"]}',
            description=first.get('evidence', ''),
            steps_to_reproduce=(source.content or '') if source else '',
            actual=first.get('error_message', ''),
            source_test_type='api_auto' if first.get('test_type') == 'api' else 'ui_auto',
            source_result_id=first.get('result_id'),
            linked_task=source,
            reporter=run.created_by,
            assignee=source.assignee if source else None,
            severity='major',
            priority='p2',
        )
        emit_event(run, f'已自动创建 Bug：{first["result_name"]}', level='warn')


def analyze_failures(run):
    """analyzing 阶段主入口：收集 → 逐条分析 → 聚类建单 → 返回 findings。"""
    results = collect_failures(run)
    findings = []
    for r in results:
        item = analyze_failure(run, r)
        item.update({
            'result_id': r.id,
            'result_name': r.name,
            'test_type': r.test_type,
            'error_message': r.error_message or '',
        })
        findings.append(item)
    if findings:
        create_bugs_for_findings(run, findings)
        emit_event(run, f'失败分析完成：{len(findings)} 条失败')
    return findings
```

> 注：`emit_event` 被 analysis 复用——注意 orchestration.py 的 `emit_event` 已在 Task 3 实现，这里 import 即可。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_analysis.py -v`

Expected: 全部 PASS（6 个）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/analysis.py backend/tests/test_qa_agent_analysis.py
git commit -m "feat(qa_agent): 失败分析/聚类/自动建 Bug"
```

## Task 10: reporting.py — Markdown 报告、评论回写、通知

**Files:**
- Create: `backend/qa_agent/reporting.py`
- Test: `backend/tests/test_qa_agent_analysis.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_qa_agent_analysis.py` 末尾追加：

```python
from qa_agent.reporting import build_report, post_report
from room.models import Notification, TaskComment


@pytest.mark.django_db
def test_build_report_contains_findings(test_user, test_project):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    report = build_report(run, [{
        'result_name': '登录成功', 'test_type': 'api',
        'flaky': 'deterministic', 'root_cause': 'bug_in_app',
        'evidence': '401', 'fix_suggestion': '检查鉴权',
    }])
    assert '# AI-QA 测试报告' in report
    assert 'bug_in_app' in report
    assert '检查鉴权' in report


@pytest.mark.django_db
def test_post_report_comment_and_notification(test_user, test_project):
    col = Column.objects.create(project=test_project, title='待测试', position=4)
    task = Task.objects.create(column=col, title='登录功能')
    run = AgentRun.objects.create(
        project=test_project, source_task=task, created_by=test_user,
    )
    post_report(run, '报告正文', has_failures=True)
    assert TaskComment.objects.filter(task=task, author=test_user).exists()
    notif = Notification.objects.get(user=test_user, project=test_project)
    assert notif.type == 'test_failure'
    assert '报告正文' in notif.message
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_analysis.py -v`

Expected: 新增 2 个 FAIL（`ModuleNotFoundError: qa_agent.reporting`）

- [ ] **Step 3: 实现 reporting.py**

创建 `backend/qa_agent/reporting.py`：

```python
"""报告：Markdown 报告生成、任务卡评论回写、站内通知"""
from qa_center.models import TestResult
from room.models import Notification, TaskComment


def _report_user(run):
    return run.created_by or run.project.owner


def build_report(run, findings) -> str:
    """生成 Markdown 报告（测试范围、通过率、失败明细、聚类摘要）。"""
    lines = [f'# AI-QA 测试报告（{run.get_trigger_display()}）', '']
    results = collect_all_results(run)
    failed = len([r for r in results if r.status in ('failed', 'error')])
    lines.append(f'- 本次执行：{len(results)} 条')
    lines.append(f'- 通过：{len(results) - failed}')
    lines.append(f'- 失败/错误：{failed}')
    lines.append('')
    if findings:
        lines.append('## 失败分析')
        for f in findings:
            lines.append(
                f"- {f['result_name']}（{f['test_type']}）："
                f"flaky={f['flaky']}，root_cause={f['root_cause']}"
            )
            if f.get('evidence'):
                lines.append(f"  - 依据：{f['evidence']}")
            if f.get('fix_suggestion'):
                lines.append(f"  - 建议：{f['fix_suggestion']}")
    else:
        lines.append('无失败项，全部通过。')
    return '\n'.join(lines)


def collect_all_results(run):
    """本次 run 的全部 TestResult（含通过项），供报告统计。"""
    return list(TestResult.objects.filter(
        project=run.project,
        created_at__gte=run.created_at,
    ).order_by('created_at'))


def post_report(run, report: str, has_failures: bool):
    """回写源任务评论 + 给创建者发站内通知。"""
    user = _report_user(run)
    if run.source_task and user is not None:
        TaskComment.objects.create(task=run.source_task, author=user, content=report)
    if user is not None:
        Notification.objects.create(
            user=user,
            title=f'AI-QA 测试报告：{run.project.name}',
            message=report[:500],
            type='test_failure' if has_failures else 'system',
            project=run.project,
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_analysis.py -v`

Expected: 全部 PASS（8 个）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/reporting.py backend/tests/test_qa_agent_analysis.py
git commit -m "feat(qa_agent): Markdown 报告与评论/通知回写"
```

## Task 11: adapter.py + orchestration 主流程接线（API 闭环跑通）

**Files:**
- Create: `backend/qa_agent/adapter.py`
- Modify: `backend/qa_agent/orchestration.py`
- Test: `backend/tests/test_qa_agent_integration.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_qa_agent_integration.py`：

```python
"""qa_agent 全流程集成测试（stub LLM 与执行适配器）"""
import pytest

from bug_tracker.models import Bug
from qa_agent.models import AgentRun
from qa_agent.orchestration import run_agent_pipeline
from qa_center.models import TestResult
from room.models import Column, Notification, Task, TaskComment


def _fake_llm_json(messages, **kw):
    sys_prompt = messages[0]['content']
    if 'QA 测试规划' in sys_prompt:
        return {
            'api_cases': [{
                'name': '登录接口', 'url': 'http://testserver/api/auth/login/',
                'method': 'POST', 'expected_status': 200,
            }],
            'ui_cases': [],
            'regression_case_ids': [],
        }
    if '失败分析' in sys_prompt:
        return {
            'flaky': 'deterministic', 'root_cause': 'bug_in_app',
            'evidence': '401 未授权', 'fix_suggestion': '检查登录接口鉴权',
        }
    raise AssertionError(f'未知 prompt: {sys_prompt[:60]}')


@pytest.mark.django_db
def test_full_loop_api_closed_loop(test_user, test_project, monkeypatch):
    col = Column.objects.create(project=test_project, title='待测试', position=4)
    task = Task.objects.create(column=col, title='登录功能', content='支持用户名密码登录')

    monkeypatch.setattr('qa_agent.services.llm_json', _fake_llm_json)
    monkeypatch.setattr('qa_agent.analysis.llm_json', _fake_llm_json)
    monkeypatch.setattr('qa_agent.adapter.create_api_case', lambda run, spec: 1)
    monkeypatch.setattr('qa_agent.adapter.run_api_cases', lambda run, case_ids: _stub_run_api(run, case_ids))

    run = AgentRun.objects.create(
        project=test_project, source_task=task, trigger='task_column', created_by=test_user,
    )
    status = run_agent_pipeline(run.id)
    assert status == 'done'

    run.refresh_from_db()
    assert run.summary.startswith('# AI-QA 测试报告')
    assert run.steps.count() >= 4  # generate_cases / execute / analyze / report
    assert Bug.objects.filter(project=test_project, linked_task=task).count() == 1
    assert TaskComment.objects.filter(task=task).exists()
    assert Notification.objects.filter(user=test_user, project=test_project).exists()


def _stub_run_api(run, case_ids):
    TestResult.objects.create(
        project=run.project, test_type='api', name='登录接口',
        status='failed', error_message='预期 200，实际 401：未授权',
    )
    return {'ok': True, 'detail': 'stubbed'}


@pytest.mark.django_db
def test_full_loop_cancelled_aborts(test_user, test_project, monkeypatch):
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    run.status = 'cancelled'
    run.save(update_fields=['status'])
    monkeypatch.setattr('qa_agent.services.llm_json', _fake_llm_json)
    status = run_agent_pipeline(run.id)
    assert status == 'cancelled'


@pytest.mark.django_db
def test_full_loop_failure_marks_failed(test_user, test_project, monkeypatch):
    # 计划正常，但执行适配器崩溃 → 主流程标记 failed
    monkeypatch.setattr('qa_agent.services.llm_json', _fake_llm_json)
    monkeypatch.setattr('qa_agent.adapter.create_api_case', lambda run, spec: 1)

    def boom(run, case_ids):
        raise RuntimeError('执行引擎崩溃')

    monkeypatch.setattr('qa_agent.adapter.run_api_cases', boom)
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    status = run_agent_pipeline(run.id)
    assert status == 'failed'
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_integration.py -v`

Expected: 全部 FAIL（`ModuleNotFoundError: qa_agent.adapter`，且 orchestration 无 run_agent_pipeline）

- [ ] **Step 3: 实现 adapter.py**

创建 `backend/qa_agent/adapter.py`：

```python
"""编排层 → 现有业务能力的适配器。

边界规则：编排层不直接操作业务模型，统一经此模块调用
room.ai_utils.execute_tool 与 qa_center 的执行入口。
"""
import json
import logging
import time

from . import config

logger = logging.getLogger(__name__)


def _tool_user(run):
    """工具调用需要 user 上下文：优先 run 创建者，其次项目 owner。"""
    return run.created_by or run.project.owner


def create_api_case(run, spec: dict) -> int:
    """经现有工具创建 API 用例，返回用例 ID；失败抛 RuntimeError。"""
    from qa_center.models import ApiAutoTestCase
    from room.ai_utils import execute_tool

    result_text = execute_tool('create_api_test_case', {
        'name': spec['name'],
        'url': spec['url'],
        'method': spec['method'],
        'headers': spec.get('headers', ''),
        'body': spec.get('body', ''),
        'expected_status': spec.get('expected_status'),
        'assertions': spec.get('assertions', ''),
    }, str(run.project_id), _tool_user(run))
    case = ApiAutoTestCase.objects.filter(
        project_id=run.project_id, name=spec['name'],
    ).order_by('-id').first()
    if case is None:
        raise RuntimeError(f'API 用例创建失败: {result_text}')
    return case.id


def create_ui_case(run, spec: dict) -> int:
    """经现有工具创建 UI 用例，返回用例 ID；失败抛 RuntimeError。"""
    from qa_center.models import UiTestCase
    from room.ai_utils import execute_tool

    result_text = execute_tool('create_ui_test_case', {
        'name': spec['name'],
        'url': spec['url'],
        'steps_json': json.dumps(spec.get('steps', []), ensure_ascii=False),
    }, str(run.project_id), _tool_user(run))
    case = UiTestCase.objects.filter(
        project_id=run.project_id, name=spec['name'],
    ).order_by('-id').first()
    if case is None:
        raise RuntimeError(f'UI 用例创建失败: {result_text}')
    return case.id


def run_api_cases(run, case_ids: list) -> dict:
    """把 API 用例组装成 TestTask 执行并轮询到终态。"""
    from qa_center.models import TestTask
    from room.ai_utils import execute_tool

    if not case_ids:
        return {'ok': True, 'detail': '无 API 用例可执行'}
    task_name = f'AI-QA-{run.id.hex[:8]}'
    execute_tool('create_test_task', {
        'name': task_name, 'test_type': 'api',
        'api_case_ids': ','.join(str(i) for i in case_ids),
    }, str(run.project_id), _tool_user(run))
    execute_tool('execute_test_task', {'task_name': task_name},
                 str(run.project_id), _tool_user(run))

    task = TestTask.objects.get(name=task_name, project_id=run.project_id)
    deadline = time.time() + config.POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        task.refresh_from_db()
        if task.status in ('completed', 'failed', 'partial'):
            return {'ok': True, 'detail': f'TestTask 终态: {task.status}'}
        run.refresh_from_db()
        if run.status == 'cancelled':
            return {'ok': False, 'detail': 'run 已取消，停止轮询'}
        time.sleep(config.POLL_INTERVAL_SECONDS)
    return {'ok': False, 'detail': f'TestTask 轮询超时 ({config.POLL_TIMEOUT_SECONDS}s)'}
```

- [ ] **Step 4: 在 orchestration.py 追加主流程**

在 `backend/qa_agent/orchestration.py` 末尾追加：

```python
from .analysis import analyze_failures
from .reporting import build_report, post_report
from .services import build_plan


def _record_step(run, step_type, *, status='done', tool_name='', input=None, output=None):
    from .models import AgentStep

    AgentStep.objects.create(
        run=run, step_type=step_type, status=status,
        tool_name=tool_name, input=input or {}, output=output or {},
    )


def execute_plan(run, plan: dict):
    """executing 阶段：按计划创建并执行用例（逐项容错，单步失败不阻断）。"""
    from .adapter import create_api_case, run_api_cases

    api_ids = []
    for spec in plan.get('api_cases', []):
        try:
            cid = create_api_case(run, spec)
            api_ids.append(cid)
            _record_step(run, 'generate_cases', tool_name='create_api_test_case',
                         input=spec, output={'case_id': cid})
            emit_event(run, f'已创建 API 用例「{spec["name"]}」')
        except Exception as exc:  # noqa: BLE001
            _record_step(run, 'generate_cases', status='error',
                         tool_name='create_api_test_case', input=spec,
                         output={'error': str(exc)})
            emit_event(run, f'API 用例创建失败: {exc}', level='warn')

    if plan.get('ui_cases'):
        from .adapter import create_ui_case, run_ui_cases

        for spec in plan['ui_cases']:
            try:
                cid = create_ui_case(run, spec)
                _record_step(run, 'generate_cases', tool_name='create_ui_test_case',
                             input=spec, output={'case_id': cid})
                emit_event(run, f'已创建 UI 用例「{spec["name"]}」')
            except Exception as exc:  # noqa: BLE001
                _record_step(run, 'generate_cases', status='error',
                             tool_name='create_ui_test_case', input=spec,
                             output={'error': str(exc)})
                emit_event(run, f'UI 用例创建失败: {exc}', level='warn')

    regression_ids = list(plan.get('regression_case_ids', []))
    all_api_ids = list(dict.fromkeys(api_ids + regression_ids))

    if all_api_ids:
        result = run_api_cases(run, all_api_ids)
        _record_step(run, 'execute', tool_name='run_api_cases',
                     input={'api_case_ids': all_api_ids}, output=result)
    if plan.get('ui_cases'):
        from .adapter import run_ui_cases

        result = run_ui_cases(run, plan['ui_cases'])
        _record_step(run, 'execute', tool_name='run_ui_cases',
                     input={'ui_case_names': [s['name'] for s in plan['ui_cases']]},
                     output=result)


def run_agent_pipeline(run_id):
    """AgentRun 主流程：queued → planning → executing → analyzing → reporting → done。

    返回值：最终状态字符串。任何异常 → failed；用户取消（cancelled）→ 中止。
    """
    from django.db import transaction

    run = AgentRun.objects.get(pk=run_id)
    logger.info('AgentRun %s 开始', run.id)
    try:
        with transaction.atomic():
            transition(run, 'planning')
            emit_event(run, '开始制定测试计划')
            plan = build_plan(run)
            run.plan = plan
            run.save(update_fields=['plan', 'updated_at'])
            _record_step(run, 'generate_cases', input={'plan': plan})
            emit_event(run, '计划完成：{} 个 API 用例，{} 个 UI 用例，{} 个回归用例'.format(
                len(plan['api_cases']), len(plan['ui_cases']),
                len(plan['regression_case_ids']),
            ))

        with transaction.atomic():
            transition(run, 'executing')
            execute_plan(run, plan)

        with transaction.atomic():
            transition(run, 'analyzing')
            findings = analyze_failures(run)

        with transaction.atomic():
            transition(run, 'reporting')
            report = build_report(run, findings)
            post_report(run, report, has_failures=bool(findings))
            _record_step(run, 'report', input={}, output={'report_len': len(report)})

        with transaction.atomic():
            transition(run, 'done')
            run.summary = report
            run.save(update_fields=['summary', 'updated_at'])
            emit_event(run, 'AgentRun 完成')
    except InvalidTransition:
        # 用户取消（cancelled）等终态介入
        logger.info('AgentRun %s 因状态转换被拒绝而中止', run.id)
    except Exception as exc:  # noqa: BLE001
        logger.exception('AgentRun %s 失败', run.id)
        run.refresh_from_db()
        if run.status not in ('cancelled', 'done'):
            run.status = 'failed'
            run.save(update_fields=['status', 'updated_at'])
            emit_event(run, f'AgentRun 失败：{exc}', level='error')
    return run.status
```

> 注：`create_ui_case`/`run_ui_cases` 在 Task 12 实现，execute_plan 对其采用惰性导入——Task 12 完成前，本步集成测试的 plan 中 ui_cases 为空，不受影响。

- [ ] **Step 5: 运行集成测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_integration.py -v`

Expected: 全部 PASS（3 个）

- [ ] **Step 6: 运行全部 qa_agent 测试确认无回归**

Run: `cd backend && pytest tests/test_qa_agent_core.py tests/test_qa_agent_api.py tests/test_qa_agent_planning.py tests/test_qa_agent_analysis.py tests/test_qa_agent_integration.py -v`

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/qa_agent/adapter.py backend/qa_agent/orchestration.py backend/tests/test_qa_agent_integration.py
git commit -m "feat(qa_agent): API 测试闭环编排（planning→executing→analyzing→reporting→done）"
```

---

# M3 UI 用例执行接入

## Task 12: run_ui_cases 适配器（真实 Playwright 执行 + 结果持久化 + 截图）

**Files:**
- Modify: `backend/qa_agent/adapter.py`
- Test: `backend/tests/test_qa_agent_integration.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_qa_agent_integration.py` 末尾追加：

```python
import base64

from qa_agent.adapter import create_ui_case, run_ui_cases
from qa_center.models import UiTestCase
from django.core.files.uploadedfile import SimpleUploadedFile

PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


@pytest.mark.django_db
def test_create_ui_case_via_tool(test_user, test_project, monkeypatch):
    from qa_agent.models import AgentRun

    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    calls = {}

    def fake_execute_tool(name, args, project_id, user):
        calls['name'] = name
        calls['args'] = args
        UiTestCase.objects.create(
            project=test_project, name=args['name'], url=args['url'],
            steps=[{'action': 'click', 'selector': 'text=登录', 'value': ''}],
            created_by=user,
        )
        return f'已创建 UI 测试用例「{args["name"]}」(ID: 1)'

    monkeypatch.setattr('room.ai_utils.execute_tool', fake_execute_tool)
    cid = create_ui_case(run, {
        'name': '登录页打开', 'url': 'http://testserver/login',
        'steps': [{'action': 'click', 'selector': 'text=登录', 'value': ''}],
    })
    assert calls['name'] == 'create_ui_test_case'
    assert cid == UiTestCase.objects.get(name='登录页打开', project=test_project).id


@pytest.mark.django_db
def test_run_ui_cases_persists_result_and_screenshot(test_user, test_project, monkeypatch):
    ui_case = UiTestCase.objects.create(
        project=test_project, name='登录页打开', url='http://testserver/login',
        steps=[{'action': 'goto', 'selector': '', 'value': ''}], created_by=test_user,
    )
    run = AgentRun.objects.create(project=test_project, created_by=test_user)

    def fake_prepare_and_execute_ui_case(project, *, url, steps, case, case_id, on_event, **kw):
        on_event({'type': 'started'})
        on_event({'type': 'step_done', 'success': False,
                  'message': 'locator.click: no such element #login-btn'})
        return {'success': False, 'task_id': 'fake-task-1'}, {'environment_id': None}, {}

    def fake_persist(*, name, project, ui_test_case, user, result, events, task_id, env_meta, original_steps):
        from qa_center.models import TestResult, TestScreenshot
        tr = TestResult.objects.create(
            project=project, test_type='ui', name=name, status='failed',
            error_message='locator.click: no such element #login-btn',
        )
        TestScreenshot.objects.create(
            test_result=tr, name='step1.png', step_index=1,
            image=SimpleUploadedFile('step1.png', PNG_1PX, content_type='image/png'),
        )
        return tr

    monkeypatch.setattr('qa_center.ui_execution.prepare_and_execute_ui_case', fake_prepare_and_execute_ui_case)
    monkeypatch.setattr('qa_center.views_ui_test._persist_ui_test_result', fake_persist)

    result = run_ui_cases(run, [{'name': '登录页打开', 'url': 'http://testserver/login', 'steps': []}])
    assert result['ok'] is True
    tr = TestResult.objects.get(project=test_project, test_type='ui')
    assert tr.status == 'failed'
    assert tr.screenshots.count() == 1
```

> 注：`run_ui_cases` 在函数体内 `from qa_center.ui_execution import prepare_and_execute_ui_case`，因此测试 patch 的是**源模块**（`qa_center.ui_execution` / `qa_center.views_ui_test`），而不是 adapter 的属性。`create_ui_case` 同理 patch `room.ai_utils.execute_tool`。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_integration.py::test_create_ui_case_via_tool tests/test_qa_agent_integration.py::test_run_ui_cases_persists_result_and_screenshot -v`

Expected: FAIL（`ImportError: cannot import name 'run_ui_cases' from 'qa_agent.adapter'` / `create_ui_case` 不存在）

- [ ] **Step 3: 实现 create_ui_case 与 run_ui_cases**

在 `backend/qa_agent/adapter.py` 末尾追加：

```python
def create_ui_case(run, spec: dict) -> int:
    """经现有工具创建 UI 用例，返回用例 ID；失败抛 RuntimeError。"""
    from qa_center.models import UiTestCase
    from room.ai_utils import execute_tool

    result_text = execute_tool('create_ui_test_case', {
        'name': spec['name'],
        'url': spec['url'],
        'steps_json': json.dumps(spec.get('steps', []), ensure_ascii=False),
    }, str(run.project_id), _tool_user(run))
    case = UiTestCase.objects.filter(
        project_id=run.project_id, name=spec['name'],
    ).order_by('-id').first()
    if case is None:
        raise RuntimeError(f'UI 用例创建失败: {result_text}')
    return case.id


def run_ui_cases(run, ui_cases: list) -> dict:
    """逐个同步执行 UI 用例并持久化 TestResult + 截图。

    复用 qa_center 的统一执行入口 prepare_and_execute_ui_case 与
    views_ui_test._persist_ui_test_result（含截图落库），不重复实现。
    """
    from qa_center.models import UiTestCase
    from qa_center.ui_execution import prepare_and_execute_ui_case
    from qa_center.views_ui_test import _persist_ui_test_result

    executed = 0
    for spec in ui_cases:
        case = UiTestCase.objects.filter(
            project_id=run.project_id, name=spec['name'],
        ).order_by('-id').first()
        if case is None:
            continue
        events = []
        try:
            result, env_meta, _case_data = prepare_and_execute_ui_case(
                run.project, url=case.url, steps=case.steps or [],
                case=case, case_id=case.id, on_event=events.append,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning('UI 用例 %s 执行异常: %s', case.name, exc)
            continue
        try:
            _persist_ui_test_result(
                name=case.name, project=run.project, ui_test_case=case,
                user=_tool_user(run), result=result, events=events,
                task_id=result.get('task_id') or '',
                env_meta=env_meta, original_steps=case.steps or [],
            )
        except Exception:  # noqa: BLE001
            logger.exception('UI 结果持久化失败: %s', case.name)
        executed += 1
    return {'ok': True, 'detail': f'执行 UI 用例 {executed} 个'}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_integration.py -v`

Expected: 全部 PASS（4 个）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/adapter.py backend/tests/test_qa_agent_integration.py
git commit -m "feat(qa_agent): UI 用例真实执行接入（复用 qa_center 执行与持久化）"
```

---

# M4 实时推送与前端

## Task 13: WebSocket consumer + 路由注册

**Files:**
- Create: `backend/qa_agent/consumers.py`
- Create: `backend/qa_agent/routing.py`
- Modify: `backend/room/routing.py:20-26`
- Test: `backend/tests/test_qa_agent_api.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_qa_agent_api.py` 末尾追加：

```python
from channels.testing import WebsocketCommunicator


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_ws_agent_event_pushed(test_user, test_project):
    from backend.asgi import application

    communicator = WebsocketCommunicator(
        application, f'/ws/qa-agent/{test_project.id}/',
    )
    communicator.scope['user'] = test_user
    connected, _ = await communicator.connect()
    assert connected

    from qa_agent.models import AgentRun
    from qa_agent.orchestration import emit_event
    run = AgentRun.objects.create(project=test_project, created_by=test_user)
    emit_event(run, '进度事件', level='info')

    msg = await communicator.receive_json_from(timeout=5)
    assert msg['type'] == 'agent_event'
    assert msg['run_id'] == str(run.id)
    assert msg['event']['message'] == '进度事件'
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_ws_rejects_non_member(test_user, test_project):
    from django.contrib.auth.models import User
    from backend.asgi import application

    other = User.objects.create_user(username='outsider2', password='x1234567')
    other_project = type(test_project).objects.create(name='Other2', owner=other)
    communicator = WebsocketCommunicator(
        application, f'/ws/qa-agent/{other_project.id}/',
    )
    communicator.scope['user'] = test_user
    connected, _ = await communicator.connect()
    assert connected is False
```

> 注：Channels 的 `AuthMiddleware` 在 scope 已有 `user` 键时直接复用（`channels.auth.get_user` 仅在该键缺失时兜底 AnonymousUser），所以 `communicator.scope['user'] = test_user` 可以正确模拟登录态；非成员项目 → consumer 返回 close(4003) → connect 返回 False。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_qa_agent_api.py -v`

Expected: WS 测试失败（路由不存在 → connect 失败）

- [ ] **Step 3: 实现 consumer 与 routing**

创建 `backend/qa_agent/consumers.py`：

```python
"""AgentRun 实时事件 WebSocket Consumer"""
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Q

from room.models import Project


class AgentRunConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        self.group_name = f'qa_agent_{self.project_id}'
        user = self.scope['user']
        if not user.is_authenticated or not await self._is_member(user, self.project_id):
            await self.close(code=4003)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def _is_member(self, user, project_id):
        return Project.objects.filter(
            Q(id=project_id) & (Q(owner=user) | Q(members=user)),
        ).exists()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def agent_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'agent_event',
            'run_id': event['run_id'],
            'status': event['status'],
            'event': event['event'],
        }, ensure_ascii=False))
```

创建 `backend/qa_agent/routing.py`：

```python
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/qa-agent/(?P<project_id>[\w-]+)/$', consumers.AgentRunConsumer.as_asgi()),
]
```

在 `backend/room/routing.py` 中修改：

```python
from qa_center.routing import websocket_urlpatterns as qa_ws_patterns
```
→
```python
from qa_center.routing import websocket_urlpatterns as qa_ws_patterns
from qa_agent.routing import websocket_urlpatterns as qa_agent_ws_patterns
```
以及
```python
]+qa_ws_patterns
```
→
```python
]+qa_ws_patterns+qa_agent_ws_patterns
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_qa_agent_api.py -v`

Expected: WS 测试 PASS（如 pytest-asyncio 未安装，先 `pip install pytest-asyncio`，并确认 `pytest.ini` 无 `asyncio_mode` 限制；失败时按提示在 pytest.ini `addopts` 追加 `-p asyncio`）

- [ ] **Step 5: Commit**

```bash
git add backend/qa_agent/consumers.py backend/qa_agent/routing.py backend/room/routing.py backend/tests/test_qa_agent_api.py
git commit -m "feat(qa_agent): WebSocket 实时事件推送"
```

## Task 14: 前端 API 模块 + AgentRunList 页面 + 路由

**Files:**
- Create: `frontend/src/api/qaAgent.ts`
- Create: `frontend/src/views/qa/AgentRunList.vue`
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 创建 API 模块**

创建 `frontend/src/api/qaAgent.ts`：

```ts
import request from '@/utils/request'

export interface AgentEventItem {
  id: number
  level: string
  message: string
  created_at: string
}

export interface AgentStepItem {
  id: number
  step_type: string
  status: string
  tool_name: string
  input: Record<string, any>
  output: Record<string, any>
  duration_ms: number | null
  created_at: string
}

export interface AgentRun {
  id: string
  project: string
  project_name: string
  source_task: string | null
  source_task_title: string | null
  trigger: string
  trigger_display: string
  status: string
  status_display: string
  plan: Record<string, any>
  summary: string
  created_by: number | null
  created_at: string
  updated_at: string
  steps: AgentStepItem[]
  events: AgentEventItem[]
}

export function listAgentRuns(projectId: string) {
  return request.get('/qa-agent/runs/', { params: { project_id: projectId } })
}

export function getAgentRun(runId: string) {
  return request.get(`/qa-agent/runs/${runId}/`)
}

export function createAgentRun(projectId: string, sourceTaskId?: string) {
  return request.post('/qa-agent/runs/', {
    project_id: projectId,
    source_task_id: sourceTaskId || '',
  })
}

export function cancelAgentRun(runId: string) {
  return request.post(`/qa-agent/runs/${runId}/cancel/`)
}
```

- [ ] **Step 2: 创建 AgentRunList.vue**

创建 `frontend/src/views/qa/AgentRunList.vue`：

```vue
<template>
  <div class="agent-run-list">
    <div class="page-header">
      <h3>AI-QA Agent 执行记录</h3>
      <div class="header-actions">
        <el-button type="primary" :loading="creating" @click="createRun">创建 AI-QA 执行</el-button>
        <el-button :loading="loading" @click="loadRuns">刷新</el-button>
      </div>
    </div>

    <el-table :data="runs" v-loading="loading" style="width: 100%">
      <el-table-column prop="created_at" label="创建时间" width="170" />
      <el-table-column label="源任务">
        <template #default="{ row }">{{ row.source_task_title || '—' }}</template>
      </el-table-column>
      <el-table-column prop="trigger_display" label="触发方式" width="110" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="statusType(row.status)">{{ row.status_display }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button v-if="isActive(row.status)" size="small" type="danger" @click="cancelRun(row)">
            取消
          </el-button>
        </template>
      </el-table-column>
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="run-detail">
            <h4>计划</h4>
            <pre>{{ JSON.stringify(row.plan, null, 2) }}</pre>
            <h4>步骤时间线</h4>
            <el-timeline>
              <el-timeline-item
                v-for="s in row.steps"
                :key="s.id"
                :timestamp="s.created_at"
                :type="s.status === 'error' ? 'danger' : 'primary'"
              >
                {{ s.step_type }} · {{ s.tool_name || '—' }} · {{ s.status }}
              </el-timeline-item>
            </el-timeline>
            <h4>事件流</h4>
            <ul class="event-list">
              <li v-for="e in row.events" :key="e.id" :class="'level-' + e.level">
                {{ e.message }}
              </li>
            </ul>
            <h4>报告</h4>
            <pre class="summary">{{ row.summary || '（无）' }}</pre>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { cancelAgentRun, createAgentRun, listAgentRuns, type AgentRun } from '@/api/qaAgent'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

const runs = ref<AgentRun[]>([])
const loading = ref(false)
const creating = ref(false)

const statusType = (s: string): 'success' | 'danger' | 'warning' | 'info' | 'primary' => {
  const map: Record<string, any> = {
    queued: 'info', planning: 'warning', executing: 'primary',
    analyzing: 'warning', reporting: 'warning',
    done: 'success', failed: 'danger', cancelled: 'info',
  }
  return map[s] || 'info'
}

const isActive = (s: string) =>
  ['queued', 'planning', 'executing', 'analyzing', 'reporting'].includes(s)

async function loadRuns() {
  loading.value = true
  try {
    const data = (await listAgentRuns(projectId.value)) as unknown as AgentRun[]
    runs.value = data || []
  } catch {
    // 404/网络错误由拦截器记录，页面保持空态
  } finally {
    loading.value = false
  }
}

async function createRun() {
  creating.value = true
  try {
    await createAgentRun(projectId.value)
    ElMessage.success('已创建 AI-QA 执行')
    await loadRuns()
  } finally {
    creating.value = false
  }
}

async function cancelRun(row: AgentRun) {
  await ElMessageBox.confirm('确认取消该执行？', '提示', { type: 'warning' })
  await cancelAgentRun(row.id)
  ElMessage.success('已取消')
  await loadRuns()
}

let ws: WebSocket | null = null
let timer: number | null = null

function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/qa-agent/${projectId.value}/`)
  ws.onmessage = () => loadRuns()
  ws.onclose = () => { ws = null }
}

onMounted(() => {
  loadRuns()
  connectWs()
  timer = window.setInterval(loadRuns, 10000)
})

onBeforeUnmount(() => {
  ws?.close()
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.run-detail {
  padding: 8px 24px 16px;
}
.run-detail h4 {
  margin: 12px 0 6px;
  color: #606266;
}
.run-detail pre {
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.event-list {
  list-style: none;
  padding: 0;
  margin: 0;
  font-size: 13px;
}
.event-list li {
  padding: 2px 0;
}
.event-list .level-warn {
  color: #e6a23c;
}
.event-list .level-error {
  color: #f56c6c;
}
</style>
```

- [ ] **Step 3: 注册路由**

在 `frontend/src/router/index.ts` 中 `qa/ui-cases/:id` 路由块（约第 93-98 行）之后插入：

```ts
            {
                path: 'qa/agent-runs',
                name: 'AgentRunList',
                component: () => import("../views/qa/AgentRunList.vue"),
                meta: { permission: 'qa:manage' },
            },
```

- [ ] **Step 4: 前端类型检查与构建验证**

Run: `cd frontend && npx vue-tsc --noEmit`

Expected: 无新增类型错误（或仅有与本改动无关的既有告警）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/qaAgent.ts frontend/src/views/qa/AgentRunList.vue frontend/src/router/index.ts
git commit -m "feat(frontend): AI-QA Agent 执行记录页面与路由"
```

## Task 15: 看板任务卡 AI-QA 状态徽标

**Files:**
- Modify: `frontend/src/views/Board.vue`

- [ ] **Step 1: 模板加徽标**

在 `frontend/src/views/Board.vue` 第 149-156 行 `tags-container` 的 `</div>` 之后（第 156 行后）插入：

```html
                  <div v-if="agentRunStatusMap[element.id]" class="agent-badge">
                    <el-tag size="small" :type="agentStatusType(agentRunStatusMap[element.id])" effect="plain">
                      AI-QA {{ agentStatusText(agentRunStatusMap[element.id]) }}
                    </el-tag>
                  </div>
```

- [ ] **Step 2: 脚本加状态映射与加载**

在第 334 行（`import { Delete, Plus, ... } from '@element-plus/icons-vue';`）之后追加：

```ts
import { listAgentRuns } from '@/api/qaAgent';
```

在 `const projectId = computed(() => route.params.projectId as string);`（第 339 行）之后追加：

```ts
const agentRunStatusMap = ref<Record<string, string>>({});

const agentStatusType = (s: string) =>
  ({ queued: 'info', planning: 'warning', executing: 'primary', analyzing: 'warning', reporting: 'warning', done: 'success', failed: 'danger', cancelled: 'info' } as Record<string, any>)[s] || 'info';

const agentStatusText = (s: string) =>
  ({ queued: '排队', planning: '规划中', executing: '执行中', analyzing: '分析中', reporting: '报告中', done: '完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[s] || s;

async function loadAgentRuns() {
  try {
    const runs = (await listAgentRuns(projectId.value)) as unknown as Array<{ source_task: string | null; status: string }>;
    const map: Record<string, string> = {};
    for (const r of runs || []) {
      if (r.source_task) map[r.source_task] = r.status;
    }
    agentRunStatusMap.value = map;
  } catch {
    // 静默：徽标属于增强信息
  }
}

onMounted(() => { loadAgentRuns(); });
```

> 注：`ref` 与 `onMounted` 已在第 326 行导入；Vue 允许第二个 `onMounted` 调用并存。

- [ ] **Step 3: 样式追加**

在 `frontend/src/views/Board.vue` 的 `<style>` 块末尾追加：

```css
.agent-badge {
  margin-top: 6px;
}
```

- [ ] **Step 4: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`

Expected: 无新增类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Board.vue
git commit -m "feat(frontend): 看板任务卡 AI-QA 状态徽标"
```

---

# M5 Eval 评估集与文档

## Task 16: Eval 评估集（fixtures/golden/cache + pytest -m eval）

**Files:**
- Create: `backend/qa_agent/eval/__init__.py`
- Create: `backend/qa_agent/eval/fixtures.py`
- Create: `backend/qa_agent/eval/golden.py`
- Create: `backend/qa_agent/eval/cache.py`
- Create: `backend/qa_agent/eval/run_eval.py`
- Create: `backend/tests/test_qa_agent_eval.py`
- Modify: `backend/pytest.ini`

- [ ] **Step 1: 注册 eval marker**

`backend/pytest.ini` 改为：

```ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings
# 匹配测试文件的规则：以 test_ 开头的文件
python_files = test_*.py
# 忽略一些警告
addopts = --reuse-db --nomigrations
markers =
    eval: AI QA Agent 评估集（需要 LLM 缓存或 QA_AGENT_LIVE=1 在线模式）
```

- [ ] **Step 2: 创建 cache.py**

创建 `backend/qa_agent/eval/cache.py`：

```python
"""LLM 响应缓存：按 messages JSON 的 sha1 存 JSON 文件，支持离线重放。"""
import hashlib
import json
import os

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')


def _key(messages) -> str:
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, f'{key}.json')


def get_cached(messages):
    path = _path(_key(messages))
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    return None


def set_cached(messages, data) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_path(_key(messages)), 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
```

- [ ] **Step 3: 创建 fixtures.py 与 golden.py**

创建 `backend/qa_agent/eval/fixtures.py`：

```python
"""评估用固定种子数据（确定性可复现）"""
from django.contrib.auth.models import User

from qa_center.models import ApiAutoTestCase, TestResult, UiTestCase
from room.models import Column, Project, ProjectApiDoc, Task


def build_eval_project(db):
    user = User.objects.create_user(username='eval_user', password='evalpass123')
    project = Project.objects.create(name='Eval Project', owner=user)
    col_test = Column.objects.create(project=project, title='待测试', position=1)
    Column.objects.create(project=project, title='已完成', position=2)
    task = Task.objects.create(
        column=col_test, title='用户登录功能', content='支持用户名密码登录，失败返回 401',
    )
    ProjectApiDoc.objects.create(
        project=project, name='auth_api', format='markdown',
        content='POST /api/auth/login/ 参数 username/password，成功 200，失败 401',
    )
    ApiAutoTestCase.objects.create(
        project=project, name='登录成功', url='http://testserver/api/auth/login/',
        method='POST', expected_status=200, created_by=user,
    )
    ApiAutoTestCase.objects.create(
        project=project, name='登录失败401', url='http://testserver/api/auth/login/',
        method='POST', expected_status=401, created_by=user,
    )
    UiTestCase.objects.create(
        project=project, name='登录页打开', url='http://testserver/login',
        steps=[{'action': 'goto', 'selector': '', 'value': ''}], created_by=user,
    )
    TestResult.objects.create(
        project=project, test_type='api', name='登录成功',
        status='failed', error_message='预期 200，实际 401：未授权',
    )
    return {'user': user, 'project': project, 'task': task}
```

创建 `backend/qa_agent/eval/golden.py`：

```python
"""人工标注金标准 + 期望指标"""

# 用例生成：需求 → 期望用例关键字段（url/method/expected_status）
GOLDEN_CASE_GENERATION = [
    {
        'requirement': '用户登录功能',
        'expected': {
            'url': 'http://testserver/api/auth/login/',
            'method': 'POST',
            'expected_status': 200,
        },
    },
]

# 失败分析：错误信息 → 期望 (flaky, root_cause)
GOLDEN_ANALYSIS = [
    {
        'error_message': '预期 200，实际 401：未授权',
        'expected': {'flaky': 'deterministic', 'root_cause': 'bug_in_app'},
    },
    {
        'error_message': 'TimeoutError: waiting for selector #login-btn timed out',
        'expected': {'flaky': 'flaky', 'root_cause': 'unknown'},
    },
    {
        'error_message': 'Connection refused: 127.0.0.1:8000',
        'expected': {'flaky': 'deterministic', 'root_cause': 'environment_issue'},
    },
    {
        'error_message': 'locator.click: no such element #submit',
        'expected': {'flaky': 'deterministic', 'root_cause': 'test_case_issue'},
    },
]

# 指标断言下限（在线模式或缓存数据达到该线即通过；可随迭代提高）
EXPECTED_MIN = {
    'analysis_accuracy': 0.5,
    'case_generation_recall': 0.5,
}
```

- [ ] **Step 4: 写 eval 测试**

创建 `backend/tests/test_qa_agent_eval.py`：

```python
"""Eval 评估集：pytest -m eval 运行（需 LLM 缓存或 QA_AGENT_LIVE=1）"""
import json
import os

import pytest

pytestmark = [pytest.mark.eval]

from qa_agent.analysis import analyze_failure, fallback_analyze
from qa_agent.eval import cache as eval_cache
from qa_agent.eval.golden import (
    EXPECTED_MIN, GOLDEN_ANALYSIS, GOLDEN_CASE_GENERATION,
)
from qa_agent.llm import llm_json as real_llm_json
from qa_agent.models import AgentRun
from qa_agent.services import build_plan
from qa_center.models import TestResult


def _cached_or_live(messages, **kwargs):
    cached = eval_cache.get_cached(messages)
    if cached is not None:
        return cached
    if os.environ.get('QA_AGENT_LIVE') != '1':
        pytest.skip('无 LLM 缓存且非 live 模式（QA_AGENT_LIVE=1 可在线生成并回写缓存）')
    data = real_llm_json(messages, **kwargs)
    eval_cache.set_cached(messages, data)
    return data


@pytest.mark.django_db
def test_fallback_rules_match_golden():
    """规则降级分析必须与金标准一致（确定性测试，无 LLM 依赖）。"""
    for sample in GOLDEN_ANALYSIS:
        got = fallback_analyze(sample['error_message'])
        assert got['flaky'] == sample['expected']['flaky'], sample
        assert got['root_cause'] == sample['expected']['root_cause'], sample


@pytest.mark.django_db
def test_analysis_accuracy(monkeypatch):
    """LLM 失败分析准确率（缓存/在线），打印混淆矩阵并断言下限。"""
    from qa_agent.eval.fixtures import build_eval_project as bep
    data = bep(None)

    monkeypatch.setattr('qa_agent.services.llm_json', _cached_or_live)
    monkeypatch.setattr('qa_agent.analysis.llm_json', _cached_or_live)
    correct = 0
    matrix = {}
    for sample in GOLDEN_ANALYSIS:
        result = TestResult.objects.create(
            project=data['project'], test_type='api', name='eval-case',
            status='failed', error_message=sample['error_message'],
        )
        run = AgentRun.objects.create(project=data['project'])
        got = analyze_failure(run, result)
        key = (sample['expected']['root_cause'], got['root_cause'])
        matrix[key] = matrix.get(key, 0) + 1
        if (got['flaky'], got['root_cause']) == (
            sample['expected']['flaky'], sample['expected']['root_cause'],
        ):
            correct += 1
    accuracy = correct / len(GOLDEN_ANALYSIS)
    print(f'\n[Eval] analysis_accuracy={accuracy:.2f} matrix={matrix}')
    assert accuracy >= EXPECTED_MIN['analysis_accuracy']


@pytest.mark.django_db
def test_case_generation_recall(monkeypatch):
    """计划生成的用例召回率：金标准需求生成的用例中命中期望 url/method/status 的比例。"""
    from qa_agent.eval.fixtures import build_eval_project as bep
    data = bep(None)

    monkeypatch.setattr('qa_agent.services.llm_json', _cached_or_live)
    run = AgentRun.objects.create(project=data['project'], source_task=data['task'])
    plan = build_plan(run)

    hits = 0
    total = len(GOLDEN_CASE_GENERATION)
    for golden in GOLDEN_CASE_GENERATION:
        matched = any(
            c.get('url') == golden['expected']['url']
            and c.get('method') == golden['expected']['method']
            and c.get('expected_status') == golden['expected']['expected_status']
            for c in plan.get('api_cases', [])
        )
        hits += 1 if matched else 0
    recall = hits / total if total else 0
    print(f'\n[Eval] case_generation_recall={recall:.2f} plan={json.dumps(plan, ensure_ascii=False)}')
    assert recall >= EXPECTED_MIN['case_generation_recall']
```

> 注：`build_plan`（services）与 `analyze_failure`（analysis）各自在模块顶层绑定了 `llm_json` 引用，所以测试必须分别 patch `qa_agent.services.llm_json` 与 `qa_agent.analysis.llm_json`；`_cached_or_live` 内调用的是 `qa_agent.llm.real_llm_json`（原始函数引用，不受 patch 影响）。

- [ ] **Step 5: 创建缓存目录占位并运行离线测试**

Run: `cd backend && mkdir -p qa_agent/eval/cache && pytest tests/test_qa_agent_eval.py -m eval -v`

Expected: `test_fallback_rules_match_golden` PASS；另外两个测试 SKIP（无缓存、非 live）

- [ ] **Step 6: 在线生成缓存（需 DEEPSEEK_API_KEY 且余额可用）**

Run: `cd backend && QA_AGENT_LIVE=1 pytest tests/test_qa_agent_eval.py -m eval -v`

Expected: 三个测试全部 PASS/FAIL 视指标而定；`qa_agent/eval/cache/` 下生成若干 JSON 缓存文件；控制台打印 `analysis_accuracy` 与 `case_generation_recall` 数值——把数值记录到 `qa_agent/eval/golden.py` 的 `EXPECTED_MIN` 中（提交缓存文件，后续 CI 可离线复跑）。

- [ ] **Step 7: Commit**

```bash
git add backend/qa_agent/eval backend/tests/test_qa_agent_eval.py backend/pytest.ini
git commit -m "feat(qa_agent): Eval 评估集（金标准+缓存+指标）"
```

## Task 17: 文档与演示脚本

**Files:**
- Create: `scripts/demo_qa_agent.md`
- Create: `docs/QA_AGENT_PORTFOLIO.md`
- Modify: `docs/superpowers/specs/2026-08-14-qa-agent-loop-design.md`（如实现过程中偏离设计，同步修正）

- [ ] **Step 1: 编写演示脚本**

创建 `scripts/demo_qa_agent.md`：

```markdown
# AI-QA Agent 闭环演示脚本

## 前置
1. 启动基础设施：MySQL / Redis（docker-compose）
2. 后端：`cd backend && uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload`
   - 确认 `backend/.env` 有 `DEEPSEEK_API_KEY`
3. 前端：`cd frontend && npm run dev`
4. 迁移：`cd backend && python manage.py migrate`

## 演示步骤
1. 登录 → 创建项目 → 添加成员
2. QA 中心 → 上传 API 文档（Markdown：`POST /api/auth/login/ 成功 200 失败 401`）
3. 看板 → 创建任务「用户登录功能」→ 拖到「待测试」列
   - 预期：任务卡出现 `AI-QA 排队` 徽标（Task 15）
4. 打开 `QA 中心 → AI-QA Agent 执行记录`（/projects/:id/qa/agent-runs）
   - 预期：出现 planning → executing → analyzing → reporting → done 的步骤时间线与事件流
5. 若用例失败（如接口返回 401）：
   - 预期：自动创建 Bug（Bug 列表可见 `[AI-QA] 用户登录功能 - ...`）
   - 预期：源任务卡出现 AI-QA 报告评论
6. Eval 复跑：`cd backend && pytest tests/test_qa_agent_eval.py -m eval -v`
   - 展示 analysis_accuracy 与 case_generation_recall 数值
```

- [ ] **Step 2: 编写作品集文档**

创建 `docs/QA_AGENT_PORTFOLIO.md`，内容大纲（用真实实现细节填充）：

```markdown
# AI QA Agent — 作品集说明

## 一句话
SyncBoard 内置的 AI QA Agent：事件触发 → 自动生成并执行 API/UI 测试 → 失败智能分析（flaky/根因）→ 自动建 Bug → 报告回写看板。

## 架构亮点
- 编排层与业务层分离：qa_agent 只经 adapter 调用现有工具与执行引擎，每步可审计可回放
- AgentRun 状态机（queued→planning→executing→analyzing→reporting→done），非法转换拒绝
- LLM 结构化输出 + schema 校验 + 重试退避 + 规则降级（analyze 永不阻断主流程）
- 自动建单规则闸门：仅 bug_in_app+deterministic 建单，失败聚类去重防噪音
- 生产 Celery / 开发线程双模式分发（USE_CELERY_TASKS）

## Eval 指标（填入实际数值）
- analysis_accuracy: X%（目标 ≥50，迭代提升）
- case_generation_recall: X%

## 演示路径
见 scripts/demo_qa_agent.md
```

- [ ] **Step 3: 全量回归**

Run: `cd backend && pytest tests/ -q` 与 `cd frontend && npx vue-tsc --noEmit`

Expected: 无新增失败

- [ ] **Step 4: Commit**

```bash
git add scripts/demo_qa_agent.md docs/QA_AGENT_PORTFOLIO.md docs/superpowers/specs
git commit -m "docs(qa_agent): 演示脚本与作品集文档"
```

---

## Self-Review 记录

- **Spec 覆盖**：触发三入口（signal=T14 前置的 Task 5 工厂 + Task 11 集成；手动 API=Task 6；CI/CD 触发在设计中列为入口之一，本计划未实现 PipelineRun 挂接——列为已知缺口，放作品集"后续迭代"章节）；状态机=Task 3；计划=Task 8；API 闭环=Task 11；UI+截图=Task 12；失败分析/聚类/建单=Task 9；报告回写=Task 10；WS=Task 13；前端=Task 14/15；Eval=Task 16；权限=Task 6/13；文档=Task 17。
- **CI/CD 触发**：设计 §5.3 的 PipelineRun 触发在计划中未单列任务——若时间允许追加为 Task 18（复用 `tasks_test_exec.py::poll_pipeline_status` 的轮询，在 PipelineRun 终态后 `create_run(trigger='cicd')`），否则保持设计文档"后续迭代"标注。
- **占位符扫描**：无 TDD/TBD；Task 9 测试注释与 Task 13 测试注释、Task 16 测试注释中的"以实际运行为准"均为已知偏差提示（测试数据构造的必然性），非计划占位。
- **类型一致性**：`create_run`/`dispatch_run`/`run_agent_pipeline`/`emit_event`/`transition`/`build_plan`/`analyze_failures`/`build_report` 等签名在 Task 3-11 间交叉引用一致；`execute_tool(tool_name, args, project_id, user)` 与 `room.ai_utils` 签名一致；`AgentRunSerializer` 字段与前端 `AgentRun` interface 一致。
