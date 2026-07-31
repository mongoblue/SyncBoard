"""共享测试 fixtures"""
import pytest
from django.contrib.auth.models import User
from room.models import Project, Column, Tag


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """清空 Django cache，避免 webhook 去重/限流等跨测试累积。

    webhook 去重（30s 窗口）与限流（5/60s）按 config id 计数，
    测试重建的 config id 从 1 复用，缓存残留会导致后续测试误判 429。
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def test_password():
    return 'testpass123'


@pytest.fixture
def test_user(db, test_password):
    return User.objects.create_user(
        username='testuser', password=test_password,
        is_staff=True, is_superuser=True,
    )


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
