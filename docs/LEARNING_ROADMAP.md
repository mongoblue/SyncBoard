# SyncBoard 学习大纲

> 持久化学习进度跟踪文档。
> 每次学习对话前先看本文档，防止上下文丢失导致语义错误。
>
> 核心原则：**代码为唯一真相源，本文档是索引和进度记录，不是权威描述。**
>
> 最后更新：2026-06-29

---

## 一、总览

### 1.1 项目一句话定位

SyncBoard / FlowSpace = **项目管理协作看板 + QA 测试中心 + AI 助手 + DevOps + RBAC 权限管理** 的全栈平台。

技术栈：

```
后端：Django 6 + DRF + Channels + Celery + Redis
数据库：MySQL 8 + Elasticsearch 7 + Redis
前端：Vue 3 + TypeScript + Pinia + Element Plus + Vite
实时通信：8 条 WebSocket 路由
子进程：4 个 Python 子进程 worker（recorder / runner）
AI：DeepSeek（OpenAI 兼容协议）
```

### 1.2 8 模块关系图

```
                         ┌─────────────────────────────────┐
                         │          Vue 3 前端              │
                         │  Board / AIChat / QA / Bug / System │
                         └──────────────┬──────────────────┘
                                        │ REST + WebSocket
                         ┌──────────────┴──────────────────┐
                         │       Django ASGI :8000          │
                         └──────────────┬──────────────────┘
                                        │
          ┌───────────────┬─────────────┼─────────────┬──────────────┐
          ▼               ▼             ▼             ▼              ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ 1.基础架构│   │ 2.WebSocket│   │ 3.room   │   │ 5.QA     │   │ 8.system │
   │ settings  │   │ 实时层    │   │ 看板协作  │   │ 测试中心  │   │ RBAC权限 │
   │ asgi/urls │   │ 8条WS路由 │   │ AI/通知   │   │ 录制/回放 │   │ 菜单/角色 │
   │ celery    │   │ 心跳/重连 │   │ Sprint    │   │ 性能/DevOps│   │ 用户管理 │
   └──────────┘   └──────────┘   └──────────┘   └────┬─────┘   └──────────┘
                                                      │
                                            ┌─────────┼─────────┐
                                            ▼         ▼         ▼
                                     ┌─────────┐ ┌─────────┐ ┌─────────┐
                                     │ 4.AI助手│ │6.UI测试 │ │7.Bug缺陷│
                                     │ToolCall │ │子进程IPC│ │状态机   │
                                     └─────────┘ └─────────┘ └─────────┘

模块依赖关系（箭头 = 被依赖方，学习时从底层往上学）：
  基础架构 → WebSocket → room → AI → QA(API) → QA(UI) → 性能/DevOps → Bug/System
```

### 1.3 全局调用链路简图

```
入口1：REST API
  浏览器 Axios → Django URL Router → DRF View → ORM → MySQL
                                              → group_send → WebSocket

入口2：WebSocket
  浏览器 new WebSocket → Channels Router → AuthMiddleware → Consumer.connect()
                                           → group_add → Channel Layer (Redis)

入口3：AI 调用
  AIChat.vue → POST /api/ai/chat/ → views/ai.py → ai_utils.py
      → build_project_context()（查 DB 拼上下文）
      → DeepSeek API（tools=AVAILABLE_TOOLS）
      → execute_tool()（操作 DB 或调测试执行器）

入口4：子进程 IPC
  Django 主进程 → subprocess.Popen → worker 子进程
      → stdin JSON Lines（发命令）
      ← stdout JSON Lines（读事件）
      → asyncio.run_coroutine_threadsafe → WebSocket 推前端
```

### 1.4 关键原则（这些记死，不能忘）

| 原则 | 说明 |
|------|------|
| WebSocket 只传通知，不传数据 | 看板拖拽 → REST 写库 → WS 发 refresh → 客户端自己拉 |
| room 核心模型用 UUID PK | Project/Column/Task 都是 UUID，AI 工具反复强调这一点 |
| Channels type 必须等于 Consumer 方法名 | 否则 Channels 找不到 handler 静默丢消息 |
| qa_center 新旧两套 API 测试并存 | 旧版：ApiTestCase + test_executor；新版：ApiAutoTestCase + api_auto_executor |
| UI 测试走子进程模式 | Django 主进程不直接跑 Playwright，通过 stdin/stdout JSON Lines 通信 |

