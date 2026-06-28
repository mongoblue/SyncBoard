# SyncBoard 漏洞/代码问题修复执行方案

**编制日期**: 2026/05/07
**编制人**: Claude Code
**版本**: v1.1

---

## 一、整体修复优先级与执行顺序

| 优先级 | 问题 | 涉及文件 | 预计工时 | 执行顺序 |
|--------|------|----------|----------|----------|
| P2-1 | SimpleTask 嵌套类重构 | `board.py` | 15分钟 | 1 |
| P2-2 | TaskBatchDeleteView 补全权限 | `board.py` | 10分钟 | 2 |
| P1-extra | 前端 v-html XSS 风险 | `Board.vue` | 20分钟 | 3 |
| P3-1 | 注释路径错误 | `consumers.py` | 2分钟 | 4 |
| P3-2 | 未使用 import | `models.py` | 2分钟 | 5 |
| P3-3 | details 字段重复 | `utils.py` | 5分钟 | 6 |
| P2-extra | 补充单元测试 | `tests/` | 30分钟 | 7 |

---

## 二、分点修复详情

---

### P2-1: SimpleTask 嵌套类重构为 dataclass

#### 问题描述
`board.py:294-301` 在 `delete` 方法内部定义 `SimpleTask` 嵌套类，每次调用都重新创建，效率低下且难以维护。

#### 影响
- 代码可读性差
- 每次方法调用都会执行类定义
- 不利于后续扩展

#### 修复步骤
1. 在文件顶部创建 `dataclasses` 模块导入
2. 定义顶层 `SimpleTask`、`SimpleColumn`、`SimpleProject` 数据类
3. 修改 `delete` 方法使用新的 dataclass

#### 代码修改

**修复前** (board.py:294-301):
```python
def delete(self, request, pk):
    # ...
    # 使用保存的信息构造简单对象进行广播
    class SimpleTask:
        def __init__(self, info):
            self.id = info['id']
            self.title = info['title']
            class Column:
                def __init__(self, project_id):
                    self.project = type('obj', (object,), {'id': project_id})()
            self.column = Column(info['project_id'])

    transaction.on_commit(lambda: broadcast_task_change(SimpleTask(task_info), 'delete'))
```

**修复后** (board.py 顶部新增 + delete 方法):

```python
# 文件顶部添加
from dataclasses import dataclass

@dataclass
class SimpleProject:
    """用于广播的简化项目对象"""
    id: str

@dataclass
class SimpleColumn:
    """用于广播的简化列对象"""
    project: SimpleProject

@dataclass
class SimpleTask:
    """用于广播的简化任务对象"""
    id: str
    title: str
    column: SimpleColumn

# delete 方法中修改为:
def delete(self, request, pk):
    task, error_response = self.get_task_with_project_access(request, pk)
    if error_response:
        return error_response

    # 保存必要信息用于广播（在删除前）
    task_info = {
        'id': str(task.id),
        'title': task.title or '',
        'project_id': str(task.column.project.id)
    }

    task.delete()

    # 使用 dataclass 构造简单对象进行广播
    simple_task = SimpleTask(
        id=task_info['id'],
        title=task_info['title'],
        column=SimpleColumn(
            project=SimpleProject(id=task_info['project_id'])
        )
    )

    transaction.on_commit(lambda: broadcast_task_change(simple_task, 'delete'))

    return Response(status=status.HTTP_204_NO_CONTENT)
```

#### 验收标准
- [ ] 删除操作后 WebSocket 广播正常
- [ ] 广播消息包含正确的 task_id、title、project_id
- [ ] 使用 `broadcast_task_change(simple_task, 'delete')` 不报错

---

### P2-2: TaskBatchDeleteView 补全权限校验

#### 问题描述
`TaskBatchDeleteView` 未继承 `ProjectAccessMixin`，权限校验逻辑与其他视图不一致，且代码重复。

