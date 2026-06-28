import pytest
from django.contrib.auth.models import User
from unittest.mock import patch

from bug_tracker.models import Bug
from qa_center.models import (
    ApiAutoTestCase,
    ApiAutoTestSuite,
    ApiTestCase,
    TestRun as QaTestRun,
    TestRunPlan as QaTestRunPlan,
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
