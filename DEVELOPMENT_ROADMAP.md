# FlowSpace 下一阶段开发方案

> 版本: v2.0 | 日期: 2026-05-08 | 作者: 全栈架构评审

---

## 一、项目现状判断

### 1.1 核心优势

| 维度 | 评价 | 说明 |
|------|------|------|
| 功能广度 | ★★★★☆ | 看板/QACenter/DevOps/AI/RBAC 覆盖完整 |
| 实时能力 | ★★★★☆ | WebSocket + Redis Channel Layer + Celery 架构成熟 |
| 前端工程化 | ★★★★☆ | Vue3+TS+Pinia 模块化，CSS变量+深色模式，指令系统 |
| CI/CD | ★★★★☆ | GitHub Actions 全流程（lint/安全/测试/E2E/部署） |
| 代码组织 | ★★★☆☆ | 前后端分层清晰，但 room 应用过重，测试覆盖不足 |

### 1.2 当前最大问题（按严重度排序）

**P0 严重问题（已修复）:**
1. ✅ 速率限制已添加
2. ✅ 后端分页已添加（Task/Notification/ViewSet）

**P0 严重问题（待修复）:**
1. ❌ **AI 助手有功能 Bug** — AIChat.vue 发送字段名错误（`message` vs `question`），响应字段名错误（`response` vs `answer`），缺少 `logger` 导入
2. ❌ **系统管理后端无权限执行** — Menu/Role/User 的 CRUD 仅依赖 `IsAuthenticated`，任何登录用户可直接调用 API
3. ❌ **WebSocket 无项目级鉴权** — BoardConsumer/ChatConsumer 不检查项目成员资格
4. ❌ **标签和搜索视图无项目门控** — TagListView/TaskSearchView 未检查项目成员

**P1 结构性问题:**
5. ❌ **room 应用承载 7 个领域** — 认证/看板/聊天/AI/搜索/通知/头像 耦合在一处
6. ❌ **QA/DevOps 与任务系统完全隔离** — 无模型关联，无法形成业务闭环
7. ❌ **AI 助手无上下文记忆** — 每次请求无状态，不支持追问
8. ❌ **项目权限只有二元模型** — 只有 owner/member，缺少项目内角色
9. ❌ **测试覆盖严重不足** — qa_center/system 模块零覆盖（刚补充了冒烟测试）

**P2 体验问题:**
10. ❌ **无审计日志** — 所有操作无追溯记录
11. ❌ **CI/CD 配置存内存而非数据库** — 重启丢失
12. ❌ **前端多个巨型组件** — Board.vue(29KB)、TestResultDetail.vue(33KB) 未拆分

---

## 二、后续开发优先级表

| 优先级 | 模块 | 建议事项 | 原因 | 技术思路 | 复杂度 | 立即开发 |
|--------|------|----------|------|----------|--------|----------|
| **P0** | AI | 修复 AIChat.vue 字段错误 | 当前AI助手不可用 | 改字段名 `message`→`question`, `response`→`answer` | 低 | ✅ |
| **P0** | AI | 修复 logger 未导入 | AI异常时500报错 | 添加 `import logging` | 低 | ✅ |
| **P0** | 安全 | 系统管理添加权限执行 | 任何登录用户可篡改系统 | 新建 `HasPermission` DRF 权限类 | 中 | ✅ |
| **P0** | 安全 | WebSocket 项目鉴权 | 非成员可监听看板数据 | connect() 中检查 project membership | 中 | ✅ |
| **P0** | 安全 | 标签/搜索添加项目门控 | 跨项目数据泄露 | TagListView/TaskSearchView 加 mixin | 低 | ✅ |
| **P1** | 权限 | 项目级角色系统 | 缺少项目内权限分层 | ProjectRole + ProjectMember 模型 | 中 | ✅ |
| **P1** | 协作 | 任务评论 | 任务协作无讨论能力 | TaskComment 模型 + 实时同步 | 中 | ✅ |
| **P1** | 协作 | 任务动态日志 | 无法追溯任务变更历史 | TaskActivityLog 模型 | 中 | ✅ |
| **P1** | AI | 对话历史持久化 | AI无法上下文追问 | AIConversation/AIMessage 模型 | 中 | ✅ |
| **P1** | QA | 测试用例关联任务 | QA与看板无法闭环 | TestCase↔Task M2M 关联 | 中 | ✅ |
| **P1** | DevOps | CI/CD配置持久化 | 重启丢失配置 | 新建 CiCdConfig 数据库模型 | 低 | ✅ |
| **P1** | 安全 | 审计日志 | 无操作追溯 | AuditLog 模型 + 关键操作埋点 | 中 | ✅ |
| **P1** | 测试 | 单元测试补充到60%覆盖 | 回归风险高 | Pytest + 共享fixtures | 高 | ✅ |
| **P2** | AI | AI项目分析报告 | AI能力升级 | 健康度分析/风险识别/周报生成 | 高 | 可延后 |
| **P2** | DevOps | 测试失败自动建Bug | QA/DevOps闭环 | 失败→自动创建Task | 中 | 可延后 |
| **P2** | 协作 | 迭代/Sprint管理 | 敏捷开发支持 | Sprint模型 + 燃尽图 | 高 | 可延后 |
| **P2** | 协作 | 任务附件 | 任务无法上传文件 | TaskAttachment模型 + 文件存储 | 中 | 可延后 |
| **P2** | 架构 | 拆分room应用 | 长期维护成本 | chat/notifications/accounts/search 独立 | 高 | 暂缓 |
| **P2** | 体验 | 前端巨型组件拆分 | 维护困难 | Board拆TaskCard/ColumnView等子组件 | 中 | 可延后 |
| **P2** | 体验 | AI流式响应 | 用户等待体验差 | SSE/WebSocket流式传输 | 高 | 可延后 |
| **P3** | 部署 | 容器化后端 | 开发环境一致性 | 完整 Docker Compose | 中 | 暂缓 |
| **P3** | 监控 | 可观测性 | 无错误追踪 | Sentry + Prometheus + Grafana | 高 | 暂缓 |
| **P3** | 国际化 | 多语言 | 海外用户 | Vue I18n + Django翻译 | 高 | 暂缓 |
| **P3** | 集成 | OAuth登录 | 便利性 | GitHub/Google OAuth2 | 中 | 暂缓 |

---

## 三、推荐的 3 条开发主线

### 主线 A：项目协作主流程闭环（P0+P1）

**目标**: 让项目协作从"能看"变为"能用"，补全任务评论、动态日志、项目级权限三大短板。

