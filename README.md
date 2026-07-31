# FlowSpace (SyncBoard) - 项目协作看板系统

FlowSpace 是一个基于 Django + Vue 3 的企业级全栈项目协作平台，集成了看板管理、实时同步、AI 智能助手、QA 质量中心、DevOps 平台、Bug 追踪、RBAC 权限管理和迭代管理。

---

## 技术栈

### 后端
| 组件 | 技术 |
|------|------|
| Web 框架 | Django (>=4.0, <7.0) |
| REST API | Django REST Framework (分页 + 限流) |
| 实时通信 | Django Channels + Redis Channel Layer (项目鉴权) |
| 异步任务 | Celery (Redis Broker/Backend) |
| 主数据库 | MySQL 8.0 |
| 全文搜索 | Haystack + Elasticsearch 7.x |
| 中文分词 | jieba + Ngram 自定义后端 |
| AI 集成 | DeepSeek API (OpenAI 兼容, 流式 SSE + Tool Calling) |
| 测试 | pytest + pytest-django + Playwright + Locust |
| 文件处理 | Pillow (头像/附件安全处理) |
| 静态文件 | Whitenoise |
| AI | DeepSeek API (OpenAI 兼容, 支持流式 SSE + Tool Calling) |

### 前端
| 组件 | 技术 |
|------|------|
| 框架 | Vue 3.5 (Composition API, `<script setup>`) |
| 语言 | TypeScript ~5.9 |
| 构建工具 | Vite 7 |
| UI 组件库 | Element Plus 2 |
| 状态管理 | Pinia 3 (模块化 board Store) |
| 路由 | Vue Router 4 (懒加载 + 权限守卫) |
| HTTP | Axios (withCredentials + CSRF) |
| 拖拽 | vuedraggable 4 |
| 图表 | ECharts 6 (雷达图、趋势图、燃尽图) |
| Markdown | marked 17 |
| 测试 | Vitest + @vue/test-utils |

### 基础设施
- **CI/CD**: GitHub Actions (lint → security scan → tests → e2e → deploy)
- **容器化**: Docker Compose (MySQL 8, Redis 7, ES 7.17, Celery Worker)
- **WebSocket**: 自动重连 3s + 心跳 30s + 观察者模式 + 项目鉴权
- **安全**: DRF 全局限流 + 登录限流 5/min + 系统/项目级 RBAC + 审计日志
- **深色模式**: CSS 变量 + localStorage 持久化 + prefers-color-scheme

---

## 项目结构

