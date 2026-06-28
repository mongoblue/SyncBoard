"""权限边界测试 — 越权访问应返回 403"""
import pytest
from django.contrib.auth.models import User
from room.models import Project, Column, Task


@pytest.mark.django_db
class TestProjectMemberGate:
    def setup_method(self):
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.member = User.objects.create_user(username='member', password='pass')
        self.outsider = User.objects.create_user(username='outsider', password='pass')
        self.project = Project.objects.create(name='P', owner=self.owner)
        self.project.members.add(self.member)
        self.col = Column.objects.create(project=self.project, title='To Do', position=1)
        self.task = Task.objects.create(column=self.col, title='Secret')

    def test_outsider_cannot_list_tasks(self, client):
        client.force_login(self.outsider)
        resp = client.get(f'/api/tasks/?project={self.project.id}')
        assert resp.status_code == 403

    def test_outsider_cannot_create_task(self, client):
        client.force_login(self.outsider)
        resp = client.post('/api/tasks/', {
            'title': 'Hack', 'column': str(self.col.id)
        }, content_type='application/json')
        assert resp.status_code == 403

    def test_outsider_cannot_view_task(self, client):
        client.force_login(self.outsider)
        resp = client.get(f'/api/tasks/{self.task.id}/')
        assert resp.status_code == 403

    def test_member_can_access(self, client):
        client.force_login(self.member)
        resp = client.get(f'/api/tasks/?project={self.project.id}')
        assert resp.status_code == 200

    def test_member_can_view_task_detail(self, client):
        client.force_login(self.member)
        resp = client.get(f'/api/tasks/{self.task.id}/')
        assert resp.status_code == 200

    def test_outsider_cannot_access_tags(self, client):
        client.force_login(self.outsider)
        resp = client.get(f'/api/tags/?project={self.project.id}')
        assert resp.status_code == 403

    def test_outsider_cannot_search(self, client):
        client.force_login(self.outsider)
        resp = client.get(f'/api/tasks/search/?q=test&project={self.project.id}')
        assert resp.status_code == 403

    def test_outsider_cannot_search_with_project_id_param(self, client):
        client.force_login(self.outsider)
        resp = client.get(f'/api/tasks/search/?q=Secret&project_id={self.project.id}')
        assert resp.status_code == 403

    def test_search_requires_project_scope(self, client):
        client.force_login(self.member)
        resp = client.get('/api/tasks/search/?q=Secret')
        assert resp.status_code == 400

    def test_outsider_cannot_create_column_in_project(self, client):
        client.force_login(self.outsider)
        resp = client.post('/api/columns/', {
            'project': str(self.project.id),
            'title': 'Injected',
            'position': 9,
        }, content_type='application/json')
        assert resp.status_code == 403
        assert not Column.objects.filter(project=self.project, title='Injected').exists()

    def test_column_project_cannot_be_changed(self, client):
        other = Project.objects.create(name='Other', owner=self.member)
        client.force_login(self.owner)
        resp = client.patch(f'/api/columns/{self.col.id}/', {
            'project': str(other.id),
        }, content_type='application/json')
        assert resp.status_code == 400
        self.col.refresh_from_db()
        assert self.col.project_id == self.project.id

    def test_task_cannot_move_to_column_from_other_project(self, client):
        other = Project.objects.create(name='Other Move', owner=self.owner)
        other_col = Column.objects.create(project=other, title='Other', position=1)
        client.force_login(self.owner)
        resp = client.patch(f'/api/tasks/{self.task.id}/', {
            'column': str(other_col.id),
        }, content_type='application/json')
        assert resp.status_code == 400
        self.task.refresh_from_db()
        assert self.task.column_id == self.col.id

    def test_task_create_rejects_tag_from_other_project(self, client):
        from room.models import Tag
        other = Project.objects.create(name='Other Tag', owner=self.member)
        other_tag = Tag.objects.create(project=other, name='Foreign', color='#ff0000')
        client.force_login(self.owner)
        resp = client.post('/api/tasks/', {
            'title': 'With foreign tag',
            'column': str(self.col.id),
            'tags': [other_tag.id],
        }, content_type='application/json')
        assert resp.status_code == 400
        assert not Task.objects.filter(title='With foreign tag').exists()

    def test_task_patch_rejects_tag_from_other_project(self, client):
        from room.models import Tag
        other = Project.objects.create(name='Other Patch Tag', owner=self.member)
        other_tag = Tag.objects.create(project=other, name='Foreign', color='#00ff00')
        client.force_login(self.owner)
        resp = client.patch(f'/api/tasks/{self.task.id}/', {
            'tags': [other_tag.id],
        }, content_type='application/json')
        assert resp.status_code == 400
        self.task.refresh_from_db()
        assert not self.task.tags.filter(id=other_tag.id).exists()

    def test_task_create_rejects_outsider_assignee(self, client):
        client.force_login(self.owner)
        resp = client.post('/api/tasks/', {
            'title': 'Bad assignee',
            'column': str(self.col.id),
            'assignee': self.outsider.id,
        }, content_type='application/json')
        assert resp.status_code == 400
        assert not Task.objects.filter(title='Bad assignee').exists()

    def test_batch_delete_rejects_missing_id_without_deleting_valid_task(self, client):
        client.force_login(self.owner)
        missing_id = '00000000-0000-0000-0000-000000000000'
        resp = client.post('/api/tasks/batch-delete/', {
            'task_ids': [str(self.task.id), missing_id],
        }, content_type='application/json')
        assert resp.status_code == 400
        assert Task.objects.filter(id=self.task.id).exists()

    def test_batch_delete_rejects_mixed_project_ids_without_deleting_any(self, client):
        other = Project.objects.create(name='Other Batch', owner=self.owner)
        other_col = Column.objects.create(project=other, title='Other', position=1)
        other_task = Task.objects.create(column=other_col, title='Other Secret')
        client.force_login(self.owner)
        resp = client.post('/api/tasks/batch-delete/', {
            'task_ids': [str(self.task.id), str(other_task.id)],
        }, content_type='application/json')
        assert resp.status_code == 400
        assert Task.objects.filter(id=self.task.id).exists()
        assert Task.objects.filter(id=other_task.id).exists()


@pytest.mark.django_db
class TestAiMemberGate:
    def setup_method(self):
        self.owner = User.objects.create_user(username='ai_owner', password='pass')
        self.outsider = User.objects.create_user(username='ai_outsider', password='pass')
        self.project = Project.objects.create(name='AI Project', owner=self.owner)

    def test_outsider_cannot_chat(self, client):
        client.force_login(self.outsider)
        resp = client.post('/api/ai/chat/', {
            'project_id': str(self.project.id),
            'question': '项目进度如何？'
        }, content_type='application/json')
        assert resp.status_code == 403

    def test_outsider_cannot_analyze_health(self, client):
        client.force_login(self.outsider)
        resp = client.post('/api/ai/analyze/health/', {
            'project_id': str(self.project.id)
        }, content_type='application/json')
        assert resp.status_code == 403

    def test_owner_can_chat(self, client):
        client.force_login(self.owner)
        resp = client.post('/api/ai/chat/', {
            'project_id': str(self.project.id),
            'question': '进度'
        }, content_type='application/json')
        assert resp.status_code == 200
