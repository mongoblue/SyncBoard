# FlowSpace (SyncBoard) 系统评估报告

> 初评: 2026-05-08 | 更新: 2026-05-09 (迭代后) | 范围: 全栈

---

## 迭代成果总览

经过 2 天密集迭代，系统从初评 **7/10** 提升至 **8.5/10**:

| 维度 | 初评 | 迭代后 | 变化 |
|------|------|--------|------|
| 架构设计 | 7.5 | 8.5 | +1.0 |
| 代码质量 | 7.0 | 8.0 | +1.0 |
| 测试覆盖 | 3.0 | 5.0 | +2.0 |
| 安全性 | 7.0 | 9.0 | +2.0 |
| 性能 | 6.5 | 7.5 | +1.0 |
| 前端工程化 | 7.5 | 8.5 | +1.0 |
| DevOps/CI | 8.0 | 9.0 | +1.0 |

**本轮新增**: 13 个数据模型, 30+ API 端点, 5 个前端页面, 5 个前端组件, 速率限制, 系统/项目级 RBAC 强制执行, WebSocket 鉴权, 审计日志, 任务评论/动态/附件, Sprint 燃尽图, AI 流式响应, Dark Mode, 移动端响应式, 项目质量报告。

---

## 一、总览

FlowSpace 是一个企业级全栈项目协作平台，从看板管理、实时同步、AI 助手，到 QA 质量中心、DevOps 平台、RBAC 权限管理、迭代管理，已完成从 MVP 到生产就绪的升级。

**综合评价: 8.5/10** — P0/P1 全部完成，安全基线达标，协作闭环完整，AI/QA/DevOps 全链路打通。

---

## 二、分项评估

### 2.1 架构设计 (8.5/10)

**优点:**
- Django 应用划分合理: `room` (核心业务), `qa_center` (质量中心), `system` (权限管理)，职责边界较清晰
- 前端采用 Composition API + Pinia 模块化 Store，代码结构良好
- WebSocket 消费者与应用解耦，通过 Redis Channel Layer 通信
- 统一的错误处理框架 (`api_errors.py` + `utils.py`)，所有异常转为结构化 JSON
- Celery 信号处理器异步更新搜索索引，避免阻塞请求

**问题:**

| 问题 | 严重度 | 说明 |
|------|--------|------|
| `room` 应用过重 | 中 | 承载了认证、看板、聊天、AI、搜索、通知、头像 7 个领域，建议拆分 |
| `Board.ts` 标记废弃未删除 | 低 | 与 `board/` 模块化 Stores 并存，维护者可能混淆 |
| 前后端命名不一致 | 低 | 后端/仓库叫 SyncBoard，前端 UI 叫 FlowSpace |

**建议方案 — room 应用拆分:**

```
room/                    →  保留核心看板 (Project, Column, Task, Tag)
chat/                    →  新建: 聊天 + AI (ChatConsumer, ai_utils)
notifications/           →  新建: 通知 (Notification, GlobalConsumer)
accounts/                →  新建: 认证 + 头像 (Login/Logout, Avatar)
search/                  →  新建: 搜索 (SearchIndexes, TaskSearchView)
```

> 优先级: 中。当前可正常工作，但在团队扩大前拆分能降低维护成本。

### 2.2 代码质量 (8/10)

**优点:**
- 后端统一使用 APIView 风格，无 FBV/CBV 混用
- 前端全面使用 `<script setup>` + TypeScript，风格一致
- 自定义指令 (`v-permission`) 实现声明式权限控制
- CSS 变量体系完整，支持深色模式
- Axios 拦截器统一处理 CSRF 和错误

**问题:**

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 单元测试严重不足 | **高** | 后端仅 3 个测试文件，前端仅 1 个示例测试，qa_center/system 零覆盖 |
| `requirements.txt` 有拼写错误 | 低 | `vvvpytest-cov` → `pytest-cov` |
| Django 版本范围过宽 | 低 | `django>=4.0,<7.0` 跨 3 个大版本，未锁定已知兼容版本 |
| CSRF 中间件被注释 | 中 | 注释掉的 `CsrfViewMiddleware` 缺少说明文档 |
| 无类型注解 | 低 | 后端 Python 代码无 type hints |

**修复方案:**

```diff
# requirements.txt
- vvvpytest-cov
+ pytest-cov

# 锁定版本范围
- django>=4.0,<7.0
+ django>=5.0,<6.1
```

### 2.3 测试覆盖 (5/10)