```
SyncBoard/
├── .github/workflows/
│   ├── ci.yml.disabled             # CI: lint/安全/单元测试/E2E (暂禁用)
│   └── cd.yml.disabled             # CD: 自动部署 staging/production (暂禁用)
├── backend/
│   ├── backend/
│   │   ├── settings.py             # Django 配置 (分页/限流/CORS/ES/Celery)
│   │   ├── asgi.py                 # ASGI 入口 (HTTP → Django, WS → Channels)
│   │   ├── wsgi.py                 # WSGI 入口 (传统部署)
│   │   ├── urls.py                 # 根路由 (4 应用 + admin + media)
│   │   ├── authentication.py       # CSRF豁免会话认证
│   │   ├── api_errors.py           # 统一错误码响应
│   │   ├── utils.py                # 自定义异常处理器
│   │   ├── throttles.py            # 登录/AI/WS 限流
│   │   ├── celery.py               # Celery 初始化
│   │   ├── tasks.py                # 搜索索引异步任务
│   │   ├── signal_processors.py    # Celery 信号处理器
│   │   └── conftest.py             # pytest WebSocket 实时上报
│   ├── room/                       # 核心业务 (看板/协作/AI/权限)
│   │   ├── models.py               # 17 个数据模型
│   │   ├── serializers.py          # 20+ 序列化器
│   │   ├── ai_utils.py             # RAG + 流式 AI + Tool Calling
│   │   ├── project_access.py       # 项目成员鉴权辅助
│   │   ├── views/                  # 模块化视图 (15 个文件)
│   │   │   ├── auth.py             # 认证
│   │   │   ├── board.py            # 看板列/任务
│   │   │   ├── project.py          # 项目 CRUD + 邀请
│   │   │   ├── tag.py              # 标签 (项目门控)
│   │   │   ├── user.py             # 用户列表/头像
│   │   │   ├── notification.py     # 通知 (含标记已读)
│   │   │   ├── comment.py          # 任务评论 + WS 广播
│   │   │   ├── activity.py         # 任务动态日志
│   │   │   ├── attachment.py       # 文件附件 (含安全处理)
│   │   │   ├── project_role.py     # 项目角色/成员管理
│   │   │   ├── sprint.py           # 迭代/Sprint + 燃尽图
│   │   │   ├── ai.py               # AI 多轮对话 + 流式 SSE + 分析
│   │   │   ├── api_docs.py         # 项目 API 文档管理
│   │   │   └── mixins.py           # 项目权限 Mixin
│   │   ├── consumers.py            # Board WS (看板实时同步, 鉴权)
│   │   ├── consumers_chat.py       # Chat WS (项目聊天, Redis Stream)
│   │   ├── consumers_global.py     # Global WS (全局通知广播)
│   │   ├── routing.py              # WS 路由配置
│   │   ├── search_indexes.py       # Haystack 搜索索引
│   │   └── urls.py                 # 50+ API 路由
│   ├── qa_center/                  # QA 质量中心 + DevOps
│   │   ├── models.py               # 20 个模型 (测试用例/结果/环境/CI/CD)
│   │   ├── serializers.py          # 序列化器
│   │   ├── views.py                # 数据工厂 + 执行入口
│   │   ├── views_api_auto_test.py  # API 测试 ViewSet + 执行
│   │   ├── views_ui_test.py        # UI 测试 ViewSet + 截图
│   │   ├── views_performance.py    # 性能测试 ViewSet
│   │   ├── views_test_result.py    # 测试结果 ViewSet
│   │   ├── views_test_link.py      # 测试↔任务关联
│   │   ├── views_devops.py         # DevOps 面板/CI/CD/Pipeline
│   │   ├── views_run_plan.py       # 测试运行计划
│   │   ├── views_environment.py    # 环境/全局变量管理
│   │   ├── views_test_run.py       # 测试运行生命周期
│   │   ├── tasks.py                # Celery 测试任务
│   │   ├── tasks_test_exec.py      # 执行引擎 Celery 任务
│   │   ├── consumers.py            # QA Dashboard/Recorder/Perf WS
│   │   ├── routing.py              # QA WS 路由
│   │   ├── api_execution/          # API 执行引擎 (orchestrator/runner/transport)
│   │   ├── assertion_core/         # 断言引擎 (IR/操作符)
│   │   ├── execution/              # 通用执行引擎 (lifecycle/runner/workers)
│   │   ├── pipeline/               # CI/CD 客户端 (GitHub/GitLab/Jenkins)
│   │   ├── services/devops/        # DevOps 服务层
│   │   ├── webhooks.py             # Webhook 安全 (HMAC/去重/限流)
│   │   ├── ssrf.py                 # SSRF 出站请求防护
│   │   ├── template_engine.py      # 变量模板引擎
│   │   ├── feature_flags.py        # 功能开关
│   │   └── locust_runner.py        # Locust 无界面压测
│   ├── bug_tracker/                # 缺陷追踪
│   │   ├── models.py               # Bug, BugTransition, BugComment
│   │   ├── views.py                # BugViewSet (CRUD + 流转 + 分配 + 统计)
│   │   ├── serializers.py          # List/Create/Update/Detail 四层序列化器
│   │   ├── state_machine.py        # 9 状态状态机 + 转换规则
│   │   ├── seed.py                 # 演示数据生成
│   │   └── urls.py                 # ViewSet 路由
│   ├── system/                     # 系统 RBAC 管理
│   │   ├── models.py               # Menu, Role, SystemUserProfile
│   │   ├── permissions.py          # HasSystemPermission 强制执行
│   │   ├── views.py                # 权限执行视图 (8×4 方法级鉴权)
│   │   └── urls.py                 # 路由配置
│   ├── tests/                      # 37+ pytest 测试文件
│   ├── performance/                # Locust 性能测试脚本
│   ├── Dockerfile                  # 后端容器 (Playwright 基础镜像)
│   ├── entrypoint.sh               # Docker 启动脚本
│   ├── requirements.txt            # Python 依赖
│   ├── pytest.ini                  # pytest 配置
│   └── manage.py                   # Django 管理入口
│
├── frontend/
│   ├── src/
│   │   ├── App.vue                 # 根组件 (暗色模式切换)
│   │   ├── main.ts                 # 应用入口 (Pinia/Router/ElementPlus)
│   │   ├── router/index.ts         # 路由 (40+ 路由, 懒加载 + 权限守卫)
│   │   ├── stores/
│   │   │   ├── Auth.ts             # 认证 + 权限 (菜单/角色/用户)
│   │   │   ├── notification.ts     # 全局通知 WebSocket
│   │   │   ├── board/              # 模块化看板 Store
│   │   │   │   ├── index.ts        # 聚合 Store + WS 连接管理
│   │   │   │   ├── column.ts       # 列 CRUD
│   │   │   │   ├── task.ts         # 任务 CRUD
│   │   │   │   ├── tag.ts          # 标签 CRUD
│   │   │   │   ├── user.ts         # 用户列表
│   │   │   │   └── types.ts        # 类型定义
│   │   │   └── composables/
│   │   │       └── useWebSocket.ts # 可复用 WS 客户端 (心跳/重连/观察者)
│   │   ├── views/                  # 47 个页面组件
│   │   │   ├── Board.vue           # 主看板 (~944行, 拖拽/搜索/筛选)
│   │   │   ├── ProjectSprints.vue  # 迭代管理
│   │   │   ├── SprintBoard.vue     # 迭代看板 + 燃尽图
│   │   │   ├── ProjectQualityReport.vue  # 五维质量报告
│   │   │   ├── AIChat.vue          # AI 助手 (流式/多轮/分析)
│   │   │   ├── Members.vue         # 成员管理 (角色选择)
│   │   │   ├── Chat.vue            # 项目实时聊天
│   │   │   ├── Settings.vue        # 项目设置 (重命名/删除)
│   │   │   ├── Notifications.vue   # 通知列表
│   │   │   ├── ProjectApiDocs.vue  # API 文档查看器
│   │   │   ├── qa/                 # QA 中心 (14 个页面)
│   │   │   │   ├── QA.vue          # 质量中心仪表板
│   │   │   │   ├── AutoCaseList.vue / AutoCaseDetail.vue
│   │   │   │   ├── UiCaseList.vue / UiCaseDetail.vue
│   │   │   │   ├── TestResultHub.vue / TestResultList.vue / TestResultDetail.vue
│   │   │   │   ├── TestRunList.vue / TestRunDetail.vue
│   │   │   │   ├── DevOpsPlatform.vue
│   │   │   │   ├── PerformanceTestResult.vue
│   │   │   │   └── components/     # QA 子组件 (14 个)
│   │   │   ├── bug/                # Bug 追踪 (4 个页面 + 17 个子组件)
│   │   │   │   ├── BugWorkbench.vue    # 统一 Bug 工作台
│   │   │   │   ├── BugList.vue         # 全部 Bug
│   │   │   │   ├── MyBugs.vue          # 我的 Bug
│   │   │   │   ├── BugDetail.vue       # Bug 详情/编辑
│   │   │   │   └── components/         # BugTable, BugFilterBar, BugStatsCards 等
│   │   │   └── system/             # 系统管理 (3 个页面)
│   │   │       ├── MenuManagement.vue
│   │   │       ├── RoleManagement.vue
│   │   │       └── UserManagement.vue
│   │   ├── components/             # 共享组件
│   │   │   ├── TaskDetailDrawer.vue # 任务详情抽屉 (评论/动态/附件)
│   │   │   ├── PipelineTimeline.vue # CI/CD 流水线时间线
│   │   │   ├── ChatDrawer.vue      # 聊天浮动面板
│   │   │   └── TestConsole.vue     # 测试控制台
│   │   ├── composables/            # 可组合函数
│   │   │   ├── useRecorderSocket.ts # UI 录制器 WS 状态机
│   │   │   └── wsHost.ts           # WS URL 构建 (dev/prod)
│   │   ├── directives/             # 自定义指令
│   │   │   └── permission.ts       # v-permission 系列指令
│   │   ├── api/                    # API 服务模块
│   │   │   ├── bug.ts              # Bug CRUD + 统计
│   │   │   ├── devops.ts           # DevOps 仪表板/CI/CD/任务
│   │   │   ├── runplan.ts          # 测试运行计划
│   │   │   ├── testrun.ts          # 测试运行
│   │   │   └── autoresult.ts       # 自动化测试结果
│   │   ├── styles/                 # 全局样式
│   │   │   ├── variables.css       # 设计令牌 (light + dark)
│   │   │   ├── global.css          # 全局/响应式/Dark Mode
│   │   │   ├── components.css      # 原子化 UI 类
│   │   │   └── element-overrides.css # Element Plus 全局覆写
│   │   ├── types/                  # TypeScript 类型
│   │   ├── utils/                  # 工具函数
│   │   │   ├── request.ts          # Axios 实例 (CSRF/拦截器)
│   │   │   ├── sanitize.ts         # XSS 安全工具
│   │   │   ├── error.ts            # 错误消息提取
│   │   │   └── echartsTheme.ts     # ECharts 主题
│   │   └── __tests__/              # 11 个 Vitest 单元测试
│   ├── Dockerfile                  # 前端容器 (多阶段: Node → Nginx)
│   ├── nginx.conf                  # Nginx 反向代理配置
│   ├── vite.config.ts              # Vite 构建配置
│   ├── vitest.config.ts            # Vitest 测试配置
│   └── package.json
│
├── e2e/                            # Playwright E2E 测试 (10 个文件)
├── api_auto_test_skeleton/         # 独立 pytest API 自动化测试项目
├── test_server/                    # Mock API 测试服务器
├── docs/                           # 项目文档 (16 个 Markdown)
│   ├── 01-项目架构.md
│   ├── 02-数据模型.md
│   ├── 03-WebSocket实时同步.md
│   ├── LEARNING_ROADMAP.md         # 学习路线
│   ├── CODE_MAP.md                 # 代码地图
│   ├── PROJECT_DEEP_DIVE.md        # 技术深潜
│   ├── bug-module-dev-doc.md       # Bug 模块开发文档
│   ├── devops-module.md            # DevOps 模块文档
│   └── ...
├── docker-compose.yml              # 6 服务编排 (MySQL/Redis/ES/Celery/Backend/Frontend)
├── API文档.md
├── DEVELOPMENT_ROADMAP.md
├── CODE_REVIEW.md
└── README.md
```

