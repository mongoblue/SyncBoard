"""
看板管理视图

提供看板列和任务的增删改查功能，包含 WebSocket 实时广播。
"""

from dataclasses import dataclass
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Prefetch
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ..models import Column, Task, Project, TaskActivityLog
from ..serializers import ColumnSerializer, TaskSerializer
from .mixins import ProjectAccessMixin


class TaskPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100
    page_size_query_param = 'page_size'


# ============== 广播用简化对象 ==============
@dataclass
class SimpleProject:
    """用于广播的简化项目对象"""
    id: str


@dataclass
class SimpleColumn:
    """用于广播的简化列对象"""
    project: SimpleProject


@dataclass
class SimpleTask:
    """用于广播的简化任务对象"""
    id: str
    title: str
    column: SimpleColumn


def broadcast_task_change(task_instance, action_type):
    """
    广播任务变更消息到 WebSocket

    Args:
        task_instance: 任务对象
        action_type: 'create' | 'update' | 'delete'
    """
    channel_layer = get_channel_layer()

    try:
        project_id = str(task_instance.column.project.id)
        room_group_name = f'board_{project_id}'
    except AttributeError:
        print('⚠️ 无法获取项目ID，广播失败')
        return

    # 安全处理：确保 title 不为空
    safe_title = task_instance.title or '未知任务'

    # 发送给该项目的房间
    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'board_update',
            'message': {
                'action': 'refresh',
                'task_id': str(task_instance.id),
                'title': safe_title,
                'user_action': action_type
            }
        }
    )

    # 发送全局弹窗通知
    action_map = {
        'create': '创建了',
        'update': '更新了',
        'delete': '删除了'
    }
    msg_text = action_map.get(action_type, '动了')

    async_to_sync(channel_layer.group_send)(
        'system_broadcast',
        {
            'type': 'global_notification',
            'message': f"任务动态：'{safe_title}' 被 {msg_text}",
            'level': 'success'
        }
    )
    print(f'📢 广播成功: {action_type} - {safe_title}')


