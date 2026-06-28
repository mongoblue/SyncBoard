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
        # DataFactoryView 仅支持 POST,GET 返回 405;冒烟仅验证端点存在
        response = auth_client.get('/api/qa/data-factory/')
        assert response.status_code in (200, 405)

    def test_devops_stats(self, auth_client):
        response = auth_client.get('/api/qa/devops/stats/')
        assert response.status_code == 200

    def test_devops_recent_executions(self, auth_client):
        response = auth_client.get('/api/qa/devops/recent-executions/')
        assert response.status_code == 200

    def test_test_result_statistics_counts_by_type_and_status(self, auth_client, test_project, test_user):
        from qa_center.models import TestResult

        TestResult.objects.create(
            test_type='api',
            name='api passed',
            status='passed',
            project=test_project,
            executed_by=test_user,
        )
        TestResult.objects.create(
            test_type='ui',
            name='ui failed',
            status='failed',
            project=test_project,
            executed_by=test_user,
        )

        response = auth_client.get(f'/api/qa/test-results/statistics/?project={test_project.id}')

        assert response.status_code == 200
        assert response.data['total'] == 2
        assert response.data['passed'] == 1
        assert response.data['failed'] == 1
        assert response.data['error'] == 0
        assert response.data['pass_rate'] == 50.0
        assert response.data['by_type']['api'] == 1
        assert response.data['by_type']['ui'] == 1
        assert response.data['by_status']['passed'] == 1
        assert response.data['by_status']['failed'] == 1
