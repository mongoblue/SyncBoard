import pytest
from django.contrib.auth.models import User
from room.models import AIConversation, Project


@pytest.mark.django_db
class TestExistingAiPermissionBoundaries:
    def setup_method(self):
        self.owner = User.objects.create_user(username='agent_owner', password='pass')
        self.outsider = User.objects.create_user(username='agent_outsider', password='pass')
        self.project = Project.objects.create(name='Agent Project', owner=self.owner)

    def test_outsider_cannot_create_ai_conversation_for_project(self, client):
        client.force_login(self.outsider)
        response = client.post('/api/ai/conversations/', {
            'project': str(self.project.id),
            'title': 'Outsider conversation',
        }, content_type='application/json')
        assert response.status_code == 403
        assert AIConversation.objects.count() == 0

    def test_owner_can_create_ai_conversation_for_project(self, client):
        client.force_login(self.owner)
        response = client.post('/api/ai/conversations/', {
            'project': str(self.project.id),
            'title': 'Owner conversation',
        }, content_type='application/json')
        assert response.status_code == 201
        assert AIConversation.objects.filter(user=self.owner, project=self.project).exists()
