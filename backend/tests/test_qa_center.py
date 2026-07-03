"""QA 中心模块冒烟测试"""
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone
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

    def test_list_test_results_includes_semantic_fields_for_api_mirror(self, auth_client, test_project, test_user):
        from qa_center.models import ApiAutoTestCase, ApiAutoTestResult, ApiAutoTestCaseResult, TestResult

        case = ApiAutoTestCase.objects.create(
            project=test_project,
            created_by=test_user,
            name='expected error case',
            url='/api/expected-error/',
            method='GET',
            expected_status=404,
        )
        auto_result = ApiAutoTestResult.objects.create(
            name='expected error run',
            status='passed',
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            error_cases=0,
            project=test_project,
            executed_by=test_user,
        )
        TestResult.objects.create(
            test_type='api',
            name='expected error run',
            status='passed',
            project=test_project,
            executed_by=test_user,
            api_auto_result=auto_result,
            source='single',
        )
        ApiAutoTestCaseResult.objects.create(
            case=case,
            test_result=auto_result,
            status_code=404,
            response_time_ms=12,
            passed=True,
            failure_type='passed',
            result_metadata={
                'provider': 'http',
                'expectation_type': 'error_response',
                'default_assertion_policy': 'expected_error_response',
                'expected_status': 404,
                'semantic_status': 'expected_error_matched',
                'semantic_label': '预期错误响应且匹配成功',
            },
        )

        response = auth_client.get('/api/qa/test-results/')

        assert response.status_code == 200
        row = next(item for item in response.data['results'] if item['name'] == 'expected error run')
        assert row['api_auto_result_id'] == auto_result.id
        assert row['semantic_status'] == 'expected_error_matched'
        assert row['semantic_label'] == '预期错误响应且匹配成功'
        assert row['expected_status'] == 404

    def test_test_result_list_uses_aggregate_status_for_multi_case_api_mirror(self, auth_client, test_project, test_user):
        from qa_center.models import ApiAutoTestCase, ApiAutoTestResult, ApiAutoTestCaseResult, TestResult

        case_a = ApiAutoTestCase.objects.create(
            project=test_project,
            created_by=test_user,
            name='expected error case A',
            url='/api/case-a/',
            method='GET',
            expected_status=404,
        )
        case_b = ApiAutoTestCase.objects.create(
            project=test_project,
            created_by=test_user,
            name='expected error case B',
            url='/api/case-b/',
            method='GET',
            expected_status=200,
        )
        auto_result = ApiAutoTestResult.objects.create(
            name='multi case run',
            status='failed',
            total_cases=2,
            passed_cases=1,
            failed_cases=1,
            error_cases=0,
            project=test_project,
            executed_by=test_user,
        )
        TestResult.objects.create(
            test_type='api',
            name='multi case run',
            status='failed',
            project=test_project,
            executed_by=test_user,
            api_auto_result=auto_result,
            source='devops',
        )
        ApiAutoTestCaseResult.objects.create(
            case=case_a,
            test_result=auto_result,
            status_code=404,
            response_time_ms=10,
            passed=True,
            failure_type='passed',
            result_metadata={
                'provider': 'http',
                'expectation_type': 'error_response',
                'default_assertion_policy': 'expected_error_response',
                'expected_status': 404,
                'semantic_status': 'expected_error_matched',
                'semantic_label': '预期错误响应且匹配成功',
            },
        )
        ApiAutoTestCaseResult.objects.create(
            case=case_b,
            test_result=auto_result,
            status_code=500,
            response_time_ms=22,
            passed=False,
            failure_type='assertion_failed',
            result_metadata={
                'provider': 'http',
                'expectation_type': 'success_response',
                'default_assertion_policy': 'success_response',
                'expected_status': 200,
                'semantic_status': 'success_response_failed',
                'semantic_label': '测试失败',
            },
        )

        response = auth_client.get('/api/qa/test-results/')

        assert response.status_code == 200
        row = next(item for item in response.data['results'] if item['name'] == 'multi case run')
        assert row['semantic_status'] == 'result_failed'
        assert row['semantic_label'] == '失败'
        assert row['expectation_type'] is None
        assert row['default_assertion_policy'] is None
        assert row['expected_status'] is None

    def test_test_result_detail_uses_aggregate_status_for_multi_case_api_mirror(self, auth_client, test_project, test_user):
        from qa_center.models import ApiAutoTestCase, ApiAutoTestResult, ApiAutoTestCaseResult, TestResult

        case_a = ApiAutoTestCase.objects.create(
            project=test_project,
            created_by=test_user,
            name='detail aggregate case A',
            url='/api/detail-a/',
            method='GET',
            expected_status=404,
        )
        case_b = ApiAutoTestCase.objects.create(
            project=test_project,
            created_by=test_user,
            name='detail aggregate case B',
            url='/api/detail-b/',
            method='GET',
            expected_status=200,
        )
        auto_result = ApiAutoTestResult.objects.create(
            name='multi case detail run',
            status='failed',
            total_cases=2,
            passed_cases=1,
            failed_cases=1,
            error_cases=0,
            project=test_project,
            executed_by=test_user,
        )
        detail_result = TestResult.objects.create(
            test_type='api',
            name='multi case detail run',
            status='failed',
            project=test_project,
            executed_by=test_user,
            api_auto_result=auto_result,
            source='devops',
        )
        ApiAutoTestCaseResult.objects.create(
            case=case_a,
            test_result=auto_result,
            status_code=404,
            response_time_ms=10,
            passed=True,
            failure_type='passed',
            result_metadata={
                'provider': 'http',
                'expectation_type': 'error_response',
                'default_assertion_policy': 'expected_error_response',
                'expected_status': 404,
                'semantic_status': 'expected_error_matched',
                'semantic_label': '预期错误响应且匹配成功',
            },
        )
        ApiAutoTestCaseResult.objects.create(
            case=case_b,
            test_result=auto_result,
            status_code=500,
            response_time_ms=20,
            passed=False,
            failure_type='assertion_failed',
            result_metadata={
                'provider': 'http',
                'expectation_type': 'success_response',
                'default_assertion_policy': 'success_response',
                'expected_status': 200,
                'semantic_status': 'success_response_failed',
                'semantic_label': '测试失败',
            },
        )

        response = auth_client.get(f'/api/qa/test-results/{detail_result.id}/')

        assert response.status_code == 200
        assert response.data['semantic_status'] == 'result_failed'
        assert response.data['semantic_label'] == '失败'
        assert response.data['expectation_type'] is None
        assert response.data['default_assertion_policy'] is None
        assert response.data['expected_status'] is None

    def test_list_performance_cases(self, auth_client):
        response = auth_client.get('/api/qa/performance-cases/')
        assert response.status_code == 200
        assert 'results' in response.data

    def test_performance_case_detail_prefers_latest_result_by_started_at(self, auth_client, test_project, test_user):
        from qa_center.models import PerformanceTestCase, PerformanceTestResult, TestResult

        case = PerformanceTestCase.objects.create(
            project=test_project,
            created_by=test_user,
            name='perf latest by start time',
            url='https://example.com/perf',
            method='GET',
            concurrent_users=5,
            duration_seconds=10,
        )
        latest_started = TestResult.objects.create(
            test_type='performance',
            name='latest started',
            project=test_project,
            status='passed',
            executed_by=test_user,
            started_at=timezone.now(),
        )
        latest_perf = PerformanceTestResult.objects.create(
            test_case=case,
            test_result=latest_started,
            executed_by=test_user,
            total_requests=100,
            successful_requests=100,
            failed_requests=0,
            avg_response_time_ms=111,
            min_response_time_ms=100,
            max_response_time_ms=120,
            p50_response_time_ms=110,
            p90_response_time_ms=115,
            p95_response_time_ms=118,
            p99_response_time_ms=119,
            throughput=20,
            error_rate=0,
        )
        stale_started = TestResult.objects.create(
            test_type='performance',
            name='stale started',
            project=test_project,
            status='passed',
            executed_by=test_user,
            started_at=timezone.now() - timezone.timedelta(days=1),
        )
        stale_perf = PerformanceTestResult.objects.create(
            test_case=case,
            test_result=stale_started,
            executed_by=test_user,
            total_requests=50,
            successful_requests=50,
            failed_requests=0,
            avg_response_time_ms=999,
            min_response_time_ms=900,
            max_response_time_ms=1000,
            p50_response_time_ms=950,
            p90_response_time_ms=980,
            p95_response_time_ms=990,
            p99_response_time_ms=995,
            throughput=5,
            error_rate=0,
        )
        assert stale_perf.executed_at >= latest_perf.executed_at

        response = auth_client.get(f'/api/qa/performance-cases/{case.id}/')

        assert response.status_code == 200
        assert response.data['last_result']['id'] == latest_perf.id
        assert response.data['last_result']['avg_response_time_ms'] == 111
        assert response.data['last_result']['throughput'] == 20

    def test_auto_suite_serializers_prefer_latest_result_by_started_at(self, test_project, test_user):
        from qa_center.models import ApiAutoTestSuite, ApiAutoTestResult
        from qa_center.serializers import ApiAutoTestSuiteSerializer, ApiAutoTestSuiteListSerializer

        suite = ApiAutoTestSuite.objects.create(
            project=test_project,
            created_by=test_user,
            name='serializer latest suite',
        )
        latest_started = ApiAutoTestResult.objects.create(
            suite=suite,
            project=test_project,
            name='latest started result',
            status='passed',
            total_cases=2,
            passed_cases=2,
            failed_cases=0,
            error_cases=0,
            duration_ms=120,
            executed_by=test_user,
            started_at=timezone.now(),
        )
        stale_started = ApiAutoTestResult.objects.create(
            suite=suite,
            project=test_project,
            name='stale started result',
            status='failed',
            total_cases=2,
            passed_cases=1,
            failed_cases=1,
            error_cases=0,
            duration_ms=240,
            executed_by=test_user,
            started_at=timezone.now() - timezone.timedelta(days=1),
        )
        ApiAutoTestResult.objects.filter(id=latest_started.id).update(
            created_at=timezone.now() - timezone.timedelta(days=2)
        )
        latest_started.refresh_from_db()
        stale_started.refresh_from_db()
        assert stale_started.created_at > latest_started.created_at

        detail_data = ApiAutoTestSuiteSerializer(instance=suite).data
        list_data = ApiAutoTestSuiteListSerializer(instance=suite).data

        assert detail_data['last_result']['id'] == latest_started.id
        assert detail_data['last_result']['status'] == 'passed'
        assert list_data['last_run']['id'] == latest_started.id
        assert list_data['last_run']['status'] == 'passed'

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