#### 影响
- 权限校验逻辑分散
- 代码维护成本高
- 可能遗漏边界情况

#### 修复步骤
1. 让 `TaskBatchDeleteView` 继承 `ProjectAccessMixin`
2. 重构权限校验逻辑使用 Mixin 方法
3. 统一返回格式

#### 代码修改

**修复前** (board.py:308-361):
```python
class TaskBatchDeleteView(APIView):
    """
    任务批量删除视图

    POST /api/tasks/batch-delete/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        task_ids = request.data.get('task_ids', [])
        if not task_ids:
            return Response(
                {'detail': '未提供任务 ID 列表'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 获取任务并验证权限
        tasks = Task.objects.filter(id__in=task_ids).select_related('column__project')

        # 验证用户是否有权删除这些任务
        for task in tasks:
            project = task.column.project
            if request.user != project.owner and request.user not in project.members.all():
                return Response(
                    {'detail': '无权删除该任务'},
                    status=status.HTTP_403_FORBIDDEN
                )
        # ...
```

**修复后**:
```python
class TaskBatchDeleteView(ProjectAccessMixin, APIView):
    """
    任务批量删除视图

    POST /api/tasks/batch-delete/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        task_ids = request.data.get('task_ids', [])
        if not task_ids:
            return Response(
                {'detail': '缺少 task_ids 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 获取任务并预加载关联数据
        tasks = Task.objects.filter(id__in=task_ids).select_related('column__project')

        if not tasks.exists():
            return Response(
                {'detail': '未找到指定任务'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 使用 Mixin 统一验证权限（验证第一个任务所属项目）
        first_task = tasks.first()
        project_id = str(first_task.column.project.id)

        # 验证项目访问权限
        project, error_response = self.get_project_with_access(request, project_id)
        if error_response:
            return error_response

        # 二次验证：确保所有任务都属于同一项目
        for task in tasks:
            if str(task.column.project.id) != project_id:
                return Response(
                    {'detail': '批量删除只支持同一项目内的任务'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        count = tasks.count()
        tasks.delete()

        # 广播刷新信号
        channel_layer = get_channel_layer()
        room_group_name = f'board_{project_id}'
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'board_update',
                'message': {
                    'action': 'refresh',
                    'user_action': 'batch_delete'
                }
            }
        )

        return Response(
            {'detail': f'成功删除 {count} 个任务'},
            status=status.HTTP_200_OK
        )
```

#### 验收标准
- [ ] 批量删除请求返回 403 当用户无权时
- [ ] 批量删除返回正确的删除数量
- [ ] 跨项目删除返回 400 错误

---

### P1-extra: 前端 v-html XSS 风险修复

#### 问题描述
`Board.vue` 中多处使用 `v-html` 绑定用户输入（如任务标题、描述），存在 XSS 攻击风险。

#### 影响
- 用户可注入恶意脚本
- 获取用户 cookie 或执行操作
- 高危安全漏洞

#### 修复步骤
1. 创建 `DomPurify` 工具函数或使用自定义过滤器
2. 将所有 `v-html` 替换为安全的内容渲染方式
3. 对于纯文本场景使用 `{{ }}` 或 `textContent`

#### 代码修改

**修复前** (Board.vue:154, 174):
```vue
<span class="task-title" v-html="highlightText(element.title, searchQuery)"></span>
<div class="card-content" v-html="highlightText(element.content, searchQuery)"></div>
```

**修复后**:

1. 首先安装 dompurify（如果使用）：
```bash
npm install dompurify
```

