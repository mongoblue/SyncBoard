"""共享测试 fixtures"""
import pytest
from django.contrib.auth.models import User
from room.models import Project, Column, Tag


@pytest.fixture
def test_password():
    return 'testpass123'


@pytest.fixture
def test_user(db, test_password):
    return User.objects.create_user(username='testuser', password=test_password)


@pytest.fixture
def auth_client(client, test_user):
    """返回已认证的 Django 测试客户端"""
    client.force_login(test_user)
    return client


@pytest.fixture
def test_project(db, test_user):
    """创建测试项目（含默认列和标签）"""
    project = Project.objects.create(name='Test Project', owner=test_user)
    Column.objects.create(project=project, title='To Do', position=1)
    Column.objects.create(project=project, title='In Progress', position=2)
    Column.objects.create(project=project, title='Done', position=3)
    Tag.objects.create(project=project, name='Bug', color='#f56c6c')
    return project