---

## 核心功能

### 1. 看板管理
- 多项目支持，每项目独立看板 + 默认列 (To Do / In Progress / Done)
- 任务卡片: 标题、描述、负责人、标签、截止日期
- **拖拽排序**: 分数位置算法，列内 + 列间
- **任务详情抽屉**: 点击卡片 → 评论/动态/附件/关联测试
- 按负责人/标签/关键词筛选 + 全文搜索高亮

### 2. 实时同步
- **看板房间** `/ws/board/{project_id}/`: 任务变动实时广播 (鉴权)
- **聊天房间** `/ws/chat/{project_id}/`: Redis Stream 持久化 (鉴权)
- **全局通知** `/ws/global/`: 系统通知 + DB 持久化
- **QA 直播间** `/ws/qa/dashboard/`: 测试日志实时推送
- 自动重连 3s + 心跳 30s + 观察者模式

### 3. 协作功能
- **任务评论**: 嵌套回复 + WebSocket 实时同步
- **任务动态**: 自动记录 创建/更新/移动/分配/评论
- **任务附件**: 上传/下载/删除 (10MB, CSRF 保护)
- **项目角色**: Owner / Admin / Editor / Viewer 四级权限
- **审计日志**: 所有关键操作可追溯

### 4. AI 智能助手
- **RAG 问答**: Elasticsearch 检索 → DeepSeek 回答
- **多轮对话**: AIConversation + AIMessage 持久化
- **流式响应 SSE**: 逐字显示 (OpenAI stream)
- **项目分析**: 健康度评分、周报生成、风险识别
- Markdown 渲染 + 任务引用来源