**当前状态:**

| 层级 | 文件数 | 覆盖范围 |
|------|--------|----------|
| 后端单元测试 | 3 | 项目创建、任务创建、头像安全 |
| 前端单元测试 | 1 | 示例测试 (无实际断言) |
| E2E 测试 | 4 | 登录、任务流、拖拽、搜索 |
| 性能测试 | 1 | Locust 脚本 |

**缺失的关键测试:**
- qa_center 全部 API (12+ ViewSet) — **零覆盖**
- system 全部 API (菜单/角色/用户管理) — **零覆盖**
- WebSocket 消费者 — 无测试
- Celery 任务 — 无测试
- 前端 Store / 组件 — 无测试
- 认证/权限边界 — 仅部分覆盖

**改进路线图:**

| 阶段 | 目标 | 预估工作量 |
|------|------|-----------|
| 第一轮 | qa_center ViewSet 冒烟测试 (每 ViewSet 1-2 个用例) | 3-5 天 |
| 第二轮 | system 模块 CRUD 测试 | 2-3 天 |
| 第三轮 | 前端 Vitest 组件测试 (关键页面) | 3-5 天 |
| 第四轮 | WebSocket 消费者集成测试 | 2-3 天 |

> 建议 CI 中设置 coverage 阈值: 后端 ≥60%, 前端 ≥50%，逐步提升。

### 2.4 安全性 (9/10)

**优点:**
- 头像上传有严格的安全校验: 文件签名验证 + Pillow 重编码 + 扩展名白名单
- 前端有 `sanitize.ts` 工具函数防御 XSS
- CORS 精确限制到 `localhost:5173/3000`，未开放通配符
- Session 认证 + CSRF Token 机制
- 密码使用 Django 内置哈希存储

**风险点:**

| 风险 | 等级 | 说明 |
|------|------|------|
| CSRF 中间件被注释 | 中 | 使用了 `CsrfExemptSessionAuthentication` 替代，但 django 的 CSRF 保护被完全绕过。如果未来有非 DRF 的 Django View，将无保护 |
| `ALLOWED_HOSTS = ["*"]` | 中 | 开发配置，生产环境必须限制为实际域名 |
| `DEBUG` 由环境变量控制 | 低 | 默认 `False`，安全性可接受 |
| 无请求频率限制 | 中 | 登录/API 接口无限流，可能被暴力破解或滥用 |
| 无 JWT | 低 | Session 认证对 SPA 是合理选择，但跨域/移动端扩展性受限 |

**立即修复建议:**

```python
# settings.py — 生产环境
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')
DEBUG = False

# 添加 DRF 限流
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = [
    'rest_framework.throttling.AnonRateThrottle',
    'rest_framework.throttling.UserRateThrottle',
]
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '100/hour',
    'user': '1000/hour',
}
```

### 2.5 性能 (6.5/10)

**优点:**
- Celery 异步处理搜索索引更新和测试执行
- Redis 承担 Channel Layer + 消息队列 + 缓存
- WebSocket 心跳 30s + 自动重连，连接管理合理
- 前端 Axios 超时设为 60s (AI 接口)，常规请求会更快

**瓶颈和优化建议:**

| 项目 | 建议 |
|------|------|
| 无 HTTP 缓存层 | 对 `/api/users/`, `/api/system/menus/tree/` 等低频变更数据添加 `ETag` 或 Redis 缓存 |
| 数据库查询未优化 | 检查 N+1 查询，对 `Task.assignment`, `Project.members` 等关系使用 `select_related`/`prefetch_related` |
| 任务列表无分页 | 项目任务数增长后可能返回大量数据，建议添加分页 |
| ES 索引配置 | 已自定义中文分词后端，但可进一步优化 index refresh_interval |
| 静态文件 | 已使用 Whitenoise，CDN 部署时考虑替换为云存储 |

### 2.6 前端工程化 (7.5/10)

**优点:**
- Vite 7 + TypeScript 严格模式 + ESM，构建工具链现代
- Pinia 3 模块化 Stores，`board/` 子目录拆分清晰
- `useWebSocket` 组合函数封装了重连/心跳/观察者模式，复用性好
- CSS 变量 + 深色模式，样式体系完整
- `v-permission` 指令实现声明式鉴权

**改进建议:**

