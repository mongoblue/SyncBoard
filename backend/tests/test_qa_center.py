"""QA 中心模块冒烟测试"""
import pytest


@pytest.mark.django_db
class TestQaCenterUnauthorized:
    def test_api_cases_requires_auth(self, client):
        response = client.get('/api/qa/api-cases/')
        assert response.status_code == 403

    def test_ui_cases_requires_auth(self, client):
        response = client.get('/api/qa/ui-cases/')
        assert response.status_code == 403

    def test_test_results_requires_auth(self, client):
        response = client.get('/api/qa/test-results/')
        assert response.status_code == 403

    def test_devops_stats_requires_auth(self, client):
        response = client.get('/api/qa/devops/stats/')
        assert response.status_code == 403


@pytest.mark.django_db
class TestQaCenterAPI:
    def test_list_api_cases(self, auth_client):
        response = auth_client.get('/api/qa/api-cases/')
        assert response.status_code == 200
        # ViewSet 自动分页
        assert 'results' in response.data
        assert 'count' in response.data

    def test_list_ui_cases(self, auth_client):
        response = auth_client.get('/api/qa/ui-cases/')
        assert response.status_code == 200
        assert 'results' in response.data

    def test_list_test_results(self, auth_client):
        response = auth_client.get('/api/qa/test-results/')
        assert response.status_code == 200
        assert 'results' in response.data

    def test_list_auto_suites(self, auth_client):
        response = auth_client.get('/api/qa/auto-suites/')
        assert response.status_code == 200
        assert 'results' in response.data

    def test_list_performance_cases(self, auth_client):
        response = auth_client.get('/api/qa/performance-cases/')
        assert response.status_code == 200
        assert 'results' in response.data

    def test_data_factory(self, auth_client):
        response = auth_client.get('/api/qa/data-factory/')
        assert response.status_code == 200

    def test_devops_stats(self, auth_client):
        response = auth_client.get('/api/qa/devops/stats/')
        assert response.status_code == 200

    def test_devops_recent_executions(self, auth_client):
        response = auth_client.get('/api/qa/devops/recent-executions/')
        assert response.status_code == 200
