"""任务评论视图"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ..models import Task, TaskComment, TaskActivityLog
from ..serializers import TaskCommentSerializer
from .mixins import ProjectAccessMixin
import logging

logger = logging.getLogger(__name__)


class TaskCommentListView(ProjectAccessMixin, APIView):
    """GET /api/tasks/{task_id}/comments/  |  POST"""

    permission_classes = [permissions.IsAuthenticated]

    def _get_task(self, task_id):
        try:
            return Task.objects.select_related('column__project').get(pk=task_id)
        except Task.DoesNotExist:
            return None

    def _broadcast_comment(self, task, comment_data):
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return
            project_id = str(task.column.project.id)
            async_to_sync(channel_layer.group_send)(
                f'board_{project_id}',
                {
                    'type': 'board_update',
                    'message': {
                        'action': 'comment_added',
                        'task_id': str(task.id),
                        'comment': comment_data,
                    }
                }
            )
        except Exception as e:
            logger.warning(f'WebSocket 广播评论失败: {e}')

    def get(self, request, task_id):
        task = self._get_task(task_id)
        if not task:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        project, error = self.get_project_with_access(request, str(task.column.project.id))
        if error:
            return error

        queryset = TaskComment.objects.filter(
            task=task, parent__isnull=True
        ).select_related('author__profile').prefetch_related('replies__author__profile')

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = TaskCommentSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = TaskCommentSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request, task_id):
        task = self._get_task(task_id)
        if not task:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)
        project, error = self.get_project_with_access(request, str(task.column.project.id))
        if error:
            return error

        data = request.data.copy()
        data['task'] = task_id

        # 验证 parent 是否属于同一任务
        parent_id = data.get('parent')
        if parent_id:
            try:
                parent_comment = TaskComment.objects.only('task_id').get(pk=parent_id)
                if str(parent_comment.task_id) != str(task_id):
                    return Response(
                        {'detail': '回复的评论不属于此任务'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except TaskComment.DoesNotExist:
                return Response(
                    {'detail': '回复的评论不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = TaskCommentSerializer(data=data)
        if serializer.is_valid():
            comment = serializer.save(author=request.user)
            TaskActivityLog.objects.create(
                task=task, user=request.user, action='commented',
                field_name='comment', new_value=comment.content[:100]
            )
            self._broadcast_comment(task, TaskCommentSerializer(comment).data)
            return Response(TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TaskCommentDetailView(ProjectAccessMixin, APIView):
    """PATCH/DELETE /api/tasks/{task_id}/comments/{comment_id}/"""

    permission_classes = [permissions.IsAuthenticated]

    def _get_comment(self, task_id, comment_id):
        try:
            return TaskComment.objects.select_related(
                'task__column__project'
            ).get(pk=comment_id, task_id=task_id)
        except TaskComment.DoesNotExist:
            return None

    def patch(self, request, task_id, comment_id):
        comment = self._get_comment(task_id, comment_id)
        if not comment:
            return Response({'detail': '评论不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 检查项目访问权限
        project, error = self.get_project_with_access(
            request, str(comment.task.column.project.id)
        )
        if error:
            return error

        if comment.author != request.user:
            return Response(
                {'detail': '只能编辑自己的评论'},
                status=status.HTTP_403_FORBIDDEN
            )

        new_content = request.data.get('content', '').strip()
        if not new_content:
            return Response(
                {'detail': '评论内容不能为空'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = TaskCommentSerializer(
            comment, data={'content': new_content}, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, task_id, comment_id):
        comment = self._get_comment(task_id, comment_id)
        if not comment:
            return Response({'detail': '评论不存在'}, status=status.HTTP_404_NOT_FOUND)

        project, error = self.get_project_with_access(
            request, str(comment.task.column.project.id)
        )
        if error:
            return error

        if comment.author != request.user and comment.task.column.project.owner != request.user:
            return Response({'detail': '无权删除'}, status=status.HTTP_403_FORBIDDEN)

        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
