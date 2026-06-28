import pytest
from django.contrib.auth.models import User

from bug_tracker.models import Bug
from qa_center.models import ApiAutoTestSuite, ApiTestCase, TestRun
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
        assert TestRun.objects.count() == 0

    def test_qa_test_run_detail_rejects_outsider(self, client):
        run = TestRun.objects.create(
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
