from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from haystack.query import SearchQuerySet
from .models import Task
from .views.mixins import ProjectAccessMixin

class TaskSearchView(ProjectAccessMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.GET.get('q', '')
        project_id = request.GET.get('project_id') or request.GET.get('project')
        if not query:
            return Response({'tasks': []})

        if not project_id:
            return Response(
                {'detail': '缺少 project 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        project, error_response = self.get_project_with_access(request, project_id)
        if error_response:
            return error_response

        results = SearchQuerySet().filter(project_id=project_id).auto_query(query).models(Task)

        tasks_data = []
        for result in results:
            if result.object:
                tasks_data.append({
                    'id': str(result.object.id),
                    'title': result.object.title,
                    'content': result.object.content
                })

        return Response({'tasks': tasks_data})