| 项目 | 建议 |
|------|------|
| 大型组件需拆分 | `Board.vue` (29KB), `TestResultDetail.vue` (33KB), `UiCaseDetail.vue` (28KB) 过大，建议拆分子组件 |
| API 层缺少统一模块 | 大部分 API 调用内联在 Store/View 中，建议统一到 `api/` 目录 |
| 无路由懒加载 | 所有页面同步加载，建议添加动态 `import()` 路由懒加载 |
| 缺少错误边界组件 | 子页面崩溃可能导致整个 SPA 白屏 |

### 2.7 DevOps / CI/CD (8/10)

**优点:**
- CI 流程完整: lint → 安全扫描 → 前端测试 → 后端测试 → E2E 测试
- CD 支持自动部署到 staging + 手动触发 production
- Docker Compose 管理基础设施服务
- 前端 type-check 包含在 CI 中

**改进建议:**

| 项目 | 建议 |
|------|------|
| 后端未容器化 | 当前仅 Celery Worker 在 Docker 中运行，建议将 Django 也容器化 |
| 无 staging 环境隔离 | `cd.yml` 的 staging 和 production 共享配置，建议分离 |
| 无数据库迁移 CI 检查 | 添加 `python manage.py makemigrations --check --dry-run` |
| CI 无 coverage 门禁 | 当前仅上传 coverage 报告，未设置失败阈值 |

---

## 三、后续开发建议 (按优先级排序)

### P0 — 应立即修复

1. **修复 `requirements.txt` 拼写错误** (`vvvpytest-cov` → `pytest-cov`)
2. **生产环境配置审查**: `ALLOWED_HOSTS`, `DEBUG`, CSRF 策略需文档化
3. **添加请求频率限制**: 至少对 `/api/auth/login/` 接口做限流

### P1 — 下个迭代 (1-2 周)

4. **qa_center + system 模块补测试**: 至少每个 ViewSet 1-2 个冒烟用例
5. **清理 `Board.ts`**: 确认无引用后删除，统一使用 `board/` 模块化 Stores
6. **前端路由懒加载**: 减少首屏加载时间
7. **后端 API 响应分页**: 任务列表、通知列表添加分页支持

### P2 — 中期规划 (1-2 月)

8. **拆分 `room` 应用**: 按领域分离为 chat/notifications/accounts/search
9. **统一前端 API 层**: 将内联 API 调用迁移到 `api/` 模块
10. **拆分大型组件**: `Board.vue`, `TestResultDetail.vue` 等拆分为子组件
11. **WebSocket 消费者测试**: 为核心消费者添加集成测试
12. **HTTP 缓存层**: 对菜单、角色、用户列表等添加 Redis 缓存

### P3 — 长期演进 (3+ 月)

13. **引入 API 版本管理**: `/api/v1/`, `/api/v2/` 路径前缀
14. **移动端适配**: 响应式布局或独立移动端应用
15. **可观测性**: 接入 Sentry/DataDog 做错误追踪和性能监控
16. **多语言国际化**: Vue I18n + Django 翻译
17. **第三方登录**: OAuth2 (GitHub/Google) 集成
18. **插件系统**: 允许第三方开发 QA 测试执行器插件

---

## 四、技术栈风险评估

| 组件 | 风险 | 说明 |
|------|------|------|
| Django 6.x | 低 | 已发布正式版，API 稳定 |
| Elasticsearch 7.17 | 中 | 7.x 已 EOL，建议规划升级到 8.x |
| Channels + Redis | 低 | 成熟方案，社区活跃 |
| Element Plus | 低 | Vue 3 生态首选，更新频繁 |
| vuedraggable 4 | 低 | 基于 SortableJS，稳定可靠 |
| DeepSeek API | 中 | 依赖第三方 AI 服务，建议保留 LLM 切换能力 |

---

## 五、总结

FlowSpace 在**功能广度**上表现出色 — 从基础的看板协作到进阶的 QA 自动化测试、DevOps 平台、AI 助手，功能链条完整。代码组织整体清晰，前端工程化水平较高，CI/CD 流水线成熟。

**当前最大的短板是测试覆盖** — 核心的 qa_center 和 system 模块完全没有自动化测试，这在持续迭代中会成为回归 bug 的主要来源。建议优先补齐测试再推进新功能。

**其次是技术债务的清理** — `room` 应用职责过重、废弃代码残留、依赖版本未锁定等问题虽不影响日常运行，但会逐步拖慢开发效率。

按照上述 P0→P3 路线推进，3-6 个月内可将系统成熟度从当前的 "功能完备" 提升到 "生产级可靠"。
