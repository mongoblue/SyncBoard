"""QA 中心模块冒烟测试"""
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth.models import User


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


@pytest.mark.django_db
class TestRunTestViewProjectScope:
    def test_run_test_rejects_project_outsider_without_starting_thread(self, client, test_project):
        outsider = User.objects.create_user(username='qa-outsider', password='pw')
        client.force_login(outsider)

        with patch('qa_center.views.threading.Thread') as thread_cls:
            response = client.post('/api/qa/run-test/', {
                'test_type': 'api',
                'project_id': str(test_project.id),
            }, content_type='application/json')

        assert response.status_code == 403
        thread_cls.assert_not_called()

    def test_run_test_accepts_project_owner_and_passes_project_to_stream(self, auth_client, test_project):
        with patch('qa_center.views.threading.Thread') as thread_cls:
            response = auth_client.post('/api/qa/run-test/', {
                'test_type': 'api',
                'project_id': str(test_project.id),
            }, content_type='application/json')

        assert response.status_code == 200
        kwargs = thread_cls.call_args.kwargs
        assert kwargs['target'].__name__ == 'stream_command_output'
        assert kwargs['args'][1:] == ('api', str(test_project.id))
        thread_cls.return_value.start.assert_called_once()

    def test_run_test_accepts_project_member(self, client, test_project):
        member = User.objects.create_user(username='qa-member', password='pw')
        test_project.members.add(member)
        client.force_login(member)

        with patch('qa_center.views.threading.Thread') as thread_cls:
            response = client.post('/api/qa/run-test/', {
                'test_type': 'api',
                'project_id': str(test_project.id),
            }, content_type='application/json')

        assert response.status_code == 200
        assert thread_cls.call_args.kwargs['args'][2] == str(test_project.id)

    def test_run_test_requires_project_scope_without_starting_thread(self, auth_client):
        with patch('qa_center.views.threading.Thread') as thread_cls:
            response = auth_client.post('/api/qa/run-test/', {
                'test_type': 'api',
            }, content_type='application/json')

        assert response.status_code == 400
        assert response.data['error'] == '请选择项目'
        thread_cls.assert_not_called()

    def test_stream_command_output_uses_project_dashboard_group(self, test_project):
        from qa_center.views import RunTestView

        process = MagicMock()
        process.stdout.readline.side_effect = ['collected 1 items\n', 'tests/test_demo.py PASSED\n', '']
        process.stdout.close = MagicMock()
        process.wait.return_value = 0

        with patch('qa_center.views.get_channel_layer') as get_layer, \
             patch('qa_center.views.async_to_sync') as to_sync, \
             patch('qa_center.views.subprocess.Popen', return_value=process) as popen:
            layer = MagicMock()
            get_layer.return_value = layer
            sender = MagicMock()
            to_sync.return_value = sender

            RunTestView().stream_command_output(['python', '-m', 'pytest'], 'api', str(test_project.id))

        to_sync.assert_called_with(layer.group_send)
        assert sender.call_args_list[0].args[0] == f'qa_dashboard_{test_project.id}'
        assert all(call.args[0] == f'qa_dashboard_{test_project.id}' for call in sender.call_args_list)
        assert popen.call_args.kwargs['env']['QA_DASHBOARD_PROJECT_ID'] == str(test_project.id)

    def test_stream_command_output_requires_project_scope(self):
        from qa_center.views import RunTestView

        with patch('qa_center.views.subprocess.Popen') as popen:
            with pytest.raises(ValueError, match='project_id is required'):
                RunTestView().stream_command_output(['python', '-m', 'pytest'], 'api')

        popen.assert_not_called()
