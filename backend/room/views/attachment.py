"""任务附件视图"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from ..models import Task, TaskAttachment
from ..serializers import TaskAttachmentSerializer
from .mixins import ProjectAccessMixin
import os


class TaskAttachmentListView(ProjectAccessMixin, APIView):
    """GET /api/tasks/{task_id}/attachments/  |  POST"""

    permission_classes = [permissions.IsAuthenticated]

    def _get_task(self, task_id):
        try:
            return Task.objects.select_related('column__project').get(pk=task_id)
        except Task.DoesNotExist:
            return None

    def get(self, request, task_id):
        task = self._get_task(task_id)
        if not task:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        project, error = self.get_project_with_access(request, str(task.column.project.id))
        if error:
            return error
        queryset = TaskAttachment.objects.filter(task=task)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = TaskAttachmentSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = TaskAttachmentSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request, task_id):
        task = self._get_task(task_id)
        if not task:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        project, error = self.get_project_with_access(request, str(task.column.project.id))
        if error:
            return error

        uploaded = request.FILES.get('file')
        if not uploaded:
            return Response({'detail': '请选择文件'}, status=status.HTTP_400_BAD_REQUEST)

        # 大小限制 10MB
        if uploaded.size > 10 * 1024 * 1024:
            return Response({'detail': '文件大小不能超过 10MB'}, status=status.HTTP_400_BAD_REQUEST)

        attachment = TaskAttachment.objects.create(
            task=task,
            uploader=request.user,
            file=uploaded,
            filename=uploaded.name,
            file_size=uploaded.size,
            content_type=uploaded.content_type or 'application/octet-stream',
        )
        serializer = TaskAttachmentSerializer(attachment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TaskAttachmentDeleteView(ProjectAccessMixin, APIView):
    """DELETE /api/tasks/{task_id}/attachments/{aid}/"""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, task_id, aid):
        task = Task.objects.select_related('column__project').get(pk=task_id) if Task.objects.filter(pk=task_id).exists() else None
        if not task:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        project, error = self.get_project_with_access(request, str(task.column.project.id))
        if error:
            return error
        attachment = get_object_or_404(TaskAttachment, pk=aid, task=task)
        if attachment.uploader != request.user and task.column.project.owner != request.user:
            return Response({'detail': '无权删除'}, status=status.HTTP_403_FORBIDDEN)
        attachment.file.delete(save=False)
        attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
