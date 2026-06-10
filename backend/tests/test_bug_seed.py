"""Bug seed 演示数据 测试"""
import pytest
from django.contrib.auth.models import User
from bug_tracker.models import Bug
from bug_tracker.seed import seed_demo_bugs


@pytest.mark.django_db
class TestSeedDemoBugs:
    def test_first_call_creates_eight(self, test_project):
        added = seed_demo_bugs(test_project)
        assert added == 8
        assert Bug.objects.filter(project=test_project, title__startswith='[DEMO]').count() == 8

    def test_idempotent(self, test_project):
        seed_demo_bugs(test_project)
        added2 = seed_demo_bugs(test_project)
        assert added2 == 0
        assert Bug.objects.filter(project=test_project, title__startswith='[DEMO]').count() == 8

    def test_covers_status_and_severity(self, test_project):
        seed_demo_bugs(test_project)
        statuses = set(Bug.objects.filter(project=test_project, title__startswith='[DEMO]').values_list('status', flat=True))
        assert {'new', 'confirmed', 'fixing', 'closed', 'reopened'}.issubset(statuses)
        severities = set(Bug.objects.filter(project=test_project, title__startswith='[DEMO]').values_list('severity', flat=True))
        assert {'blocker', 'critical', 'major', 'minor'}.issubset(severities)


@pytest.mark.django_db
class TestSeedDemoAPI:
    def test_requires_owner(self, client, test_project, db):
        other = User.objects.create_user('otheruser', password='x')
        client.force_login(other)
        resp = client.post(f'/api/bugs/seed-demo/?project_id={test_project.id}')
        assert resp.status_code == 403

    def test_owner_creates_bugs(self, auth_client, test_project):
        resp = auth_client.post(f'/api/bugs/seed-demo/?project_id={test_project.id}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['added'] == 8
        assert Bug.objects.filter(project=test_project, title__startswith='[DEMO]').count() == 8

    def test_missing_project_id_returns_400(self, auth_client):
        resp = auth_client.post('/api/bugs/seed-demo/')
        assert resp.status_code == 400

    def test_nonexistent_project_returns_404(self, auth_client):
        resp = auth_client.post('/api/bugs/seed-demo/?project_id=00000000-0000-0000-0000-000000000000')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestSeedBugsCommand:
    def test_command_no_project_silent(self, db, capsys):
        from django.core.management import call_command
        call_command('seed_bugs_demo')
        captured = capsys.readouterr()
        # 无项目时输出 WARNING，不抛异常
        assert '未找到目标项目' in captured.out or captured.out == ''

    def test_command_with_project_creates(self, test_project, capsys):
        from django.core.management import call_command
        call_command('seed_bugs_demo', '--project', str(test_project.id))
        assert Bug.objects.filter(project=test_project, title__startswith='[DEMO]').count() == 8
