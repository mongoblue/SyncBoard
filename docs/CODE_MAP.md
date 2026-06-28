# SyncBoard 代码导览

> 一份中粒度的模块地图，帮助你快速定位代码、理解业务流向。
> 建议配合文件顶部的注释头阅读，先看图再进代码。

---

## 1. 顶层架构

### 1.1 一句话定位

SyncBoard 是一个 **项目管理协作 + 自动化测试中心** 平台。左边是看板（Kanban）管理任务/Sprint/Bug/AI 助手，右边是 QA 中心（API/UI/性能测试 + DevOps 流水线）。

### 1.2 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Django 6 + DRF + Channels（WebSocket）+ Celery + Redis |
| 数据库 | MySQL（主）+ Elasticsearch 7（全文搜索）+ Redis（缓存+消息队列） |
| 前端 | Vue 3 + Pinia + Element Plus + Vue Router |
| 实时通信 | 8 条 WebSocket 路由（看板/聊天/QA/录制/性能/测试运行） |
| 子进程 | 4 个 Python 子进程 worker（recorder / runner，各含 supervisor + worker） |

### 1.3 目录结构

```
SyncBoard/
├── backend/                  # Django 项目
│   ├── backend/              # 项目配置：settings, asgi, celery, urls, tasks
│   ├── room/                 # 核心协作看板（项目/任务/评论/通知/Sprint/AI/文档）
│   ├── qa_center/            # 测试中心（21 模型 + 45+ 路由 + 4 worker 子进程）
│   ├── bug_tracker/          # Bug 缺陷跟踪（独立状态机）
│   ├── system/               # RBAC 系统管理（菜单/角色/用户）
│   ├── tests/                # 26 个 pytest 测试文件
│   └── performance/          # Locust 性能测试脚本
├── frontend/                 # Vue 3 前端
│   └── src/
│       ├── api/              # 后端接口封装（devops, runplan, testrun, bug, autoresult）
│       ├── components/       # 全局通用组件（含 bug/ 子目录）
│       ├── composables/      # 通用组合式函数（WS 客户端、录制器）
│       ├── directives/       # 自定义指令（v-permission）
│       ├── router/           # 路由配置 + 权限守卫
│       ├── stores/           # Pinia 状态（board/ 子模块 + composables/useWebSocket）
│       ├── styles/           # 全局样式
│       ├── types/            # TS 类型定义
│       ├── utils/            # 工具（request 拦截器、error、sanitize）
│       └── views/            # 页面（含 bug/、qa/、system/ 子目录）
└── docs/                     # 项目文档（含本文件）
```