### 5. QA 质量中心
- **API 测试**: HTTP 用例管理 + JSONPath 断言 + 批量执行
- **UI 测试**: Playwright 录制器 + 步骤配置 + 截图
- **性能测试**: Locust 无界面压测 + 实时指标图表
- **自动化测试**: 套件/用例/断言 三层管理
- **自动建 Bug**: 测试失败 → 自动创建关联缺陷任务
- **数据工厂**: Faker 批量生成测试数据

### 6. DevOps 平台
- **CI/CD 配置**: Jenkins/GitLab/GitHub 数据库持久化
- **Pipeline 时间线**: 执行历史可视化 + Webhook 回调
- **测试任务调度**: 手动/定时 Cron/Webhook 触发
- **Dashboard**: 趋势/分布/通过率统计

### 7. Bug Tracker（缺陷追踪）
- **9 状态状态机**: open → confirmed → in_progress → fixed → testing → verified → closed（含 rejected/duplicate 终止态）
- **工作台视图**: 统一 Bug 列表 + 我的 Bug + 统计卡片 + 筛选栏
- **流转管理**: 严格状态转换规则引擎，`BugTransition` 审计日志
- **自动建 Bug**: 测试失败/错误 → 自动创建关联缺陷（source_test_type/source_case_id/source_result_id 可溯源）
- **生命周期可视化**: BugDetail 页展示完整流转时间线 + 生命周期进度条
- **多维度筛选**: 按状态/严重程度/优先级/负责人/报告人过滤