**适合现在做的原因**: 当前协作体验接近个人看板工具，缺少团队协作必备的讨论和追溯能力。这些是产品化的基础。

**具体功能点**:
1. 任务评论区（实时 WebSocket 同步）
2. 任务变更动态日志
3. 项目级角色（Owner/Admin/Editor/Viewer）
4. 安全漏洞修复（WebSocket鉴权、系统管理权限执行、标签/搜索门控）
5. 审计日志

**后端改造点**:
- 新建模型: `ProjectRole`, `ProjectMember`, `TaskComment`, `TaskActivityLog`, `AuditLog`
- 新建 DRF 权限类: `HasSystemPermission`, `HasProjectRole`
- BoardConsumer/ChatConsumer 加项目成员鉴权
- TagListView/TaskSearchView 加 ProjectAccessMixin
- 系统管理视图全部加 `HasSystemPermission`

**前端改造点**:
- Board.vue 任务详情弹窗加评论面板
- 新建 TaskComment.vue 组件（实时 WebSocket）
- 新建 TaskActivity.vue 组件（时间线）
- 系统管理页面：无权限时显示 403 而非空白按钮
- 路由守卫加 `meta.permission` 检查

**数据库变更**:
- 5 个新模型
- Project 表不变（用新表扩展）

**测试点**:
- 系统管理权限执行测试
- WebSocket 鉴权测试
- 评论 CRUD + 实时同步测试
- 动态日志自动记录测试

**验收标准**:
- 任何非管理员无法调用系统管理 API
- 非项目成员 WebSocket 连接被拒绝
- 任务评论实时同步到所有在线用户
- 任务变更自动记录并展示时间线

---

### 主线 B：QA / DevOps 与任务系统打通（P1+P2）

**目标**: 打通测试—缺陷—任务闭环，让 QA Center 从独立工具变为项目交付工具链的一环。

**适合现在做的原因**: QA Center 功能成熟但孤立运行，打通后可形成"测试→Bug→修复→验证"闭环，大幅提升产品完整性。

**具体功能点**:
1. 测试用例 ↔ 任务关联（M2M）
2. 测试失败自动创建缺陷任务
3. DevOps PipelineRun 绑定 Project
4. CI/CD 配置持久化到数据库
5. 性能测试结果 → 项目质量报告
6. 通知系统打通：测试失败/部署成功/质量风险推送

**后端改造点**:
- 新建模型: `CiCdConfig`（数据库替代内存字典）、`PipelineRun`、`TaskTestLink`（M2M through表）
- ApiTestCase/UiTestCase/PerformanceTestCase 加 `related_tasks` M2M
- 测试失败回调 → 自动创建 Task
- DevOps 统计接口加项目维度的质量评分
- 通知类型扩展: `test_failure`, `deploy_success`, `quality_risk`

**前端改造点**:
- QA 用例详情页新增"关联任务"选择器
- 任务详情页新增"关联测试用例"展示
- DevOps 平台 PipelineRun 时间线组件
- 项目 Dashboard 新增质量评分卡片
- 新建 ProjectQualityReport.vue

**数据库变更**:
- 3 个新模型
- 2 个 M2M through 表
- ApiTestCase/UiTestCase/PerformanceTestCase 加 M2M 字段

**测试点**:
- 测试失败自动创建任务流程测试
- PipelineRun 完整生命周期测试
- 质量报告数据准确性测试

**验收标准**:
- 测试用例可关联/取消关联任务
- 自动化测试失败后自动生成 Bug 任务
- DevOps Dashboard 展示项目质量趋势
- CI/CD 配置重启不丢失

---

### 主线 C：AI 助手升级为项目智能分析助手（P1+P2）

**目标**: 从简单的 RAG 问答升级为具备分析、预测、报告能力的项目智能助手。

**适合现在做的原因**: AI 基础架构已具备（DeepSeek API + ES 搜索），当前只需修复 Bug + 增强 Prompt 即可快速提升体验。对话持久化和分析能力是差异化的关键。

**具体功能点**:
1. 修复 AIChat.vue 通信 Bug（P0 紧急）
2. 对话历史持久化（前端 + 后端）
3. 多轮对话支持（上下文记忆）
4. 项目健康度分析
5. Sprint 总结/周报生成
6. 风险任务识别
7. 自然语言查询项目状态
8. AI 结果可追溯引用

**后端改造点**:
- 新建模型: `AIConversation`, `AIMessage`
- 重构 `ai_utils.py`: 支持多轮对话、流式响应、工具调用
- 新建 Prompt 模板系统: 健康度分析/周报/风险评估 等预设模板
- 新建 `/api/ai/conversations/` 端点（CRUD）
- 新建 `/api/ai/analyze/` 端点（项目分析）

**前端改造点**:
- 修复 AIChat.vue Bug
- 删除死代码 Chatbot.vue
- 新建 AIDashboard.vue（项目分析卡片）
- 聊天 UI 支持 Markdown 渲染 + 引用展示
- 侧边栏新增快捷分析入口

**数据库变更**:
- 2 个新模型
- 预设 Prompt 模板可用 JSON 配置文件管理（不必须建表）

**测试点**:
- 对话 CRUD + 历史持久化测试
- 多轮对话上下文拼接测试
- 分析报告内容有效性验证

**验收标准**:
- AIChat 可正常问答
- 对话历史跨页面刷新不丢失
- 支持至少 5 轮连续对话
- 周报/健康度分析输出结构正确

---

## 四、4 个 Sprint 详细计划

### Sprint 1 — 安全加固 + AI Bug 修复（1-2 周）

| 维度 | 内容 |
|------|------|
| **目标** | 修复所有 P0 安全漏洞和 AI Bug，系统达到可用+安全基线 |
| **后端任务** | ① 新建 `HasSystemPermission` DRF 权限类 ② 系统管理所有视图加权限执行 ③ BoardConsumer/ChatConsumer 加项目成员鉴权 ④ TagListView/TaskSearchView 加 ProjectAccessMixin ⑤ 修复 project.py 缺少 logger 导入 ⑥ 新建 `throttles.py`（已完成）⑦ 新建 `AuditLog` 模型 |
| **前端任务** | ① 修复 AIChat.vue 字段错误 ② 删除死代码 Chatbot.vue ③ 系统管理页面无权限显示 403 状态 ④ 路由守卫加 `meta.permission` 检查 |
| **测试任务** | ① 系统管理权限边界测试（未授权=403）② WebSocket 鉴权测试 ③ 标签/搜索门控测试 ④ AI 问答端到端测试 |
| **风险点** | WebSocket 鉴权改动可能影响现有连接逻辑 |
| **交付物** | 安全的系统管理 API、鉴权的 WebSocket、可用的 AI 助手、审计日志基础 |
| **验收标准** | ① 非管理员调用 /api/system/menus/ POST → 403 ② 非成员连接 /ws/board/{id}/ → 被拒 ③ AIChat 可正常问答 ④ 审计日志记录关键操作 |