### 1.5 已确认的文档与代码不一致清单（每次学习前核对）

以下是之前读代码发现 PROEJCT_DEEP_DIVE.md 文档与实际代码不符的地方，**以后不要根据错误结论推理**：

| # | 文档说的 | 代码实际情况 | 严重程度 |
|---|---------|-------------|---------|
| 1 | `_send_notification` group_send type 是 `system_message` | 实际是 `type: 'global_notification'`（对应 GlobalConsumer.global_notification 方法），文档写错了 Channels type | 中 |
| 2 | AI 工具名有 `run_api_test_case` | 实际是 `run_api_test`（少了个 _case） | 低 |
| 3 | Tool Calling 3 轮后返回"已超过工具调用上限" | 实际是 `while tool_rounds < 3`，3 轮后不报错，而是**再调一次不带 tools 的请求做最终总结** | 高 |
| 4 | `run_api_test` 工具用 `requests`（旧版执行器已演化） | 实际仍用 `from django.test import Client`，只能打项目内部 URL | 高 |
| 5 | Locust 固定文件名 `locustfile_current.py`，同时只能跑一个 | 实际已改成 `locustfile_{execution_id}.py` + `metrics_{execution_id}.json`，支持并发 | 中 |

---

## 二、8 模块学习计划

### 学习顺序说明

按**依赖关系从底层到上层**排列。每个模块学完后，下一个模块需要的概念都已建立：

```
1. 基础架构 → 2. WebSocket → 3. room 看板 → 4. AI → 5. QA API
                                                        → 6. QA UI
                                                        → 7. 性能/DevOps
                                                        → 8. Bug/System
```

---

### 模块 1：基础架构

#### A. 职责一句话

Django 项目的骨架——配置、入口、路由、服务调度。

#### A. 必读源码清单

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★★ | `backend/backend/settings.py` | INSTALLED_APPS、DATABASES、CHANNEL_LAYERS、CELERY、CORS、REST_FRAMEWORK、MEDIA/STATIC |
| ★★★ | `backend/backend/asgi.py` | ProtocolTypeRouter：HTTP→Django ASGI / WS→URLRouter |
| ★★★ | `backend/backend/urls.py` | 顶层 URL 分发：/api/→room / /api/qa/→qa_center / /api/system/→system / /api/→bug_tracker |
| ★★☆ | `backend/backend/celery.py` | Celery 初始化、search_index_update task |
| ★★☆ | `backend/backend/tasks.py` | 搜索索引异步更新 |
| ★☆☆ | `backend/backend/throttles.py` | 登录限流 5/min |
| ★☆☆ | `backend/manage.py` | Django 入口 |

#### B. 核心流程

```
uvicorn backend.asgi:application
  → asgi.py: get_asgi_application()  # 初始化 Django
  → asgi.py: ProtocolTypeRouter {
        "http"     → django_asgi_app
        "websocket" → AuthMiddlewareStack → URLRouter(room.routing.websocket_urlpatterns)
    }
  → HTTP 请求 → urls.py → 分发到各 app 的 urls
  → WebSocket → room.routing → Board/Chat/Global + qa_center.routing → 5 条 QA WS
```

#### C. 学习检查点

- [ ] `asgi.py` 里 `get_asgi_application()` 为什么必须在 import routing 之前？
- [ ] `INSTALLED_APPS` 包括哪 4 个自有 app + 哪些第三方？
- [ ] `CORS_ALLOWED_ORIGINS` 配置了哪些 Origin？Cookie 怎么跨域？
- [ ] Celery broker 和 Channel Layer 用的 Redis 分别是哪个 db？
- [ ] `/api/` 同时 include 了 room 和 bug_tracker，路由冲突了怎么办？

#### D. 与其他模块的交界点

- `asgi.py` 是 WebSocket 模块的唯一入口
- `urls.py` 决定了每个 HTTP 请求进哪个 app
- `settings.py` 的 INSTALLED_APPS 决定哪些模块被加载

---

### 模块 2：WebSocket 实时层

#### A. 职责一句话

项目中所有实时推送的通道层——看板/聊天/通知/QA 进度/录制/性能指标全部走 WS。

