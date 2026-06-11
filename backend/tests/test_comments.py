"""任务评论 CRUD + 权限测试"""
import pytest
from django.contrib.auth.models import User
from room.models import Project, Column, Task, TaskComment


@pytest.mark.django_db
class TestCommentAPI:
    def setup_method(self):
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')
        self.project = Project.objects.create(name='Test', owner=self.owner)
        self.project.members.add(self.member)
        self.col = Column.objects.create(project=self.project, title='To Do', position=1)
        self.task = Task.objects.create(column=self.col, title='Test Task')

    def _comment_url(self, task_id=None):
        tid = task_id or self.task.id
        return f'/api/tasks/{tid}/comments/'

    def test_create_comment_as_member(self, client):
        client.force_login(self.member)
        resp = client.post(self._comment_url(), {'content': '测试评论'}, content_type='application/json')
        assert resp.status_code == 201
        assert TaskComment.objects.filter(task=self.task).count() == 1

    def test_create_comment_as_outsider_rejected(self, client):
        client.force_login(self.outsider)
        resp = client.post(self._comment_url(), {'content': 'hack'}, content_type='application/json')
        assert resp.status_code == 403

    def test_list_comments(self, client):
        client.force_login(self.member)
        TaskComment.objects.create(task=self.task, author=self.member, content='C1')
        TaskComment.objects.create(task=self.task, author=self.owner, content='C2')
        resp = client.get(self._comment_url())
        assert resp.status_code == 200
        assert resp.data['count'] == 2

    def test_edit_own_comment(self, client):
        client.force_login(self.member)
        c = TaskComment.objects.create(task=self.task, author=self.member, content='Old')
        resp = client.patch(
            f'/api/tasks/{self.task.id}/comments/{c.id}/',
            {'content': 'New'}, content_type='application/json'
        )
        assert resp.status_code == 200
        c.refresh_from_db()
        assert c.content == 'New'

    def test_cannot_edit_others_comment(self, client):
        client.force_login(self.member)
        c = TaskComment.objects.create(task=self.task, author=self.owner, content='Owner')
        resp = client.patch(
            f'/api/tasks/{self.task.id}/comments/{c.id}/',
            {'content': 'Hijack'}, content_type='application/json'
        )
        assert resp.status_code == 403

    def test_delete_own_comment(self, client):
        client.force_login(self.member)
        c = TaskComment.objects.create(task=self.task, author=self.member, content='Del')
        resp = client.delete(f'/api/tasks/{self.task.id}/comments/{c.id}/')
        assert resp.status_code == 204
        assert not TaskComment.objects.filter(pk=c.id).exists()

    def test_owner_can_delete_others_comment(self, client):
        client.force_login(self.owner)
        c = TaskComment.objects.create(task=self.task, author=self.member, content='ByMember')
        resp = client.delete(f'/api/tasks/{self.task.id}/comments/{c.id}/')
        assert resp.status_code == 204

    def test_empty_content_rejected(self, client):
        client.force_login(self.member)
        resp = client.patch(
            f'/api/tasks/{self.task.id}/comments/999/',
            {'content': ''}, content_type='application/json'
        )
        assert resp.status_code == 404  # comment 999 doesn't exist


@pytest.mark.django_db
class TestActivityLog:
    def setup_method(self):
        self.user = User.objects.create_user(username='dev', password='pass')
        self.project = Project.objects.create(name='P', owner=self.user)
        self.c1 = Column.objects.create(project=self.project, title='Todo', position=1)
        self.c2 = Column.objects.create(project=self.project, title='Done', position=2)

    def test_task_creation_creates_activity(self, client):
        client.force_login(self.user)
        resp = client.post('/api/tasks/', {
            'title': 'New Task', 'column': str(self.c1.id), 'position': 0
        }, content_type='application/json')
        assert resp.status_code == 201
        from room.models import TaskActivityLog
        assert TaskActivityLog.objects.filter(action='created').exists()

    def test_task_move_creates_activity(self, client):
        client.force_login(self.user)
        task = Task.objects.create(column=self.c1, title='Move Me')
        resp = client.patch(f'/api/tasks/{task.id}/', {
            'column': str(self.c2.id)
        }, content_type='application/json')
        assert resp.status_code == 200
        from room.models import TaskActivityLog
        assert TaskActivityLog.objects.filter(action='moved', field_name='column').exists()

    def test_activity_list_requires_auth(self, client):
        task = Task.objects.create(column=self.c1, title='T')
        resp = client.get(f'/api/tasks/{task.id}/activities/')
        assert resp.status_code == 403
