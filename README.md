# FlowSpace (SyncBoard) - 项目协作看板系统

FlowSpace 是一个基于 Django + Vue 3 的企业级全栈项目协作平台，集成了看板管理、实时同步、AI 智能助手、QA 质量中心、DevOps 平台、RBAC 权限管理和迭代管理。

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
| 测试 | pytest + pytest-django + Playwright + Locust |
| 文件处理 | Pillow (头像/附件安全处理) |
| 静态文件 | Whitenoise |
| AI | DeepSeek API (OpenAI 兼容, 支持流式 SSE) |

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
│   ├── ci.yml                      # CI: lint/安全/单元测试/E2E
│   └── cd.yml                      # CD: 自动部署 staging/production
├── backend/
│   ├── backend/
│   │   ├── settings.py             # Django 配置 (分页/限流/CORS/ES/Celery)
│   │   ├── authentication.py       # CSRF豁免会话认证
│   │   ├── api_errors.py           # 统一错误码
│   │   ├── utils.py                # 自定义异常处理器
│   │   ├── throttles.py            # 登录限流
│   │   ├── celery.py               # Celery 初始化
│   │   ├── tasks.py                # 搜索索引异步任务
│   │   ├── signal_processors.py    # Celery 信号处理器
│   │   └── conftest.py             # pytest WebSocket 实时上报
│   ├── room/                       # 核心业务 (看板/协作/AI/权限)
│   │   ├── models.py               # 22 个数据模型
│   │   ├── serializers.py          # 20+ 序列化器
│   │   ├── ai_utils.py             # RAG + 流式 AI
│   │   ├── views/                  # 模块化视图 (14 个文件)
│   │   │   ├── auth.py             # 认证
│   │   │   ├── board.py            # 看板列/任务
│   │   │   ├── project.py          # 项目/RAG问答
│   │   │   ├── tag.py              # 标签 (含项目门控)
│   │   │   ├── user.py             # 用户列表
│   │   │   ├── notification.py     # 通知
│   │   │   ├── comment.py          # 任务评论 + WebSocket
│   │   │   ├── activity.py         # 任务动态日志
│   │   │   ├── attachment.py       # 任务附件
│   │   │   ├── project_role.py     # 项目角色/成员
│   │   │   ├── sprint.py           # 迭代/Sprint + 燃尽图
│   │   │   ├── ai.py               # AI 多轮对话 + 流式 + 分析
│   │   │   └── mixins.py           # 项目权限 Mixin
│   │   ├── consumers.py            # Board WebSocket (鉴权)
│   │   ├── consumers_chat.py       # Chat WebSocket (鉴权)
│   │   ├── consumers_global.py     # Global 通知 WebSocket
│   │   └── urls.py                 # 50+ API 路由
│   ├── qa_center/                  # QA 质量中心 + DevOps
│   │   ├── models.py               # 15 个模型
│   │   ├── serializers.py          #
│   │   ├── views_*.py              # 10 个视图文件
│   │   ├── test_executor.py        # 测试执行
│   │   ├── api_auto_executor.py    # 自动化测试引擎 + 自动建Bug
│   │   ├── locust_runner.py        # 无界面 Locust
│   │   ├── bug_utils.py            # 测试失败→Bug自动创建
│   │   └── utils/                  # recorder.py, runner.py
│   ├── system/                     # 系统 RBAC 管理
│   │   ├── models.py               # Menu, Role, SystemUserProfile
│   │   ├── permissions.py          # HasSystemPermission
│   │   └── views.py                # 权限执行视图
│   ├── tests/                      # 25+ 测试用例
│   ├── e2e/                        # Playwright E2E (4个)
│   └── performance/                # Locust 脚本
│
├── frontend/
│   ├── src/
│   │   ├── App.vue                 # 根组件 (暗色模式切换)
│   │   ├── main.ts
│   │   ├── router/index.ts         # 路由 (懒加载 + meta.permission 权限守卫)
│   │   ├── stores/
│   │   │   ├── Auth.ts             # 认证 + 权限
│   │   │   ├── notification.ts     # 通知 WebSocket
│   │   │   ├── board/              # 模块化看板 Store (task/column/tag/user)
│   │   │   └── composables/
│   │   ├── views/                  # 30+ 页面
│   │   │   ├── Board.vue           # 主看板 (拖拽/搜索/筛选)
│   │   │   ├── ProjectSprints.vue  # 迭代管理
│   │   │   ├── SprintBoard.vue     # 迭代看板 + 燃尽图
│   │   │   ├── ProjectQualityReport.vue  # 质量报告
│   │   │   ├── AIChat.vue          # AI 助手 (流式/多轮/分析)
│   │   │   ├── Members.vue         # 成员管理 (角色选择)
│   │   │   ├── qa/                 # QA 中心 (11 个页面)
│   │   │   └── system/             # 系统管理 (3 个页面)
│   │   ├── components/
│   │   │   ├── TaskDetailDrawer.vue # 任务详情 (评论/动态/附件/关联测试)
│   │   │   ├── PipelineTimeline.vue # CI/CD 执行历史
│   │   │   ├── ChatDrawer.vue      # 聊天浮动抽屉
│   │   │   ├── Chatbot.vue         # AI 聊天机器人
│   │   │   └── TestConsole.vue     # QA 终端
│   │   ├── directives/permission.ts # 响应式权限指令
│   │   ├── styles/
│   │   │   ├── variables.css       # 设计令牌
│   │   │   └── global.css          # 全局 + 响应式 + Dark Mode
│   │   └── utils/                  # request.ts, sanitize.ts
│   └── package.json
│
├── docker-compose.yml
├── API文档.md
├── DEVELOPMENT_ROADMAP.md
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

