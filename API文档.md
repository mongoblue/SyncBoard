# FlowSpace (SyncBoard) API 文档

> 版本: v2.0 | 更新: 2026-05-09 | 端点总数: 80+

---

## 1. 基础信息

- **基础路径**: `http://localhost:8000/api/`
- **认证**: Django Session + CSRF Token (`X-CSRFToken` 头)
- **限流**: 匿名 100/min, 认证 1000/min, 登录 5/min
- **分页**: 列表接口默认 `?page=1&page_size=20`，返回 `{count, next, previous, results}`
- **WebSocket 鉴权**: 看板/聊天需项目成员身份

### 错误响应格式

```json
{
  "error": true,
  "code": "ERROR_CODE",
  "message": "描述",
  "details": {}
}
```

### 常见状态码

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 204 | 删除成功 |
| 400 | 参数错误 |
| 401 | 未登录 |
| 403 | 无权限 (系统权限或项目成员资格) |
| 404 | 资源不存在 |
| 429 | 请求过于频繁 |

---

## 2. 认证模块

### `POST /api/auth/login/`
限流: 5次/分钟

请求:
```json
{"username": "admin", "password": "password123"}
```
响应 (200):
```json
{"id": 1, "username": "admin", "email": "admin@example.com", "profile": {"avatar": "..."}}
```
失败 (401): `{"detail": "用户名或密码错误"}`

### `POST /api/auth/logout/`
响应: `{"detail": "注销成功"}`

### `GET /api/auth/me/`
要求: 认证
响应: 同登录接口，未登录 401

---

## 3. 项目管理

### `GET /api/projects/`
获取用户参与的项目列表。要求: 认证

### `POST /api/projects/`
创建项目 (自动生成 3 个默认列 + 4 个默认角色 + 4 个默认标签)
```json
{"name": "项目名称", "description": "描述"}
```

### `DELETE /api/projects/{id}/`
仅项目 Owner 可删除

### `POST /api/projects/{id}/invite/`
```json
{"username": "要邀请的用户名"}
```

---

## 4. 看板列

### `GET /api/columns/?project=<id>`
要求: 认证 + 项目成员。返回列 + 嵌套任务

### `POST /api/columns/`
要求: 认证 + 项目成员
```json
{"title": "列名", "project": "项目ID", "position": 1}
```

### `PATCH /api/columns/{id}/`
更新列标题/位置

### `DELETE /api/columns/{id}/`
列下有任务时拒绝

---

## 5. 任务管理

### `GET /api/tasks/?project=<id>&page=1&page_size=20`
分页列表，max 100条/页。要求: 认证 + 项目成员

### `POST /api/tasks/`
要求: 认证 + 项目成员
```json
{"title":"标题", "content":"描述", "column":"列ID", "assignee":1, "tags":[1,2]}
```
创建/更新/删除均通过 WebSocket 广播到看板房间

### `PATCH /api/tasks/{id}/`
部分更新 (标题/内容/列/负责人/标签/位置)

### `DELETE /api/tasks/{id}/`
删除任务

### `POST /api/tasks/batch-delete/`
```json
{"task_ids": ["id1", "id2"]}
```

### `GET /api/tasks/search/?q=关键词&project_id=<id>`
全文搜索 (ES + Haystack)

---

## 6. 标签管理

### `GET /api/tags/?project=<id>`
要求: 认证 + 项目成员

### `POST /api/tags/`
要求: 认证 + 项目成员
```json
{"name":"Bug", "color":"#f56c6c", "project":"项目ID"}
```

### `PATCH/DELETE /api/tags/{id}/`
要求: 认证 + 项目成员

---

## 7. 任务协作

### 评论
#### `GET /api/tasks/{task_id}/comments/`
评论列表 (分页，含嵌套回复)。要求: 项目成员

#### `POST /api/tasks/{task_id}/comments/`
创建评论 (WebSocket 广播 + 自动 ActivityLog)
```json
{"content": "评论内容", "parent": null}
```

