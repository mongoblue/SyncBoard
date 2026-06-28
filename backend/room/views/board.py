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
from django.contrib.auth.models import User
from django.db.models import Prefetch
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ..models import Column, Task, Project, TaskActivityLog, Tag
from ..serializers import ColumnSerializer, TaskSerializer
from .mixins import ProjectAccessMixin


def _user_belongs_to_project(user, project):
    """检查用户是否是项目 owner 或成员。"""
    return user == project.owner or project.members.filter(id=user.id).exists()


def _validate_task_relationships(project, data):
    """校验任务关联字段不跨项目。"""
    tags = data.get('tags')
    if tags is not None:
        tag_ids = [tag.get('id') if isinstance(tag, dict) else tag for tag in tags]
        if Tag.objects.filter(id__in=tag_ids).exclude(project=project).exists():
            return Response(
                {'detail': '标签不属于当前项目'},
                status=status.HTTP_400_BAD_REQUEST
            )

    assignee_id = data.get('assignee')
    if assignee_id:
        try:
            assignee = User.objects.get(pk=assignee_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response(
                {'detail': '负责人不存在'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not _user_belongs_to_project(assignee, project):
            return Response(
                {'detail': '负责人不是项目成员'},
                status=status.HTTP_400_BAD_REQUEST
            )

    return None


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
        project_id = request.data.get('project')
        if not project_id:
            return Response(
                {'detail': '缺少 project 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        project, error_response = self.get_project_with_access(request, project_id)
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

        if 'project' in request.data and str(request.data.get('project')) != str(column.project_id):
            return Response(
                {'detail': '不能修改列所属项目'},
                status=status.HTTP_400_BAD_REQUEST
            )

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

        validation_error = _validate_task_relationships(column.project, request.data)
        if validation_error:
            return validation_error

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

        if 'column' in request.data:
            target_column, column_error = self.get_column_with_project_access(request, request.data.get('column'))
            if column_error:
                return column_error
            if target_column.project_id != task.column.project_id:
                return Response(
                    {'detail': '任务不能移动到其他项目的列'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        validation_error = _validate_task_relationships(task.column.project, request.data)
        if validation_error:
            return validation_error

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

        requested_ids = [str(task_id) for task_id in task_ids]
        unique_requested_ids = list(dict.fromkeys(requested_ids))

        # 获取任务并预加载关联数据
        tasks = list(
            Task.objects.filter(id__in=unique_requested_ids).select_related('column__project')
        )

        if not tasks:
            return Response(
                {'detail': '未找到指定任务'},
                status=status.HTTP_404_NOT_FOUND
            )

        found_ids = {str(task.id) for task in tasks}
        if found_ids != set(unique_requested_ids):
            return Response(
                {'detail': '部分任务不存在'},
                status=status.HTTP_400_BAD_REQUEST
            )

        project_ids = {str(task.column.project.id) for task in tasks}
        if len(project_ids) != 1:
            return Response(
                {'detail': '批量删除只支持同一项目内的任务'},
                status=status.HTTP_400_BAD_REQUEST
            )

        project_id = project_ids.pop()

        # 验证项目访问权限
        project, error_response = self.get_project_with_access(request, project_id)
        if error_response:
            return error_response

        count = len(tasks)

        with transaction.atomic():
            # 在删除前记录活动日志
            for task in tasks:
                TaskActivityLog.objects.create(
                    task=task, user=request.user, action='deleted',
                    field_name='task', new_value=task.title
                )

            Task.objects.filter(id__in=unique_requested_ids).delete()

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
