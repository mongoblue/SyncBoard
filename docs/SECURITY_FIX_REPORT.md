# SyncBoard 安全问题修复报告 + 进阶优化报告

**修复日期**: 2026/05/07
**修复版本**: v1.0-security-fix

---

## 一、安全问题修复（已完成）

### 修复摘要

本次修复解决了 8 个安全问题，按照 P0-P3 优先级依次修复：

| 优先级 | 问题 | 状态 |
|--------|------|------|
| P0 | 数据库密码硬编码 | ✅ 已修复 |
| P0 | 批量删除越权漏洞 | ✅ 已修复 |
| P0 | 任务列表越权访问 | ✅ 已修复 |
| P1 | WebSocket XSS风险 | ✅ 已修复 |
| P1 | 广播在事务外执行 | ✅ 已修复 |
| P2 | 数据工厂缺少限流 | ✅ 已修复 |
| P2 | RAG异常信息泄露 | ✅ 已修复 |
| P3 | 魔法数值抽取 | ✅ 已修复 |

---

### P0-1: 数据库密码硬编码

**文件**: `backend/backend/settings.py:85`

**修复前**:
```python
'PASSWORD': os.environ.get('DB_PASSWORD', '13579Mnb!'),
```

**修复后**:
```python
'PASSWORD': os.environ.get('DB_PASSWORD', ''),
```

**说明**: 删除硬编码的默认密码，强制要求通过环境变量配置。

---

### P0-2: 批量删除越权漏洞

**文件**: `backend/room/views/board.py:239-283`

**修复方案**: 添加了项目成员权限校验，确保用户只能删除自己有权访问的项目中的任务。

**关键代码**:
```python
# 获取任务并验证权限
tasks = Task.objects.filter(id__in=task_ids).select_related('column__project')

# 验证用户是否有权删除这些任务
for task in tasks:
    project = task.column.project
    if request.user != project.owner and request.user not in project.members.all():
        return Response({'detail': '无权删除该任务'}, status=status.HTTP_403_FORBIDDEN)
```

---

### P0-3: 任务列表/创建越权访问

**文件**: `backend/room/views/board.py:140-198`

**修复方案**:
1. GET 请求添加项目访问权限校验
2. POST 请求验证 column 所属项目的访问权限
3. 关联查询优化：添加 `select_related` 和 `prefetch_related` 避免 N+1 问题

---

### P1-1: WebSocket XSS风险

**文件**: `backend/room/consumers.py`

**修复方案**: 在 WebSocket 消息广播前对所有字符串值进行 HTML 转义：

```python
import html

def sanitize_html(text):
    """转义 HTML 特殊字符，防止 XSS 攻击"""
    if text is None:
        return ''
    return html.escape(str(text), quote=True)
```

---

### P1-2: 广播在事务外执行

**文件**: `backend/room/views/board.py`

**修复方案**: 使用 Django 的 `transaction.on_commit()` 确保只有在数据库事务成功提交后才发送 WebSocket 广播：

```python
from django.db import transaction

if serializer.is_valid():
    task = serializer.save()
    transaction.on_commit(lambda: broadcast_task_change(task, 'create'))
```

---

### P2-1: 数据工厂缺少限流

**文件**: `backend/qa_center/views.py`

**修复方案**:
1. 添加数量上限 `MAX_DATA_FACTORY_COUNT = 1000`
2. 添加参数类型校验和范围校验
3. 错误信息不再返回具体异常，避免信息泄露

---

### P2-2: RAG异常信息泄露

**文件**: `backend/room/views/project.py`

**修复方案**: 异常信息写入日志而非返回给前端：

```python
except Exception as e:
    logger.error(f"RAG问答异常: {str(e)}", exc_info=True)
    return Response(
        {'detail': '处理问题时出现错误，请稍后重试'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
```

---

### P3: 魔法数值抽取

**涉及文件**:
- `backend/room/models.py` - 新增 `DEFAULT_POSITION` 常量
- `backend/qa_center/views.py` - 从 models 导入常量
- `frontend/src/types/kanban.ts` - 导出 `DEFAULT_POSITION`
- `frontend/src/stores/board/task.ts` - 使用常量
- `frontend/src/views/Board.vue` - 使用常量

---

## 二、进阶优化方案（已完成）

### 1. 项目访问权限 Mixin

**文件**: `backend/room/views/mixins.py` (新建)

**说明**: 创建了 `ProjectAccessMixin` 类，提供统一的项目访问权限校验逻辑：

```python
class ProjectAccessMixin:
    def get_project_with_access(self, request, project_id):
        """验证用户是否有权访问指定项目"""

    def get_column_with_project_access(self, request, column_id):
        """验证用户是否有权访问指定列所属的项目"""

    def get_task_with_project_access(self, request, task_id):
        """验证用户是否有权访问指定任务所属的项目"""
```