@pytest.mark.django_db
def test_execute_test_task_updates_last_result_for_unified_single_case(test_project, test_user):
    from qa_center.models import TestTask, ApiAutoTestCase, ApiAutoTestResult
    from qa_center.tasks_test_exec import execute_test_task

    case = ApiAutoTestCase.objects.create(
        project=test_project,
        created_by=test_user,
        name='async task case',
        url='/api/async-task/',
        method='GET',
        expected_status=200,
    )
    task = TestTask.objects.create(
        project=test_project,
        created_by=test_user,
        name='async api task',
        test_type='api',
        trigger_type='manual',
        test_config={'api_cases': [case.id]},
        status='idle',
    )

    fake_result = ApiAutoTestResult.objects.create(
        suite=case.suite,
        project=test_project,
        name='async task case_result',
        status='running',
        total_cases=1,
        executed_by=test_user,
        started_at=timezone.now(),
    )

    class _FakeOrchestrator:
        def execute(self_inner):
            fake_result.status = 'passed'
            fake_result.completed_at = timezone.now()
            fake_result.save(update_fields=['status', 'completed_at'])
            return {'test_result': fake_result, 'case_result': None, 'runtime_mode': 'mock'}

    from qa_center.models import TestResult
    TestResult.objects.create(
        test_type='api',
        name='async mirrored result',
        status='passed',
        project=test_project,
        executed_by=test_user,
        api_auto_result=fake_result,
        source='single',
    )
    with patch('qa_center.tasks_test_exec.use_unified_runner_for_async_triggers', return_value=True), \
         patch('qa_center.tasks_test_exec.create_api_auto_single_case_orchestrator', return_value=_FakeOrchestrator()):
        response = execute_test_task.run(task.id)

    task.refresh_from_db()
    assert response['status'] == 'success'
    assert task.status == 'completed'