---

### Sprint 2 — 项目协作闭环（1-2 周）

| 维度 | 内容 |
|------|------|
| **目标** | 补全任务评论、动态日志、项目级角色，形成基础协作闭环 |
| **后端任务** | ① 新建 `ProjectRole`、`ProjectMember` 模型 ② 新建 `TaskComment` 模型 + CRUD API ③ 新建 `TaskActivityLog` 模型 + 自动记录 ④ 新建 TaskComment WebSocket 消费者 ⑤ 项目权限中间件 (HasProjectRole) ⑥ 任务变更信号 → 自动写 ActivityLog |
| **前端任务** | ① 任务详情弹窗加评论面板 ② 新建 TaskComment.vue + TaskActivity.vue ③ Board.vue 任务卡片点击展开详情 ④ 项目成员管理加角色选择 ⑤ 新建 ProjectSettings.vue（角色配置） |
| **测试任务** | ① 评论 CRUD + 实时同步测试 ② 动态日志自动记录测试 ③ 项目角色权限测试 ④ WebSocket 评论同步测试 |
| **风险点** | Board.vue 改动可能影响拖拽逻辑；评论 WebSocket 需要新房间设计 |
| **交付物** | 可评论的任务面板、任务变更时间线、项目级角色管理 |
| **验收标准** | ① 任务评论可创建/查看，实时同步 ② 任务状态/负责人变更自动记录 ③ Owner/Admin/Editor/Viewer 四级权限生效 |

---

### Sprint 3 — QA/DevOps 与看板打通（1-2 周）

| 维度 | 内容 |
|------|------|
| **目标** | 打通测试—缺陷—任务闭环，CI/CD 配置持久化 |
| **后端任务** | ① 新建 `CiCdConfig` 数据库模型（迁移内存数据）② 新建 `PipelineRun` 模型 ③ 新建 `TaskTestLink` M2M through 表 ④ ApiTestCase/UiTestCase 加 `related_tasks` M2M ⑤ 测试失败回调 → 自动创建 Bug Task ⑥ DevOps 统计加项目质量评分 ⑦ 通知类型扩展: test_failure/deploy_success/quality_risk |
| **前端任务** | ① QA 用例详情加"关联任务"选择器 ② 任务详情加"关联测试用例"展示 ③ DevOps 平台 PipelineRun 时间线 ④ 新建 ProjectQualityReport.vue ⑤ 项目 Dashboard 加质量评分卡片 ⑥ 通知列表支持新类型图标 |
| **测试任务** | ① 测试失败自动创建任务流程测试 ② PipelineRun 生命周期测试 ③ 质量评分算法准确性测试 ④ 通知推送端到端测试 |
| **风险点** | 内存 CiCdConfig 迁移可能丢数据；自动创建 Bug 需防重复 |
| **交付物** | 测试-任务双向关联、CI/CD 数据库持久化、项目质量报告、自动 Bug 创建 |
| **验收标准** | ① 测试用例可关联/取消关联任务 ② 自动化测试失败后自动生成 Bug 任务 ③ DevOps Dashboard 展示质量趋势 ④ CI/CD 配置重启不丢失 |

---

### Sprint 4 — AI 助手升级（1-2 周）

| 维度 | 内容 |
|------|------|
| **目标** | AI 支持多轮对话、项目分析报告、周报生成 |
| **后端任务** | ① 新建 `AIConversation` + `AIMessage` 模型 ② 重构 ai_utils.py 支持多轮对话 ③ 新建 Prompt 模板系统（健康度/周报/风险）④ 新建 `/api/ai/conversations/` 端点 ⑤ 新建 `/api/ai/analyze/` 端点 ⑥ AI 工具调用框架（可选） |
| **前端任务** | ① AIChat 支持多轮对话 + 历史加载 ② Markdown 渲染 + 引用展示 ③ 新建 AIDashboard.vue（分析卡片）④ 侧边栏快捷分析入口 ⑤ 预设分析模板选择器 |
| **测试任务** | ① 对话 CRUD + 持久化测试 ② 多轮对话上下文拼接测试 ③ 分析报告输出结构验证 ④ AI 错误处理测试 |
| **风险点** | 分析报告质量依赖 Prompt 调优；长对话 token 消耗大 |
| **交付物** | 持久化多轮对话、项目健康度分析、周报生成、风险识别 |
| **验收标准** | ① 跨页面刷新对话不丢失 ② 支持 5+ 轮连续对话 ③ 周报/健康度输出结构规范 ④ 分析结果引用具体任务 |

---

## 五、数据库模型改造方案

### 5.1 推荐新建的模型

#### ProjectRole + ProjectMember

```python
# room/models.py 新增

class ProjectRole(models.Model):
    """项目级角色"""
    project = models.ForeignKey(Project, on_delete=CASCADE, related_name='roles')
    name = models.CharField(max_length=50)        # Owner, Admin, Editor, Viewer
    key = models.CharField(max_length=30)          # owner, admin, editor, viewer
    permissions = models.JSONField(default=list)   # ['task:create','task:delete','member:invite',...]
    is_system = models.BooleanField(default=False) # 系统预置角色不可删除
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['project', 'key']

class ProjectMember(models.Model):
    """项目成员（替代 Project.members M2M）"""
    project = models.ForeignKey(Project, on_delete=CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=CASCADE, related_name='project_memberships')
    role = models.ForeignKey(ProjectRole, on_delete=SET_NULL, null=True, related_name='members')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['project', 'user']
```

**索引**: `(project, user)` 唯一索引

#### TaskComment

```python
class TaskComment(models.Model):
    """任务评论"""
    task = models.ForeignKey(Task, on_delete=CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=CASCADE, related_name='task_comments')
    content = models.TextField()
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=CASCADE, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['task', 'created_at'])]
```

#### TaskActivityLog

```python
class TaskActivityLog(models.Model):
    """任务变更日志"""
    task = models.ForeignKey(Task, on_delete=CASCADE, related_name='activity_logs')
    user = models.ForeignKey(User, on_delete=CASCADE, related_name='task_activities')
    action = models.CharField(max_length=50)           # created / updated / deleted / moved / assigned / commented
    field_name = models.CharField(max_length=50, blank=True)  # title / column / assignee / tags / status
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['task', '-created_at'])]
```

