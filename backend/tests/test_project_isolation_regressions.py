import pytest
from django.contrib.auth.models import User
from unittest.mock import patch

from bug_tracker.models import Bug
from qa_center.models import (
    ApiAutoTestCase,
    ApiAutoTestSuite,
    ApiTestCase,
    ApiTestResult,
    PerformanceTestCase,
    PerformanceTestResult,
    TestEnvironment as QaTestEnvironment,
    TestGlobalVar as QaTestGlobalVar,
    TestResult as QaTestResult,
    TestRun as QaTestRun,
    TestRunPlan as QaTestRunPlan,
    UiTestCase,
)
from room.models import Column, Project


@pytest.mark.django_db
class TestProjectIsolationRegressions:
    def setup_method(self):
        self.owner = User.objects.create_user(username='iso_owner', password='pass')
        self.outsider = User.objects.create_user(username='iso_outsider', password='pass')
        self.project = Project.objects.create(name='Secret Project', owner=self.owner)
        self.column = Column.objects.create(project=self.project, title='Todo', position=1)

    def test_anonymous_auto_suites_list_is_rejected(self, client):
        resp = client.get('/api/qa/auto-suites/')
        assert resp.status_code in (401, 403)

    def test_anonymous_auto_suite_create_is_rejected_not_500(self, client):
        resp = client.post(
            '/api/qa/auto-suites/',
            data={'project': self.project.id, 'name': 'anonymous suite'},
            content_type='application/json',
        )
        assert resp.status_code in (401, 403)
        assert ApiAutoTestSuite.objects.count() == 0

    def test_bug_list_rejects_outsider_project_filter(self, client):
        Bug.objects.create(project=self.project, title='Hidden bug', reporter=self.owner)
        client.force_login(self.outsider)

        resp = client.get(f'/api/bugs/?project={self.project.id}')

        assert resp.status_code == 403

    def test_bug_detail_rejects_outsider(self, client):
        bug = Bug.objects.create(project=self.project, title='Hidden bug', reporter=self.owner)
        client.force_login(self.outsider)

        resp = client.get(f'/api/bugs/{bug.id}/')

        assert resp.status_code == 403

    def test_bug_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/bugs/',
            data={
                'project': str(self.project.id),
                'title': 'Injected bug',
                'description': 'Should not be created',
                'severity': 'major',
                'priority': 'p1',
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert Bug.objects.count() == 0

    def test_bug_stats_rejects_outsider_project(self, client):
        Bug.objects.create(project=self.project, title='Hidden bug', reporter=self.owner)
        client.force_login(self.outsider)

        resp = client.get(f'/api/bugs/stats/?project={self.project.id}')

        assert resp.status_code == 403

    def test_qa_api_cases_list_rejects_outsider_project_filter(self, client):
        ApiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Hidden case',
            url='/api/health/',
            method='GET',
            expected_status=200,
        )
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/api-cases/?project={self.project.id}')

        assert resp.status_code == 403

    def test_qa_api_case_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/api-cases/',
            data={
                'project': self.project.id,
                'name': 'Injected case',
                'url': '/api/health/',
                'method': 'GET',
                'expected_status': 200,
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert ApiTestCase.objects.count() == 0

    def test_qa_run_batch_rejects_outsider_cases(self, client):
        case = ApiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Hidden case',
            url='/api/health/',
            method='GET',
            expected_status=200,
        )
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/api-cases/run-batch/',
            data={'case_ids': [case.id]},
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert QaTestRun.objects.count() == 0

    def test_qa_test_run_detail_rejects_outsider(self, client):
        run = QaTestRun.objects.create(
            project=self.project,
            name='Hidden run',
            trigger='manual',
            test_type='api',
            status='passed',
            triggered_by=self.owner,
        )
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/runs/{run.id}/')

        assert resp.status_code == 403

    def _create_run_plan_fixture(self):
        suite = ApiAutoTestSuite.objects.create(
            project=self.project,
            name='Secret Suite',
            created_by=self.owner,
        )
        case = ApiAutoTestCase.objects.create(
            suite=suite,
            created_by=self.owner,
            name='Secret Case',
            url='/api/secret/',
            method='GET',
            expected_status=200,
        )
        plan = QaTestRunPlan.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret Plan',
            case_ids=[case.id],
        )
        return suite, case, plan

    def test_run_plan_list_rejects_outsider_project_filter(self, client):
        self._create_run_plan_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/run-plans/?project={self.project.id}')

        assert resp.status_code == 403

    def test_run_plan_list_without_project_does_not_leak_foreign_plans(self, client):
        _, _, plan = self._create_run_plan_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/run-plans/')

        assert resp.status_code == 200
        names = [p['name'] for p in resp.data['results']]
        assert plan.name not in names

    def test_run_plan_cases_rejects_outsider_project(self, client):
        self._create_run_plan_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/run-plans/cases/?project={self.project.id}')

        assert resp.status_code == 403

    def test_run_plan_create_rejects_outsider_project(self, client):
        _, case, _ = self._create_run_plan_fixture()
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/run-plans/',
            data={
                'project': str(self.project.id),
                'name': 'Injected Plan',
                'case_ids': [case.id],
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not QaTestRunPlan.objects.filter(name='Injected Plan').exists()

    def test_run_plan_detail_update_delete_execute_reject_outsider(self, client):
        _, _, plan = self._create_run_plan_fixture()
        client.force_login(self.outsider)

        detail = client.get(f'/api/qa/run-plans/{plan.id}/')
        update = client.patch(
            f'/api/qa/run-plans/{plan.id}/',
            data={'name': 'Updated by outsider'},
            content_type='application/json',
        )
        with patch('qa_center.views_run_plan.threading.Thread') as thread_cls:
            execute = client.post(
                f'/api/qa/run-plans/{plan.id}/execute/',
                data={},
                content_type='application/json',
            )
        delete = client.delete(f'/api/qa/run-plans/{plan.id}/')

        assert detail.status_code == 403
        assert update.status_code == 403
        assert execute.status_code == 403
        assert delete.status_code == 403
        thread_cls.assert_not_called()
        plan.refresh_from_db()
        assert plan.name == 'Secret Plan'

    def test_run_plan_member_can_access_project_plan(self, client):
        _, _, plan = self._create_run_plan_fixture()
        member = User.objects.create_user(username='iso_member', password='pass')
        self.project.members.add(member)
        client.force_login(member)

        list_resp = client.get(f'/api/qa/run-plans/?project={self.project.id}')
        detail = client.get(f'/api/qa/run-plans/{plan.id}/')
        cases = client.get(f'/api/qa/run-plans/cases/?project={self.project.id}')
        with patch('qa_center.views_run_plan.threading.Thread') as thread_cls:
            execute = client.post(
                f'/api/qa/run-plans/{plan.id}/execute/',
                data={},
                content_type='application/json',
            )

        assert list_resp.status_code == 200
        assert detail.status_code == 200
        assert cases.status_code == 200
        assert execute.status_code == 202
        thread_cls.return_value.start.assert_called_once()

    def _create_environment_fixture(self):
        default_env = QaTestEnvironment.objects.create(
            project=self.project,
            name='secret-default-env',
            base_url='https://secret.example.com',
            variables={'token': 'secret-token'},
            is_default=True,
            created_by=self.owner,
        )
        staging_env = QaTestEnvironment.objects.create(
            project=self.project,
            name='secret-staging-env',
            base_url='https://staging.secret.example.com',
            variables={'token': 'staging-token'},
            is_default=False,
            created_by=self.owner,
        )
        return default_env, staging_env

    def _create_global_var_fixture(self):
        return QaTestGlobalVar.objects.create(
            project=self.project,
            key='SECRET_TOKEN',
            value='super-secret-token',
            is_secret=True,
            created_by=self.owner,
        )

    def test_environment_list_rejects_outsider_project_filter(self, client):
        self._create_environment_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/environments/?project={self.project.id}')

        assert resp.status_code == 403

    def test_environment_list_without_project_does_not_leak_foreign_envs(self, client):
        default_env, _ = self._create_environment_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/environments/')

        assert resp.status_code == 200
        names = [env['name'] for env in resp.data['results']]
        assert default_env.name not in names

    def test_environment_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/environments/',
            data={
                'project': self.project.id,
                'name': 'injected-env',
                'variables': {'token': 'injected'},
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not QaTestEnvironment.objects.filter(name='injected-env').exists()

    def test_environment_detail_update_delete_set_default_reject_outsider(self, client):
        default_env, staging_env = self._create_environment_fixture()
        client.force_login(self.outsider)

        detail = client.get(f'/api/qa/environments/{staging_env.id}/')
        update = client.patch(
            f'/api/qa/environments/{staging_env.id}/',
            data={'name': 'updated-by-outsider', 'is_default': True},
            content_type='application/json',
        )
        set_default = client.post(f'/api/qa/environments/{staging_env.id}/set_default/')
        delete = client.delete(f'/api/qa/environments/{staging_env.id}/')

        assert detail.status_code == 403
        assert update.status_code == 403
        assert set_default.status_code == 403
        assert delete.status_code == 403
        default_env.refresh_from_db()
        staging_env.refresh_from_db()
        assert default_env.is_default is True
        assert staging_env.is_default is False
        assert staging_env.name == 'secret-staging-env'

    def test_global_var_list_rejects_outsider_project_filter(self, client):
        self._create_global_var_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/global-vars/?project={self.project.id}')

        assert resp.status_code == 403

    def test_global_var_list_without_project_does_not_leak_foreign_vars(self, client):
        global_var = self._create_global_var_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/global-vars/')

        assert resp.status_code == 200
        items = resp.data['results']
        assert global_var.key not in [item['key'] for item in items]
        assert global_var.value not in [item['value'] for item in items]

    def test_global_var_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/global-vars/',
            data={
                'project': self.project.id,
                'key': 'INJECTED_TOKEN',
                'value': 'injected-secret',
                'is_secret': True,
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not QaTestGlobalVar.objects.filter(key='INJECTED_TOKEN').exists()

    def test_global_var_detail_update_delete_reject_outsider(self, client):
        global_var = self._create_global_var_fixture()
        client.force_login(self.outsider)

        detail = client.get(f'/api/qa/global-vars/{global_var.id}/')
        update = client.patch(
            f'/api/qa/global-vars/{global_var.id}/',
            data={'value': 'updated-by-outsider'},
            content_type='application/json',
        )
        delete = client.delete(f'/api/qa/global-vars/{global_var.id}/')

        assert detail.status_code == 403
        assert update.status_code == 403
        assert delete.status_code == 403
        global_var.refresh_from_db()
        assert global_var.value == 'super-secret-token'

    def test_environment_and_global_var_member_can_access_project_resources(self, client):
        _, staging_env = self._create_environment_fixture()
        global_var = self._create_global_var_fixture()
        member = User.objects.create_user(username='iso_env_member', password='pass')
        self.project.members.add(member)
        client.force_login(member)

        env_list = client.get(f'/api/qa/environments/?project={self.project.id}')
        env_detail = client.get(f'/api/qa/environments/{staging_env.id}/')
        env_set_default = client.post(f'/api/qa/environments/{staging_env.id}/set_default/')
        var_list = client.get(f'/api/qa/global-vars/?project={self.project.id}')
        var_detail = client.get(f'/api/qa/global-vars/{global_var.id}/')

        assert env_list.status_code == 200
        assert env_detail.status_code == 200
        assert env_set_default.status_code == 200
        assert var_list.status_code == 200
        assert var_detail.status_code == 200
        assert var_detail.data['value'] == 'super-secret-token'

    def _create_result_fixture(self):
        ui_case = UiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret UI Case',
            url='/secret-ui/',
            steps=[{'action': 'click', 'selector': '#secret'}],
        )
        api_case = ApiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret API Case',
            url='/api/secret/',
            method='GET',
            expected_status=200,
        )
        result = QaTestResult.objects.create(
            project=self.project,
            test_type='ui',
            name='Secret Result',
            status='failed',
            ui_test_case=ui_case,
            executed_by=self.owner,
            test_log='secret log',
            error_message='secret error',
        )
        api_result = ApiTestResult.objects.create(
            test_case=api_case,
            status_code=200,
            response_body='secret response body',
            response_headers={'X-Secret': 'yes'},
            response_time_ms=12,
            passed=True,
            executed_by=self.owner,
        )
        perf_case = PerformanceTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret Perf Case',
            url='https://secret.example.com/path',
            method='GET',
        )
        perf_result = PerformanceTestResult.objects.create(
            test_case=perf_case,
            test_result=result,
            executed_by=self.owner,
            total_requests=10,
            failed_requests=1,
            avg_response_time=120,
            min_response_time=80,
            max_response_time=300,
            requests_per_second=2.5,
        )
        return result, ui_case, api_case, api_result, perf_case, perf_result

    def test_test_result_list_rejects_outsider_project_filter(self, client):
        self._create_result_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/test-results/?project={self.project.id}')

        assert resp.status_code == 403

    def test_test_result_list_without_project_does_not_leak_foreign_results(self, client):
        result, *_ = self._create_result_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/test-results/')

        assert resp.status_code == 200
        items = resp.data['results']
        assert result.name not in [item['name'] for item in items]

    def test_test_result_detail_update_delete_complete_upload_reject_outsider(self, client):
        result, *_ = self._create_result_fixture()
        client.force_login(self.outsider)

        detail = client.get(f'/api/qa/test-results/{result.id}/')
        update = client.patch(
            f'/api/qa/test-results/{result.id}/',
            data={'status': 'passed', 'test_log': 'tampered'},
            content_type='application/json',
        )
        complete = client.post(
            f'/api/qa/test-results/{result.id}/complete/',
            data={'status': 'passed', 'test_log': 'tampered'},
            content_type='application/json',
        )
        upload = client.post(
            f'/api/qa/test-results/{result.id}/upload_screenshot/',
            data={'base64_image': 'data:image/png;base64,aGVsbG8='},
            content_type='application/json',
        )
        delete = client.delete(f'/api/qa/test-results/{result.id}/')

        assert detail.status_code == 403
        assert update.status_code == 403
        assert complete.status_code == 403
        assert upload.status_code == 403
        assert delete.status_code == 403
        result.refresh_from_db()
        assert result.status == 'failed'
        assert result.test_log == 'secret log'

    def test_test_result_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/test-results/',
            data={
                'project': self.project.id,
                'test_type': 'api',
                'name': 'Injected Result',
                'status': 'passed',
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not QaTestResult.objects.filter(name='Injected Result').exists()

    def test_create_from_ui_test_rejects_outsider_case(self, client):
        _, ui_case, *_ = self._create_result_fixture()
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/test-results/create_from_ui_test/',
            data={'ui_test_case_id': ui_case.id, 'run_result': {'success': True}},
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert QaTestResult.objects.filter(ui_test_case=ui_case).count() == 1

    def test_test_result_statistics_rejects_outsider_project_filter(self, client):
        self._create_result_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/test-results/statistics/?project={self.project.id}')

        assert resp.status_code == 403

    def test_test_result_statistics_without_project_does_not_count_foreign_results(self, client):
        self._create_result_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/test-results/statistics/')

        assert resp.status_code == 200
        assert resp.data['total'] == 0

    def test_api_results_reject_outsider_project_data(self, client):
        _, _, api_case, api_result, *_ = self._create_result_fixture()
        client.force_login(self.outsider)

        list_resp = client.get('/api/qa/api-results/')
        filtered = client.get(f'/api/qa/api-results/?test_case={api_case.id}')
        detail = client.get(f'/api/qa/api-results/{api_result.id}/')

        assert list_resp.status_code == 200
        assert api_result.id not in [item['id'] for item in list_resp.data['results']]
        assert filtered.status_code == 403
        assert detail.status_code == 403

    def test_performance_results_reject_outsider_project_data(self, client):
        _, _, _, _, perf_case, perf_result = self._create_result_fixture()
        client.force_login(self.outsider)

        list_resp = client.get('/api/qa/performance-results/')
        by_project = client.get(f'/api/qa/performance-results/?project={self.project.id}')
        by_case = client.get(f'/api/qa/performance-results/?test_case={perf_case.id}')
        detail = client.get(f'/api/qa/performance-results/{perf_result.id}/')

        assert list_resp.status_code == 200
        assert perf_result.id not in [item['id'] for item in list_resp.data['results']]
        assert by_project.status_code == 403
        assert by_case.status_code == 403
        assert detail.status_code == 403

    def test_result_member_can_access_project_results(self, client):
        result, _, _, api_result, _, perf_result = self._create_result_fixture()
        member = User.objects.create_user(username='iso_result_member', password='pass')
        self.project.members.add(member)
        client.force_login(member)

        result_detail = client.get(f'/api/qa/test-results/{result.id}/')
        api_detail = client.get(f'/api/qa/api-results/{api_result.id}/')
        perf_detail = client.get(f'/api/qa/performance-results/{perf_result.id}/')

        assert result_detail.status_code == 200
        assert api_detail.status_code == 200
        assert perf_detail.status_code == 200
