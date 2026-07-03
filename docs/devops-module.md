# DevOps 测试平台模块开发文档

> **项目**: SyncBoard  
> **模块路径**: `backend/qa_center/` + `frontend/src/`  
> **API 前缀**: `/api/qa/devops/`  
> **前端路由**: `/projects/:projectId/qa/devops`  
> **最后更新**: 2026-07-02

---

## 目录

1. [模块概述](#1-模块概述)
2. [系统架构](#2-系统架构)
3. [数据模型](#3-数据模型)
4. [API 接口设计](#4-api-接口设计)
5. [后端核心实现](#5-后端核心实现)
6. [安全机制](#6-安全机制)
7. [配置与特性开关](#7-配置与特性开关)
8. [前端架构](#8-前端架构)
9. [数据流与执行流程](#9-数据流与执行流程)
10. [文件清单](#10-文件清单)
11. [扩展指南](#11-扩展指南)

---

## 1. 模块概述

DevOps 测试平台是 SyncBoard 质量保障中心（QA Center）的核心子模块，提供以下关键能力：

| 能力 | 说明 |
|------|------|
| **仪表板统计** | 测试用例总数、通过率、每日趋势图表、按类型分布 |
| **CI/CD 集成** | 对接 Jenkins / GitLab CI / GitHub Actions，支持 Webhook 回调 |
| **测试任务管理** | 创建、编辑、执行、删除测试任务，支持 API/UI/性能/回归四种类型 |
| **Pipeline 流水线** | 管理 Pipeline 运行记录，支持手动触发和外部 CI 回调 |
| **质量报告** | 从测试覆盖、通过率、性能、Bug 密度、部署成功率五个维度评估项目质量 |
| **快速测试** | 无需创建持久任务即可临时执行测试 |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3)                     │
│  DevOpsPlatform.vue  TestTaskDetail.vue  PipelineTimeline│
│  CiCdConfigDialog    TestTaskDialog     BatchRunDialog   │
├─────────────────────────────────────────────────────────┤
│                  API Layer (axios)                       │
│  frontend/src/api/devops.ts                              │
├─────────────────────────────────────────────────────────┤
│              Backend REST API (DRF)                      │
│  urls.py  →  12 个视图类 (views_devops.py)               │
├─────────────────────────────────────────────────────────┤
│              Business Logic Layer                        │
│  ┌───────────┬──────────────┬──────────────┐             │
│  │ Executor  │ Pipeline     │ Webhook      │             │
│  │ (thread/  │ Client       │ Security     │             │
│  │  celery)  │ (Jenkins/    │ (HMAC/RL/    │             │
│  │           │  GitLab/Mock)│  Dedup)      │             │
│  └───────────┴──────────────┴──────────────┘             │
├─────────────────────────────────────────────────────────┤
│                   Data Layer                             │
│  Django ORM → PostgreSQL                                 │
│  Models: TestTask, CiCdConfig, PipelineRun, TestResult   │
├─────────────────────────────────────────────────────────┤
│              Notification & WS                           │
│  Django Channels (WebSocket) + Notification DB           │
└─────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **项目隔离（Project Scoping）**: 所有 DevOps 资源（任务、配置、运行记录）均绑定到 `Project`，通过 `project_access_q()` 和 `ensure_project_id_access()` 实现权限控制。
2. **双模式执行**: 支持 Celery 异步任务执行（生产环境）和 daemon 线程执行（开发环境）。
3. **Mock CI 支持**: 开发/测试阶段可用 Mock CI 客户端模拟 Pipeline，通过 `USE_REAL_CI` 开关控制。
4. **Fail-Closed 安全**: Webhook 端点公开暴露，必须在应用层实现 HMAC 签名验证、Token 认证、去重和频率限制。

---

## 3. 数据模型

### 3.1 TestTask（测试任务）

**表名**: `qa_test_tasks`

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | CharField(200) | 任务名称 |
| `description` | TextField | 任务描述 |
| `test_type` | CharField(20) | 测试类型: api / ui / performance / regression |
| `trigger_type` | CharField(20) | 触发方式: manual / scheduled / webhook |
| `cron_expression` | CharField(100) | 定时 Cron 表达式 |
| `webhook_url` | CharField(500) | Webhook 回调 URL |
| `test_config` | JSONField | 测试配置（含 api_cases、ui_cases、environment、parallel） |
| `status` | CharField(20) | 当前状态: idle / running / completed / failed |
| `execution_count` | IntegerField | 累计执行次数 |
| `last_executed` | DateTimeField | 最后执行时间 |
| `notify_on_success` | BooleanField | 成功时是否通知 |
| `notify_on_failure` | BooleanField | 失败时是否通知 |
| `notification_channels` | JSONField | 通知渠道列表 |
| `is_active` | BooleanField | 是否启用 |
| `created_by` | FK → User | 创建者 |
| `last_result` | FK → TestResult | 最近一次执行结果 |
| `project` | FK → Project | 所属项目 |

**test_config JSON 示例**:
```json
{
  "api_cases": [1, 2, 3],
  "ui_cases": [4, 5],
  "environment": "staging",
  "parallel": true
}
```

### 3.2 CiCdConfig（CI/CD 集成配置）

**表名**: `qa_cicd_config`

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | CharField(255) | 配置名称 |
| `ci_type` | CharField(20) | CI 类型: jenkins / gitlab / github |
| `webhook_url` | URLField | Webhook 回调地址 |
| `api_token` | CharField(255) | API Token（用于 Webhook 认证） |
| `ci_url` | URLField | CI Server URL |
| `ci_token` | CharField(255) | CI API Token（用于调用 CI API） |
| `ci_project` | CharField(255) | CI 项目/仓库名 |
| `ci_job_name` | CharField(255) | CI Job/Pipeline 名称 |
| `verify_ssl` | BooleanField | 是否验证 SSL 证书 |
| `branch` | CharField(100) | 监听分支（默认 main） |
| `auto_trigger` | BooleanField | 是否自动触发 |
| `test_suite_ids` | JSONField | 关联测试套件 ID 列表 |
| `headers` | JSONField | 自定义请求头 |
| `is_active` | BooleanField | 是否启用（软删除标记） |
| `created_by` | FK → User | 创建者 |
| `project` | FK → Project | 所属项目 |

### 3.3 PipelineRun（Pipeline 运行记录）

**表名**: `qa_pipeline_run`

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | CharField(20) | 状态: pending / queued / running / passed / failed / cancelled / skipped |
| `commit_sha` | CharField(40) | 提交 SHA |
| `branch` | CharField(100) | 分支名 |
| `ci_type` | CharField(20) | CI 类型 |
| `external_queue_id` | CharField(255) | 外部队列 ID |
| `external_run_id` | CharField(255) | 外部运行 ID（用于去重） |
| `external_url` | URLField | 外部 CI URL |
| `error_message` | TextField | 错误信息 |
| `is_mock` | BooleanField | 是否为 Mock 模拟 |
| `jobs_summary` | JSONField | Job 执行摘要 |
| `log_output` | TextField | 日志输出 |
| `test_results_summary` | JSONField | 测试结果摘要 |
| `started_at` / `completed_at` | DateTimeField | 开始/完成时间 |
| `cicd_config` | FK → CiCdConfig | 关联的 CI/CD 配置 |
| `project` | FK → Project | 所属项目 |

**唯一约束**: `(cicd_config, external_run_id)` — 防止同一次外部 Pipeline 重复记录。

### 3.4 TestResult（测试结果，共享模型）

**表名**: `qa_test_results`

该模型被整个 QA Center 共享使用。DevOps 模块通过 `source='devops'` 区分其产生的记录。

| 关键字段 | 说明 |
|---------|------|
| `test_type` | 测试类型: api / ui / performance / regression |
| `status` | 状态: passed / failed / error / running / pending |
| `source` | 来源: devops / single |
| `test_params` | 测试配置快照（JSON） |
| `test_log` | 详细执行日志（JSON） |
| `actual_result` | 结果摘要文本 |
| `duration_ms` | 执行时长（毫秒） |
| `project` | 所属项目 |

---

## 4. API 接口设计

所有接口前缀为 `/api/qa/devops/`。除 Webhook 回调外，均需要 DRF Session 认证。

### 4.1 仪表板统计

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/stats/` | 获取仪表板统计数据 |

**查询参数**:
- `days` (int, 默认 7): 统计天数
- `project_id` (str): 项目过滤

**响应结构**:
```json
{
  "overview": {
    "total_cases": 100, "api_cases": 60, "ui_cases": 40,
    "total_executions": 500, "today_executions": 12,
    "pass_rate": 95.5, "avg_response_time": 234.5
  },
  "status_count": { "passed": 480, "failed": 15, "error": 5, "running": 0 },
  "by_type": { "api": 300, "ui": 150, "performance": 40, "regression": 10 },
  "daily_trend": [
    { "date": "2026-06-26", "total": 70, "passed": 65, "failed": 4, "error": 1 }
  ]
}
```

### 4.2 最近执行记录

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/recent-executions/` | 获取最近执行记录 |

**查询参数**: `limit` (默认 10), `test_type`, `project_id`

### 4.3 CI/CD 配置管理

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/cicd-config/` | 获取配置列表（仅活跃） |
| POST | `/cicd-config/` | 创建新配置 |
| GET | `/cicd-config/{id}/` | 获取单个配置详情 |
| PUT | `/cicd-config/{id}/` | 更新配置 |
| DELETE | `/cicd-config/{id}/` | 软删除（设置 is_active=False） |
| POST | `/cicd-config/{id}/trigger/` | 手动触发 Pipeline |
| POST | `/cicd-config/{id}/webhook/` | 外部 CI Webhook 回调（无需认证） |

### 4.4 测试任务管理

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/tasks/` | 获取任务列表（支持 type/status 过滤） |
| POST | `/tasks/` | 创建任务 |
| GET | `/tasks/{id}/` | 获取任务详情 |
| PUT | `/tasks/{id}/` | 更新任务（运行中禁止修改） |
| DELETE | `/tasks/{id}/` | 删除任务（运行中禁止删除） |
| POST | `/tasks/{id}/execute/` | 执行测试任务 |
| GET | `/tasks/{id}/status/` | 获取当前执行状态 |
| GET | `/tasks/{id}/history/` | 获取执行历史（最近 20 条） |

**任务执行请求 (POST /tasks/{id}/execute/)**:

无需请求体。后端会自动读取任务关联的 `test_config` 中的 `api_cases` 和 `ui_cases`。

**任务执行响应**:
```json
{
  "message": "测试任务已启动",
  "execution_id": 42,
  "task": { /* TestTask 序列化数据 */ },
  "runtime_mode": { "mode": "thread", "is_mock": false }
}
```

### 4.5 快速测试

| 方法 | URL | 说明 |
|------|-----|------|
| POST | `/quick-test/` | 执行临时快速测试 |

**请求体**:
```json
{ "type": "api", "test_cases": [1, 2, 3] }
```

### 4.6 Pipeline 运行记录

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/pipeline-runs/` | 获取 Pipeline 运行列表 |
| GET | `/pipeline-runs/{id}/` | 获取单条 Pipeline 详情 |

### 4.7 项目质量报告

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/quality-report/` | 获取项目质量报告 |

**评分维度**（每维度满分 20 分）：

| 维度 | 评分规则 |
|------|---------|
| 测试覆盖率 | 关联了测试用例的任务数 / 总任务数 × 20 |
| 测试通过率 | 最近 10 次测试结果的通过率 × 20 |
| 性能指标 | P95 < 500ms → 20分; < 1000ms → 15分; < 2000ms → 10分; 其他 → 5分 |
| Bug 密度 | Bug数/任务数 < 10% → 20分; < 20% → 15分; < 30% → 10分; 其他 → 5分 |
| 部署成功率 | 最近 10 次真实 Pipeline 的通过率 × 20 |

---

## 5. 后端核心实现

### 5.1 视图层 (views_devops.py)

共 12 个视图类，位于 `backend/qa_center/views_devops.py`（约 1232 行）：

| 视图类 | 行号 | 功能 |
|--------|------|------|
| `DashboardStatsView` | 201 | 仪表板统计 |
| `RecentExecutionsView` | 295 | 最近执行记录 |
| `CiCdIntegrationView` | 322 | CI/CD 配置 CRUD |
| `TestTaskView` | 405 | 测试任务 CRUD |
| `TestTaskExecuteView` | 501 | 测试任务执行 |
| `TestTaskStatusView` | 731 | 任务状态查询 |
| `TestTaskHistoryView` | 764 | 任务执行历史 |
| `QuickTestView` | 802 | 快速测试 |
| `PipelineRunListView` | 874 | Pipeline 运行列表 |
| `PipelineRunDetailView` | 921 | Pipeline 运行详情 |
| `PipelineRunTriggerView` | 955 | 手动触发 Pipeline |
| `PipelineRunWebhookView` | 1052 | Webhook 回调处理 |
| `ProjectQualityReportView` | 1126 | 项目质量报告 |

### 5.2 权限与项目隔离

所有视图均使用统一的权限控制辅助函数：

```python
def _accessible_test_tasks(user):
    """返回用户可访问的测试任务查询集（按项目权限过滤）"""
    return TestTask.objects.filter(project_access_q('project', user)).distinct()

def _apply_project_filter(request, queryset, project_path='project'):
    """按 project_id 查询参数过滤查询集，同时验证用户对该项目的访问权限"""
    project_id = request.query_params.get('project_id')
    if not project_id:
        return queryset
    ensure_project_id_access(request.user, project_id)
    return queryset.filter(**{f'{project_path}_id': project_id})

def _get_accessible_test_task(user, task_id):
    """获取单个任务，验证项目访问权限，无权限时抛出 PermissionDenied"""
    task = TestTask.objects.select_related('project', 'created_by', 'last_result').get(id=task_id)
    ensure_project_id_access(user, task.project_id)
    return task
```

**权限矩阵**:

| 操作 | 权限要求 |
|------|---------|
| 查看任务/配置/运行记录 | 项目成员 (project_access_q) |
| 创建任务/配置 | 目标项目的项目成员 |
| 修改任务/配置 | 所属项目的项目成员 + 运行时锁定 |
| 删除任务/配置 | 所属项目的项目成员 + 运行时锁定 |
| 执行任务 | 所属项目的项目成员 |
| Webhook 回调 | 无需 Session 认证（应用层安全校验） |

### 5.3 任务执行引擎

任务执行支持两种模式，由 `settings.USE_CELERY_TASKS` 控制：

#### 模式 A: Celery 异步执行 (USE_CELERY_TASKS=True)

```
POST /tasks/{id}/execute/
  → TestTaskExecuteView.post()
    → execute_test_task.apply_async(args=[task.id], queue='qa_long')
      → tasks_test_exec.py: execute_test_task()
        → _execute_api_cases_via_unified()   # API 用例
        → execute_ui_test_cases()             # UI 用例
        → mirror_to_test_result()             # 结果同步到 TestResult
```

#### 模式 B: Daemon 线程执行 (USE_CELERY_TASKS=False)

```
POST /tasks/{id}/execute/
  → TestTaskExecuteView.post()
    → threading.Thread(target=self._execute_test_task, args=(task, test_result))
      → _execute_api_cases_via_unified()   # API 用例
      → execute_ui_test_cases()             # UI 用例
      → _simulate_test_execution()          # 无用例时的模拟执行
```

#### 执行流程详情

```python
def _execute_test_task(self, task, test_result):
    """后台执行测试任务的核心逻辑"""
    # 1. 读取 test_config 中的 api_cases / ui_cases
    api_case_ids = test_config.get('api_cases', [])
    ui_case_ids = test_config.get('ui_cases', [])

    # 2. 执行 API 用例（通过 Unified Runner）
    if api_case_ids:
        api_results = _execute_api_cases_via_unified(api_case_ids)

    # 3. 执行 UI 用例（从 views_ui_test 导入）
    if ui_case_ids:
        ui_results = execute_ui_test_cases(ui_case_ids)

    # 4. 无配置用例时：模拟执行 5 个用例（80% 通过率）
    if not api_case_ids and not ui_case_ids:
        logs = self._simulate_test_execution(task)

    # 5. 更新 TestResult（状态、时长、日志、结果摘要）
    test_result.status = 'passed' if failed_count == 0 else 'failed'
    test_result.test_log = json.dumps(execution_report)

    # 6. 更新任务状态和关联
    task.status = 'completed' if failed_count == 0 else 'failed'
    task.last_result = test_result

    # 7. 发送 WebSocket 通知
    _send_notification(project, 'deploy_success' | 'test_failure', message)
```

#### API 用例执行（Unified Runner 集成）

```
_execute_api_cases_via_unified(case_ids)
  → 对每个 case:
    → ApiAutoTestResult.objects.create(status='running')
    → create_api_auto_single_case_orchestrator(case, user=None, test_result=...)
    → orchestrator.execute()
    → 提取 case_result（passed / status_code / response_time_ms 等）
    → mirror_to_test_result(auto_result, source='devops')
    → sync_unified_run_from_auto_result(auto_result, source='devops')
```

### 5.4 Pipeline 引擎

#### Pipeline Client 抽象层

位于 `backend/qa_center/pipeline/__init__.py`：

```python
class CiClient(ABC):
    @abstractmethod
    def trigger(self, config: CiCdConfig, ref: str, trigger_source: str) -> TriggerResult:
        """触发 CI Pipeline，返回 TriggerResult"""
        ...

@dataclass
class TriggerResult:
    external_queue_id: str
    external_run_id: str
    external_url: str
```

**实现类**:
- `JenkinsClient` (`pipeline/jenkins.py`): 通过 Jenkins REST API 触发构建
- `GitLabClient` (`pipeline/gitlab.py`): 通过 GitLab CI API 触发 Pipeline
- `MockCiClient` (`pipeline/__init__.py`): 开发/测试环境模拟，USE_REAL_CI=False 时使用

#### Pipeline 触发流程

```
POST /cicd-config/{id}/trigger/
  → PipelineRunTriggerView.post()
    → 去重检查 (30 秒窗口)
    → RuntimeGuard 检查
    → 创建 PipelineRun(status='running', is_mock=...)
    → [USE_REAL_CI=True]:
        → get_client(config).trigger(config, ref, trigger_source)
        → 更新 PipelineRun 外部 ID 和状态
        → poll_pipeline_status.apply_async(args=[run.id], queue='qa_pipeline')
    → [USE_REAL_CI=False]:
        → threading.Thread(target=_simulate_run, args=(run,))
        → 3 秒后随机 passed/failed，填充模拟结果
```

### 5.5 通知机制

```python
def _send_notification(project, ntype, message):
    """广播通知到 WebSocket 并保存到数据库"""
    # 1. WebSocket 广播到 system_broadcast 组
    channel_layer.group_send('system_broadcast', {
        'type': 'global_notification',
        'message': message,
        'level': 'warning' | 'success',
    })
    # 2. 持久化到 Notification 表（最多 50 个活跃用户）
    for user in User.objects.filter(is_active=True)[:50]:
        Notification.objects.create(user=user, title='系统通知', message=message, ...)
```

---

## 6. 安全机制

### 6.1 Webhook 安全（三层防护）

Webhook 端点是公开暴露的（`permission_classes = []`），必须在应用层实现完整的安全防护。

#### 第一层: 频率限制 (Rate Limiting)

```python
# webhooks.py
_RATE_LIMIT_MAX = 5          # 每个配置每分钟最多 5 次
_RATE_LIMIT_WINDOW_SEC = 60  # 滑动窗口 60 秒

def check_webhook_rate_limit(ci_config_id: int) -> Tuple[bool, int]:
    """使用 Django cache 实现滑动窗口计数器"""
    window = int(time.time()) // _RATE_LIMIT_WINDOW_SEC
    key = f"webhook:ratelimit:{ci_config_id}:{window}"
    count = cache.incr(key)  # 自增计数
    return count > _RATE_LIMIT_MAX, count
```

#### 第二层: HMAC-SHA256 签名验证

```python
def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str):
    """支持 GitHub X-Hub-Signature-256 和 GitLab X-Gitlab-Token 风格"""
    expected_sig = signature_header[len(header_prefix):]
    computed_sig = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, expected_sig)
```

- GitHub 风格: Header `X-Hub-Signature-256: sha256=<hex>`, 前缀 `sha256=`
- GitLab 风格: Header `X-Gitlab-Token: <token>`, 无前缀

#### 第三层: Token 认证

```python
# 使用 hmac.compare_digest 进行常量时间比较，防止时序攻击
expected_token = config.api_token.strip()
provided_token = request.headers.get('X-CI-Token', '').strip()
if not expected_token or not provided_token:
    return 403  # fail-closed: 未配置 token 或未提供 token 都拒绝
if not hmac.compare_digest(provided_token, expected_token):
    return 403
```

### 6.2 去重机制

防止同一 Webhook 重复处理：

```python
_DEDUP_TTL_SEC = 300  # 5 分钟记忆窗口

def check_webhook_dedup(ci_config_id: int, external_run_id: str) -> bool:
    """首次调用返回 False（允许通过）并设置缓存，后续调用返回 True（拒绝）"""
    key = f"webhook:dedup:{ci_config_id}:{external_run_id}"
    is_new = cache.add(key, int(time.time()), timeout=_DEDUP_TTL_SEC)
    return not is_new
```

### 6.3 RuntimeGuard

`RuntimeGuard` 在严格环境下禁止 Mock CI 回退：
- `is_strict()`: 检查运行时环境
- `require_celery_for_runtime_entrypoint()`: 严格环境要求 Celery
- `build_runtime_mode()`: 返回当前运行时模式信息

---

## 7. 配置与特性开关

所有开关通过 `settings.py` 中的环境变量控制：

| 设置项 | 默认值 | 说明 |
|--------|--------|------|
| `USE_CELERY_TASKS` | `False` | True 时使用 Celery 异步执行，False 时使用 daemon 线程 |
| `USE_REAL_CI` | `False` | True 时调用真实 CI 平台 API，False 时使用 Mock 客户端 |
| `USE_UNIFIED_API_RUNNER` | `False` | True 时 API 用例使用 Unified Runner |
| `USE_UNIFIED_RUNNER_FOR_ASYNC_TRIGGERS` | `False` | True 时异步触发器（含 DevOps 任务）使用 Unified Runner |

**推荐配置**:

| 环境 | USE_CELERY_TASKS | USE_REAL_CI |
|------|------------------|-------------|
| 本地开发 | False | False |
| 测试/Staging | True | False (或 True) |
| 生产 | True | True |

---

## 8. 前端架构

### 8.1 文件组织

```
frontend/src/
├── api/devops.ts                    # API 调用封装
├── types/devops.ts                  # TypeScript 类型定义
├── views/qa/
│   ├── DevOpsPlatform.vue           # 主页面（仪表板 + 任务列表 + Pipeline 时间线）
│   ├── TestTaskDetail.vue           # 测试任务详情页
│   └── components/
│       ├── CiCdConfigDialog.vue     # CI/CD 配置对话框
│       ├── TestTaskDialog.vue       # 测试任务创建/编辑对话框
│       └── BatchRunExecuteDialog.vue # 批量执行对话框
├── components/
│   └── PipelineTimeline.vue         # Pipeline 时间线组件
└── router/index.ts                  # 路由定义
```

### 8.2 路由定义

```typescript
// frontend/src/router/index.ts
{
  path: '/projects/:projectId/qa/devops',
  name: 'DevOpsPlatform',
  component: () => import('@/views/qa/DevOpsPlatform.vue'),
  meta: { permission: 'qa:devops:list' }
},
{
  path: '/projects/:projectId/qa/devops/tasks/:id',
  name: 'TestTaskDetail',
  component: () => import('@/views/qa/TestTaskDetail.vue'),
  meta: { permission: 'qa:devops:list' }
}
```

### 8.3 RBAC 权限

在 `backend/system/management/commands/init_rbac_data.py` 中注册：

```python
# code: 'qa:devops:list'
# path: '/qa/devops'
# icon: 'Platform'
# type: 'menu'
# order: 5
```

### 8.4 前端页面要点

#### DevOpsPlatform.vue

- 三大功能卡片: CI/CD 集成 / 自动化测试 / 测试报告
- 统计面板: 总用例数、通过率、今日执行数
- 用例分布: API/UI 测试用例数量
- 最近执行表格: 可点击行跳转到 TestResultDetail
- 测试任务表格: 查看/执行/编辑/删除操作
- Pipeline 时间线: 通过 `PipelineTimeline` 组件渲染
- 任务执行轮询: 调用 `getTestTaskStatus()` 每 2 秒轮询（最多 30 次）

#### TestTaskDetail.vue

- 基本信息与执行统计
- 测试配置展示: 列出关联的 API/UI 用例（名称从 API 解析）
- 执行历史表格: 状态、时间戳、时长
- 实时执行日志: 可折叠的请求/响应/断言详情

### 8.5 API 客户端工具函数

```typescript
// 状态映射
getStatusType(status) → Element Plus Tag 颜色类型
getStatusText(status) → 中文显示文本
getTestTypeType(type) → 测试类型标签颜色
getTestTypeText(type) → 测试类型中文名
getCiCdTypeText(type) → CI/CD 类型中文名

// 格式化
formatDuration(ms) → "1.5s" / "120ms" / "2.3m"
formatDateTime(isoString) → "2026/07/02 14:30:00"
```

---

## 9. 数据流与执行流程

### 9.1 测试任务执行完整流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 用户点击「执行」                                                    │
│   ↓                                                              │
│ POST /api/qa/devops/tasks/{id}/execute/                          │
│   ↓                                                              │
│ TestTaskExecuteView.post()                                       │
│   ├─ 权限检查: _get_accessible_test_task()                        │
│   ├─ 状态检查: 任务不能已在运行中                                    │
│   ├─ 用例验证: validate_test_task_config_cases()                  │
│   ├─ 更新任务: status='running', execution_count++                │
│   ├─ 创建结果: TestResult(source='devops', status='running')      │
│   ├─ 执行派发:                                                     │
│   │   ├─ [Celery] → execute_test_task.delay(task.id)             │
│   │   └─ [Thread] → threading.Thread(_execute_test_task)         │
│   └─ 返回: execution_id, task, runtime_mode                      │
│                                                                  │
│ 后台执行 (_execute_test_task)                                     │
│   ├─ 读取 test_config.api_cases / ui_cases                       │
│   ├─ API 用例 → _execute_api_cases_via_unified()                  │
│   │   └─ per case: orchestrator → mirror → sync                  │
│   ├─ UI 用例 → execute_ui_test_cases()                            │
│   ├─ (无用例) → _simulate_test_execution() (80% pass rate)       │
│   ├─ 汇总: passed/failed/pass_rate                                │
│   ├─ 更新 TestResult: status, duration, test_log                  │
│   ├─ 更新 TestTask: status, last_result                           │
│   └─ WebSocket 通知 + DB Notification                            │
│                                                                  │
│ 前端轮询 GET /api/qa/devops/tasks/{id}/status/ (每2秒, 最多30次)  │
│   └─ 状态变更 → 更新 UI → 停止轮询                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Pipeline Webhook 回调流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 外部 CI (Jenkins/GitLab/GitHub Actions)                          │
│   ↓ POST /api/qa/devops/cicd-config/{id}/webhook/                │
│                                                                  │
│ PipelineRunWebhookView.post()                                    │
│   ├─ 查找配置: CiCdConfig.objects.get(pk=id, is_active=True)      │
│   ├─ [Layer 1] 频率限制: check_webhook_rate_limit()               │
│   ├─ [Layer 2] HMAC 签名: verify_webhook_signature()              │
│   ├─ [Layer 3] Token 认证: hmac.compare_digest()                  │
│   ├─ 去重检查: check_webhook_dedup(external_run_id)               │
│   ├─ 创建 PipelineRun: status/commit_sha/branch/external_url     │
│   └─ 返回: { "message": "Webhook received", "run_id": N }        │
└─────────────────────────────────────────────────────────────────┘
```

### 9.3 质量报告计算流程

```
GET /api/qa/devops/quality-report/?project_id=X
   ↓
ProjectQualityReportView.get()
   ├─ 1. 测试覆盖率
   │   └─ 关联测试用例的任务数 / 总任务数 × 20
   ├─ 2. 测试通过率
   │   └─ 最近 10 次 TestResult 通过数 / 10 × 20
   ├─ 3. 性能指标
   │   └─ 最近 5 次 PerformanceTestResult 的 P95 均值 → 映射到分数
   ├─ 4. Bug 密度
   │   └─ Bug 数量 / 总任务数 → 百分比 → 映射到分数
   ├─ 5. 部署成功率
   │   └─ 最近 10 次真实 PipelineRun 通过数 / 10 × 20
   ├─ 30 天趋势: 每日 passed/total/rate
   └─ 返回: total_score, dimensions[], trend[], summary
```

---

## 10. 文件清单

### 后端文件

| 文件路径 | 行数 | 职责 |
|---------|------|------|
| `backend/qa_center/views_devops.py` | 1232 | 所有 DevOps 视图类（12 个） |
| `backend/qa_center/urls.py` | 88 | URL 路由注册 |
| `backend/qa_center/models.py` | 179-251, 664-764 | DevOps 模型定义（TestTask, CiCdConfig, PipelineRun） |
| `backend/qa_center/serializers.py` | - | DevOps 序列化器（TestTask*, CiCdConfig） |
| `backend/qa_center/webhooks.py` | 162 | Webhook 安全工具（签名/去重/限流） |
| `backend/qa_center/tasks_test_exec.py` | - | Celery 异步执行任务 |
| `backend/qa_center/pipeline/__init__.py` | - | CI Client 抽象 + Mock 实现 + 工厂函数 |
| `backend/qa_center/pipeline/jenkins.py` | - | Jenkins Pipeline Client |
| `backend/qa_center/pipeline/gitlab.py` | - | GitLab CI Pipeline Client |
| `backend/qa_center/pipeline/state_mapping.py` | - | Pipeline 状态映射 |
| `backend/qa_center/result_sink.py` | - | ApiAutoTestResult → TestResult 镜像 |
| `backend/qa_center/feature_flags.py` | - | Feature Flag 辅助函数 |
| `backend/qa_center/migrations/0007_testresult_source.py` | - | TestResult.source 字段迁移 |

### 前端文件

| 文件路径 | 职责 |
|---------|------|
| `frontend/src/api/devops.ts` | API 调用封装 + 工具函数 |
| `frontend/src/types/devops.ts` | TypeScript 类型定义 |
| `frontend/src/views/qa/DevOpsPlatform.vue` | DevOps 主页面（仪表板） |
| `frontend/src/views/qa/TestTaskDetail.vue` | 测试任务详情页 |
| `frontend/src/views/qa/components/CiCdConfigDialog.vue` | CI/CD 配置对话框 |
| `frontend/src/views/qa/components/TestTaskDialog.vue` | 测试任务对话框 |
| `frontend/src/views/qa/components/BatchRunExecuteDialog.vue` | 批量执行对话框 |
| `frontend/src/components/PipelineTimeline.vue` | Pipeline 时间线组件 |
| `frontend/src/views/ProjectQualityReport.vue` | 项目质量报告页 |
| `frontend/src/router/index.ts` | 路由定义 |

---

## 11. 扩展指南

### 11.1 添加新的 CI 平台支持

1. 在 `backend/qa_center/pipeline/` 下创建新的 Client 类，继承 `CiClient` 抽象基类
2. 实现 `trigger()` 方法，返回 `TriggerResult`
3. 在 `pipeline/__init__.py` 的 `get_client()` 工厂函数中注册新类型
4. 更新 `CiCdConfig` 模型的 `ci_type` choices
5. 更新前端 `devops.ts` 的 `getCiCdTypeText()` 和类型定义

### 11.2 添加新的测试类型

1. 更新 `TestTask` 和 `TestResult` 模型的 `test_type` choices
2. 在 `TestTaskExecuteView._execute_test_task()` 中添加新的执行分支
3. 在 `DashboardStatsView` 的 `by_type` 统计中包含新类型
4. 更新前端的 `TestType` 类型和 `getTestTypeText()` 映射

### 11.3 添加新的质量报告维度

1. 在 `ProjectQualityReportView.get()` 中添加新的维度计算逻辑
2. 维度分数映射到 `dimensions` 列表
3. 更新 `total_score` 累加逻辑
4. 更新前端 `ProjectQualityReport.vue` 的展示

### 11.4 扩展通知渠道

当前通知通过 WebSocket 广播 + 数据库持久化。如需扩展：
1. 修改 `_send_notification()` 函数，添加新的通知渠道（如邮件、钉钉、企业微信）
2. 利用 `TestTask.notification_channels` JSON 字段存储渠道配置
3. 根据 `TestTask.notify_on_success` / `notify_on_failure` 过滤通知

---

> **相关文档**: 
> - QA Center 整体开发文档: `docs/qa-center.md`
> - API 自动化测试 Runner 文档: `docs/api-runner.md`
> - 项目权限系统文档: `docs/project-access.md`