#### A. 必读源码清单

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★★ | `backend/room/routing.py` | WS 路由汇总：board + chat + global + qa_center 5 条 |
| ★★★ | `backend/room/consumers.py` | BoardConsumer：鉴权(4003) + group_add + receive(空壳) + board_update |
| ★★★ | `backend/room/consumers_chat.py` | ChatConsumer：Redis Stream 持久化 + xrange 历史回放 + HTML 转义 |
| ★★☆ | `backend/room/consumers_global.py` | GlobalConsumer：system_broadcast group + global_notification 方法（⚠️ 注意不是 system_message） |
| ★★★ | `backend/qa_center/routing.py` | 5 条 QA WS 路由 |
| ★★★ | `backend/qa_center/consumers.py` | QAConsumer / RecorderConsumer / PerformanceTestConsumer / TestRunProgressConsumer / UiRunConsumer |
| ★★☆ | `frontend/src/stores/composables/useWebSocket.ts` | 通用 WS 封装：心跳30s + 重连3s + 观察者模式 |

#### B. 8 条 WebSocket 全表

| 路径 | Consumer | Group | 鉴权 | 用途 |
|------|----------|-------|------|------|
| `/ws/board/<project_id>/` | BoardConsumer | `board_{project_id}` | 项目成员 | 看板实时同步 |
| `/ws/chat/<project_id>/` | ChatConsumer | `chat_{project_id}` | 项目成员 | 聊天室 |
| `/ws/global/` | GlobalConsumer | `system_broadcast` | 已认证 | 全局通知 |
| `/ws/qa/dashboard/` | QAConsumer | `qa_dashboard` | 无 | 测试执行进度 |
| `/ws/qa/recorder/` | RecorderConsumer | `recorder_{channel_name}` | 无 | UI 录制器 |
| `/ws/qa/performance/<id>/` | PerformanceTestConsumer | `performance_test_{id}` | 无 | 性能指标 |
| `/ws/qa/test-run/<id>/` | TestRunProgressConsumer | `test_run_{id}` | 无 | TestRun 进度 |
| `/ws/qa/run/<task_id>/` | UiRunConsumer | `ui_run_{task_id}` | 无 | UI 回放进度 |

#### C. 核心流程（以看板为例）

```
用户 A 浏览器                     Django                       用户 B 浏览器
     │                              │                              │
     │── connect ws/board/proj1/ ──→│                              │
     │                              │── group_add(board_proj1)     │
     │                              │── check member → 鉴权        │
     │←── accept ──────────────────│                              │
     │                              │                              │
     │── PATCH /api/tasks/{id} ────→│                              │
     │                              │── Task.objects.update()      │
     │                              │── group_send(board_proj1,    │
     │                              │     {type: 'board_update',   │
     │                              │      action: 'refresh'})     │
     │                              │                              │
     │                              │                              │── board_update(event)
     │                              │                              │── ws.send(refresh)
     │                              │                              │── GET /api/columns/
     │                              │                              │── 重新拉数据
```

#### D. 学习检查点

- [ ] Channels 鉴权失败为什么 `close(4003)` 而不是 401？
- [ ] ChatConsumer 为什么用 Redis Stream 而不是 MySQL？
- [ ] `group_send` 的 `type` 字段为什么必须等于 Consumer 上的方法名？
- [ ] `RecorderConsumer` 的 group 为什么是 `recorder_{channel_name}` 而不是固定名？
- [ ] 前端 `useWebSocket.ts` 心跳多久一次？重连多久？怎么区分主动关闭和网络断开？

---

### 模块 3：room 看板协作

#### A. 职责一句话

项目管理 + 看板任务 + Sprint + 通知 + 评论/附件/活动日志 + AI 对话持久化。

