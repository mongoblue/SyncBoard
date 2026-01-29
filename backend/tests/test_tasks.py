# backend/tests/test_tasks.py
import pytest
from django.contrib.auth.models import User
from room.models import Project, Column, Task


@pytest.mark.django_db
class TestTaskAPI:

    # 1. 前置准备：构造一条完整的“数据链”
    # 用户 -> 项目 -> 列 -> (准备测试任务)
    def setup_method(self):
        # 创建用户
        self.user = User.objects.create_user(username="task_tester", password="password")

        # 创建项目
        self.project = Project.objects.create(name="Task Test Project", owner=self.user)

        # 创建一个列 (To Do)
        self.column = Column.objects.create(project=self.project, title="To Do", position=1)

        # 接口基础路径
        self.list_url = '/api/tasks/'

        # 预先登录
        self.client_tools = None  # 这里的 client 由 pytest fixture 传入，下面会赋值

    # 2. 测试：成功创建任务
    def test_create_task(self, client):
        client.force_login(self.user)

        data = {
            "title": "测试任务",
            "content": "这是一个自动化测试创建的任务",
            "column": self.column.id,  # 必须关联到一个存在的列ID
            "position": 0
        }

        response = client.post(self.list_url, data)

        # 断言
        assert response.status_code == 201
        assert response.data['title'] == "测试任务"
        # 验证数据库里真的有这条数据
        assert Task.objects.filter(title="测试任务").exists()

    # 3. 测试：修改任务 (比如拖拽导致 column 变化，或者改标题)
    def test_update_task(self, client):
        client.force_login(self.user)

        # 先在数据库里插一条任务
        task = Task.objects.create(
            title="旧标题",
            column=self.column,
            position=0
        )

        # 发送 PATCH 请求修改它
        update_data = {
            "title": "新标题",
            "content": "内容也被改了"
        }
        detail_url = f'/api/tasks/{task.id}/'  # 详情页 URL

        response = client.patch(detail_url, update_data, content_type='application/json')

        assert response.status_code == 200
        assert response.data['title'] == "新标题"

        # 再次查库确认
        task.refresh_from_db()  # 刷新对象状态
        assert task.title == "新标题"

    # 4. 测试：删除任务
    def test_delete_task(self, client):
        client.force_login(self.user)

        task = Task.objects.create(title="待删除任务", column=self.column)

        detail_url = f'/api/tasks/{task.id}/'
        response = client.delete(detail_url)

        assert response.status_code == 204  # 204 No Content
        # 确认数据库里没了
        assert not Task.objects.filter(id=task.id).exists()

    # 5. (进阶) 测试：给不存在的列创建任务应该失败
    def test_create_task_invalid_column(self, client):
        client.force_login(self.user)

        data = {
            "title": "失败任务",
            "column": 99999,  # 不存在的列 ID
        }

        response = client.post(self.list_url, data)
        assert response.status_code == 400  # 应该是 Bad Request