### 7. 项目质量报告
- **五维评分**: 测试覆盖 / 通过率 / 性能 / Bug密度 / 部署成功率
- **雷达图 + 趋势图**: ECharts 可视化
- **30天趋势**: 每日测试通过率变化

### 8. 迭代/Sprint 管理
- 迭代 CRUD + 任务添加/移除
- **燃尽图**: 理想线 vs 实际剩余 (ECharts)
- 完成进度条 + 任务状态追踪

### 9. RBAC 权限管理
- **系统级**: Menu/Role/User → HasSystemPermission 强制执行
- **项目级**: ProjectRole (4级) / ProjectMember → HasProjectRole
- **前端**: 路由权限守卫 + `v-permission` 响应式指令
- **WebSocket**: 项目成员鉴权 (connect 时检查)

### 10. 安全特性
- DRF 全局限流 (匿名100/min, 认证1000/min) + 登录 5/min
- 系统管理 API 按方法鉴权 (8 View × 4 HTTP 方法)
- WebSocket 项目鉴权 (非成员 → close 4003)
- 文件上传安全 (签名校验 + 重编码 + 类型白名单)
- XSS 防护 + CSRF Token + CORS 白名单
- 审计日志 (user/action/resource/ip)

### 11. 用户体验
- **Dark Mode**: 切换按钮 + localStorage + 跟随系统
- **响应式**: 768px/1024px 断点，看板列纵向堆叠，侧边栏折叠
- **统一状态**: LoadingState / ErrorState / EmptyState 模式
- **快捷键入口**: 侧边栏直达迭代/质量报告/AI 助手

---

## 快速开始

### 环境要求
- Python 3.11+ | Node.js 20.19+ | MySQL 8.0 | Redis 7 | ES 7.17 (可选)

### Docker 启动基础设施

```bash
docker-compose up -d    # MySQL + Redis + ES + Celery Worker
```

### 后端

```bash
cd backend
python -m venv venv && source venv/bin/activate   # or .\venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # 编辑数据库/AI 配置
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_ci_data     # 可选: 示例数据
uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

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
| `/api/qa/auto-execute/` | POST | 执行自动化测试 |
| `/api/qa/link-task/` | POST | 关联测试↔任务 |
| `/api/qa/unlink-task/` | POST | 取消关联 |

### DevOps
| `/api/qa/devops/stats/` | GET | 仪表板统计 |
| `/api/qa/devops/cicd-config/` | CRUD | CI/CD 配置 (DB持久化) |
| `/api/qa/devops/pipeline-runs/` | GET | Pipeline 执行历史 |
| `/api/qa/devops/pipeline-runs/{id}/` | GET | 执行详情 |
| `/api/qa/devops/cicd-config/{id}/trigger/` | POST | 手动触发 |
| `/api/qa/devops/cicd-config/{id}/webhook/` | POST | Webhook 回调 |
| `/api/qa/devops/quality-report/` | GET | 项目质量报告 |

### 系统管理
| `/api/system/menus/` | CRUD | 菜单管理 (鉴权) |
| `/api/system/roles/` | CRUD | 角色管理 (鉴权) |
| `/api/system/users/` | CRUD | 用户管理 (鉴权) |

### WebSocket
| 路径 | 用途 | 鉴权 |
|------|------|------|
| `/ws/board/{project_id}/` | 看板实时同步 | ✅ 项目成员 |
| `/ws/chat/{project_id}/` | 项目聊天 + 历史 | ✅ 项目成员 |
| `/ws/global/` | 全局通知 | ✅ 认证 |
| `/ws/qa/dashboard/` | 测试日志 | ✅ 认证 |
| `/ws/qa/recorder/` | UI 录制器 | ✅ 认证 |
| `/ws/qa/performance/{id}/` | 性能实时指标 | ✅ 认证 |

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