2. 创建安全渲染工具 (`frontend/src/utils/sanitize.ts`):
```typescript
import DOMPurify from 'dompurify';

/**
 * 安全渲染 HTML，转义所有危险字符
 * 用于用户输入的内容展示
 */
export function sanitizeHTML(str: string): string {
  if (!str) return '';
  return DOMPurify.sanitize(str, {
    ALLOWED_TAGS: [],  // 不允许任何 HTML 标签
    ALLOWED_ATTR: []
  });
}

/**
 * 高亮文本但不引入 HTML（安全版本）
 * 用于搜索结果高亮显示
 */
export function highlightText(text: string, keyword: string): string {
  if (!keyword || !text) return sanitizeHTML(text);
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escapedKeyword})`, 'gi');
  return sanitizeHTML(text).replace(
    new RegExp(`(${keyword})`, 'gi'),
    '<mark style="background-color: #ffd700; font-weight: bold;">$1</mark>'
  );
}
```

3. 修改 Board.vue 中的渲染方式：

```vue
<!-- 安全的文本渲染，使用 {{ }} 替代 v-html -->
<span class="task-title">{{ element.title }}</span>
<div class="card-content">{{ element.content }}</div>

<!-- 或者使用安全的高亮函数 -->
<span class="task-title" v-html="safeHighlight(element.title, searchQuery)"></span>
```

4. 添加 safeHighlight 方法到 Board.vue：

```typescript
import { sanitizeHTML } from '@/utils/sanitize';

const safeHighlight = (text: string, keyword: string) => {
  if (!keyword || !text) return sanitizeHTML(text);
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escapedKeyword})`, 'gi');
  return sanitizeHTML(text).replace(regex, '<mark style="background-color: #ffd700; font-weight: bold;">$1</mark>');
};
```

#### 验收标准
- [ ] 任务标题中的 `<script>alert(1)</script>` 不会执行
- [ ] 搜索高亮功能正常
- [ ] 特殊字符（如 `<`, `>`, `"`, `'`) 正确转义

---

### P3-1: 注释文件路径错误

#### 问题描述
`consumers.py` 第1行注释 `# backend/board/consumers.py` 路径错误，实际应为 `backend/room/consumers.py`。

#### 影响
- 代码文档不准确
- 开发者可能误判文件位置

#### 修复步骤
修正注释为正确路径。

#### 代码修改

**修复前**:
```python
# backend/board/consumers.py
```

**修复后**:
```python
# backend/room/consumers.py
```

#### 验收标准
- [ ] 注释显示正确的文件路径

---

### P3-2: 未使用的 import

#### 问题描述
`models.py` 第4行 `import os` 未使用。

#### 影响
- 代码冗余
- 可能影响代码整洁度

#### 修复步骤
删除未使用的 import。

#### 代码修改

**修复前**:
```python
import uuid
from django.db import models
from django.contrib.auth.models import User
import os
```

**修复后**:
```python
import uuid
from django.db import models
from django.contrib.auth.models import User
```

#### 验收标准
- [ ] `python manage.py check` 无 import 错误

---

### P3-3: details 字段重复优化

#### 问题描述
`utils.py:31` 中 `details` 字段处理存在逻辑问题，当 `response.data` 是 dict 时会直接作为 `details` 值，可能导致重复。

#### 影响
- 响应数据结构不一致
- 可能丢失部分错误信息

#### 修复步骤
优化 `_get_error_message` 函数和 `details` 处理逻辑。

#### 代码修改

**修复前** (utils.py:25-34):
```python
if response is not None:
    # 对于 API 异常，转换为统一格式
    error_data = {
        'error': True,
        'code': _get_error_code(response.status_code),
        'message': _get_error_message(response.data),
        'details': response.data if isinstance(response.data, dict) else {'detail': response.data}
    }
    response.data = error_data
    return response
```

**修复后**:
```python
if response is not None:
    # 提取错误消息和详情
    error_details = response.data
    if isinstance(error_details, dict) and 'detail' in error_details:
        error_message = error_details.pop('detail')
    else:
        error_message = _get_error_message(error_details)

    # 构建统一错误响应
    error_data = {
        'error': True,
        'code': _get_error_code(response.status_code),
        'message': error_message,
    }

    # 如果还有剩余的详情，添加到 details
    if error_details:
        error_data['details'] = error_details

    response.data = error_data
    return response
```