### 1.4 前后端协同图

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Vue 3 + Pinia)                     │
│  Board.vue  Chat.vue  AIChat.vue  ApiCaseDetail.vue  ...    │
│    │            │          │              │                  │
│    ▼            │          │              │                  │
│  boardStore    │          │         api/*.ts                │
│    │            │          │              │                  │
│    ▼            ▼          ▼              ▼                  │
│  useWebSocket  (直连 WS)   HTTP REST (DRF)                  │
└───────┬──────────┬──────────┬──────────────┬─────────────────┘
        │          │          │              │
   WS (Channels)  │          │         HTTP (Django ASGI)
        │          │          │              │
        ▼          │          ▼              ▼
┌──────────────────────────────────────────────────────────────┐
│                      后端 (Django 6)                          │
│  asgi.py: ProtocolTypeRouter → http→Django / ws→Channels     │
│  urls.py: /api/ → room    /api/qa/ → qa_center               │
│           /api/ → bug_tracker    /api/system/ → system        │
│  celery.py: 异步搜索索引更新                                   │
│  qa_center/workers/: 子进程 runner/recorder                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 后端 App 分章节

### 2.1 `room` —— 核心协作看板

**职责**：项目管理、看板任务、Sprint、AI 助手、通知、评论、附件、API 文档。

**代码入口**：`urls.py`（43 条路由）、`routing.py`（3 条 WS 路由）、`consumers.py`（BoardConsumer）、`consumers_chat.py`（ChatConsumer）、`consumers_global.py`（GlobalConsumer）

**数据模型**（17 个，按业务分组）：

| 分组 | 模型 | 关键字段 |
|---|---|---|
| 用户 | `UserProfile` | 头像扩展 |
| 项目 | `Project` | UUID PK, owner, members |
| 看板 | `Column`, `Task` | UUID PK, position, tags, assignee |
| 标签 | `Tag` | name, color |
| 角色 | `ProjectRole`, `ProjectMember` | 项目级 RBAC |
| 评论 | `TaskComment` | 内容, 图片 |
| 附件 | `TaskAttachment` | 文件上传 |
| 活动 | `TaskActivityLog` | 变更记录 |
| 通知 | `Notification` | 类型, 已读/未读 |
| 审计 | `AuditLog` | 操作审计 |
| AI | `AIConversation`, `AIMessage` | 对话历史 |
| Sprint | `Sprint`, `SprintTask` | 迭代 + 燃尽图 |
| 文档 | `ProjectApiDoc` | 项目 API 文档 |

**关键视图文件**（views/ 下 15 个模块）：

| 文件 | 封装的路由 |
|---|---|
| `auth.py` | 登录/登出/当前用户 |
| `project.py` | 项目 CRUD + 邀请 |
| `board.py` | 看板列 + 任务 CRUD |
| `tag.py` | 标签 CRUD |
| `comment.py` | 任务评论 |
| `attachment.py` | 任务附件 |
| `activity.py` | 任务活动日志 |
| `notification.py` | 通知列表/已读 |
| `user.py` | 用户列表/头像 |
| `sprint.py` | Sprint + 任务 + 燃尽图 |
| `ai.py` | AI 对话/Chat/分析 |
| `api_docs.py` | 项目 API 文档 |
| `project_role.py` | 项目角色/成员 |
| `search.py` | 任务搜索（Haystack） |
| `mixins.py` | 公共 mixin（项目成员鉴权） |

**WebSocket 路由**：

| 路径 | Consumer | 推送时机 |
|---|---|---|
| `ws/board/<project_id>/` | `BoardConsumer` | 任务增删改、列变化、用户进出 |
| `ws/chat/<project_id>/` | `ChatConsumer` | 聊天消息 |
| `ws/global/` | `GlobalConsumer` | 全局通知（系统级） |

### 2.2 `qa_center` —— 测试中心（最大 App）

**职责**：API/UI/性能测试用例管理、自动化测试执行、测试计划编排、CI/CD 集成、测试运行结果追踪。

**代码入口**：`urls.py`（45+ 路由，含 15 个 ViewSet）、`routing.py`（5 条 WS 路由）、`consumers.py`（5 个 Consumer）、`workers/`（4 个子进程）

**数据模型**（21 个，按业务分组）：

| 分组 | 模型 | 说明 |
|---|---|---|
| **接口测试（旧）** | `ApiTestCase` | 单用例：url/method/headers/body/expected_response/expected_status |
| | `ApiTestResult` | 单次执行结果 |
| **接口测试（新）** | `ApiAutoTestSuite` | 自动化套件（归类用例） |
| | `ApiAutoTestCase` | 自动化用例（含 content_type/query_params/form_files/timeout） |
| | `ApiAutoTestAssertion` | 独立断言规则（可排序） |
| | `ApiAutoTestExtractor` | 独立变量提取器（可排序，支持链式传递） |
| | `ApiAutoTestResult` | 套件/计划执行结果 |
| | `ApiAutoTestCaseResult` | 单用例在套件中的执行结果 |
| **UI 测试** | `UiTestCase` | UI 自动化用例（步骤 + 选择器） |
| | `TestScreenshot` | 执行截图 |
| **性能测试** | `PerformanceTestCase` | 性能测试配置 |
| | `PerformanceTestResult` | 性能测试结果 |
| **编排与执行** | `TestRunPlan` | 测试执行计划（关联 suite + 用例 + 环境） |
| | `TestRun` | 测试运行实例（批次） |
| | `TestRunCaseResult` | 批次中单条用例结果（关联 ApiTestCase 外键） |
| | `TestEnvironment` | 测试环境（URL 前缀、变量） |
| | `TestGlobalVar` | 全局变量（模板渲染时注入） |
| **DevOps** | `CiCdConfig` | CI/CD 集成配置（webhook/trigger） |
| | `PipelineRun` | 流水线运行记录 |
| | `TestTask` | 测试任务（定时/手动触发） |

**新旧两套并存说明**：

- 旧版 `ApiTestCase`（走 `views_api_test.py` + `test_executor.py`，用 `django.test.Client` 打内部 URL）**仍被前端 ApiCaseList/Detail.vue 使用**，是日常单用例编辑/运行的主路径。
- 新版 `ApiAutoTestCase`（走 `api_auto_executor.py` + `run_plan_executor.py`，用 `requests` 打真实 HTTP）**被批量执行计划/套件使用**，支持文件上传、Query 参数、链式变量提取等高级功能。
- 两套**共享** `unified_assertions.py` 断言层，输入格式不同但执行逻辑统一。

**关键执行器/工具模块**：

| 文件 | 职责 |
|---|---|
| `api_auto_executor.py` | 新版套件级执行器，`requests` 发送，写 `ApiAutoTestResult` |
| `run_plan_executor.py` | 测试计划执行器，`ThreadPoolExecutor` 并发，调 api_auto_executor |
| `test_executor.py` | 旧版执行器，`django.test.Client` 发送，写 `TestRun`/`TestResult` |
| `unified_assertions.py` | 统一断言层，新旧两套都调用，支持 10+ 断言类型 |
| `extractors.py` | 变量提取器（JSONPath/XPath/Header/Cookie） |
| `template_engine.py` | 模板引擎（变量渲染 `{{var}}`，含全局变量 + 环境变量 + 上游提取） |
| `request_builder.py` | 请求构造器（URL 拼接、Query 参数、Header 合并） |
| `assertion_engine.py` | 旧断言引擎（已被 unified_assertions 替代，逐步弃用） |
| `bug_utils.py` | 测试失败自动建 Bug 工具 |
| `locust_runner.py` | Locust 性能测试运行器 |

**WebSocket 路由**：

| 路径 | Consumer | 推送时机 |
|---|---|---|
| `ws/qa/dashboard/` | `QAConsumer` | 测试计划执行进度（每用例完成时广播） |
| `ws/qa/recorder/` | `RecorderConsumer` | UI 录制器：录制步骤、单步试跑结果 |
| `ws/qa/performance/<execution_id>/` | `PerformanceTestConsumer` | 性能测试实时指标 |
| `ws/qa/test-run/<run_id>/` | `TestRunProgressConsumer` | 旧版测试运行进度 |
| `ws/qa/run/<task_id>/` | `UiRunConsumer` | UI 自动化执行进度 |

**子进程 Worker**：

| 文件 | 角色 |
|---|---|
| `workers/runner_supervisor.py` | 管理 runner_worker 子进程，事件注册表 + 流式读取 |
| `workers/runner_worker.py` | 实际执行测试任务（Playwright）的子进程 |
| `workers/recorder_supervisor.py` | 管理 recorder_worker 子进程 |
| `workers/recorder_worker.py` | 录制/回放子进程（Playwright + CDP） |
| `workers/protocol.py` | 进程间通信协议定义 |

**视图文件索引**（12 个 views_*.py）：

| 文件 | 封装的业务 |
|---|---|
| `views_api_test.py` | 旧版 API 用例 CRUD + 单跑 + 批量跑 + 结果 |
| `views_api_auto_test.py` | 新版套件/用例/断言/提取器 CRUD + 执行 |
| `views_ui_test.py` | UI 用例 CRUD + 截图 |
| `views_test_result.py` | 通用测试结果 |
| `views_performance.py` | 性能测试 CRUD |
| `views_run_plan.py` | 测试计划 CRUD + 执行触发 |
| `views_environment.py` | 测试环境 + 全局变量 |
| `views_test_run.py` | TestRun 列表/详情/取消/重跑 |
| `views_test_link.py` | 用例 ↔ 看板任务关联/解绑 |
| `views_devops.py` | DevOps 仪表盘/CI/CD/任务/流水线/质量报告 |
| `views.py` | 数据工厂 + 快速测试 |

### 2.3 `bug_tracker` —— 缺陷跟踪

**职责**：独立 Bug 生命周期管理，含 9 状态状态机。

**数据模型**（3 个）：

| 模型 | 说明 |
|---|---|
| `Bug` | Bug 主模型（严重度/优先级/状态/指派/关联项目） |
| `BugTransition` | 状态流转记录（谁在什么时候把状态从 A 改成 B） |
| `BugComment` | Bug 评论 |

**路由**（`/api/bugs/` 前缀）：

| 路径 | 视图 |
|---|---|
| `bugs/` | `BugViewSet`（CRUD + 状态流转） |
| `bugs/stats/` | `BugStatsView`（统计） |
| `bugs/seed-demo/` | `BugSeedDemoView`（演示数据） |

**状态机**：`bug_tracker/state_machine.py` 定义了 9 种状态间的合法流转（open → confirmed → assigned → in_progress → fixed → verified → closed / reopened / wontfix）。

### 2.4 `system` —— RBAC 系统管理

**职责**：菜单权限管理、角色管理、用户管理。

**数据模型**（3 个）：

| 模型 | 说明 |
|---|---|
| `Menu` | 菜单/权限点（目录/菜单/按钮三级，树形结构） |
| `Role` | 角色（关联 Menu，多对多） |
| `SystemUserProfile` | 系统用户扩展（关联 Role） |

**路由**（`/api/system/` 前缀）：

| 路径 | 视图 |
|---|---|
| `menus/` / `menus/tree/` / `menus/<id>/` | 菜单 CRUD + 树形 |
| `roles/` / `roles/<id>/` | 角色 CRUD |
| `users/` / `users/<id>/` / `users/<id>/reset-password/` | 用户管理 |
| `user/permissions/` | 当前用户权限查询 |

---

## 3. 前端分章节

### 3.1 入口与路由

**`main.ts`**：注册 Pinia → Vue Router → Element Plus → 全部 Element Plus 图标全局注册 → `v-permission` 自定义指令 → 挂载。

**`router/index.ts`**：
- 顶层：`/` → 重定向到 `/projects`，`/login` 独立
- 项目内：`/projects/:projectId` → `ProjectLayout`（侧栏布局壳），子路由 27 个页面
- 权限守卫 `beforeEach`：检查登录态 → 检查 `meta.permission`（调用 `authStore.checkPermission`）→ 无权限重定向到看板

### 3.2 状态层（Pinia Stores）

| Store | 文件 | 职责 |
|---|---|---|
| `auth` | `stores/Auth.ts` | 用户登录态、菜单树、权限列表、`checkPermission()` |
| `board` | `stores/board/index.ts` | 看板聚合 Store，组合 column/task/tag/user 四个子 Store + WebSocket |
| `board/column` | `stores/board/column.ts` | 看板列 CRUD |
| `board/task` | `stores/board/task.ts` | 任务卡片 CRUD（含拖拽排序） |
| `board/tag` | `stores/board/tag.ts` | 项目标签 CRUD |
| `board/user` | `stores/board/user.ts` | 看板用户列表 |
| `notification` | `stores/notification.ts` | 全局通知 WebSocket（`/ws/global/`），桌面通知 + 未读计数 |

**`board/index.ts` 聚合模式**：看板页不直接操作 column/task/tag/user store，而是通过 `useBoardStore` 统一入口。`useBoardStore` 内部组合 4 个子 Store，对外暴露兼容旧的 API（`Columns`/`Users` 等 computed 别名），同时管理 WebSocket 连接和消息分发。

**`stores/composables/useWebSocket.ts`（通用 WS 客户端）**：
- 心跳：每 30s 发 `{"type": "ping"}` 保活
- 重连：断开后 3s 自动重连（非主动关闭时）
- 观察者模式：`messageListeners` Set 存储回调，收到消息时广播给所有订阅者
- 去重：已连接时不重复创建

### 3.3 API 层（`api/`）

| 文件 | 绑定的后端路由前缀 | 封装内容 |
|---|---|---|
| `devops.ts` | `/api/qa/devops/` | 仪表盘统计、CI/CD 配置、测试任务 CRUD + 执行、流水线 |
| `runplan.ts` | `/api/qa/run-plans/` | 测试计划 CRUD + 执行触发 + WS 进度主题 |
| `testrun.ts` | `/api/qa/runs/` | TestRun 列表/详情/取消/重跑/用例结果 |
| `autoresult.ts` | `/api/qa/auto-results/` | 自动化执行结果 + 转 Bug |
| `bug.ts` | `/api/bugs/` | Bug CRUD + 状态/严重度/优先级类型 |

### 3.4 视图层（`views/`）

按业务分组：

**项目级**：

| 文件 | 说明 |
|---|---|
| `Projects.vue` | 项目列表入口 |
| `ProjectLayout.vue` | 项目内通用布局（左侧菜单 + 右侧子路由 `<router-view>`） |
| `Settings.vue` | 项目设置 |

**看板与迭代**：

| 文件 | 说明 |
|---|---|
| `Board.vue` | 看板主视图（列 + 任务卡片拖拽、搜索筛选、批量选择/删除） |
| `ProjectSprints.vue` | Sprint 迭代列表 |
| `SprintBoard.vue` | 单迭代看板（Sprint 内的任务管理） |

**QA 中心**（`views/qa/`）：

| 文件 | 说明 |
|---|---|
| `QA.vue` | QA 中心首页 |
| `ApiCaseList.vue` | API 用例列表（**走旧版** `/qa/api-cases/`） |
| `ApiCaseDetail.vue` | API 用例编辑/创建 + 单次运行（**走旧版**） |
| `ApiCaseRunDetail.vue` | 单次 API 执行结果详情 |
| `UiCaseList.vue` | UI 用例列表 |
| `UiCaseDetail.vue` | UI 用例编辑 + 录制面板（嵌入 `RecorderPanel.vue`） |
| `TestRunList.vue` | 测试执行批次列表 |
| `TestRunDetail.vue` | 批次详情（含每用例结果） |
| `TestResultList.vue` | 测试结果列表 |
| `TestResultDetail.vue` | 单结果详情 |
| `AutoResultDetail.vue` | 自动化执行结果详情（**走新版**） |
| `DevOpsPlatform.vue` | DevOps 仪表板 |
| `TestTaskDetail.vue` | DevOps 测试任务详情 |
| `PerformanceTestResult.vue` | 性能测试结果 |

**Bug 跟踪**（`views/bug/`）：

| 文件 | 说明 |
|---|---|
| `BugList.vue` | Bug 列表（筛选/排序） |
| `MyBugs.vue` | 我的 Bug |
| `BugDetail.vue` | Bug 详情 + 状态流转 + 评论 |

**AI & 沟通**：

| 文件 | 说明 |
|---|---|
| `AIChat.vue` | AI 助手聊天 |
| `Chat.vue` | 项目聊天室 |
| `Notifications.vue` | 通知中心 |

**系统管理**（`views/system/`）：

| 文件 | 说明 |
|---|---|
| `MenuManagement.vue` | 菜单/权限点管理 |
| `RoleManagement.vue` | 角色管理 |
| `UserManagement.vue` | 用户管理 |

**其他**：

| 文件 | 说明 |
|---|---|
| `Members.vue` | 项目成员管理 |
| `Tags.vue` | 项目标签管理 |
| `Stats.vue` | 项目统计图表（ECharts） |
| `ProjectQualityReport.vue` | 项目质量报告 |
| `ProjectApiDocs.vue` | API 文档浏览 |
| `Login.vue` | 登录页 |

**QA 子组件**（`views/qa/components/`）：

| 文件 | 说明 |
|---|---|
| `RequestPanel.vue` | 请求编辑面板（URL/Headers/Body） |
| `ResponsePanel.vue` | 响应展示面板 |
| `TestsPanel.vue` | 断言/提取器配置面板 |
| `CurlPanel.vue` | cURL 导入/导出 |
| `RunProgressBar.vue` | 执行进度条 |
| `BatchRunExecuteDialog.vue` | 批量执行计划对话框（**走新版**） |
| `TestTaskDialog.vue` | 测试任务创建/编辑对话框 |
| `CiCdConfigDialog.vue` | CI/CD 配置对话框 |
| `RecorderPanel.vue` | UI 录制器面板（嵌入 `UiCaseDetail.vue`） |

### 3.5 组件层（`components/`）

| 文件 | 说明 |
|---|---|
| `TaskDetailDrawer.vue` | 任务详情抽屉（右侧滑出） |
| `ChatDrawer.vue` | 聊天抽屉 |
| `AvatarUpload.vue` | 头像上传 |
| `PipelineTimeline.vue` | 流水线执行时间线 |
| `TestConsole.vue` | 测试执行控制台 |
| `bug/EditableText.vue` | 行内可编辑文本（Bug 字段编辑用） |

### 3.6 Composables

| 文件 | 说明 |
|---|---|
| `useRecorderSocket.ts` | UI 录制 WebSocket 状态机（idle → connecting → recording → paused → stopped → error） |
| `wsHost.ts` | dev 模式直连后端 8000 端口（绕开 Vite 代理，避免 WS 关闭时污染 HTTP keepalive pool） |

### 3.7 WebSocket 接入点（前端视角）

| 前端调用位置 | WS 路径 | 用途 |
|---|---|---|
| `stores/board/index.ts` → `useWebSocket` | `ws/board/<projectId>/` | 看板实时同步 |
| `stores/notification.ts` → 原生 WebSocket | `ws/global/` | 全局通知 |
| `composables/useRecorderSocket.ts` | `ws/qa/recorder/` | UI 录制 |
| `api/runplan.ts` → 监听 WS | `ws/qa/dashboard/` | 测试计划执行进度 |
| 播放 UI 录制回放 | `ws/qa/run/<taskId>/` | UI 执行进度 |
| 性能测试 | `ws/qa/performance/<id>/` | 性能测试实时指标 |
| 旧版测试运行 | `ws/qa/test-run/<runId>/` | 测试运行进度 |

---

## 4. 跨前后端核心业务流程

以下每条流程按时间顺序列出关键步骤，标注文件路径。

### 4.1 登录与权限

```
Login.vue
  → POST /api/auth/login/  (room/views/auth.py: LoginView)
  → authStore 设 user + menus + permissions
  → router beforeEach (router/index.ts:246)
    → 检查 authStore.user（未登录跳 /login）
    → 检查 meta.permission → authStore.checkPermission(perm)
    → 无权限重定向到当前项目看板
  → ProjectLayout.vue 侧栏菜单通过 authStore.menus 渲染
  → v-permission 指令 (directives/permission.ts) 控制按钮级显隐
```

### 4.2 看板任务实时同步

```
拖拽 Task 卡片（Board.vue）
  → boardStore.moveTask(taskId, newColumnId, newPosition)
    → PATCH /api/tasks/<id>/  (room/views/board.py: TaskDetailView)
    → 后端保存位置后触发 BoardConsumer 广播
  → BoardConsumer (room/consumers.py:80 receive)
    → channel_layer.group_send("board_<projectId>", {type: "board_update", ...})
  → 其他客户端 boardStore.handleSocketMessage 接收
    → 根据 action 类型（refresh/column_created/task_moved/...）更新本地状态
```

### 4.3 API 测试单跑（旧版路径）

```
ApiCaseDetail.vue 点击"运行"
  → POST /api/qa/api-cases/{id}/run/  (qa_center/views_api_test.py: ApiTestCaseRunView)
  → 用 django.test.Client 发送请求（仅能打项目内部 URL）
  → 从 expected_response.assertions 取出断言列表
  → unified_assertions.run_assertions(assertions, ctx)  ← 统一断言层
  → 如果 assertions 中没有 status_code 断言，则用 expected_status 字段兜底
  → 写 ApiTestResult（用例结果）+ TestRun + TestRunCaseResult（双写）
  → 返回 { passed, assertion_results, status_code, ... }
```

### 4.4 测试计划批量执行（新版路径）

```
BatchRunExecuteDialog.vue 点击"执行"
  → POST /api/qa/run-plans/{id}/execute/  (qa_center/views_run_plan.py)
  → TestRunPlanExecutor.execute()  (qa_center/run_plan_executor.py)
    → 按 plan 配置取 suite + cases + environment
    → template_engine 渲染全局变量 + 环境变量
    → 并发模式：ThreadPoolExecutor(max_workers)
    → 每个 case 调 _execute_one()
      → requests.request() 真实 HTTP 请求
      → unified_assertions.run_assertions(active_assertions, ctx)
      → extractors.run_extractors() 变量提取
      → 串行模式：提取结果注入下游 case 的 ctx
      → 写 ApiAutoTestCaseResult
      → WS 广播进度到 ws/qa/dashboard/  (QAConsumer)
    → 全部完成后写 ApiAutoTestResult
    → 失败时调 bug_utils.create_bug_from_test_failure() 自动建 Bug
```

### 4.5 UI 录制 → 用例保存 → 回放

```
UiCaseDetail.vue 嵌入 RecorderPanel.vue
  → 点击"开始录制"
  → useRecorderSocket.ts 连接 ws/qa/recorder/
  → 发 {command: "start_recording", url, viewport}
  → RecorderConsumer (qa_center/consumers.py)
    → 启动 recorder_supervisor 子进程
    → recorder_worker 通过 Playwright + CDP 录制用户操作
    → 流式回传录制步骤（type: "step_recorded"）
  → 前端 RecorderPanel 实时展示步骤列表
  → 点击"停止录制"
  → 步骤写入 UiTestCase.steps JSON 字段
  → 保存：POST/PUT /api/qa/ui-cases/
  → 回放：runner_supervisor 启动 runner_worker
    → 逐步执行 steps → ws/qa/run/<taskId>/ 推送进度
```

### 4.6 测试失败自动建 Bug

```
api_auto_executor / run_plan_executor 执行完
  → 如果 case 失败
  → bug_utils.create_bug_from_test_failure(case, test_result, error_message)
    → 在 bug_tracker.Bug 表创建一条 Bug
    → 关联到 case 所属项目
    → 前端 BugList.vue 可看到自动创建的 Bug
```

---

## 5. 数据库 ER 关系简图

```
Project (UUID) ──1:N── Column (UUID) ──1:N── Task (UUID)
    │                    │                      │
    │                    │                      ├── N:N ── Tag
    │                    │                      ├── 1:N ── TaskComment
    │                    │                      ├── 1:N ── TaskAttachment
    │                    │                      ├── 1:N ── TaskActivityLog
    │                    │                      └── N:N ── ApiTestCase (旧)
    │                    │
    ├── 1:N ── Sprint ── N:N ── Task
    ├── 1:N ── ApiTestCase (旧) ── 1:N ── ApiTestResult
    ├── 1:N ── ApiAutoTestSuite ── 1:N ── ApiAutoTestCase
    │                                    ├── 1:N ── ApiAutoTestAssertion
    │                                    ├── 1:N ── ApiAutoTestExtractor
    │                                    └── 1:N ── ApiAutoTestCaseResult
    ├── 1:N ── TestRunPlan ── N:N ── ApiAutoTestCase
    ├── 1:N ── UiTestCase ── 1:N ── TestScreenshot
    ├── 1:N ── Bug (bug_tracker)
    ├── 1:N ── ProjectRole ── 1:N ── ProjectMember
    └── 1:N ── CiCdConfig ── 1:N ── PipelineRun

TestRun ── 1:N ── TestRunCaseResult ── FK ── ApiTestCase (旧)
                                       ── FK ── ApiAutoTestCase (新)

User ── 1:1 ── UserProfile
     ── 1:N ── Notification
     ── 1:N ── AIConversation ── 1:N ── AIMessage
```

---

## 6. 怎么用这份文档

1. **拿到一个需求** → 先在 §4「核心业务流程」找到最接近的流程链 → 看大致涉及哪些文件
2. **打开文件** → 读文件顶部注释头（如果有）→ 进函数，用 IDE 跳转跟调用链
3. **不知道某个 API 路由在哪** → 到 §2 对应 app 的「路由」表查 → 找到 views 文件 → 定位具体 View
4. **不知道前端某个页面用哪个 Store** → 到 §3.4 视图层查该页面 → 到 §3.2 查对应的 Store 文件
5. **WebSocket 消息对不上** → 到 §3.7 查 WS 接入点 → 到 §2 对应 app 的 WebSocket 路由表查 Consumer

---

*文档更新于 2026-06-22。如果你在阅读中发现任何过时或不准确的地方，请告知，我会及时更新。*