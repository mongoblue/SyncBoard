"""认证模块测试"""
import pytest


@pytest.mark.django_db
class TestAuth:
    def test_login_success(self, client, test_user, test_password):
        response = client.post('/api/auth/login/', {
            'username': test_user.username,
            'password': test_password,
        })
        assert response.status_code == 200
        assert response.data['username'] == test_user.username

    def test_login_wrong_password(self, client, test_user):
        response = client.post('/api/auth/login/', {
            'username': test_user.username,
            'password': 'wrongpassword',
        })
        assert response.status_code == 401

    def test_logout(self, auth_client):
        response = auth_client.post('/api/auth/logout/')
        assert response.status_code == 200
        assert response.data['detail'] == '注销成功'

    def test_current_user_authenticated(self, auth_client, test_user):
        response = auth_client.get('/api/auth/me/')
        assert response.status_code == 200
        assert response.data['username'] == test_user.username

    def test_current_user_unauthenticated(self, client):
        response = client.get('/api/auth/me/')
        assert response.status_code == 401