@pytest.mark.django_db
def test_execute_test_task_preserves_execution_count_for_prequeued_unified_single_case(test_project, test_user):
    from qa_center.models import TestTask, ApiAutoTestCase, ApiAutoTestResult, TestResult
    from qa_center.tasks_test_exec import execute_test_task

    case = ApiAutoTestCase.objects.create(
        project=test_project,
        created_by=test_user,
        name='prequeued async task case',
        url='/api/prequeued-async-task/',
        method='GET',
        expected_status=200,
    )
    task = TestTask.objects.create(
        project=test_project,
        created_by=test_user,
        name='prequeued async api task',
        test_type='api',
        trigger_type='manual',
        test_config={'api_cases': [case.id]},
        status='running',
        execution_count=1,
    )

    fake_result = ApiAutoTestResult.objects.create(
        suite=case.suite,
        project=test_project,
        name='prequeued async task case_result',
        status='running',
        total_cases=1,
        executed_by=test_user,
        started_at=timezone.now(),
    )

    class _FakeOrchestrator:
        def execute(self_inner):
            fake_result.status = 'passed'
            fake_result.completed_at = timezone.now()
            fake_result.save(update_fields=['status', 'completed_at'])
            return {'test_result': fake_result, 'case_result': None, 'runtime_mode': 'mock'}

    TestResult.objects.create(
        test_type='api',
        name='prequeued async mirrored result',
        status='passed',
        project=test_project,
        executed_by=test_user,
        api_auto_result=fake_result,
        source='devops',
    )
    with patch('qa_center.tasks_test_exec.use_unified_runner_for_async_triggers', return_value=True), \
         patch('qa_center.tasks_test_exec.create_api_auto_single_case_orchestrator', return_value=_FakeOrchestrator()):
        response = execute_test_task.run(task.id)

    task.refresh_from_db()
    assert response['status'] == 'success'
    assert task.status == 'completed'
    assert task.execution_count == 1
    assert task.last_result is not None
    assert task.last_result.api_auto_result_id == fake_result.id
    assert task.last_result.task_id == str(task.id)


