"""任务动态日志视图"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination
from ..models import Task, TaskActivityLog
from ..serializers import TaskActivityLogSerializer
from .mixins import ProjectAccessMixin


class TaskActivityListView(ProjectAccessMixin, APIView):
    """GET /api/tasks/{task_id}/activities/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, task_id):
        try:
            task = Task.objects.select_related('column__project').get(pk=task_id)
        except Task.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        project, error = self.get_project_with_access(request, str(task.column.project.id))
        if error:
            return error

        queryset = TaskActivityLog.objects.filter(task=task)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = TaskActivityLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = TaskActivityLogSerializer(queryset, many=True)
        return Response(serializer.data)