#### A. 必读源码清单

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★★ | `backend/room/models.py` | 全部 16 个模型：Project/Column/Task/Tag/Notification/TaskComment/TaskAttachment/TaskActivityLog/AuditLog/AIConversation/AIMessage/Sprint/SprintTask/ProjectApiDoc/ProjectRole/ProjectMember |
| ★★☆ | `backend/room/urls.py` | 50+ API 路由 |
| ★★☆ | `backend/room/views/board.py` | Task CRUD + batch delete + move + search |
| ★★☆ | `backend/room/views/project.py` | Project CRUD + invite + RAG |
| ★☆☆ | `backend/room/views/auth.py` | Login/Logout/Me |
| ★☆☆ | `backend/room/views/comment.py` | 评论 + WebSocket |
| ★☆☆ | `backend/room/views/notification.py` | 通知列表/已读 |
| ★☆☆ | `backend/room/views/sprint.py` | Sprint + 燃尽图 |
| ★★☆ | `backend/room/serializers.py` | 20+ 序列化器 |
| ★★☆ | `frontend/src/router/index.ts` | 27 子路由 + beforeEach 权限守卫 |
| ★★★ | `frontend/src/stores/board/index.ts` | 看板聚合 Store（组合 column/task/tag/user） |
| ★★☆ | `frontend/src/views/Board.vue` | 看板主视图 |

#### B. 核心模型关系

```
Project (UUID)
  ├── 1:N ── Column (UUID)
  │            └── 1:N ── Task (UUID)
  │                       ├── N:N ── Tag
  │                       ├── 1:N ── TaskComment
  │                       ├── 1:N ── TaskAttachment
  │                       ├── 1:N ── TaskActivityLog
  │                       ├── N:N ── ApiTestCase（旧）
  │                       └── N:N ── UiTestCase
  ├── 1:N ── Sprint ── N:N ── Task
  ├── 1:N ── ProjectRole ── 1:N ── ProjectMember
  ├── 1:N ── Notification
  ├── 1:N ── AIConversation ── 1:N ── AIMessage
  ├── 1:N ── ProjectApiDoc
  └── 1:N ── Bug（来自 bug_tracker）
```

#### C. 关键信号（Django Signals）

- `post_save User` → 自动创建 UserProfile
- `post_save Task` → 创建 TaskActivityLog（created）
- `pre_save Task` → 检测 title/column/assignee 变化 → 创建 TaskActivityLog
- `post_save Project` → 创建 4 个默认角色（Owner/Admin/Editor/Viewer）

#### D. 学习检查点

- [ ] Project/Column/Task 为什么用 UUID 而不是自增 ID？
- [ ] task 拖拽排序用的是什么算法（position 浮点数还是什么）？
- [ ] BoardConsumer.receive 里 move_task 为什么是空壳？
- [ ] 前端的 `useBoardStore` 为什么是聚合模式？
- [ ] `DEFAULT_PROJECT_ROLES` 定义了哪 4 级权限？各自的权限有哪些？

---

### 模块 4：AI 助手

#### A. 职责一句话

基于 DeepSeek 的项目 AI 助手——项目上下文 + 多轮对话 + Tool Calling（17 个工具） + 流式 SSE + 项目分析。

#### A. 必读源码清单

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★★ | `backend/room/ai_utils.py` | SYSTEM_PROMPT、build_project_context、AVAILABLE_TOOLS(17个)、execute_tool(大 if-elif)、客户端初始化 |
| ★★★ | `backend/room/views/ai.py` | AIChatView（Tool Calling）、AIStreamChatView（SSE）、健康度/周报/风险/Sprint 分析 |
| ★★☆ | `frontend/src/views/AIChat.vue` | AI 聊天界面 |

#### B. AI 调用两条路径

```
路径1：非流式 + Tool Calling（用于需要操作的请求）
  AIChat.vue → POST /api/ai/chat/
    → build_project_context()            # 查 DB 拼上下文
    → _chat_with_tools()                 # while tool_rounds < 3
        → DeepSeek chat.completions.create(tools=AVAILABLE_TOOLS)
        → if msg.tool_calls:
            → execute_tool(name, args)   # 操作 DB
            → 结果塞回 messages
            → tool_rounds += 1
        → else: return msg.content       # 收敛了，返回答案
    → 写 AIMessage（user + assistant 两条）

路径2：流式 SSE（纯问答，不操作）
  AIChat.vue → POST /api/ai/chat/stream/
    → get_streaming_answer()             # stream=True
    → StreamingHttpResponse(generator)
    → 前端逐字显示
    → 流结束后写 AIMessage
```

#### C. 17 个 AI 工具一览