#### `PATCH /api/tasks/{task_id}/comments/{comment_id}/`
编辑自己的评论

#### `DELETE /api/tasks/{task_id}/comments/{comment_id}/`
删除 (作者或项目 Owner)

### 动态日志
#### `GET /api/tasks/{task_id}/activities/`
任务变更时间线 (分页)
```json
[{
  "id": 1, "user_detail": {...},
  "action": "updated", "field_name": "title",
  "old_value": "旧标题", "new_value": "新标题",
  "created_at": "2026-05-09T10:00:00Z"
}]
```

### 附件
#### `GET /api/tasks/{task_id}/attachments/`
附件列表。要求: 项目成员

#### `POST /api/tasks/{task_id}/attachments/`
上传附件 (multipart/form-data, `file` 字段, 最大 10MB)

#### `DELETE /api/tasks/{task_id}/attachments/{aid}/`
删除附件 (上传者或项目 Owner)

### 关联测试
#### `GET /api/tasks/{task_id}/linked-tests/`
查看任务关联的测试用例
```json
{"task_id": "...", "linked_tests": [
  {"test_type":"api", "id":1, "name":"用例名", "url":"/api/..."}
], "count": 3}
```

---

## 8. 项目角色与成员

### `GET /api/projects/{id}/roles/`
项目角色列表。要求: 项目成员

### `POST /api/projects/{id}/roles/`
创建角色。要求: 项目 Owner
```json
{"name":"Reviewer", "key":"reviewer", "permissions":["task:create","task:edit"]}
```

### `PUT /api/projects/{id}/roles/{rid}/`
更新角色。要求: 项目 Owner。系统预置角色 (is_system=true) 不可修改

### `DELETE /api/projects/{id}/roles/{rid}/`
删除角色。要求: 项目 Owner

### `GET /api/projects/{id}/members/`
成员列表 (含角色)。要求: 项目成员

### `PUT /api/projects/{id}/members/`
修改成员角色。要求: 项目 Owner
```json
{"user_id": 1, "role_id": 2}
```

### `DELETE /api/projects/{id}/members/?user_id=<id>`
移除成员。要求: 项目 Owner

---

## 9. 迭代/Sprint

### `GET /api/projects/{id}/sprints/`
迭代列表 (含任务数/完成数)。要求: 项目成员

### `POST /api/projects/{id}/sprints/`
创建迭代。要求: 项目成员
```json
{"name":"Sprint 1", "goal":"完成核心功能", "start_date":"2026-05-01", "end_date":"2026-05-14"}
```

### `GET/PUT/DELETE /api/projects/{id}/sprints/{sid}/`
迭代详情/更新/删除

### `POST /api/projects/{id}/sprints/{sid}/tasks/`
添加任务到迭代
```json
{"task_id": "uuid"}
```

### `DELETE /api/projects/{id}/sprints/{sid}/tasks/?task_id=<uuid>`
从迭代移除任务

### `GET /api/projects/{id}/sprints/{sid}/burndown/`
燃尽图数据
```json
{
  "sprint_name": "Sprint 1", "total_tasks": 10,
  "burndown": [
    {"date":"2026-05-01", "remaining":10, "ideal":10.0},
    {"date":"2026-05-02", "remaining":8, "ideal":9.3}
  ]
}
```

---

## 10. AI 助手

### `GET /api/ai/conversations/?project_id=<id>`
对话列表。要求: 认证

### `POST /api/ai/conversations/`
创建对话
```json
{"project_id": "uuid", "title": "新对话"}
```

### `DELETE /api/ai/conversations/{id}/`
删除对话 (仅所有者)

### `POST /api/ai/chat/`
发送消息 (多轮对话)
```json
{
  "project_id": "uuid",
  "question": "项目进度如何？",
  "conversation_id": 1
}
```
响应:
```json
{
  "conversation_id": 1,
  "answer": "基于项目数据...",
  "references": [{"id":"uuid", "title":"任务名", ...}],
  "question": "项目进度如何？"
}
```