class ColumnListView(ProjectAccessMixin, APIView):
    """
    看板列列表视图

    GET /api/columns/?project=<id>
    POST /api/columns/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project')

        if not project_id:
            return Response(
                {'detail': '缺少 project 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 使用 Mixin 验证项目访问权限
        project, error_response = self.get_project_with_access(request, project_id)
        if error_response:
            return error_response

        columns = Column.objects.filter(project_id=project_id).order_by('position').prefetch_related(
            Prefetch('tasks', queryset=Task.objects.select_related(
                'column', 'assignee__profile'
            ).prefetch_related('tags'))
        )
        serializer = ColumnSerializer(columns, many=True)
        return Response(serializer.data)

    def post(self, request):
        # 验证 column 所属项目的访问权限
        column_id = request.data.get('id')
        if column_id:
            column, error_response = self.get_column_with_project_access(request, column_id)
            if error_response:
                return error_response

        serializer = ColumnSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ColumnDetailView(ProjectAccessMixin, APIView):
    """
    看板列详情视图

    GET /api/columns/<id>/
    PATCH /api/columns/<id>/
    DELETE /api/columns/<id>/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Column, pk=pk)

    def get(self, request, pk):
        """获取列详情"""
        column, error_response = self.get_column_with_project_access(request, pk)
        if error_response:
            return error_response

        serializer = ColumnSerializer(column)
        return Response(serializer.data)

    def patch(self, request, pk):
        column, error_response = self.get_column_with_project_access(request, pk)
        if error_response:
            return error_response

        serializer = ColumnSerializer(column, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        column, error_response = self.get_column_with_project_access(request, pk)
        if error_response:
            return error_response

        if column.tasks.exists():
            return Response(
                {'detail': '该列下还有任务，不能删除'},
                status=status.HTTP_400_BAD_REQUEST
            )
        column.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskListView(ProjectAccessMixin, APIView):
    """
    任务列表视图

    GET /api/tasks/?project=<id>&page=1&page_size=20
    POST /api/tasks/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project')
        if not project_id:
            return Response(
                {'detail': '缺少 project 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 使用 Mixin 验证项目访问权限
        project, error_response = self.get_project_with_access(request, project_id)
        if error_response:
            return error_response

        queryset = Task.objects.filter(
            column__project_id=project_id
        ).select_related('assignee').prefetch_related('tags')

        paginator = TaskPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = TaskSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = TaskSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        # 使用 Mixin 验证 column 所属项目的访问权限
        column_id = request.data.get('column')
        if not column_id:
            return Response(
                {'detail': '缺少 column 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        column, error_response = self.get_column_with_project_access(request, column_id)
        if error_response:
            return error_response

        serializer = TaskSerializer(data=request.data)
        if serializer.is_valid():
            task = serializer.save()
            # 使用 on_commit 确保事务提交后再广播
            transaction.on_commit(lambda: broadcast_task_change(task, 'create'))
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TaskDetailView(ProjectAccessMixin, APIView):
    """
    任务详情视图

    GET /api/tasks/<id>/
    PATCH /api/tasks/<id>/
    DELETE /api/tasks/<id>/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Task, pk=pk)

    def get(self, request, pk):
        """获取任务详情"""
        task, error_response = self.get_task_with_project_access(request, pk)
        if error_response:
            return error_response

        serializer = TaskSerializer(task)
        return Response(serializer.data)

    def patch(self, request, pk):
        task, error_response = self.get_task_with_project_access(request, pk)
        if error_response:
            return error_response

        serializer = TaskSerializer(task, data=request.data, partial=True)

        if serializer.is_valid():
            updated_task = serializer.save()
            transaction.on_commit(lambda: broadcast_task_change(updated_task, 'update'))
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        task, error_response = self.get_task_with_project_access(request, pk)
        if error_response:
            return error_response

        # 保存必要信息用于广播（在删除前）
        task_info = {
            'id': str(task.id),
            'title': task.title or '',
            'project_id': str(task.column.project.id)
        }

        # 在删除前记录活动日志（post_delete 中无法创建，因为 FK 约束）
        TaskActivityLog.objects.create(
            task=task, user=request.user, action='deleted',
            field_name='task', new_value=task.title
        )

        task.delete()

        # 使用 dataclass 构造简单对象进行广播
        simple_task = SimpleTask(
            id=task_info['id'],
            title=task_info['title'],
            column=SimpleColumn(
                project=SimpleProject(id=task_info['project_id'])
            )
        )

        transaction.on_commit(lambda: broadcast_task_change(simple_task, 'delete'))

        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskBatchDeleteView(ProjectAccessMixin, APIView):
    """
    任务批量删除视图

    POST /api/tasks/batch-delete/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        task_ids = request.data.get('task_ids', [])
        if not task_ids:
            return Response(
                {'detail': '缺少 task_ids 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 获取任务并预加载关联数据
        tasks = Task.objects.filter(id__in=task_ids).select_related('column__project')

        if not tasks.exists():
            return Response(
                {'detail': '未找到指定任务'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 使用 Mixin 统一验证权限（验证第一个任务所属项目）
        first_task = tasks.first()
        project_id = str(first_task.column.project.id)

        # 验证项目访问权限
        project, error_response = self.get_project_with_access(request, project_id)
        if error_response:
            return error_response

        # 二次验证：确保所有任务都属于同一项目
        for task in tasks:
            if str(task.column.project.id) != project_id:
                return Response(
                    {'detail': '批量删除只支持同一项目内的任务'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        count = tasks.count()

        # 在删除前记录活动日志
        for task in tasks:
            TaskActivityLog.objects.create(
                task=task, user=request.user, action='deleted',
                field_name='task', new_value=task.title
            )

        tasks.delete()

        # 广播刷新信号
        channel_layer = get_channel_layer()
        room_group_name = f'board_{project_id}'
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'board_update',
                'message': {
                    'action': 'refresh',
                    'user_action': 'batch_delete'
                }
            }
        )

        return Response(
            {'detail': f'成功删除 {count} 个任务'},
            status=status.HTTP_200_OK
        )