| 分类 | 工具名（实际代码中的名称） | 功能 |
|------|--------------------------|------|
| 看板 | `create_task` | 创建任务 |
| 看板 | `update_task_assignee` | 分配负责人 |
| 看板 | `move_task` | 移动任务 |
| 看板 | `search_tasks` | 搜索任务 |
| 看板 | `get_project_stats` | 项目统计 |
| API 测试 | `create_api_test_case` | 创建 API 用例 |
| API 测试 | `list_api_cases` | 列出 API 用例 |
| API 测试 | `run_api_test` | 运行 API 用例（⚠️ 非 run_api_test_case） |
| UI 测试 | `create_ui_test_case` | 创建 UI 用例 |
| UI 测试 | `generate_ui_steps` | 生成 UI 步骤 |
| UI 测试 | `list_ui_cases` | 列出 UI 用例 |
| 测试执行 | `create_test_task` | 创建测试任务 |
| 测试执行 | `execute_test_task` | 执行测试任务 |
| CI/CD | `trigger_pipeline` | 触发流水线 |
| 文档 | `get_api_docs` | 获取 API 文档 |
| 分析 | `get_test_stats` | 测试统计 |
| 分析 | `get_recent_failures` | 最近失败用例 |

#### D. 学习检查点

- [ ] `build_project_context` 包含哪几个 section？截断策略是什么？
- [ ] Tool Calling 为什么 `while tool_rounds < 3`，3 轮后发生了什么？（⚠️ 注意代码实际情况）
- [ ] `execute_tool("run_api_test", ...)` 用的是什么 HTTP 客户端？（⚠️ 不是 requests）
- [ ] `AIStreamChatView` 的流结束后怎么持久化 AIMessage？
- [ ] `generate_ui_steps` 工具为什么返回 `UI_STEPS_GENERATE|...` sentinel？
- [ ] DeepSeek 调用有哪几层异常处理？402 状态码返回什么？

---

### 模块 5：QA API 测试

#### A. 职责一句话

API 测试用例管理 + 执行引擎——包含新旧两套体系、变量模板、断言引擎、变量提取器、测试计划。

#### A. 必读源码清单

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★★ | `backend/qa_center/models.py` | 全部模型：两套 API 测试模型 + 断言/提取器/结果/环境/变量/计划 |
| ★★★ | `backend/qa_center/api_auto_executor.py` | ApiAutoTestExecutor：变量池→渲染→requests→断言→提取→写结果→建Bug |
| ★★☆ | `backend/qa_center/test_executor.py` | 旧版执行器 |
| ★★★ | `backend/qa_center/unified_assertions.py` | 统一断言层，两套都调用 |
| ★★☆ | `backend/qa_center/template_engine.py` | `{{var}}` 渲染 + base_url 拼接 + 变量池三层优先级 |
| ★★☆ | `backend/qa_center/extractors.py` | 变量提取器 |
| ★★☆ | `backend/qa_center/request_builder.py` | Query 参数 / Form 文件 |
| ★★☆ | `backend/qa_center/bug_utils.py` | 自动建 Bug |

#### B. 新旧两套 API 测试对比

| | 旧版 | 新版 |
|---|------|------|
| 核心模型 | `ApiTestCase` | `ApiAutoTestCase`（在 Suite 下） |
| 断言 | `expected_response.assertions` 数组 | 独立 `ApiAutoTestAssertion` 模型 |
| 变量提取 | `response_extractions` 字段 | 独立 `ApiAutoTestExtractor` 模型 |
| 执行方式 | `test_executor.py`（仍用 Django test Client） | `api_auto_executor.py`（用 requests 库） |
| 变量池 | 无 | 有（全局→环境→上游 三层） |
| 模板渲染 | 无 | 支持 `{{var}}` |
| 批量执行 | TestRun + TestRunCaseResult | ApiAutoTestResult + ApiAutoTestCaseResult |
| 前端页面 | ApiCaseList/Detail.vue | BatchRunExecuteDialog.vue |

#### C. 新版执行器核心流程