### 8. 项目质量报告
- **五维评分**: 测试覆盖 / 通过率 / 性能 / Bug密度 / 部署成功率
- **雷达图 + 趋势图**: ECharts 可视化
- **30天趋势**: 每日测试通过率变化

### 9. 迭代/Sprint 管理
- 迭代 CRUD + 任务添加/移除
- **燃尽图**: 理想线 vs 实际剩余 (ECharts)
- 完成进度条 + 任务状态追踪

### 10. RBAC 权限管理
- **系统级**: Menu/Role/User → HasSystemPermission 强制执行
- **项目级**: ProjectRole (4级) / ProjectMember → HasProjectRole
- **前端**: 路由权限守卫 + `v-permission` 响应式指令
- **WebSocket**: 项目成员鉴权 (connect 时检查)

### 11. 安全特性
- DRF 全局限流 (匿名100/min, 认证1000/min) + 登录 5/min
- 系统管理 API 按方法鉴权 (8 View × 4 HTTP 方法)
- WebSocket 项目鉴权 (非成员 → close 4003)
- 文件上传安全 (签名校验 + 重编码 + 类型白名单)
- XSS 防护 + CSRF Token + CORS 白名单
- 审计日志 (user/action/resource/ip)

### 12. 用户体验
- **Dark Mode**: 切换按钮 + localStorage + 跟随系统
- **响应式**: 768px/1024px 断点，看板列纵向堆叠，侧边栏折叠
- **统一状态**: LoadingState / ErrorState / EmptyState 模式
- **快捷键入口**: 侧边栏直达迭代/质量报告/AI 助手

---

## 快速开始

### 环境要求
- Python 3.11+ | Node.js 20.19+ | MySQL 8.0 | Redis 7
- Elasticsearch 7.17 (可选 — 仅全文搜索功能需要)

### Docker 启动基础设施 (推荐)

```bash
# 启动 MySQL + Redis + Elasticsearch + Celery Worker
docker-compose up -d db redis elasticsearch celery_worker

# 或仅启动必要服务
docker-compose up -d db redis
```

### 后端

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # 编辑数据库/Redis/AI 配置
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_ci_data          # 可选: 示例项目数据
python manage.py seed_bugs_demo        # 可选: 示例 Bug 数据
python manage.py init_rbac_data        # 可选: 初始化 RBAC 权限数据
uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173 (已配置代理到后端 8000)
```

> 前端开发服务器会自动将 `/api`、`/ws`、`/media` 请求代理到后端 `localhost:8000`。
>
> **首次启动建议**: 后端启动后访问 `http://localhost:8000/admin/` 用超级用户登录，然后访问 `http://localhost:5173` 使用前端。

