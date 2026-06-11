"""系统管理模块冒烟测试"""
import pytest


@pytest.mark.django_db
class TestSystemUnauthorized:
    def test_menus_requires_auth(self, client):
        response = client.get('/api/system/menus/')
        assert response.status_code == 403

    def test_roles_requires_auth(self, client):
        response = client.get('/api/system/roles/')
        assert response.status_code == 403

    def test_users_requires_auth(self, client):
        response = client.get('/api/system/users/')
        assert response.status_code == 403


@pytest.mark.django_db
class TestSystemAPI:
    def test_list_menus(self, auth_client):
        response = auth_client.get('/api/system/menus/')
        assert response.status_code == 200

    def test_menu_tree(self, auth_client):
        response = auth_client.get('/api/system/menus/tree/')
        assert response.status_code == 200

    def test_list_roles(self, auth_client):
        response = auth_client.get('/api/system/roles/')
        assert response.status_code == 200

    def test_list_users(self, auth_client):
        response = auth_client.get('/api/system/users/')
        assert response.status_code == 200

    def test_current_user_permissions(self, auth_client):
        response = auth_client.get('/api/system/user/permissions/')
        assert response.status_code == 200
        assert 'permissions' in response.data
        assert 'menus' in response.data