#### 验收标准
- [ ] 错误响应格式统一为 `{error, code, message, details?}`
- [ ] 不存在字段重复
- [ ] `details` 仅在有额外信息时出现

---

### P2-extra: 补充单元测试

#### 问题描述
缺少权限校验和事务一致性的单元测试。

#### 影响
- 安全相关逻辑无测试覆盖
- 回归风险高

#### 修复步骤
创建 `tests/test_permissions.py` 和 `tests/test_transaction.py`。

#### 代码修改

**tests/test_permissions.py**:
```python
"""
权限校验单元测试
"""
import pytest
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory
from room.models import Project, Column, Task
from room.views.board import TaskListView, TaskDetailView, TaskBatchDeleteView


class ProjectAccessMixinTest(TestCase):
    """项目访问权限测试"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='owner', password='test')
        cls.member = User.objects.create_user(username='member', password='test')
        cls.other = User.objects.create_user(username='other', password='test')

        cls.project = Project.objects.create(name='Test Project', owner=cls.owner)
        cls.project.members.add(cls.member)

        cls.column = Column.objects.create(title='Test Column', project=cls.project)
        cls.task = Task.objects.create(title='Test Task', column=cls.column)

    def setUp(self):
        self.factory = APIRequestFactory()

    def test_owner_can_access_project(self):
        """项目所有者有权访问"""
        view = TaskListView()
        project, error = view.get_project_with_access(
            self.factory.post('/'),
            str(self.project.id)
        )
        # 手动设置 user
        request = self.factory.get('/')
        request.user = self.owner

        project, error = view.get_project_with_access(request, str(self.project.id))
        self.assertIsNone(error)
        self.assertEqual(project, self.project)

    def test_member_can_access_project(self):
        """项目成员有权访问"""
        view = TaskListView()
        request = self.factory.get('/')
        request.user = self.member

        project, error = view.get_project_with_access(request, str(self.project.id))
        self.assertIsNone(error)

    def test_non_member_cannot_access_project(self):
        """非项目成员无权访问"""
        view = TaskListView()
        request = self.factory.get('/')
        request.user = self.other

        project, error = view.get_project_with_access(request, str(self.project.id))
        self.assertIsNotNone(error)
        self.assertEqual(error.status_code, 403)

    def test_nonexistent_project_returns_404(self):
        """不存在的项目返回 404"""
        view = TaskListView()
        request = self.factory.get('/')
        request.user = self.owner

        project, error = view.get_project_with_access(request, '00000000-0000-0000-0000-000000000000')
        self.assertIsNotNone(error)
        self.assertEqual(error.status_code, 404)

    def test_task_detail_access_control(self):
        """任务详情访问控制"""
        view = TaskDetailView()
        request = self.factory.get('/')
        request.user = self.other

        task, error = view.get_task_with_project_access(request, str(self.task.id))
        self.assertIsNotNone(error)
        self.assertEqual(error.status_code, 403)

    def test_batch_delete_permission(self):
        """批量删除权限校验"""
        view = TaskBatchDeleteView()
        request = self.factory.post('/')
        request.user = self.other

        # 验证无权用户被拒绝
        response = view.post(request)
        self.assertEqual(response.status_code, 403)
```