@pytest.mark.django_db
def test_execute_test_task_unified_single_case_syncs_result_centers_without_preseeded_mirror(test_project, test_user, monkeypatch):
    from qa_center import api_execution
    from qa_center.models import ApiAutoTestAssertion, ApiAutoTestCase, ApiAutoTestSuite, TestResult, TestRunCaseResult, TestTask
    from qa_center.tasks_test_exec import execute_test_task

    monkeypatch.setenv("APP_ENV", "test")

    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        created_by=test_user,
        name='async unified expected error suite',
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        project=test_project,
        created_by=test_user,
        name='async unified expected error case',
        url='https://api.example.test/async-missing',
        method='GET',
        expected_status=404,
    )
    ApiAutoTestAssertion.objects.create(
        case=case,
        assertion_type='status_code',
        expected_value='404',
        comparison_operator='eq',
        is_active=True,
    )
    task = TestTask.objects.create(
        project=test_project,
        created_by=test_user,
        name='async unified expected error task',
        test_type='api',
        trigger_type='manual',
        test_config={'api_cases': [case.id]},
        status='idle',
    )

    transport = api_execution.MockTransport(
        responses=[
            api_execution.TransportResponse(
                status_code=404,
                headers={'Content-Type': 'application/json'},
                cookies={},
                body_bytes=b'{"detail":"not found"}',
                text='{"detail":"not found"}',
                elapsed_ms=9,
                final_url='https://api.example.test/async-missing',
                redirect_chain=[],
            ),
        ]
    )

    with patch('qa_center.tasks_test_exec.use_unified_runner_for_async_triggers', return_value=True), \
         patch('qa_center.api_execution.orchestrators.MockTransport', return_value=transport):
        response = execute_test_task.run(task.id)

    task.refresh_from_db()
    assert response['status'] == 'success'
    assert task.status == 'completed'
    assert task.last_result is not None

    mirrored = task.last_result
    auto_result = mirrored.api_auto_result
    case_result = TestRunCaseResult.objects.get(test_run__name=auto_result.name, api_auto_case=case)

    assert auto_result.status == 'passed'
    assert mirrored.status == 'passed'
    assert case_result.status == 'passed'
    assert case_result.result_metadata['expectation_type'] == 'error_response'
    assert case_result.result_metadata['default_assertion_policy'] == 'expected_error_response'
    assert case_result.result_metadata['expected_status'] == 404
    assert case_result.result_metadata['semantic_status'] == 'expected_error_matched'