#### TaskAttachment

```python
class TaskAttachment(models.Model):
    """任务附件"""
    task = models.ForeignKey(Task, on_delete=CASCADE, related_name='attachments')
    uploader = models.ForeignKey(User, on_delete=CASCADE, related_name='uploaded_files')
    file = models.FileField(upload_to='attachments/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
```

#### Sprint（迭代）

```python
class Sprint(models.Model):
    """迭代/冲刺"""
    project = models.ForeignKey(Project, on_delete=CASCADE, related_name='sprints')
    name = models.CharField(max_length=255)
    goal = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

class SprintTask(models.Model):
    """迭代-任务关联"""
    sprint = models.ForeignKey(Sprint, on_delete=CASCADE, related_name='sprint_tasks')
    task = models.ForeignKey(Task, on_delete=CASCADE, related_name='sprints')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['sprint', 'task']
```

#### TaskTestLink（QA关联）

```python
class TaskTestLink(models.Model):
    """任务-测试用例关联"""
    task = models.ForeignKey('room.Task', on_delete=CASCADE, related_name='test_links')
    # 使用 GenericForeignKey 关联多种测试类型
    content_type = models.ForeignKey(ContentType, on_delete=CASCADE)
    object_id = models.PositiveIntegerField()
    test_case = GenericForeignKey('content_type', 'object_id')
    linked_by = models.ForeignKey(User, on_delete=CASCADE)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['task', 'content_type', 'object_id']
        indexes = [models.Index(fields=['content_type', 'object_id'])]
```

#### CiCdConfig（数据库持久化）

```python
class CiCdConfig(models.Model):
    """CI/CD 配置（替代内存字典）"""
    CI_TYPES = [('jenkins','Jenkins'),('gitlab','GitLab CI'),('github','GitHub Actions')]
    project = models.ForeignKey(Project, on_delete=CASCADE, related_name='cicd_configs')
    name = models.CharField(max_length=255)
    ci_type = models.CharField(max_length=20, choices=CI_TYPES)
    webhook_url = models.URLField(blank=True)
    api_token = models.CharField(max_length=255, blank=True)  # 加密存储
    branch = models.CharField(max_length=100, default='main')
    auto_trigger = models.BooleanField(default=False)
    test_suite_ids = models.JSONField(default=list)  # 关联的测试套件ID列表
    headers = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

#### PipelineRun

```python
class PipelineRun(models.Model):
    """CI/CD 流水线执行记录"""
    STATUSES = [('pending','Pending'),('running','Running'),('passed','Passed'),('failed','Failed')]
    cicd_config = models.ForeignKey(CiCdConfig, on_delete=CASCADE, related_name='pipeline_runs')
    project = models.ForeignKey(Project, on_delete=CASCADE, related_name='pipeline_runs')
    status = models.CharField(max_length=20, choices=STATUSES, default='pending')
    commit_sha = models.CharField(max_length=40, blank=True)
    branch = models.CharField(max_length=100, blank=True)
    log_output = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
```

#### AuditLog

```python
class AuditLog(models.Model):
    """通用审计日志"""
    user = models.ForeignKey(User, on_delete=SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=100)              # 'task.create', 'project.delete', 'member.invite'
    resource_type = models.CharField(max_length=50)         # 'task', 'project', 'member', 'role'
    resource_id = models.CharField(max_length=100, blank=True)
    detail = models.JSONField(default=dict)                 # 变更详情
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['action', '-created_at']),
        ]
```

#### AIConversation + AIMessage

```python
class AIConversation(models.Model):
    """AI 对话会话"""
    user = models.ForeignKey(User, on_delete=CASCADE, related_name='ai_conversations')
    project = models.ForeignKey(Project, on_delete=CASCADE, related_name='ai_conversations', null=True)
    title = models.CharField(max_length=255, default='新对话')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