**应用**: `ColumnListView`、`ColumnDetailView`、`TaskListView`、`TaskDetailView` 均已继承此 Mixin。

---

### 2. 任务列表分页

**文件**: `backend/room/views/board.py` - `TaskListView`

**说明**: 为任务列表添加了分页功能，支持 `page` 和 `page_size` 参数：

```python
# 分页配置
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# 返回格式
{
    'results': [...],
    'count': 100,
    'page': 1,
    'page_size': 20,
    'total_pages': 5
}
```

---

### 3. 统一错误响应格式

**文件**: `backend/backend/utils.py` (更新)

**说明**: 更新了 `custom_exception_handler`，将所有异常响应统一为以下格式：

```json
{
    "error": true,
    "code": "ERROR_CODE",
    "message": "错误消息",
    "details": {...}
}
```

**错误码映射**:
- `BAD_REQUEST` - 400
- `PERMISSION_DENIED` - 403
- `NOT_FOUND` - 404
- `INTERNAL_ERROR` - 500

---

### 4. 数据库索引

**文件**: `backend/room/migrations/0006_add_indexes.py` (新建)

**说明**: 为常用查询字段添加了数据库索引：

| 模型 | 索引 | 用途 |
|------|------|------|
| Task | `column` | 按列查询任务 |
| Task | `position` | 任务排序 |
| Task | `assignee` | 按负责人筛选 |
| Task | `column + position` | 列内任务排序 |
| Column | `project` | 按项目查列 |
| Column | `project + position` | 项目列排序 |
| Project | `owner` | 项目所有者查询 |
| Project | `created_at` | 项目时间排序 |
| Tag | `project` | 按项目查标签 |
| Notification | `user + is_read` | 未读通知查询 |
| Notification | `user + created_at` | 通知时间排序 |

**应用方式**:
```bash
cd backend
python manage.py migrate
```

---

## 三、文件变更总览

### 新建文件

| 文件 | 说明 |
|------|------|
| `backend/room/views/mixins.py` | 项目访问权限校验 Mixin |
| `backend/backend/api_errors.py` | 统一错误响应工具 |
| `backend/room/migrations/0006_add_indexes.py` | 数据库索引迁移 |
| `docs/SECURITY_FIX_REPORT.md` | 本修复报告 |

### 修改文件

| 文件 | 变更说明 |
|------|----------|
| `backend/backend/settings.py` | 删除硬编码数据库密码 |
| `backend/room/views/board.py` | 权限校验、分页、Mixin使用、事务处理 |
| `backend/room/views/project.py` | 异常信息脱敏 |
| `backend/room/models.py` | 新增常量定义 |
| `backend/room/consumers.py` | XSS防护 |
| `backend/qa_center/views.py` | 限流保护 |
| `backend/backend/utils.py` | 统一错误格式 |
| `frontend/src/types/kanban.ts` | 导出位置常量 |
| `frontend/src/stores/board/task.ts` | 使用位置常量 |
| `frontend/src/views/Board.vue` | 使用位置常量 |

---

## 四、安全检查清单

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 数据库密码配置 | ✅ | 不再有硬编码密码 |
| 任务删除权限 | ✅ | 校验项目成员关系 |
| 任务读取权限 | ✅ | 校验项目访问权限 |
| 任务创建权限 | ✅ | 校验列所属项目权限 |
| 任务修改/删除权限 | ✅ | 统一使用 Mixin |
| WebSocket XSS | ✅ | HTML 转义处理 |
| 数据工厂限流 | ✅ | 最大 1000 条/次 |
| 异常信息泄露 | ✅ | 不返回内部错误详情 |
| 事务一致性 | ✅ | 广播在 on_commit 中 |
| 列表分页 | ✅ | 支持分页避免大数据量 |
| 数据库索引 | ✅ | 常用查询已建索引 |

---

## 五、待后续优化项（建议）

以下优化项需要在后续迭代中处理：

1. **前端 XSS 防护**: `Board.vue` 中使用 `v-html` 显示任务内容，建议改用 `textContent` 或添加前端 XSS 过滤

2. **API 限流**: 当前数据工厂有数量限制，但其他写操作 API 建议增加频率限制

3. **审计日志**: 关键操作（删除项目、批量删除等）建议记录审计日志

4. **缓存策略**: 热门数据（项目列表、用户信息）建议添加 Redis 缓存

5. **单元测试**: 建议为安全相关逻辑增加单元测试覆盖率

---

**报告生成时间**: 2026-05-07
**修复人员**: Claude Code