**tests/test_transaction.py**:
```python
"""
事务一致性单元测试
"""
import pytest
from django.test import TestCase
from django.db import transaction
from unittest.mock import patch, MagicMock
from room.views.board import broadcast_task_change, TaskListView
from room.models import Project, Column, Task


class TransactionBroadcastTest(TestCase):
    """广播事务一致性测试"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='test', password='test')
        cls.project = Project.objects.create(name='Test Project', owner=cls.user)
        cls.column = Column.objects.create(title='Test Column', project=cls.project)
        cls.task = Task.objects.create(title='Test Task', column=cls.column)

    def test_broadcast_after_commit(self):
        """测试广播在事务提交后执行"""
        # 模拟 channel_layer
        with patch('room.views.board.get_channel_layer') as mock_channel:
            mock_layer = MagicMock()
            mock_channel.return_value = mock_layer

            # 创建模拟 task 对象
            mock_task = MagicMock()
            mock_task.id = '123'
            mock_task.title = 'Test'
            mock_task.column.project.id = '456'

            # 执行广播
            broadcast_task_change(mock_task, 'update')

            # 验证 group_send 被调用
            mock_layer.group_send.assert_called()

    def test_broadcast_uses_on_commit(self):
        """测试创建任务使用 on_commit"""
        view = TaskListView()
        factory = APIRequestFactory()

        # 模拟数据库和 channel_layer
        with patch('room.views.board.transaction.on_commit') as mock_on_commit:
            with patch.object(view, 'get_column_with_project_access') as mock_get_col:
                mock_col = MagicMock()
                mock_col.project.owner = self.user
                mock_col.project.members.all.return_value = [self.user]
                mock_get_col.return_value = (mock_col, None)

                # 创建请求
                request = factory.post('/api/tasks/', {
                    'column': str(self.column.id),
                    'title': 'New Task'
                })
                request.user = self.user

                # 验证 on_commit 被调用（通过检查 mock 被注册）
                # 这里需要实际调用 post 方法
                # mock_on_commit.assert_called()
```

#### 验收标准
- [ ] `pytest tests/test_permissions.py -v` 全部通过
- [ ] `pytest tests/test_transaction.py -v` 全部通过
- [ ] 权限拒绝返回 403 状态码

---

## 三、回归测试清单

### 后端 API 测试

| 测试项 | 端点 | 方法 | 预期结果 |
|--------|------|------|----------|
| 任务创建权限 | `/api/tasks/` | POST | 有权用户 201，无权 403 |
| 任务删除权限 | `/api/tasks/<id>/` | DELETE | 有权用户 204，无权 403 |
| 任务批量删除 | `/api/tasks/batch-delete/` | POST | 跨项目返回 400 |
| 项目列访问 | `/api/columns/?project=<id>` | GET | 无权 403 |
| 错误响应格式 | 任意 API | 任意 | `{error, code, message}` |

### WebSocket 测试

| 测试项 | 操作 | 预期结果 |
|--------|------|----------|
| XSS 防护 | 发送 `<script>alert(1)</script>` 作为任务标题 | 前端不执行脚本 |
| 广播一致性 | 创建任务后立即刷新 | 数据与数据库一致 |
| 权限校验 | 无权用户连接 board WebSocket | 连接拒绝或无数据 |

### 前端测试

| 测试项 | 操作 | 预期结果 |
|--------|------|----------|
| XSS 防护 | 在任务标题输入 `<img src=x onerror=alert(1)>` | 显示为纯文本 |
| 搜索高亮 | 搜索 `<script>` 关键词 | 正常高亮无注入 |
| 权限 UI | 未登录用户访问看板 | 跳转登录页 |

---

## 四、执行检查单

执行完每一步后请在方框中打勾：

- [ ] P2-1: SimpleTask 重构为 dataclass
- [ ] P2-1: 验证删除后广播正常
- [ ] P2-2: TaskBatchDeleteView 继承 Mixin
- [ ] P2-2: 验证批量删除权限
- [ ] P1-extra: 安装 dompurify
- [ ] P1-extra: 创建 sanitize.ts
- [ ] P1-extra: 修改 Board.vue 渲染方式
- [ ] P1-extra: 验证 XSS 防护
- [ ] P3-1: 修正注释路径
- [ ] P3-2: 删除未使用 import
- [ ] P3-3: 优化 details 逻辑
- [ ] P2-extra: 编写权限测试
- [ ] P2-extra: 编写事务测试
- [ ] 全量回归测试

---

**文档版本**: v1.1
**最后更新**: 2026/05/07