@pytest.mark.django_db
def test_execute_test_task_updates_last_result_for_legacy_single_case(test_project, test_user):
    from qa_center.models import TestTask, ApiAutoTestCase, ApiAutoTestResult, TestResult
    from qa_center.tasks_test_exec import execute_test_task

    case = ApiAutoTestCase.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy async task case',
        url='/api/legacy-async-task/',
        method='GET',
        expected_status=200,
    )
    task = TestTask.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy async api task',
        test_type='api',
        trigger_type='manual',
        test_config={'api_cases': [case.id]},
        status='idle',
    )

    fake_result = ApiAutoTestResult.objects.create(
        suite=case.suite,
        project=test_project,
        name='legacy async task case_result',
        status='passed',
        total_cases=1,
        executed_by=test_user,
        started_at=timezone.now(),
        completed_at=timezone.now(),
    )
    mirrored = TestResult.objects.create(
        test_type='api',
        name='legacy async mirrored result',
        status='passed',
        project=test_project,
        executed_by=test_user,
        api_auto_result=fake_result,
        source='single',
    )

    class _FakeExecutor:
        def execute_single_case(self_inner, _case):
            class _FakeCaseResult:
                test_result = fake_result
            return _FakeCaseResult()

    with patch('qa_center.tasks_test_exec.use_unified_runner_for_async_triggers', return_value=False), \
         patch('qa_center.api_auto_executor.ApiAutoTestExecutor', return_value=_FakeExecutor()):
        response = execute_test_task.run(task.id)

    task.refresh_from_db()
    assert response['status'] == 'success'
    assert task.status == 'completed'


@pytest.mark.django_db
def test_execute_test_task_legacy_single_case_syncs_result_centers_without_preseeded_mirror(test_project, test_user):
    from unittest.mock import MagicMock, patch

    from qa_center.models import ApiAutoTestAssertion, ApiAutoTestCase, ApiAutoTestSuite, TestResult, TestRunCaseResult, TestTask
    from qa_center.tasks_test_exec import execute_test_task

    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy async expected error suite',
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        project=test_project,
        created_by=test_user,
        name='legacy async expected error case',
        url='https://api.example.test/legacy-async-missing',
        method='GET',
        expected_status=404,
    )
    ApiAutoTestAssertion.objects.create(
        case=case,
        assertion_type='status_code',
        expected_value='404',
        comparison_operator='eq',
        is_active=True,
    )
    task = TestTask.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy async expected error task',
        test_type='api',
        trigger_type='manual',
        test_config={'api_cases': [case.id]},
        status='idle',
    )

    response = MagicMock()
    response.status_code = 404
    response.text = '{"detail":"not found"}'
    response.json.return_value = {'detail': 'not found'}
    response.headers = {'Content-Type': 'application/json'}
    response.elapsed.total_seconds.return_value = 0.01
    response.cookies = {}

    with patch('qa_center.tasks_test_exec.use_unified_runner_for_async_triggers', return_value=False), \
         patch('qa_center.api_auto_executor.validate_target_url', return_value=case.url), \
         patch('qa_center.api_auto_executor.requests.request', return_value=response):
        result = execute_test_task.run(task.id)

    task.refresh_from_db()
    assert result['status'] == 'success'
    assert task.status == 'completed'
    assert task.last_result is not None

    mirrored = task.last_result
    auto_result = mirrored.api_auto_result
    case_result = TestRunCaseResult.objects.get(test_run__name=auto_result.name, api_auto_case=case)

    assert auto_result.status == 'passed'
    assert auto_result.passed_cases == 1
    assert auto_result.failed_cases == 0
    assert auto_result.error_cases == 0
    assert mirrored.status == 'passed'
    assert mirrored.source == 'single'
    assert case_result.status == 'passed'
    assert case_result.result_metadata['expectation_type'] == 'error_response'
    assert case_result.result_metadata['default_assertion_policy'] == 'expected_error_response'
    assert case_result.result_metadata['expected_status'] == 404
    assert case_result.result_metadata['semantic_status'] == 'expected_error_matched'