```
ApiAutoTestExecutor(suite_id).execute()
  → 1. 加载 suite + active_cases（按 sort_order 排序）
  → 2. 解析变量池
       build_variable_pool(environment, global_vars)
       优先级：globals（低）< environment（中）< overrides（高）
  → 3. 创建 ApiAutoTestResult(status='running')
  → 4. for case in active_cases:
       → render_value(headers)        # 渲染 headers 中的 {{var}}
       → resolve_url(case.url)        # base_url 拼接
       → render_string(case.body)     # 渲染 body 中的 {{var}}
       → normalize_query_params()
       → build_file_tuples()
       → requests.request(method, url, headers, params, json/data, files, timeout=30)
       → ResponseContext.from_raw(...)
       → run_assertions(active_assertions, ctx)    # 统一断言
       → expected_status 兜底检查
       → 写 ApiAutoTestCaseResult
  → 5. 汇总 → 更新 ApiAutoTestResult status
  → 6. 如果 failed/error → 自动创建 Bug
```

#### D. 学习检查点

- [ ] 变量池三层优先级从低到高分别是什么？
- [ ] `{{var}}` 找不到时是报错还是保留原样？为什么？
- [ ] 新版执行器 timeout 是多少？用的是 `case.timeout_seconds` 还是写死的值？
- [ ] `headers = case.headers` 后有没有做 copy？
- [ ] 自动建 Bug 的去重逻辑是什么？用哪三个字段？
- [ ] 旧版为什么叫"旧版"但还没有废弃？什么场景还在用？
- [ ] `_smart_eq` 为什么要单独处理 `bool` 类型？
- [ ] `expected_status` 兜底检查什么时候触发？

---

### 模块 6：QA UI 测试

#### A. 职责一句话

Playwright 浏览器录制 + 回放——通过子进程模式实现，Django 主进程不直接跑 Playwright。

#### A. 必读源码清单（本期最复杂）

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★★ | `backend/qa_center/workers/runner_supervisor.py` | execute_ui_case：子进程启停 + watchdog + stderr drain + 全局注册表 |
| ★★★ | `backend/qa_center/workers/runner_worker.py` | Worker 入口：接收 stdin case_data → Playwright 执行步骤 → stdout 事件 |
| ★★★ | `backend/qa_center/workers/recorder_supervisor.py` | RecorderSession：启停 send/stop + 读 stdout + drain stderr |
| ★★★ | `backend/qa_center/workers/recorder_worker.py` | 录制 Worker：Playwright + CDP + 注入 JS + 稳定 selector 算法 + el-select 特殊处理 |
| ★★☆ | `backend/qa_center/consumers.py` | RecorderConsumer（双向命令）+ _map_event（事件名映射） |
| ★★☆ | `frontend/src/views/qa/UiCaseDetail.vue` | UI 用例编辑页 |
| ★★☆ | `frontend/src/views/qa/components/RecorderPanel.vue` | 录制面板 |
| ★★☆ | `frontend/src/composables/useRecorderSocket.ts` | 录制 WS 状态机 |

#### B. 录制流程

```
用户点"开始录制"
  → useRecorderSocket.ts 连 ws/qa/recorder/
  → 发 {command: "start_recording", url, viewport}
  → RecorderConsumer.start()
      → RecorderSession.start()
          → subprocess.Popen([python, -m, qa_center.workers.recorder_worker])
          → send({"cmd": "start", "url": "...", "viewport": {}})
  → recorder_worker:
      → Playwright launch chromium (headless=False)
      → context.add_init_script(RECORDING_SCRIPT)  # 注入 JS
      → page.expose_binding("onRecordEvent", on_record_event)
      → page.goto(url)
      → 用户在浏览器里点 → JS emit → stdout JSON → supervisor 读 → WS 推前端
  → 前端 RecorderPanel 实时追加步骤到列表
  → 用户点"停止录制" → 步骤保存到 UiTestCase.steps
```

#### C. 回放流程

```
用户点"运行"
  → POST /api/qa/ui-cases/{id}/run/ → 返回 {task_id}
  → execute_ui_case(case_data, on_event)
      → subprocess.Popen([python, -m, qa_center.workers.runner_worker])
      → register_runner(task_id, proc)     # 全局表
      → stdin.write(case_data_json + '\n')
      → watchdog Timer(300s)               # 超时 terminate
      → stderr drain 线程                  # 防管道满
      → for line in proc.stdout:           # 逐行读事件
          → json.loads(line)
          → on_event(event)                # group_send 到 ui_run_{task_id}
          → if event.type == 'finished': break
      → unregister_runner(task_id)
  → 前端 ws/qa/run/{task_id}/ ← UiRunConsumer ← 实时进度
```