### `POST /api/ai/chat/stream/`
流式响应 (SSE)。参数同上。响应为 `text/event-stream`:
```
data: {"chunk": "基于"}
data: {"chunk": "当前"}
data: {"done": true, "conversation_id": 1, "references": [...]}
```

### `POST /api/ai/analyze/health/`
项目健康度分析
```json
{"project_id": "uuid"}
```
响应: `{"project":"项目名", "analysis":"AI分析文本", "data":{...}}`

### `POST /api/ai/analyze/weekly/`
周报生成。参数同上

### `POST /api/chat/` (兼容旧版)
简单 RAG 问答
```json
{"project_id": "uuid", "question": "问题"}
```

---

## 11. QA 质量中心

### API 测试用例 (ViewSet)
`GET/POST/PUT/PATCH/DELETE /api/qa/api-cases/`

| 字段 | 说明 |
|------|------|
| name | 用例名称 |
| url | 请求 URL |
| method | GET/POST/PUT/PATCH/DELETE |
| headers | JSON 请求头 |
| body | 请求体 |
| expected_status | 预期状态码 |
| expected_response | 预期响应 JSON |
| related_tasks | 关联任务 ID 列表 (M2M) |

### UI 测试用例 (ViewSet)
`GET/POST/PUT/PATCH/DELETE /api/qa/ui-cases/`

### 自动化测试 (ViewSet)
| 端点 | 说明 |
|------|------|
| `/api/qa/auto-suites/` | 套件 CRUD |
| `/api/qa/auto-cases/` | 用例 CRUD |
| `/api/qa/auto-assertions/` | 断言 CRUD |
| `/api/qa/auto-execute/` | `POST {"suite_id":1}` 执行套件 |
| `/api/qa/auto-results/` | 套件级结果 |
| `/api/qa/auto-case-results/` | 用例级结果 |

### 性能测试 (ViewSet)
`/api/qa/performance-cases/` + `/api/qa/performance-results/`

### 测试结果 (ViewSet)
`/api/qa/test-results/` (支持按 test_type/status/project 筛选)

### 关联管理
#### `POST /api/qa/link-task/`
```json
{"test_type":"api", "case_id":1, "task_id":"uuid"}
```

#### `POST /api/qa/unlink-task/`
参数同上，取消关联

### 数据工厂
#### `GET /api/qa/data-factory/`
返回随机测试数据

---

## 12. DevOps 平台

### `GET /api/qa/devops/stats/?days=30`
仪表板统计
```json
{"overview":{"total":100,"passed":85,"failed":12},
 "by_type":{"api":{"total":40,"passed":38}}, "daily_trend":[...]}
```

### `GET /api/qa/devops/recent-executions/?limit=20`
最近执行记录

### CI/CD 配置 (数据库持久化)
| 端点 | 说明 |
|------|------|
| `GET/POST /api/qa/devops/cicd-config/` | 列表/创建 |
| `PUT/DELETE /api/qa/devops/cicd-config/{id}/` | 更新/软删除 |

```json
{"name":"CI","type":"jenkins","webhook_url":"...","project_id":"...","branch":"main","auto_trigger":false}
```

### Pipeline 执行
| 端点 | 说明 |
|------|------|
| `GET /api/qa/devops/pipeline-runs/?project_id=X` | 执行历史 |
| `GET /api/qa/devops/pipeline-runs/{id}/` | 执行详情 (含日志) |
| `POST /api/qa/devops/cicd-config/{id}/trigger/` | 手动触发 |
| `POST /api/qa/devops/cicd-config/{id}/webhook/` | Webhook 回调 |

Webhook 示例:
```bash
curl -X POST /api/qa/devops/cicd-config/1/webhook/ \
  -H "X-CI-Token: your-token" \
  -d '{"status":"passed","commit_sha":"abc123","test_results_summary":{"total":20,"passed":18}}'
```