@pytest.mark.django_db
def test_legacy_api_auto_executor_single_case_persists_expected_error_semantics(test_project, test_user):
    from unittest.mock import MagicMock, patch

    from qa_center.api_auto_executor import ApiAutoTestExecutor
    from qa_center.models import ApiAutoTestCase, ApiAutoTestResult, ApiAutoTestSuite

    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy expected error suite',
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        project=test_project,
        created_by=test_user,
        name='legacy expected error case',
        url='https://api.example.test/legacy-missing',
        method='GET',
        expected_status=404,
    )

    auto_result = ApiAutoTestResult.objects.create(
        suite=case.suite,
        project=test_project,
        name='legacy expected error run',
        status='running',
        total_cases=1,
        executed_by=test_user,
        started_at=timezone.now(),
    )

    response = MagicMock()
    response.status_code = 404
    response.text = '{"detail":"not found"}'
    response.json.return_value = {'detail': 'not found'}
    response.headers = {'Content-Type': 'application/json'}
    response.elapsed.total_seconds.return_value = 0.01
    response.cookies = {}

    with patch('qa_center.api_auto_executor.validate_target_url', return_value=case.url), \
         patch('qa_center.api_auto_executor.requests.request', return_value=response):
        case_result = ApiAutoTestExecutor(suite_id=case.suite_id, user=test_user).execute_single_case(
            case,
            test_result=auto_result,
        )

    metadata = case_result.result_metadata or {}
    auto_result.refresh_from_db()

    assert case_result.passed is True
    assert auto_result.status == 'passed'
    assert auto_result.passed_cases == 1
    assert auto_result.failed_cases == 0
    assert auto_result.error_cases == 0
    assert auto_result.completed_at is not None
    assert metadata.get('expectation_type') == 'error_response'
    assert metadata.get('default_assertion_policy') == 'expected_error_response'
    assert metadata.get('expected_status') == 404
    assert case_result.assertion_details[0]['assertion_type'] == 'status_code'
    assert case_result.assertion_details[0]['expected_value'] == 404
    assert case_result.assertion_details[0]['passed'] is True
    assert case_result.assertion_details[0]['source'] == 'provider_default'


def test_legacy_api_auto_executor_execute_syncs_expected_error_semantics_into_result_centers(test_project, test_user):
    from qa_center.api_auto_executor import ApiAutoTestExecutor
    from qa_center.models import ApiAutoTestAssertion, ApiAutoTestCase, ApiAutoTestSuite, TestResult, TestRunCaseResult
    from qa_center.result_sink import _select_preferred_mirror

    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy expected error suite execute',
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        project=test_project,
        created_by=test_user,
        name='legacy expected error case execute',
        url='https://api.example.test/legacy-missing-execute',
        method='GET',
        expected_status=404,
    )
    ApiAutoTestAssertion.objects.create(
        case=case,
        assertion_type='status_code',
        expected_value='404',
        comparison_operator='eq',
        is_active=True,
    )

    response = MagicMock()
    response.status_code = 404
    response.text = '{"detail":"not found"}'
    response.json.return_value = {'detail': 'not found'}
    response.headers = {'Content-Type': 'application/json'}
    response.elapsed.total_seconds.return_value = 0.01
    response.cookies = {}

    with patch('qa_center.api_auto_executor.validate_target_url', return_value=case.url), \
         patch('qa_center.api_auto_executor.requests.request', return_value=response):
        auto_result = ApiAutoTestExecutor(suite_id=case.suite_id, user=test_user).execute()

    mirrored = _select_preferred_mirror(auto_result=auto_result)
    case_result = TestRunCaseResult.objects.get(test_run__name=auto_result.name, api_auto_case=case)

    assert auto_result.status == 'passed'
    assert auto_result.passed_cases == 1
    assert auto_result.failed_cases == 0
    assert auto_result.error_cases == 0
    assert mirrored.source == 'single'
    assert mirrored.status == 'passed'
    assert case_result.status == 'passed'
    assert case_result.result_metadata['expectation_type'] == 'error_response'
    assert case_result.result_metadata['default_assertion_policy'] == 'expected_error_response'
    assert case_result.result_metadata['expected_status'] == 404