#### D. 子进程 IPC 设计要点

```
Django 主进程                     Worker 子进程 (Playwright)
     │                                    │
     │── subprocess.Popen ────────────────→│ 启动
     │── stdin.write(json + '\n') ────────→│ 发命令/数据
     │── stdin.close() ───────────────────→│ 通知不再有输入
     │                                    │
     │←── stdout line by line ────────────│ 读事件
     │    (JSON Lines 格式)                │
     │                                    │
     │   watchdog Timer(300s)             │ 超时保护
     │   stderr drain thread              │ 防阻塞
     │                                    │
     │── proc.terminate() ───────────────→│ 中止
     │── unregister ─────────────────────→│ 清理
```

#### E. 学习检查点

- [ ] 录制时注入的 JS 里稳定 selector 算法优先级是什么？（id → data-testid → role+name → text → class chain → nth-child）
- [ ] `el-id-*` 为什么被过滤？不过滤会怎样？
- [ ] el-select 下拉项录制时做了什么特殊处理？为什么？
- [ ] `_RUNNERS` 全局表有什么已知限制？
- [ ] `_EVENTS` 缓存是干嘛的？TTL 多久？
- [ ] worker 进程 segfault 了，主进程怎么知道？
- [ ] stdout 读的是 JSON Lines 而不是 protobuf，理由是什么？
- [ ] `_map_event` 做了什么？为什么需要这个映射？

---

### 模块 7：性能测试 + DevOps

#### A. 职责一句话

Locust 无界压测 + DevOps Dashboard/CI-CD/Pipeline/TestTask/质量报告。

#### A. 必读源码清单

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★★ | `backend/qa_center/locust_runner.py` | 动态生成 locustfile + 文件 IPC + monitor 线程 + p50/p90/p95/p99 |
| ★★☆ | `backend/qa_center/views_performance.py` | 性能测试 API + WS 推送 |
| ★★★ | `backend/qa_center/views_devops.py` | Dashboard + CI/CD + Pipeline + TestTask + _send_notification + Webhook |
| ★★☆ | `frontend/src/views/qa/DevOpsPlatform.vue` | DevOps 仪表板 |
| ★★☆ | `frontend/src/api/devops.ts` | DevOps API 封装 |

#### B. 性能测试流程

```
POST /api/qa/performance-cases/{id}/start/
  → LocustRunner.start_test()
      → generate_locustfile(test_case, metrics_file)
          → 拼 Python 代码 → 写入 locustfile_{execution_id}.py
              → @events.request.add_listener 实时写 metrics
              → @events.test_stop.add_listener 标记完成
      → subprocess.Popen(["locust", "-f", file, "--headless", ...])
      → _monitor_process 线程
          → while proc alive:
              → 读 metrics_file (JSON)
              → 更新 TestMetrics(p50/p90/p95/p99/throughput/error_rate)
              → _notify_callbacks
              → sleep(0.5)
  → callback → group_send("performance_test_{id}")
      → PerformanceTestConsumer.test_update → ws.send
          → 前端实时图表
```

#### C. DevOps 四块业务

```
1. Dashboard 大盘
   GET /api/qa/devops/stats/
   → TestResult 聚合查询 → 总数/通过/失败/类型分布/30天趋势

2. CI/CD 配置
   GET/POST/PATCH/DELETE /api/qa/devops/cicd-config/
   → CiCdConfig 模型 CRUD

3. Pipeline 触发/Webhook
   触发：POST /api/qa/devops/cicd-config/{id}/trigger/
        → PipelineRun(status='running') → 后台模拟（⚠️ 真实 CI 集成未完成）
   Webhook：POST /api/qa/devops/cicd-config/{id}/webhook/（permission_classes=[]）
        → X-CI-Token header 校验 → 外部上报 Pipeline 结果

4. TestTask 编排
   POST /api/qa/devops/tasks/{id}/execute/
   → 后台线程 _execute_test_task()
       → 调旧版 execute_api_test_cases / execute_ui_test_cases
       → 写 TestResult
       → _send_notification()
           → group_send('system_broadcast', {type: 'global_notification', ...})
           → bulk_create Notification
```

#### D. 学习检查点