---

## 测试

| 类型 | 命令 |
|------|------|
| 后端 API | `cd backend && pytest tests/ -v` |
| E2E | `E2E_BASE_URL=http://localhost:5173 pytest e2e/ -v` |
| 性能 | `locust -f performance/locustfile.py --headless -u 10 -r 1 --run-time 60s` |
| 前端 | `cd frontend && npm run test:run` |

---

## 主要 API 端点 (50+)

### 认证
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/auth/login/` | POST | 登录 (限流 5/min) |
| `/api/auth/logout/` | POST | 登出 |
| `/api/auth/me/` | GET | 当前用户 |

### 看板
| `/api/projects/` | GET/POST | 项目列表/创建 |
| `/api/projects/{id}/` | DELETE | 删除项目 |
| `/api/projects/{id}/invite/` | POST | 邀请成员 |
| `/api/columns/` | GET/POST | 列管理 |
| `/api/tasks/` | GET/POST | 任务 CRUD (分页) |
| `/api/tasks/{id}/` | PATCH/DELETE | 更新/删除任务 |
| `/api/tasks/search/` | GET | 全文搜索 |
| `/api/tags/` | GET/POST | 标签管理 |

### 协作
| `/api/tasks/{id}/comments/` | GET/POST | 评论列表/创建 (WebSocket 广播) |
| `/api/tasks/{id}/comments/{cid}/` | PATCH/DELETE | 编辑/删除评论 |
| `/api/tasks/{id}/activities/` | GET | 任务变更时间线 |
| `/api/tasks/{id}/attachments/` | GET/POST | 附件列表/上传 |
| `/api/tasks/{id}/attachments/{aid}/` | DELETE | 删除附件 |
| `/api/tasks/{id}/linked-tests/` | GET | 关联测试用例 |

### 项目角色
| `/api/projects/{id}/roles/` | GET/POST | 角色管理 |
| `/api/projects/{id}/roles/{rid}/` | PUT/DELETE | 角色编辑/删除 |
| `/api/projects/{id}/members/` | GET/PUT/DELETE | 成员+角色管理 |

### 迭代/Sprint
| `/api/projects/{id}/sprints/` | GET/POST | 迭代列表/创建 |
| `/api/projects/{id}/sprints/{sid}/` | GET/PUT/DELETE | 迭代详情 |
| `/api/projects/{id}/sprints/{sid}/tasks/` | POST/DELETE | 添加/移除任务 |
| `/api/projects/{id}/sprints/{sid}/burndown/` | GET | 燃尽图数据 |

### AI 助手
| `/api/ai/conversations/` | GET/POST | 对话列表/新建 |
| `/api/ai/conversations/{id}/` | DELETE | 删除对话 |
| `/api/ai/chat/` | POST | 发送消息 (多轮) |
| `/api/ai/chat/stream/` | POST | 流式响应 (SSE) |
| `/api/ai/analyze/health/` | POST | 项目健康度分析 |
| `/api/ai/analyze/weekly/` | POST | 周报生成 |
| `/api/chat/` | POST | 兼容旧版 RAG 问答 |

### QA 质量中心
| `/api/qa/api-cases/` | ViewSet | API 测试用例 |
| `/api/qa/ui-cases/` | ViewSet | UI 测试用例 |
| `/api/qa/auto-suites/` | ViewSet | 自动化测试套件 |
| `/api/qa/auto-assertions/` | ViewSet | 断言配置 |
| `/api/qa/auto-extractors/` | ViewSet | 变量提取器 |
| `/api/qa/auto-results/` | ViewSet | 测试结果详情 |
| `/api/qa/run-plans/` | ViewSet | 测试运行计划 |
| `/api/qa/environments/` | ViewSet | 测试环境管理 |
| `/api/qa/global-vars/` | ViewSet | 全局变量 |
| `/api/qa/runs/` | GET/POST | 测试运行列表/创建 |
| `/api/qa/runs/{id}/cancel/` | POST | 取消运行 |
| `/api/qa/runs/{id}/rerun/` | POST | 重新运行 |
| `/api/qa/auto-execute/` | POST | 执行自动化测试 |
| `/api/qa/link-task/` | POST | 关联测试↔任务 |
| `/api/qa/unlink-task/` | POST | 取消关联 |
| `/api/qa/data-factory/` | GET | 随机测试数据生成 |

### Bug Tracker（缺陷追踪）
| `/api/bugs/` | GET/POST | Bug 列表/创建 |
| `/api/bugs/{id}/` | GET/PATCH/DELETE | Bug 详情/更新/删除 |
| `/api/bugs/{id}/transition/` | POST | 状态流转 (状态机) |
| `/api/bugs/{id}/assign/` | POST | 分配负责人 |
| `/api/bugs/{id}/comments/` | GET/POST | Bug 评论 |
| `/api/bugs/my/` | GET | 我的 Bug |
| `/api/bugs/stats/` | GET | Bug 统计面板 |
| `/api/bugs/seed-demo/` | POST | 生成演示数据 |

### DevOps
| `/api/qa/devops/stats/` | GET | 仪表板统计 |
| `/api/qa/devops/cicd-config/` | CRUD | CI/CD 配置 (DB持久化) |
| `/api/qa/devops/cicd-config/{id}/trigger/` | POST | 手动触发 Pipeline |
| `/api/qa/devops/cicd-config/{id}/webhook/` | POST | Webhook 回调 |
| `/api/qa/devops/cicd-config/{id}/test/` | POST | 测试连接 |
| `/api/qa/devops/tasks/` | CRUD | 测试任务管理 |
| `/api/qa/devops/tasks/{id}/execute/` | POST | 执行测试任务 |
| `/api/qa/devops/tasks/{id}/history/` | GET | 任务执行历史 |
| `/api/qa/devops/pipeline-runs/` | GET | Pipeline 执行历史 |
| `/api/qa/devops/pipeline-runs/{id}/` | GET | 执行详情 |
| `/api/qa/devops/quality-report/` | GET | 项目质量报告 |
| `/api/qa/devops/quick-test/` | POST | 快速测试 |

### 系统管理
| `/api/system/menus/` | CRUD | 菜单管理 (鉴权) |
| `/api/system/roles/` | CRUD | 角色管理 (鉴权) |
| `/api/system/users/` | CRUD | 用户管理 (鉴权) |

### WebSocket
| 路径 | 用途 | 鉴权 |
|------|------|------|
| `/ws/board/{project_id}/` | 看板实时同步 | ✅ 项目成员 |
| `/ws/chat/{project_id}/` | 项目聊天 + 历史 (Redis Stream) | ✅ 项目成员 |
| `/ws/global/` | 全局通知广播 | ✅ 认证 |
| `/ws/qa/dashboard/{project_id}/` | QA 仪表板实时日志 | ✅ 认证 |
| `/ws/qa/recorder/{project_id}/` | UI 录制器双向通信 | ✅ 认证 |
| `/ws/qa/performance/{exec_id}/` | 性能测试实时指标 | ✅ 认证 |
| `/ws/qa/test-run/{run_id}/` | 测试运行进度推送 | ✅ 认证 |
| `/ws/qa/run/{task_id}/` | UI 自动化执行进度 | ✅ 认证 |

---

## 配置说明

### 环境变量 (backend/.env)
```env
DEBUG=True
DJANGO_SECRET_KEY=your-secret-key

DB_NAME=syncboard
DB_USER=your-db-user
DB_PASSWORD=your-db-password
DB_HOST=127.0.0.1

REDIS_HOST=127.0.0.1            # Channels + Celery

HAYSTACK_URL=http://127.0.0.1:9200/  # Elasticsearch (可选)

OPENAI_API_KEY=sk-xxx            # DeepSeek/OpenAI API Key
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

> 复制 `backend/.env.example` 为 `backend/.env` 并填入实际配置。

---

## 许可证

MIT License