@pytest.mark.django_db
def test_legacy_api_auto_executor_single_case_does_not_infer_http_failure_when_assertion_engine_returns_no_results(test_project, test_user):
    from unittest.mock import MagicMock, patch

    from qa_center.api_auto_executor import ApiAutoTestExecutor
    from qa_center.models import ApiAutoTestCase, ApiAutoTestResult, ApiAutoTestSuite

    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy unknown error suite',
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        project=test_project,
        created_by=test_user,
        name='legacy unknown error case',
        url='https://api.example.test/legacy-error',
        method='GET',
        expected_status=200,
    )

    auto_result = ApiAutoTestResult.objects.create(
        suite=case.suite,
        project=test_project,
        name='legacy unknown error run',
        status='running',
        total_cases=1,
        executed_by=test_user,
        started_at=timezone.now(),
    )

    response = MagicMock()
    response.status_code = 500
    response.text = '{"detail":"boom"}'
    response.json.return_value = {'detail': 'boom'}
    response.headers = {'Content-Type': 'application/json'}
    response.elapsed.total_seconds.return_value = 0.01
    response.cookies = {}

    with patch('qa_center.api_auto_executor.validate_target_url', return_value=case.url), \
         patch('qa_center.api_auto_executor.requests.request', return_value=response), \
         patch('qa_center.api_auto_executor.ua.run_assertions', return_value=[]):
        case_result = ApiAutoTestExecutor(suite_id=case.suite_id, user=test_user).execute_single_case(
            case,
            test_result=auto_result,
        )

    auto_result.refresh_from_db()

    assert case_result.passed is True
    assert case_result.failure_type == 'passed'
    assert auto_result.status == 'passed'
    assert auto_result.passed_cases == 1
    assert auto_result.failed_cases == 0
    assert auto_result.error_cases == 0


@pytest.mark.django_db
def test_legacy_api_auto_executor_execute_does_not_infer_http_failure_when_assertion_engine_returns_no_results(test_project, test_user):
    from unittest.mock import MagicMock, patch

    from qa_center.api_auto_executor import ApiAutoTestExecutor
    from qa_center.models import ApiAutoTestCase, ApiAutoTestSuite

    suite = ApiAutoTestSuite.objects.create(
        project=test_project,
        created_by=test_user,
        name='legacy execute unknown error suite',
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        project=test_project,
        created_by=test_user,
        name='legacy execute unknown error case',
        url='https://api.example.test/legacy-execute-error',
        method='GET',
        expected_status=200,
    )

    response = MagicMock()
    response.status_code = 500
    response.text = '{"detail":"boom"}'
    response.json.return_value = {'detail': 'boom'}
    response.headers = {'Content-Type': 'application/json'}
    response.elapsed.total_seconds.return_value = 0.01
    response.cookies = {}

    with patch('qa_center.api_auto_executor.validate_target_url', return_value=case.url), \
         patch('qa_center.api_auto_executor.requests.request', return_value=response), \
         patch('qa_center.api_auto_executor.ua.run_assertions', return_value=[]):
        auto_result = ApiAutoTestExecutor(suite_id=case.suite_id, user=test_user).execute()

    case_result = auto_result.case_results.get(case=case)
    assert case_result.passed is True
    assert case_result.failure_type == 'passed'
    assert auto_result.status == 'passed'
    assert auto_result.passed_cases == 1
    assert auto_result.failed_cases == 0
    assert auto_result.error_cases == 0


@pytest.mark.django_db
def test_legacy_api_auto_executor_classifier_does_not_upgrade_empty_assertion_5xx_to_error():
    from types import SimpleNamespace

    from qa_center.api_auto_executor import ApiAutoTestExecutor

    case_result = SimpleNamespace(
        passed=False,
        failure_type='assertion_failed',
        result_metadata={
            'expectation_type': 'success_response',
        },
        assertion_details=[],
        status_code=500,
    )

    assert ApiAutoTestExecutor._classify_case_result(case_result) == (0, 1, 0)