### 项目质量报告
#### `GET /api/qa/devops/quality-report/?project_id=X`
```json
{
  "total_score": 78.5,
  "dimensions": [
    {"name":"测试覆盖","score":15.0,"max":20,"detail":"8/20 任务有测试"},
    {"name":"测试通过率","score":18.0,"max":20,"detail":"9/10 通过"},
    {"name":"性能指标","score":15.0,"max":20,"detail":"P95: 320ms"},
    {"name":"Bug密度","score":15.0,"max":20,"detail":"12.5%"},
    {"name":"部署成功率","score":15.5,"max":20,"detail":"7/9 成功"}
  ],
  "trend": [{"date":"2026-04-09","rate":85.0}, ...]
}
```

### 测试任务
| 端点 | 说明 |
|------|------|
| `GET/POST /api/qa/devops/tasks/` | 任务管理 |
| `GET/PUT/DELETE /api/qa/devops/tasks/{id}/` | 任务详情 |
| `POST /api/qa/devops/tasks/{id}/execute/` | 执行任务 |
| `GET /api/qa/devops/tasks/{id}/status/` | 查询状态 |
| `GET /api/qa/devops/tasks/{id}/history/` | 执行历史 |

---

## 13. 系统管理

所有端点要求认证 + 对应系统权限码:

| 端点 | GET | POST | PUT | DELETE | 权限码 |
|------|-----|------|-----|--------|--------|
| `/api/system/menus/` | ✅ | `sys:menu:add` | - | - | `sys:menu:list` |
| `/api/system/menus/{id}/` | `sys:menu:list` | - | `sys:menu:edit` | `sys:menu:delete` | - |
| `/api/system/menus/tree/` | ✅ | - | - | - | 认证即可 |
| `/api/system/roles/` | `sys:role:list` | `sys:role:add` | - | - | - |
| `/api/system/roles/{id}/` | `sys:role:list` | - | `sys:role:edit` | `sys:role:delete` | - |
| `/api/system/users/` | `sys:user:list` | `sys:user:add` | - | - | - |
| `/api/system/users/{id}/` | `sys:user:list` | - | `sys:user:edit` | `sys:user:delete` | - |
| `/api/system/users/{id}/reset-password/` | - | `sys:user:reset-password` | - | - | - |
| `/api/system/user/permissions/` | ✅ | - | - | - | 认证即可 |

---

## 14. WebSocket 接口

| 路径 | 方向 | 鉴权 | 说明 |
|------|------|------|------|
| `/ws/board/{project_id}/` | 双向 | ✅ 项目成员 | 看板实时同步 |
| `/ws/chat/{project_id}/` | 双向 | ✅ 项目成员 | 项目聊天 (Redis Stream) |
| `/ws/global/` | 双向 | ✅ 认证 | 全局通知 |
| `/ws/qa/dashboard/` | 服务端推送 | ✅ 认证 | 测试日志 |
| `/ws/qa/recorder/` | 双向 | ✅ 认证 | UI 录制器 |
| `/ws/qa/performance/{id}/` | 服务端推送 | ✅ 认证 | 性能指标 |

### 消息格式
```json
{"type": "message_type", "data": {...}}
```

| 消息类型 | 触发时机 |
|----------|----------|
| `task_created/updated/deleted` | 任务 CRUD |
| `user_joined/left` | 在线状态 |
| `comment_added` | 新评论 |
| `notification` | 系统通知 |
| `test_log/progress` | QA 测试 |
| `performance_stats` | 性能指标 |

---

## 15. 项目角色权限

项目创建时自动生成 4 个默认角色:

| 角色 | Key | 权限 |
|------|-----|------|
| Owner | owner | 全部权限 (含删除项目) |
| Admin | admin | task:*, member:*, project:settings |
| Editor | editor | task:create/edit/move |
| Viewer | viewer | 只读 |

---

## 16. 版本

- API 版本: v2.0
- 文档更新: 2026-05-09
