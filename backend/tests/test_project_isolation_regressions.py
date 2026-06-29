import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from unittest.mock import patch

from bug_tracker.models import Bug
from qa_center.models import (
    ApiAutoTestCase,
    ApiAutoTestSuite,
    ApiTestCase,
    ApiTestResult,
    CiCdConfig,
    PerformanceTestCase,
    PerformanceTestResult,
    PipelineRun,
    TestEnvironment as QaTestEnvironment,
    TestGlobalVar as QaTestGlobalVar,
    TestResult as QaTestResult,
    TestRun as QaTestRun,
    TestRunPlan as QaTestRunPlan,
    TestTask as QaTestTask,
    UiTestCase,
)
from room.models import Column, Project, Task


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
            successful_requests=9,
            failed_requests=1,
            avg_response_time_ms=120,
            min_response_time_ms=80,
            max_response_time_ms=300,
            p50_response_time_ms=110,
            p90_response_time_ms=220,
            p95_response_time_ms=260,
            p99_response_time_ms=300,
            throughput=2.5,
            error_rate=10.0,
        )
        return result, ui_case, api_case, api_result, perf_case, perf_result

    def _create_ui_screenshot_fixture(self):
        result, ui_case, *_ = self._create_result_fixture()
        result.task_id = 'secret-ui-task'
        result.temp_dir_path = ''
        result.save(update_fields=['task_id', 'temp_dir_path'])
        from qa_center.models import TestScreenshot
        screenshot = TestScreenshot.objects.create(
            test_result=result,
            name='Secret UI Screenshot',
            step_index=0,
        )
        screenshot.image.save('secret-ui.png', ContentFile(b'secret screenshot'), save=True)
        return result, ui_case, screenshot

    def _create_ui_case_fixture(self):
        ui_case = UiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret UI Isolation Case',
            url='/secret-ui-isolation/',
            steps=[{'action': 'click', 'selector': '#secret-ui'}],
        )
        linked_task = Task.objects.create(
            column=self.column,
            title='Secret UI Linked Task',
            content='hidden ui task details',
            position=1,
        )
        ui_case.related_tasks.add(linked_task)
        running_result = QaTestResult.objects.create(
            project=self.project,
            test_type='ui',
            name='Secret UI Running Result',
            status='running',
            ui_test_case=ui_case,
            executed_by=self.owner,
            started_at=timezone.now(),
            task_id='secret-ui-task',
        )
        return ui_case, linked_task, running_result

    def test_ui_case_list_rejects_outsider_project_filter(self, client):
        self._create_ui_case_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/ui-cases/?project={self.project.id}')

        assert resp.status_code == 403

    def test_ui_case_list_without_project_does_not_leak_foreign_cases(self, client):
        ui_case, _, _ = self._create_ui_case_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/ui-cases/')

        assert resp.status_code == 200
        items = resp.data['results']
        assert ui_case.id not in [item['id'] for item in items]
        assert ui_case.name not in [item['name'] for item in items]

    def test_ui_case_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/ui-cases/',
            data={
                'project': self.project.id,
                'name': 'Injected UI Case',
                'url': '/injected-ui/',
                'steps': [{'action': 'click', 'selector': '#inject'}],
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not UiTestCase.objects.filter(name='Injected UI Case').exists()

    def test_ui_case_detail_update_delete_reject_outsider(self, client):
        ui_case, _, _ = self._create_ui_case_fixture()
        client.force_login(self.outsider)

        detail = client.get(f'/api/qa/ui-cases/{ui_case.id}/')
        update = client.patch(
            f'/api/qa/ui-cases/{ui_case.id}/',
            data={'name': 'Tampered UI Case'},
            content_type='application/json',
        )
        delete = client.delete(f'/api/qa/ui-cases/{ui_case.id}/')

        assert detail.status_code == 403
        assert update.status_code == 403
        assert delete.status_code == 403
        ui_case.refresh_from_db()
        assert ui_case.name == 'Secret UI Isolation Case'

    def test_ui_case_run_and_linked_tasks_reject_outsider_before_side_effects(self, client):
        ui_case, linked_task, _ = self._create_ui_case_fixture()
        initial_result_count = QaTestResult.objects.count()
        client.force_login(self.outsider)

        with patch('qa_center.views_ui_test.execute_ui_case') as execute_ui_case:
            run_resp = client.post(f'/api/qa/ui-cases/{ui_case.id}/run/')
        linked_tasks = client.get(f'/api/qa/ui-cases/{ui_case.id}/linked-tasks/')

        assert run_resp.status_code == 403
        assert linked_tasks.status_code == 403
        execute_ui_case.assert_not_called()
        assert QaTestResult.objects.count() == initial_result_count
        assert Task.objects.filter(id=linked_task.id).exists()

    def test_ui_run_abort_events_reject_outsider_bound_task_before_side_effects(self, client):
        _, _, running_result = self._create_ui_case_fixture()
        client.force_login(self.outsider)

        with patch('qa_center.views_ui_test.runner_supervisor.is_runner_alive') as is_alive, \
                patch('qa_center.views_ui_test.runner_supervisor.abort_runner') as abort_runner, \
                patch('qa_center.views_ui_test.runner_supervisor.get_events') as get_events:
            abort_resp = client.post(f'/api/qa/ui-cases/runs/{running_result.task_id}/abort/')
            events_resp = client.get(f'/api/qa/ui-cases/runs/{running_result.task_id}/events/')

        assert abort_resp.status_code == 403
        assert events_resp.status_code == 403
        is_alive.assert_not_called()
        abort_runner.assert_not_called()
        get_events.assert_not_called()
        running_result.refresh_from_db()
        assert running_result.status == 'running'
        assert running_result.aborted is False

    def test_ui_case_member_can_access_project_case(self, client):
        ui_case, linked_task, _ = self._create_ui_case_fixture()
        member = User.objects.create_user(username='iso_ui_member', password='pass')
        self.project.members.add(member)
        other_owner = User.objects.create_user(username='iso_ui_other_owner', password='pass')
        other_project = Project.objects.create(name='Other UI Project', owner=other_owner)
        foreign_case = UiTestCase.objects.create(
            project=other_project,
            created_by=other_owner,
            name='Other UI Case',
            url='/other-ui/',
            steps=[],
        )
        initial_result_count = QaTestResult.objects.count()
        client.force_login(member)

        list_resp = client.get('/api/qa/ui-cases/')
        detail = client.get(f'/api/qa/ui-cases/{ui_case.id}/')
        linked_tasks = client.get(f'/api/qa/ui-cases/{ui_case.id}/linked-tasks/')
        with patch('qa_center.views_ui_test.execute_ui_case', return_value={'success': True, 'summary': {}}):
            run_resp = client.post(f'/api/qa/ui-cases/{ui_case.id}/run/')

        assert list_resp.status_code == 200
        returned_ids = [item['id'] for item in list_resp.data['results']]
        assert ui_case.id in returned_ids
        assert foreign_case.id not in returned_ids
        assert detail.status_code == 200
        assert linked_tasks.status_code == 200
        assert str(linked_task.id) in [str(item['id']) for item in linked_tasks.data]
        assert run_resp.status_code == 200
        assert run_resp.data['success'] is True
        assert QaTestResult.objects.count() == initial_result_count + 1

    def test_ui_run_screenshot_by_index_rejects_outsider(self, client, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            result, _, _ = self._create_ui_screenshot_fixture()
            client.force_login(self.outsider)

            resp = client.get(f'/api/qa/ui-run/{result.task_id}/screenshot/0/')

            assert resp.status_code == 403

    def test_ui_run_screenshot_by_index_member_can_access(self, client, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            result, _, _ = self._create_ui_screenshot_fixture()
            member = User.objects.create_user(username='iso_screenshot_member', password='pass')
            self.project.members.add(member)
            client.force_login(member)

            resp = client.get(f'/api/qa/ui-run/{result.task_id}/screenshot/0/')

            assert resp.status_code == 200
            assert b''.join(resp.streaming_content) == b'secret screenshot'

    def test_ui_run_screenshot_unknown_task_does_not_scan_global_temp_dir(self, client, tmp_path, settings):
        safe_root = tmp_path / '.playwright-temp'
        screenshot_dir = safe_root / 'foreign-run' / 'screenshots'
        screenshot_dir.mkdir(parents=True)
        (screenshot_dir / 'step_0.png').write_bytes(b'foreign temp screenshot')
        settings.BASE_DIR = tmp_path
        client.force_login(self.owner)

        resp = client.get('/api/qa/ui-run/unknown-task/screenshot/0/')

        assert resp.status_code == 404

    def test_ui_run_raw_screenshot_requires_task_binding(self, client, tmp_path, settings):
        safe_root = tmp_path / '.playwright-temp'
        screenshot_dir = safe_root / 'secret-run' / 'screenshots'
        screenshot_dir.mkdir(parents=True)
        screenshot_path = screenshot_dir / 'step_0.png'
        screenshot_path.write_bytes(b'secret temp screenshot')
        settings.BASE_DIR = tmp_path
        client.force_login(self.owner)

        resp = client.get(f'/api/qa/ui-run/screenshot/?path={screenshot_path}')

        assert resp.status_code == 400

    def test_ui_run_raw_screenshot_rejects_outsider_bound_task(self, client, tmp_path, settings):
        safe_root = tmp_path / '.playwright-temp'
        temp_dir = safe_root / 'secret-run'
        screenshot_dir = temp_dir / 'screenshots'
        screenshot_dir.mkdir(parents=True)
        screenshot_path = screenshot_dir / 'step_0.png'
        screenshot_path.write_bytes(b'secret temp screenshot')
        settings.BASE_DIR = tmp_path
        result, _, _ = self._create_ui_screenshot_fixture()
        result.temp_dir_path = str(temp_dir)
        result.save(update_fields=['temp_dir_path'])
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/ui-run/screenshot/?task_id={result.task_id}&path={screenshot_path}')

        assert resp.status_code == 403

    def test_test_screenshot_media_rejects_outsider_and_anonymous(self, client, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            _, _, screenshot = self._create_ui_screenshot_fixture()
            url = f'/media/{screenshot.image.name}'

            anonymous = client.get(url)
            client.force_login(self.outsider)
            outsider = client.get(url)

            assert anonymous.status_code in (401, 403)
            assert outsider.status_code == 403

    def test_test_screenshot_media_member_can_access(self, client, tmp_path):
        with override_settings(MEDIA_ROOT=tmp_path):
            _, _, screenshot = self._create_ui_screenshot_fixture()
            member = User.objects.create_user(username='iso_media_screenshot_member', password='pass')
            self.project.members.add(member)
            client.force_login(member)

            resp = client.get(f'/media/{screenshot.image.name}')

            assert resp.status_code == 200
            assert b''.join(resp.streaming_content) == b'secret screenshot'

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

    def _create_performance_case_fixture(self):
        perf_case = PerformanceTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret Performance Case',
            url='https://secret.example.com/perf',
            method='GET',
            headers={'Authorization': 'Bearer perf-secret'},
            body='secret body',
        )
        linked_task = Task.objects.create(
            column=self.column,
            title='Secret Linked Task',
            content='hidden task details',
            position=1,
        )
        perf_case.related_tasks.add(linked_task)
        running_result = QaTestResult.objects.create(
            project=self.project,
            test_type='performance',
            name='Secret Performance Run',
            status='running',
            executed_by=self.owner,
            started_at=timezone.now(),
            test_params={'test_case_id': perf_case.id},
            response_time_ms=123,
            throughput=45.6,
            error_rate=1.2,
        )
        return perf_case, linked_task, running_result

    def test_performance_case_list_rejects_outsider_project_filter(self, client):
        self._create_performance_case_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/performance-cases/?project={self.project.id}')

        assert resp.status_code == 403

    def test_performance_case_list_without_project_does_not_leak_foreign_cases(self, client):
        perf_case, _, _ = self._create_performance_case_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/performance-cases/')

        assert resp.status_code == 200
        items = resp.data['results']
        assert perf_case.id not in [item['id'] for item in items]
        assert perf_case.name not in [item['name'] for item in items]

    def test_performance_case_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/performance-cases/',
            data={
                'project': self.project.id,
                'name': 'Injected Performance Case',
                'url': 'https://example.com/load',
                'method': 'GET',
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not PerformanceTestCase.objects.filter(name='Injected Performance Case').exists()

    def test_performance_case_actions_reject_outsider_before_side_effects(self, client):
        perf_case, linked_task, running_result = self._create_performance_case_fixture()
        initial_result_count = QaTestResult.objects.count()
        client.force_login(self.outsider)

        detail = client.get(f'/api/qa/performance-cases/{perf_case.id}/')
        update = client.patch(
            f'/api/qa/performance-cases/{perf_case.id}/',
            data={'name': 'Tampered Performance Case'},
            content_type='application/json',
        )
        results = client.get(f'/api/qa/performance-cases/{perf_case.id}/results/')
        linked_tasks = client.get(f'/api/qa/performance-cases/{perf_case.id}/linked-tasks/')
        status_resp = client.get(
            f'/api/qa/performance-cases/{perf_case.id}/status/?execution_id={running_result.id}'
        )
        stop_resp = client.post(
            f'/api/qa/performance-cases/{perf_case.id}/stop/',
            data={'execution_id': running_result.id},
            content_type='application/json',
        )
        with patch('qa_center.views_performance.run_performance_test.delay') as delay:
            execute = client.post(f'/api/qa/performance-cases/{perf_case.id}/execute/')
        delete = client.delete(f'/api/qa/performance-cases/{perf_case.id}/')

        assert detail.status_code == 403
        assert update.status_code == 403
        assert results.status_code == 403
        assert linked_tasks.status_code == 403
        assert status_resp.status_code == 403
        assert stop_resp.status_code == 403
        assert execute.status_code == 403
        assert delete.status_code == 403
        delay.assert_not_called()
        perf_case.refresh_from_db()
        running_result.refresh_from_db()
        assert perf_case.name == 'Secret Performance Case'
        assert running_result.status == 'running'
        assert running_result.aborted is False
        assert QaTestResult.objects.count() == initial_result_count
        assert Task.objects.filter(id=linked_task.id).exists()

    def test_performance_case_member_can_access_project_case(self, client):
        perf_case, linked_task, running_result = self._create_performance_case_fixture()
        member = User.objects.create_user(username='iso_perf_member', password='pass')
        self.project.members.add(member)
        other_owner = User.objects.create_user(username='iso_perf_other_owner', password='pass')
        other_project = Project.objects.create(name='Other Performance Project', owner=other_owner)
        foreign_case = PerformanceTestCase.objects.create(
            project=other_project,
            created_by=other_owner,
            name='Other Performance Case',
            url='https://other.example.com/perf',
            method='GET',
        )
        client.force_login(member)

        list_resp = client.get('/api/qa/performance-cases/')
        detail = client.get(f'/api/qa/performance-cases/{perf_case.id}/')
        results = client.get(f'/api/qa/performance-cases/{perf_case.id}/results/')
        linked_tasks = client.get(f'/api/qa/performance-cases/{perf_case.id}/linked-tasks/')
        status_resp = client.get(
            f'/api/qa/performance-cases/{perf_case.id}/status/?execution_id={running_result.id}'
        )

        assert list_resp.status_code == 200
        returned_ids = [item['id'] for item in list_resp.data['results']]
        assert perf_case.id in returned_ids
        assert foreign_case.id not in returned_ids
        assert detail.status_code == 200
        assert results.status_code == 200
        assert linked_tasks.status_code == 200
        assert str(linked_task.id) in [str(item['id']) for item in linked_tasks.data]
        assert status_resp.status_code == 200
        assert status_resp.data['state'] == 'running'

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

    def _create_devops_dashboard_fixture(self):
        api_case = ApiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret DevOps API Case',
            url='/api/devops-secret/',
            method='GET',
            expected_status=200,
        )
        ui_case = UiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret DevOps UI Case',
            url='/devops-secret/',
            steps=[{'action': 'click', 'selector': '#secret'}],
        )
        passed_result = QaTestResult.objects.create(
            project=self.project,
            api_test_case=api_case,
            test_type='api',
            name='Secret DevOps Passed Result',
            status='passed',
            executed_by=self.owner,
            response_time_ms=45,
        )
        failed_result = QaTestResult.objects.create(
            project=self.project,
            ui_test_case=ui_case,
            test_type='ui',
            name='Secret DevOps Failed Result',
            status='failed',
            executed_by=self.owner,
        )
        return api_case, ui_case, passed_result, failed_result

    def test_devops_stats_rejects_outsider_project_filter(self, client):
        self._create_devops_dashboard_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/devops/stats/?project_id={self.project.id}')

        assert resp.status_code == 403

    def test_devops_stats_without_project_does_not_count_foreign_data(self, client):
        self._create_devops_dashboard_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/devops/stats/')

        assert resp.status_code == 200
        assert resp.data['overview']['total_cases'] == 0
        assert resp.data['overview']['api_cases'] == 0
        assert resp.data['overview']['ui_cases'] == 0
        assert resp.data['overview']['total_executions'] == 0
        assert resp.data['overview']['today_executions'] == 0
        assert resp.data['status_count']['passed'] == 0
        assert resp.data['status_count']['failed'] == 0
        assert resp.data['status_count']['error'] == 0
        assert all(day['total'] == 0 for day in resp.data['daily_trend'])

    def test_devops_recent_executions_rejects_outsider_project_filter(self, client):
        self._create_devops_dashboard_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/devops/recent-executions/?project_id={self.project.id}')

        assert resp.status_code == 403

    def test_devops_recent_executions_without_project_does_not_leak_foreign_results(self, client):
        _, _, passed_result, failed_result = self._create_devops_dashboard_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/devops/recent-executions/')

        assert resp.status_code == 200
        returned_ids = [item['id'] for item in resp.data]
        returned_names = [item['name'] for item in resp.data]
        assert passed_result.id not in returned_ids
        assert failed_result.id not in returned_ids
        assert passed_result.name not in returned_names
        assert failed_result.name not in returned_names

    def test_devops_dashboard_member_sees_only_accessible_project_data(self, client):
        api_case, _, passed_result, _ = self._create_devops_dashboard_fixture()
        member = User.objects.create_user(username='iso_devops_member', password='pass')
        self.project.members.add(member)
        other_owner = User.objects.create_user(username='iso_devops_other_owner', password='pass')
        other_project = Project.objects.create(name='Other DevOps Project', owner=other_owner)
        other_case = ApiTestCase.objects.create(
            project=other_project,
            created_by=other_owner,
            name='Other DevOps API Case',
            url='/api/other-devops/',
            method='GET',
            expected_status=200,
        )
        foreign_result = QaTestResult.objects.create(
            project=other_project,
            api_test_case=other_case,
            test_type='api',
            name='Other DevOps Result',
            status='failed',
            executed_by=other_owner,
        )
        client.force_login(member)

        stats = client.get(f'/api/qa/devops/stats/?project_id={self.project.id}')
        recent = client.get(f'/api/qa/devops/recent-executions/?project_id={self.project.id}')

        assert stats.status_code == 200
        assert stats.data['overview']['total_cases'] == 2
        assert stats.data['overview']['api_cases'] == 1
        assert stats.data['overview']['ui_cases'] == 1
        assert stats.data['overview']['total_executions'] == 2
        assert stats.data['status_count']['passed'] == 1
        assert stats.data['status_count']['failed'] == 1
        assert recent.status_code == 200
        returned_ids = [item['id'] for item in recent.data]
        assert passed_result.id in returned_ids
        assert foreign_result.id not in returned_ids
        assert all(str(item['project']) == str(self.project.id) for item in recent.data)
        assert api_case.project_id == self.project.id

    def test_devops_quality_report_rejects_outsider_project(self, client):
        self._create_devops_dashboard_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/devops/quality-report/?project_id={self.project.id}')

        assert resp.status_code == 403

    def test_devops_quality_report_member_can_access_project_report(self, client):
        self._create_devops_dashboard_fixture()
        member = User.objects.create_user(username='iso_quality_member', password='pass')
        self.project.members.add(member)
        Task.objects.create(
            column=self.column,
            title='Quality Report Task',
            content='visible only to project members',
            position=2,
        )
        other_owner = User.objects.create_user(username='iso_quality_other_owner', password='pass')
        other_project = Project.objects.create(name='Other Quality Project', owner=other_owner)
        other_column = Column.objects.create(project=other_project, title='Todo', position=1)
        Task.objects.create(column=other_column, title='Other Quality Task', position=1)
        Bug.objects.create(project=other_project, title='Other Quality Bug', reporter=other_owner)
        client.force_login(member)

        resp = client.get(f'/api/qa/devops/quality-report/?project_id={self.project.id}')

        assert resp.status_code == 200
        assert resp.data['project_id'] == str(self.project.id)
        assert resp.data['summary']['total_tasks'] == 1
        assert resp.data['summary']['bug_count'] == 0

    def _create_devops_task_fixture(self):
        task = QaTestTask.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret DevOps Task',
            test_type='api',
            trigger_type='manual',
            test_config={'api_cases': [], 'ui_cases': []},
            status='idle',
        )
        history = QaTestResult.objects.create(
            project=self.project,
            test_type='api',
            name='Secret DevOps Task - 执行 #1',
            source='devops',
            status='passed',
            executed_by=self.owner,
            test_params={'task': 'history'},
        )
        return task, history

    def test_devops_task_list_without_project_does_not_leak_foreign_tasks(self, client):
        task, _ = self._create_devops_task_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/devops/tasks/')

        assert resp.status_code == 200
        assert task.id not in [item['id'] for item in resp.data]
        assert task.name not in [item['name'] for item in resp.data]

    def test_devops_task_detail_rejects_outsider(self, client):
        task, _ = self._create_devops_task_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/devops/tasks/{task.id}/')

        assert resp.status_code == 403

    def test_devops_task_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/devops/tasks/',
            data={
                'project': self.project.id,
                'name': 'Injected DevOps Task',
                'test_type': 'api',
                'trigger_type': 'manual',
                'test_config': {'api_cases': [], 'ui_cases': []},
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not QaTestTask.objects.filter(name='Injected DevOps Task').exists()

    def test_devops_task_actions_reject_outsider_before_side_effects(self, client):
        task, history = self._create_devops_task_fixture()
        initial_result_count = QaTestResult.objects.count()
        client.force_login(self.outsider)

        status_resp = client.get(f'/api/qa/devops/tasks/{task.id}/status/')
        history_resp = client.get(f'/api/qa/devops/tasks/{task.id}/history/')
        update_resp = client.put(
            f'/api/qa/devops/tasks/{task.id}/',
            data={'name': 'Tampered DevOps Task'},
            content_type='application/json',
        )
        with patch('qa_center.views_devops.threading.Thread') as thread_cls:
            execute_resp = client.post(f'/api/qa/devops/tasks/{task.id}/execute/')
        delete_resp = client.delete(f'/api/qa/devops/tasks/{task.id}/')

        assert status_resp.status_code == 403
        assert history_resp.status_code == 403
        assert update_resp.status_code == 403
        assert execute_resp.status_code == 403
        assert delete_resp.status_code == 403
        thread_cls.assert_not_called()
        task.refresh_from_db()
        assert task.name == 'Secret DevOps Task'
        assert task.status == 'idle'
        assert task.execution_count == 0
        assert QaTestResult.objects.count() == initial_result_count
        assert QaTestResult.objects.filter(id=history.id).exists()

    def test_devops_task_member_can_access_project_task(self, client):
        task, history = self._create_devops_task_fixture()
        member = User.objects.create_user(username='iso_devops_task_member', password='pass')
        self.project.members.add(member)
        other_owner = User.objects.create_user(username='iso_devops_task_other_owner', password='pass')
        other_project = Project.objects.create(name='Other DevOps Task Project', owner=other_owner)
        foreign_task = QaTestTask.objects.create(
            project=other_project,
            created_by=other_owner,
            name='Other DevOps Task',
            test_type='api',
            trigger_type='manual',
            test_config={},
        )
        client.force_login(member)

        list_resp = client.get('/api/qa/devops/tasks/')
        detail_resp = client.get(f'/api/qa/devops/tasks/{task.id}/')
        status_resp = client.get(f'/api/qa/devops/tasks/{task.id}/status/')
        history_resp = client.get(f'/api/qa/devops/tasks/{task.id}/history/')

        assert list_resp.status_code == 200
        returned_ids = [item['id'] for item in list_resp.data]
        assert task.id in returned_ids
        assert foreign_task.id not in returned_ids
        assert detail_resp.status_code == 200
        assert status_resp.status_code == 200
        assert history_resp.status_code == 200
        assert history.id in [item['id'] for item in history_resp.data]

    def _create_devops_task_case_config_fixture(self):
        member = User.objects.create_user(username='iso_devops_task_case_member', password='pass')
        self.project.members.add(member)
        api_case = ApiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Project DevOps API Case',
            url='/api/project-devops/',
            method='GET',
            expected_status=200,
        )
        ui_case = UiTestCase.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Project DevOps UI Case',
            url='/project-devops/',
            steps=[{'action': 'click', 'selector': '#project'}],
        )
        other_owner = User.objects.create_user(username='iso_devops_task_case_other_owner', password='pass')
        other_project = Project.objects.create(name='Other DevOps Case Project', owner=other_owner)
        foreign_api_case = ApiTestCase.objects.create(
            project=other_project,
            created_by=other_owner,
            name='Foreign DevOps API Case',
            url='/api/foreign-devops/',
            method='GET',
            expected_status=200,
        )
        foreign_ui_case = UiTestCase.objects.create(
            project=other_project,
            created_by=other_owner,
            name='Foreign DevOps UI Case',
            url='/foreign-devops/',
            steps=[{'action': 'click', 'selector': '#foreign'}],
        )
        return member, api_case, ui_case, foreign_api_case, foreign_ui_case

    def test_devops_task_create_rejects_foreign_api_ui_cases(self, client):
        member, _, _, foreign_api_case, foreign_ui_case = self._create_devops_task_case_config_fixture()
        client.force_login(member)

        resp = client.post(
            '/api/qa/devops/tasks/',
            data={
                'project': self.project.id,
                'name': 'Poisoned DevOps Task',
                'test_type': 'api',
                'trigger_type': 'manual',
                'test_config': {
                    'api_cases': [foreign_api_case.id],
                    'ui_cases': [foreign_ui_case.id],
                },
            },
            content_type='application/json',
        )

        assert resp.status_code == 400
        assert not QaTestTask.objects.filter(name='Poisoned DevOps Task').exists()

    def test_devops_task_update_rejects_foreign_api_ui_cases_and_preserves_config(self, client):
        member, api_case, ui_case, foreign_api_case, foreign_ui_case = self._create_devops_task_case_config_fixture()
        original_config = {'api_cases': [api_case.id], 'ui_cases': [ui_case.id]}
        task = QaTestTask.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Config Protected DevOps Task',
            test_type='api',
            trigger_type='manual',
            test_config=original_config,
            status='idle',
        )
        client.force_login(member)

        resp = client.put(
            f'/api/qa/devops/tasks/{task.id}/',
            data={
                'test_config': {
                    'api_cases': [foreign_api_case.id],
                    'ui_cases': [foreign_ui_case.id],
                },
            },
            content_type='application/json',
        )

        assert resp.status_code == 400
        task.refresh_from_db()
        assert task.test_config == original_config

    def test_devops_task_execute_rejects_poisoned_foreign_case_config_before_side_effects(self, client):
        member, _, _, foreign_api_case, foreign_ui_case = self._create_devops_task_case_config_fixture()
        task = QaTestTask.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Preexisting Poisoned DevOps Task',
            test_type='api',
            trigger_type='manual',
            test_config={
                'api_cases': [foreign_api_case.id],
                'ui_cases': [foreign_ui_case.id],
            },
            status='idle',
        )
        initial_result_count = QaTestResult.objects.count()
        client.force_login(member)

        with patch('qa_center.views_devops.threading.Thread') as thread_cls:
            resp = client.post(f'/api/qa/devops/tasks/{task.id}/execute/')

        assert resp.status_code == 400
        thread_cls.assert_not_called()
        task.refresh_from_db()
        assert task.status == 'idle'
        assert task.execution_count == 0
        assert QaTestResult.objects.count() == initial_result_count

    def _create_cicd_pipeline_fixture(self):
        config = CiCdConfig.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Secret CI Config',
            ci_type='jenkins',
            webhook_url='https://ci.example.com/hook',
            api_token='secret-token',
            branch='main',
            headers={'Authorization': 'Bearer secret'},
            test_suite_ids=[],
        )
        run = PipelineRun.objects.create(
            project=self.project,
            cicd_config=config,
            status='failed',
            branch='main',
            commit_sha='abc123',
            log_output='secret pipeline log',
            test_results_summary={'total': 1, 'failed': 1},
        )
        return config, run

    def test_cicd_config_list_rejects_outsider_project_filter(self, client):
        self._create_cicd_pipeline_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/devops/cicd-config/?project_id={self.project.id}')

        assert resp.status_code == 403

    def test_cicd_config_list_without_project_does_not_leak_foreign_configs(self, client):
        config, _ = self._create_cicd_pipeline_fixture()
        client.force_login(self.outsider)

        resp = client.get('/api/qa/devops/cicd-config/')

        assert resp.status_code == 200
        assert config.id not in [item['id'] for item in resp.data]
        assert config.name not in [item['name'] for item in resp.data]

    def test_cicd_config_create_rejects_outsider_project(self, client):
        client.force_login(self.outsider)

        resp = client.post(
            '/api/qa/devops/cicd-config/',
            data={
                'project_id': self.project.id,
                'name': 'Injected CI Config',
                'type': 'jenkins',
                'webhook_url': 'https://ci.example.com/injected',
                'api_token': 'injected-token',
                'headers': {'Authorization': 'Bearer injected'},
            },
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert not CiCdConfig.objects.filter(name='Injected CI Config').exists()

    def test_cicd_config_detail_update_delete_reject_outsider(self, client):
        config, _ = self._create_cicd_pipeline_fixture()
        client.force_login(self.outsider)

        detail = client.get(f'/api/qa/devops/cicd-config/{config.id}/')
        update = client.put(
            f'/api/qa/devops/cicd-config/{config.id}/',
            data={
                'name': 'Tampered CI Config',
                'api_token': 'tampered-token',
                'headers': {'Authorization': 'Bearer tampered'},
            },
            content_type='application/json',
        )
        delete = client.delete(f'/api/qa/devops/cicd-config/{config.id}/')

        assert detail.status_code == 403
        assert update.status_code == 403
        assert delete.status_code == 403
        config.refresh_from_db()
        assert config.name == 'Secret CI Config'
        assert config.api_token == 'secret-token'
        assert config.headers == {'Authorization': 'Bearer secret'}
        assert config.is_active is True

    def test_pipeline_runs_reject_outsider_project_and_config_filters(self, client):
        config, _ = self._create_cicd_pipeline_fixture()
        client.force_login(self.outsider)

        by_project = client.get(f'/api/qa/devops/pipeline-runs/?project_id={self.project.id}')
        by_config = client.get(f'/api/qa/devops/pipeline-runs/?cicd_config_id={config.id}')

        assert by_project.status_code == 403
        assert by_config.status_code == 403

    def test_pipeline_run_detail_rejects_outsider(self, client):
        _, run = self._create_cicd_pipeline_fixture()
        client.force_login(self.outsider)

        resp = client.get(f'/api/qa/devops/pipeline-runs/{run.id}/')

        assert resp.status_code == 403

    def test_pipeline_trigger_rejects_outsider_before_side_effects(self, client):
        config, _ = self._create_cicd_pipeline_fixture()
        initial_run_count = PipelineRun.objects.count()
        client.force_login(self.outsider)

        with patch('qa_center.views_devops.threading.Thread') as thread_cls:
            resp = client.post(f'/api/qa/devops/cicd-config/{config.id}/trigger/')

        assert resp.status_code == 403
        thread_cls.assert_not_called()
        assert PipelineRun.objects.count() == initial_run_count

    def test_cicd_webhook_rejects_config_without_api_token_before_side_effects(self, client):
        config = CiCdConfig.objects.create(
            project=self.project,
            created_by=self.owner,
            name='Tokenless CI Config',
            ci_type='jenkins',
            webhook_url='https://ci.example.com/tokenless',
            api_token='',
            branch='main',
        )
        initial_run_count = PipelineRun.objects.count()

        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'passed', 'branch': 'main', 'log_output': 'injected log'},
            content_type='application/json',
        )

        assert resp.status_code == 403
        assert PipelineRun.objects.count() == initial_run_count

    def test_cicd_webhook_rejects_missing_or_wrong_token_before_side_effects(self, client):
        config, _ = self._create_cicd_pipeline_fixture()
        initial_run_count = PipelineRun.objects.count()

        missing = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'passed', 'branch': 'main', 'log_output': 'missing token log'},
            content_type='application/json',
        )
        wrong = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={'status': 'failed', 'branch': 'main', 'log_output': 'wrong token log'},
            content_type='application/json',
            HTTP_X_CI_TOKEN='wrong-token',
        )

        assert missing.status_code == 403
        assert wrong.status_code == 403
        assert PipelineRun.objects.count() == initial_run_count

    def test_cicd_webhook_accepts_valid_x_ci_token(self, client):
        config, _ = self._create_cicd_pipeline_fixture()
        initial_run_count = PipelineRun.objects.count()

        resp = client.post(
            f'/api/qa/devops/cicd-config/{config.id}/webhook/',
            data={
                'status': 'passed',
                'branch': 'main',
                'commit_sha': 'def456',
                'log_output': 'valid webhook log',
                'test_results_summary': {'total': 2, 'passed': 2},
            },
            content_type='application/json',
            HTTP_X_CI_TOKEN='secret-token',
        )

        assert resp.status_code == 201
        assert PipelineRun.objects.count() == initial_run_count + 1
        new_run = PipelineRun.objects.get(id=resp.data['run_id'])
        assert new_run.project_id == config.project_id
        assert new_run.cicd_config_id == config.id
        assert new_run.commit_sha == 'def456'

    def test_cicd_pipeline_member_can_access_project_resources(self, client):
        config, run = self._create_cicd_pipeline_fixture()
        member = User.objects.create_user(username='iso_cicd_member', password='pass')
        self.project.members.add(member)
        other_owner = User.objects.create_user(username='iso_cicd_other_owner', password='pass')
        other_project = Project.objects.create(name='Other CI Project', owner=other_owner)
        foreign_config = CiCdConfig.objects.create(
            project=other_project,
            created_by=other_owner,
            name='Other CI Config',
            ci_type='gitlab',
            webhook_url='https://ci.example.com/other',
            branch='main',
        )
        foreign_run = PipelineRun.objects.create(
            project=other_project,
            cicd_config=foreign_config,
            status='passed',
            branch='main',
        )
        client.force_login(member)

        config_list = client.get(f'/api/qa/devops/cicd-config/?project_id={self.project.id}')
        config_detail = client.get(f'/api/qa/devops/cicd-config/{config.id}/')
        runs_by_project = client.get(f'/api/qa/devops/pipeline-runs/?project_id={self.project.id}')
        runs_by_config = client.get(f'/api/qa/devops/pipeline-runs/?cicd_config_id={config.id}')
        run_detail = client.get(f'/api/qa/devops/pipeline-runs/{run.id}/')
        with patch('qa_center.views_devops.threading.Thread') as thread_cls:
            trigger = client.post(f'/api/qa/devops/cicd-config/{config.id}/trigger/')

        assert config_list.status_code == 200
        listed_config_ids = [item['id'] for item in config_list.data]
        assert config.id in listed_config_ids
        assert foreign_config.id not in listed_config_ids
        assert config_detail.status_code == 200
        assert runs_by_project.status_code == 200
        project_run_ids = [item['id'] for item in runs_by_project.data['results']]
        assert run.id in project_run_ids
        assert foreign_run.id not in project_run_ids
        assert runs_by_config.status_code == 200
        config_run_ids = [item['id'] for item in runs_by_config.data['results']]
        assert run.id in config_run_ids
        assert foreign_run.id not in config_run_ids
        assert run_detail.status_code == 200
        assert trigger.status_code == 201
        thread_cls.return_value.start.assert_called_once()
        new_run_id = trigger.data['run_id']
        new_run = PipelineRun.objects.get(id=new_run_id)
        assert new_run.project_id == self.project.id