- [ ] 性能测试和主 Django 进程通过什么方式通信？
- [ ] Locust 文件已按什么字段隔离？支持并发了吗？
- [ ] p95/p99 怎么计算的？时间复杂度？
- [ ] 读取 metrics_file 时被 Locust 写了一半怎么办？
- [ ] `_send_notification` 的 level 是根据什么判断的？（代码里是文字匹配）
- [ ] Webhook 端点 `permission_classes=[]` 安全吗？
- [ ] TestTask 用 threading 不用 Celery，有什么问题？
- [ ] 开启 UI_TEST_DEBUG 时事件流写到哪里？

---

### 模块 8：Bug 缺陷 + System 权限

#### A. 职责一句话

Bug 状态机管理 + 系统级菜单/角色/用户 RBAC。

#### A. 必读源码清单

| 优先级 | 文件 | 关注点 |
|--------|------|--------|
| ★★☆ | `backend/bug_tracker/models.py` | Bug/BugTransition/BugComment 模型 |
| ★★☆ | `backend/bug_tracker/views.py` | BugViewSet + 统计 + 演示数据 |
| ★★☆ | `backend/bug_tracker/state_machine.py` | 9 状态流转规则 |
| ★★☆ | `backend/system/models.py` | Menu/Role/SystemUserProfile |
| ★★☆ | `backend/system/views.py` | 菜单树/角色 CRUD/用户管理/权限查询 |
| ★★☆ | `backend/system/permissions.py` | HasSystemPermission |
| ★★☆ | `frontend/src/views/bug/BugList.vue` | Bug 列表 |
| ★★☆ | `frontend/src/views/bug/BugDetail.vue` | Bug 详情 + 状态流转 |
| ★★☆ | `frontend/src/router/index.ts` | beforeEach 权限守卫 |
| ★★☆ | `frontend/src/directives/permission.ts` | v-permission 指令 |

#### B. Bug 状态机

```
open → confirmed → assigned → in_progress → fixed → verified → closed
  │                                            │         ↑
  └────────── wontfix ─────────────────────────┘         │
  └────────── reopened ──────────────────────────────────┘
```

#### C. 两层权限体系

```
系统级 RBAC：
  Menu（菜单/权限点，三级树：目录/菜单/按钮）
    ↕ N:N
  Role（角色）
    ↕
  SystemUserProfile（用户）

项目级 RBAC：
  ProjectRole（Owner/Admin/Editor/Viewer 四级）
    ↕
  ProjectMember（用户 + 角色）

前端：
  router beforeEach → authStore.checkPermission(meta.permission)
  v-permission 指令 → 按钮级显隐
```

#### D. 学习检查点

- [ ] Bug 状态机有哪些状态？合法流转有哪些？
- [ ] `create_bug_from_test_failure` 怎么避免重复建 Bug？
- [ ] 系统权限和项目权限有什么区别？
- [ ] 前端路由守卫怎么拒绝无权限访问？
- [ ] `v-permission` 指令怎么工作？

---

## 三、进度看板

| 阶段 | 模块 | 状态 | 开始日期 | 完成日期 | 笔记 |
|------|------|------|---------|---------|------|
| 1 | 基础架构 | ⬜ 未开始 | — | — | — |
| 2 | WebSocket 实时层 | ⬜ 未开始 | — | — | — |
| 3 | room 看板协作 | ⬜ 未开始 | — | — | — |
| 4 | AI 助手 | ⬜ 未开始 | — | — | — |
| 5 | QA API 测试 | ⬜ 未开始 | — | — | — |
| 6 | QA UI 测试 | ⬜ 未开始 | — | — | — |
| 7 | 性能测试 + DevOps | ⬜ 未开始 | — | — | — |
| 8 | Bug + System | ⬜ 未开始 | — | — | — |

状态说明：⬜ 未开始 | 🔄 学习中 | ✅ 已吃透

---

## 四、学习笔记区

> 每学完一个模块，在下面追加关键发现、易错点、代码片段引用。
>
> 格式：`## 模块N：xxx` + 日期 + 内容。

---

<!-- 示例笔记模板：
## 模块1：基础架构（2026-06-29）

### 关键发现
- xxx

### 易错点
- xxx

### 待深入
- xxx
-->

---

*本文件是学习进度跟踪文档，不是权威代码文档。所有结论以源码为准。*