class AIMessage(models.Model):
    """AI 对话消息"""
    ROLE_CHOICES = [('user','用户'),('assistant','助手'),('system','系统')]
    conversation = models.ForeignKey(AIConversation, on_delete=CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_used = models.PositiveIntegerField(default=0)
    # 引用来源（任务ID列表）
    references = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
```

### 5.2 不需要建的模型

| 模型 | 建议 | 原因 |
|------|------|------|
| Requirement/Story | **不建** | 当前 Task 模型可承载需求，通过 `type` 字段区分即可 |
| TestPlan | **不建** | ApiAutoTestSuite 已覆盖测试计划场景 |
| WebhookEvent | **不建** | 可作为 AuditLog 的子类型，暂不独立建表 |

---

## 六、API 设计方案

### 6.1 任务评论

| API 路径 | 方法 | 功能 | 权限 | 请求体 | 返回 |
|----------|------|------|------|--------|------|
| `/api/tasks/{id}/comments/` | GET | 评论列表 | 项目成员 | — | `{results:[Comment], count:N}` |
| `/api/tasks/{id}/comments/` | POST | 创建评论 | 项目成员 | `{content, parent_id?}` | `Comment` |
| `/api/tasks/{id}/comments/{cid}/` | PATCH | 编辑评论 | 评论作者 | `{content}` | `Comment` |
| `/api/tasks/{id}/comments/{cid}/` | DELETE | 删除评论 | 评论作者/项目管理员 | — | `204` |

Comment 结构:
```json
{
  "id": 1, "task": "uuid", "author": {"id":1,"username":"admin"},
  "content": "评论内容", "parent": null, "replies": [],
  "created_at": "2026-05-08T10:00:00Z"
}
```

### 6.2 任务动态

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/tasks/{id}/activities/` | GET | 任务变更日志 | 项目成员 |

Activity 结构:
```json
{
  "id": 1, "user": {"id":1,"username":"admin"},
  "action": "moved", "field_name": "column",
  "old_value": "To Do", "new_value": "In Progress",
  "created_at": "2026-05-08T09:30:00Z"
}
```

### 6.3 任务附件

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/tasks/{id}/attachments/` | GET | 附件列表 | 项目成员 |
| `/api/tasks/{id}/attachments/` | POST | 上传附件 | 项目编辑者+ |
| `/api/tasks/{id}/attachments/{aid}/` | DELETE | 删除附件 | 上传者/管理员 |

### 6.4 项目成员权限

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/projects/{id}/roles/` | GET/POST | 项目角色管理 | 项目管理员 |
| `/api/projects/{id}/roles/{rid}/` | PUT/DELETE | 角色CRUD | 项目管理员 |
| `/api/projects/{id}/members/` | GET | 成员列表(含角色) | 项目成员 |
| `/api/projects/{id}/members/{uid}/` | PUT | 修改成员角色 | 项目管理员 |
| `/api/projects/{id}/members/{uid}/` | DELETE | 移除成员 | 项目管理员 |

### 6.5 迭代管理

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/projects/{id}/sprints/` | GET/POST | 迭代列表/创建 | 项目成员/编辑者 |
| `/api/projects/{id}/sprints/{sid}/` | PUT/DELETE | 更新/删除迭代 | 项目编辑者 |
| `/api/projects/{id}/sprints/{sid}/tasks/` | POST | 添加任务到迭代 | 项目编辑者 |
| `/api/projects/{id}/sprints/{sid}/tasks/{tid}/` | DELETE | 从迭代移除任务 | 项目编辑者 |
| `/api/projects/{id}/sprints/{sid}/burndown/` | GET | 燃尽图数据 | 项目成员 |

### 6.6 测试-任务关联

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/qa/test-cases/{id}/link-task/` | POST | 关联任务 | 项目编辑者 |
| `/api/qa/test-cases/{id}/unlink-task/{tid}/` | DELETE | 取消关联 | 项目编辑者 |
| `/api/tasks/{id}/linked-tests/` | GET | 关联的测试用例 | 项目成员 |

### 6.7 AI 分析

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/ai/conversations/` | GET/POST | 对话列表/新建 | 认证用户 |
| `/api/ai/conversations/{id}/` | DELETE | 删除对话 | 对话所有者 |
| `/api/ai/conversations/{id}/messages/` | GET | 历史消息 | 对话所有者 |
| `/api/ai/chat/` | POST | 发送消息(多轮) | 认证用户 |
| `/api/ai/analyze/health/` | POST | 项目健康度分析 | 项目成员 |
| `/api/ai/analyze/weekly/` | POST | 周报生成 | 项目成员 |
| `/api/ai/analyze/risks/` | POST | 风险任务识别 | 项目成员 |
| `/api/ai/analyze/sprint-summary/` | POST | Sprint 总结 | 项目成员 |

### 6.8 DevOps 执行记录

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/qa/devops/cicd-config/` | GET/POST | CI/CD配置管理 | 项目编辑者 |
| `/api/qa/devops/pipeline-runs/` | GET | 执行历史 | 项目成员 |
| `/api/qa/devops/pipeline-runs/{id}/` | GET | 执行详情 | 项目成员 |
| `/api/qa/devops/cicd-config/{id}/trigger/` | POST | 手动触发 | 项目编辑者 |

### 6.9 审计日志

| API 路径 | 方法 | 功能 | 权限 |
|----------|------|------|------|
| `/api/audit-logs/` | GET | 审计日志查询 | 系统管理员 |
| `/api/projects/{id}/audit-logs/` | GET | 项目级审计日志 | 项目管理员 |

---

## 七、前端页面与组件改造方案

### 7.1 新增页面

| 页面 | 路由 | 说明 |
|------|------|------|
| `TaskDetail.vue` | `/projects/:pid/tasks/:tid` | 任务详情独立页（评论+动态+附件+关联测试） |
| `ProjectMembers.vue` | `/projects/:pid/members` | 成员管理增强版（含角色选择） |
| `ProjectSprints.vue` | `/projects/:pid/sprints` | 迭代看板 |
| `SprintBoard.vue` | `/projects/:pid/sprints/:sid` | 单个迭代的任务面板+燃尽图 |
| `ProjectQualityReport.vue` | `/projects/:pid/quality` | 项目质量报告 |
| `AIDashboard.vue` | `/projects/:pid/ai-dashboard` | AI 分析仪表板 |

### 7.2 需要重构的页面

| 页面 | 当前问题 | 改造方案 |
|------|----------|----------|
| `Board.vue` (29KB) | 巨型组件，逻辑+UI耦合 | 拆分为: TaskCard.vue, ColumnView.vue, TaskCreateDialog.vue, TaskDetailDrawer.vue, BoardToolbar.vue |
| `TestResultDetail.vue` (33KB) | 太大难维护 | 拆分为: ResultOverview.vue, PerformanceCharts.vue, AssertionDetails.vue |
| `UiCaseDetail.vue` (28KB) | 录制器逻辑嵌入视图 | 拆分为: StepEditor.vue, RecorderPanel.vue, StepPreview.vue |
| `AIChat.vue` | 字段Bug+无Markdown | 重建为 AIChatPage.vue，集成 marked，修复字段 |
| `ProjectLayout.vue` | 菜单逻辑复杂 | 提取 SideMenu.vue 组件 |

### 7.3 新增组件

| 组件 | 用途 | 复用场景 |
|------|------|----------|
| `TaskComment.vue` | 评论列表+输入框+实时更新 | TaskDetail |
| `TaskActivity.vue` | 时间线组件 | TaskDetail |
| `TaskAttachment.vue` | 附件上传+预览 | TaskDetail |
| `TaskTestLink.vue` | 关联测试用例选择器 | TaskDetail, QA CaseDetail |
| `RoleSelector.vue` | 项目角色下拉选择 | ProjectMembers, ProjectSettings |
| `SprintPicker.vue` | 迭代选择器 | TaskCreateDialog |
| `QualityScoreCard.vue` | 质量评分卡片 | ProjectDashboard, QualityReport |
| `PipelineTimeline.vue` | CI/CD 时间线 | DevOpsPlatform |
| `AuditLogTable.vue` | 审计日志表格 | 系统管理 |
| `AIAnalysisCard.vue` | AI 分析结果卡片 | AIDashboard |
| `PermissionGuard.vue` | 权限包裹组件(替代指令) | 全局 |
| `LoadingState.vue` | 统一加载态 | 全局 |
| `ErrorState.vue` | 统一错误态+重试按钮 | 全局 |

### 7.4 Pinia Store 拆分建议

```
stores/
├── auth.ts              # 认证+权限 (已有)
├── board/
│   ├── index.ts         # 统一入口 (已完成)
│   ├── task.ts          # 任务 CRUD
│   ├── column.ts        # 列管理
│   ├── tag.ts           # 标签管理
│   ├── user.ts          # 用户管理
│   └── comment.ts       # 新增: 评论管理 + WebSocket
├── sprint.ts            # 新增: 迭代管理
├── ai.ts                # 新增: AI 对话 + 分析
├── devops.ts            # 新增: CI/CD 执行状态
├── notification.ts      # 通知 (已有)
└── composables/
    ├── useWebSocket.ts  # WebSocket 封装 (已有)
    ├── usePagination.ts # 新增: 分页组合函数
    └── useAuditLog.ts   # 新增: 审计日志查询
```

### 7.5 WebSocket Composable 优化

```typescript
// 优化点1: 支持房间鉴权 token 传递
function connect(url: string, token?: string) {
  const wsUrl = token ? `${url}?token=${token}` : url;
  // ...
}

// 优化点2: 支持消息确认 ACK
function sendWithAck(msg: any): Promise<void> {
  return new Promise((resolve, reject) => {
    const ackId = generateId();
    ws.send(JSON.stringify({ ...msg, ackId }));
    // 超时 5s reject
  });
}

// 优化点3: 支持房间切换 (离开旧房间，加入新房间)
function switchRoom(oldRoom: string, newRoom: string) {
  close();
  connect(newRoom);
}
```

### 7.6 权限指令优化

```typescript
// 问题: 当前指令在 mounted 时检查，权限变化后不响应
// 优化: 使用 watchEffect 让权限响应式更新

app.directive('permission', {
  mounted(el, binding) {
    const authStore = useAuthStore();
    const stop = watchEffect(() => {
      if (!authStore.checkPermission(binding.value)) {
        el.style.display = 'none';
      } else {
        el.style.display = '';
      }
    });
    el._permissionStop = stop; // 清理用
  },
  unmounted(el) {
    el._permissionStop?.();
  }
});
```

### 7.7 错误处理和 Loading 状态规范

```vue
<!-- 统一模式: 每个数据加载组件使用此结构 -->
<template>
  <LoadingState v-if="loading" />
  <ErrorState v-else-if="error" :message="error" @retry="fetchData" />
  <EmptyState v-else-if="!data.length" description="暂无数据" />
  <div v-else>
    <!-- 正常内容 -->
  </div>
</template>
```

### 7.8 用户体验改进点

1. **任务拖拽反馈**: 拖拽时高亮目标列 + 位置预览
2. **全局搜索**: 顶部搜索栏支持搜索任务/项目/测试用例
3. **快捷键**: `Ctrl+K` 全局命令面板，`N` 快速创建任务
4. **通知聚合**: 同类通知折叠（"3条新评论"而非3条单独通知）
5. **移动端适配**: 响应式布局（当前仅适配桌面）
6. **深色模式**: CSS 变量已完备，添加切换开关即可

---

## 八、AI 助手升级方案

### 8.1 整体架构

```
┌─────────────────────────────────────────────────┐
│                  Frontend                        │
│  AIChatPage  ←→  AIDashboard (分析卡片)          │
└──────────────────┬──────────────────────────────┘
                   │ HTTP POST / SSE
┌──────────────────▼──────────────────────────────┐
│              AI Service Layer                    │
│  /api/ai/chat/     (多轮对话)                    │
│  /api/ai/analyze/  (分析报告)                    │
│  PromptManager     (模板管理)                    │
└──────┬──────────────────────────┬───────────────┘
       │                          │
┌──────▼──────┐  ┌───────────────▼──────────────┐
│  RAG Engine │  │  Project Data Collector       │
│  ES Search  │  │  Tasks + Comments + Sprints   │
│  Haystack   │  │  TestResults + PipelineRuns   │
└──────┬──────┘  └───────────────┬──────────────┘
       │                          │
┌──────▼──────────────────────────▼──────────────┐
│         DeepSeek API (OpenAI Compatible)        │
└─────────────────────────────────────────────────┘
```

### 8.2 数据流（多轮对话）

```
1. 用户选择/创建对话会话 → GET /api/ai/conversations/
2. 用户发消息 → POST /api/ai/chat/ {conversation_id, project_id, message}
3. 后端:
   a. 加载最近 N 轮对话历史 (最近 10 条消息)
   b. RAG 搜索相关任务上下文
   c. 拼接 system_prompt + history + context + user_message
   d. 调用 DeepSeek API
   e. 保存消息到 DB
   f. 返回完整响应
4. 前端渲染 Markdown + 引用
```

### 8.3 Prompt 设计

#### 健康度分析 Prompt
```
System: 你是项目管理专家。分析项目健康度，输出 JSON。

Context: 项目 "{project_name}" 当前数据:
- 总任务 {total}，完成率 {completion_rate}%
- 逾期任务 {overdue} 个
- 本周新增 {new_this_week}，完成 {completed_this_week}
- 最近测试通过率 {test_pass_rate}%
- {active_sprint} 迭代燃尽趋势: {burndown_data}

要求:
1. 计算健康度评分 (0-100)
2. 识别 Top 3 风险点
3. 给出具体改进建议
4. 输出 JSON: {"score": N, "risks": [...], "suggestions": [...]}
```

#### 周报生成 Prompt
```
System: 你是项目周报撰写助手。基于本周数据生成周报。

Context: 本周 ({week_start} ~ {week_end}) 项目数据:
- 完成任务: {completed_tasks}
- 进行中: {in_progress_tasks}
- 新增问题: {new_issues}
- 测试结果: {test_results_summary}

格式: 标题 / 本周进展 / 下周计划 / 风险与问题 / 数据概览
```

#### 风险识别 Prompt
```
System: 你是项目风险分析师。识别需要关注的任务。

Context: 项目任务列表含: 标题/状态/负责人/标签/创建日期/最近更新

风险规则:
- 超过3天未更新且状态为"In Progress" → 高风险
- 截止日期在2天内且未完成 → 紧急
- 分配给离职/不活跃成员 → 需重新分配
- 阻塞任务无进展 → 中风险
```

### 8.4 安全边界

| 边界 | 方案 |
|------|------|
| **数据隔离** | AI 查询只返回当前项目数据（project_id 过滤强制） |
| **Token 限制** | 上下文长度控制在 4000 tokens 内，超出截断旧消息 |
| **敏感信息** | 不在上下文中包含密码/Token/密钥等字段 |
| **API 限流** | AI 端点单独限流: 20次/分钟/用户 |
| **内容过滤** | 用户输入长度限制 2000 字，拒绝非项目相关问题 |
| **成本控制** | 记录每次调用的 token 消耗，设置月度预算告警 |

### 8.5 前端交互设计

```
AIChatPage 布局:
┌─────────────┬──────────────────────┐
│ 对话列表     │                      │
│ [+新建对话]  │  💬 对话消息区        │
│             │                      │
│ 历史对话1    │  [用户] 本周进度怎样？ │
│ 历史对话2    │  [AI] 本周完成了...   │
│             │  📎 引用了 3 个任务   │
│             │                      │
│             ├──────────────────────┤
│             │ [输入框]         [发送]│
│             │ [🎯分析模板选择器]     │
└─────────────┴──────────────────────┘

分析模板快捷入口:
┌─────────────────────────────────────┐
│ 📊 健康度分析  📝 生成周报           │
│ ⚠️ 风险识别    📈 Sprint总结         │
│ 🧪 测试建议    🐛 生成Bug报告        │
└─────────────────────────────────────┘
```

---

## 九、QA / DevOps / 看板闭环方案

### 9.1 测试用例关联任务

```
数据模型:
  Task ←→ TaskTestLink (GenericFK) ←→ ApiTestCase / UiTestCase / PerformanceTestCase

API流程:
  1. 在任务详情页，点击"关联测试用例"
  2. 弹出搜索框，可搜索已存在的测试用例
  3. 选择后 POST /api/qa/test-cases/{id}/link-task/
  4. 关联展示在任务详情和用例详情两处
```

### 9.2 测试失败自动创建 Bug

```
流程:
  1. 自动化测试执行 (ApiAutoTestExecuteView)
  2. 检测到用例失败 (passed=False)
  3. 检查: 该用例是否有关联任务? 若有且任务状态为"Done"，skip
  4. 若无关/任务非Done → 自动创建 Bug Task:
     - title: "[测试失败] {case_name}"
     - content: "自动化测试失败\n- 接口: {url}\n- 预期: {expected}\n- 实际: {actual}\n- 失败详情: {error}"
     - column: 项目第一个列 (To Do)
     - tags: ["Bug", "Auto-generated"]
     - assignee: 用例创建者
  5. 创建 TaskTestLink 关联
  6. 发送通知给 assignee
```

### 9.3 CI/CD 执行结果反写

```
PipelineRun 生命周期:
  pending → running → passed/failed

触发方式:
  - Webhook: POST /api/qa/devops/cicd-config/{id}/webhook/
  - 手动: POST /api/qa/devops/cicd-config/{id}/trigger/
  - 定时: Celery Beat 读取 cron_expression

执行结果处理:
  - Passed → 更新 PipelineRun status=passed, 记录 test_results
  - Failed → 更新 status=failed, 解析失败日志
    → 查找关联的 test_case
    → 若有关联任务 → 在任务评论区添加 "CI 构建 #N 失败"
    → 发送通知 to 项目成员
```

### 9.4 项目质量报告

```
评分维度 (每项 0-20 分, 总分 100):
  1. 测试覆盖率 (关联测试的任务数 / 总任务数)
  2. 测试通过率 (最近 10 次执行)
  3. 性能指标 (P95 延迟 vs 阈值)
  4. Bug 密度 (Bug 标签任务数 / 总任务数)
  5. 部署成功率 (最近 10 次 Pipeline)

展示:
  - 雷达图: 5 个维度
  - 趋势折线图: 最近 30 天评分变化
  - 改进建议: AI 生成
```

---

## 十、安全与权限增强方案

### 10.1 项目级 RBAC 实现

```python
# backend/room/permissions.py (新建)

from rest_framework.permissions import BasePermission

class HasProjectRole(BasePermission):
    """检查用户在项目中的角色权限"""
    def __init__(self, required_permission):
        self.required_permission = required_permission

    def has_permission(self, request, view):
        # 从 URL 或 request 获取 project_id
        project_id = view.kwargs.get('project_id') or view.kwargs.get('pk')
        if not project_id:
            return False
        return check_project_permission(request.user, project_id, self.required_permission)

class HasSystemPermission(BasePermission):
    """检查用户是否拥有系统级权限码"""
    def __init__(self, permission_code):
        self.permission_code = permission_code

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            profile = request.user.system_profile
            return self.permission_code in profile.get_all_permissions()
        except SystemUserProfile.DoesNotExist:
            return False
```

**使用方式:**
```python
# system/views.py
class MenuListView(APIView):
    permission_classes = [IsAuthenticated, HasSystemPermission('sys:menu:list')]

class RoleListView(APIView):
    permission_classes = [IsAuthenticated, HasSystemPermission('sys:role:list')]

# room/views/board.py
class TaskListView(APIView):
    permission_classes = [IsAuthenticated, HasProjectRole('task:create')]
```

### 10.2 WebSocket 权限校验

```python
# consumers.py BoardConsumer.connect()
async def connect(self):
    user = self.scope['user']
    if not user.is_authenticated:
        await self.close()
        return

    project_id = self.scope['url_route']['kwargs']['project_id']
    if not await self.is_project_member(user, project_id):
        await self.close(code=4003)
        return

    await self.accept()
    await self.channel_layer.group_add(f'board_{project_id}', self.channel_name)

@database_sync_to_async
def is_project_member(self, user, project_id):
    return Project.objects.filter(
        Q(id=project_id) & (Q(owner=user) | Q(members=user))
    ).exists()
```

### 10.3 审计日志埋点

```python
# 关键操作点
AUDIT_POINTS = {
    'task.create':      '创建任务',
    'task.update':      '更新任务',
    'task.delete':      '删除任务',
    'task.comment':     '评论任务',
    'project.create':   '创建项目',
    'project.delete':   '删除项目',
    'member.invite':    '邀请成员',
    'member.remove':    '移除成员',
    'member.role_change':'修改成员角色',
    'role.create':      '创建角色',
    'role.update':      '更新角色',
    'test.execute':     '执行测试',
    'cicd.trigger':     '触发部署',
    'ai.query':         'AI 查询',
}

# 实现: Django 信号 or 装饰器
@audit_log('task.update')
def update_task(request, task_id):
    ...

# 审计日志中间件 (记录所有写操作)
class AuditLogMiddleware:
    def __call__(self, request):
        response = self.get_response(request)
        if request.method in ('POST','PUT','PATCH','DELETE'):
            AuditLog.objects.create(
                user=request.user,
                action=f'{request.resolver_match.url_name}.{request.method.lower()}',
                resource_type=...,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT',''),
            )
        return response
```

### 10.4 其他安全增强

| 项目 | 方案 |
|------|------|
| **文件上传安全** | 头像已安全处理，附件上传同理：签名校验+Pillow重编码+类型白名单+大小限制(10MB) |
| **敏感操作二次确认** | 删除项目/移除成员/清空数据 → 前端 ElMessageBox + 后端验证密码 |
| **CSRF** | 当前 CsrfExemptSessionAuthentication + withCredentials 可用，建议生产环境启用 CSRF 中间件 |
| **Session** | 设置 `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SECURE=True`(生产) |
| **CORS** | 当前 localhost 白名单正确，生产部署需更新为实际域名 |
| **ALLOWED_HOSTS** | 生产环境设为实际域名列表，禁止 `*` |

---

## 十一、测试与质量保障方案

### 11.1 测试金字塔

```
              ╱  E2E: Playwright (10-15 用例)
             ╱   关键用户流程
            ╱
           ╱   集成测试: pytest (60+ 用例)
          ╱    API + WebSocket + Celery
         ╱
        ╱     前端组件测试: Vitest (30+ 用例)
       ╱      Store + 组件
      ╱
     ╱       单元测试: pytest (80+ 用例)
    ╱        模型 + 工具函数 + 权限
   ╱
  ╱
```

### 11.2 各层测试计划

| 层级 | 工具 | 目标数量 | 覆盖重点 |
|------|------|----------|----------|
| **后端单元** | pytest | 80+ | 模型方法、序列化器、权限类、工具函数、信号处理器 |
| **API 集成** | pytest + APIClient | 60+ | 所有 CRUD 端点、权限边界、分页、限流、错误处理 |
| **WebSocket** | pytest + async test | 10+ | 连接鉴权、消息广播、房间隔离 |
| **Celery 任务** | pytest + eager mode | 8+ | 搜索索引更新、通知发送 |
| **前端 Store** | Vitest | 15+ | 每个 Store 的 actions/getters、mock API |
| **前端组件** | Vitest + vue-test-utils | 15+ | 关键组件渲染、事件、权限指令 |
| **E2E** | Playwright | 15+ | 登录→建项目→加任务→拖拽→评论→AI问答 完整流程 |
| **安全** | pytest + 自定义 | 10+ | SQL注入、XSS、越权访问、文件上传攻击 |
| **性能** | Locust | 持续 | 关键 API 的 P95<500ms 保证 |

### 11.3 覆盖率目标

| 模块 | 当前 | Sprint2目标 | Sprint4目标 |
|------|------|-------------|-------------|
| `room/` | ~30% | 60% | 80% |
| `qa_center/` | ~5% | 40% | 70% |
| `system/` | ~5% | 50% | 80% |
| `backend/` | ~50% | 70% | 85% |
| **前端** | ~2% | 30% | 50% |

---

## 十二、3 个月路线图

### 第 1 个月 — 稳定主流程和权限体系

| 维度 | 内容 |
|------|------|
| **核心目标** | 修复所有 P0 安全问题，建立项目级 RBAC，任务协作基础功能 |
| **关键功能** | 系统权限强制执行、WebSocket鉴权、任务评论、动态日志、项目角色 |
| **技术任务** | ① HasSystemPermission/HasProjectRole DRF类 ② WebSocket鉴权重构 ③ TaskComment+ActivityLog模型+API ④ ProjectRole+ProjectMember模型+API ⑤ 审计日志基础 ⑥ AIChat Bug修复 |
| **风险** | WebSocket鉴权改动可能影响现有实时功能 |
| **验收标准** | ① 所有P0安全问题修复 ② 4级项目角色可用 ③ 任务可评论+追溯变更 ④ 审计日志记录关键操作 |

### 第 2 个月 — 打通 QA / DevOps / 任务闭环

| 维度 | 内容 |
|------|------|
| **核心目标** | 测试-缺陷-任务形成闭环，CI/CD数据可追溯，项目质量可度量 |
| **关键功能** | 测试任务关联、失败自动建Bug、PipelineRun持久化、质量报告、迭代管理 |
| **技术任务** | ① TaskTestLink M2M+API ② CiCdConfig+PipelineRun模型 ③ Sprint模型+API+燃尽图 ④ 质量评分算法 ⑤ 通知系统扩展 ⑥ 前端 Dashboard 质量卡片 |
| **风险** | 自动建Bug可能重复创建；质量评分算法需验证 |
| **验收标准** | ① 测试失败→Bug任务自动生成 ② CI/CD执行记录可查询 ③ 迭代燃尽图可用 ④ 质量评分雷达图展示 |

### 第 3 个月 — AI 智能分析和产品化体验

| 维度 | 内容 |
|------|------|
| **核心目标** | AI 从问答工具升级为分析助手，UI/UX产品化打磨 |
| **关键功能** | 多轮对话、健康度分析、周报生成、风险识别、AI结果引用、移动端适配 |
| **技术任务** | ① AIConversation+AIMessage模型 ② Prompt模板系统 ③ 分析报告API ④ 流式响应(SSE) ⑤ 前端组件拆分+统一加载/错误态 ⑥ 深色模式切换 |
| **风险** | AI分析质量依赖Prompt调优；流式响应增加复杂度 |
| **验收标准** | ① 多轮对话可追问 ② 周报/健康度分析可用 ③ AI结果引用具体任务 ④ 所有页面有统一错误/加载态 ⑤ 深色模式可用 |

---

## 十三、最终建议

### 下一步应该先做什么

**立刻做（本周内）:**

1. **修复 AI 助手 Bug**（15分钟）
   - `frontend/src/views/AIChat.vue`: `message` → `question`, `response` → `answer`
   - `backend/room/views/project.py`: 加 `import logging; logger = logging.getLogger(__name__)`

2. **系统管理权限执行**（2-3小时）
   - 新建 `backend/system/permissions.py` → `HasSystemPermission` 类
   - 给 `system/views.py` 所有视图加权限检查
   - 这是当前最大的安全漏洞

3. **WebSocket 项目鉴权**（2-3小时）
   - `BoardConsumer.connect()` 加项目成员检查
   - `ChatConsumer.connect()` 加项目成员检查
   - 防止非成员监听/参与其他项目的实时通信

这三项修完，系统达到基本安全基线。然后按照 Sprint 1-4 推进。

### 架构建议

1. **不要急于拆分 room 应用** — 当前功能还在快速迭代期，过早拆分会增加跨应用通信成本。等功能稳定后再拆。

2. **不要引入微服务** — Django Monolith + Celery Worker + Redis 当前架构足够支撑到 100+ 用户。除非遇到明确的性能瓶颈。

3. **优先做数据模型层的事** — 评论、动态日志、项目角色这些基础模型建好后，前端可以逐步迭代。模型设计要一次到位。

4. **测试别追求完美覆盖率** — 先覆盖关键路径（登录→项目→看板→任务CRUD）和权限边界（越权访问=403）。60% 覆盖率的针对性测试远好过 90% 覆盖率的无用测试。

5. **AI 不要过度设计** — 当前 RAG 基础已可用，优先修复 Bug + 加对话历史持久化。分析报告功能用好的 Prompt 工程就能实现，不需要复杂的 Agent 框架。
