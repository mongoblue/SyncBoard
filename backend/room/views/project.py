"""
项目管理视图

提供项目的增删改查、成员邀请、RAG 智能问答等功能。
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.db.models import Q
from haystack.query import SearchQuerySet
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from ..models import Project, Column, Task, Tag, ProjectMember, ProjectRole
from ..serializers import ProjectSerializer
from ..ai_utils import get_rag_answer, format_task_context
import logging

logger = logging.getLogger(__name__)


class ProjectListView(APIView):
    """
    项目列表视图

    GET /api/projects/
    POST /api/projects/
    DELETE /api/projects/<id>/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members=request.user)
        ).distinct().order_by('-created_at')

        serializer = ProjectSerializer(projects, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if request.user.is_authenticated:
            data['owner'] = request.user.id

        serializer = ProjectSerializer(data=data)
        if serializer.is_valid():
            # 1. 先保存项目
            project = serializer.save()

            # 2. 自动创建默认列
            Column.objects.create(project=project, title='To Do', position=1)
            Column.objects.create(project=project, title='In Progress', position=2)
            Column.objects.create(project=project, title='Done', position=3)

            # 3. 创建默认标签
            default_tags = [
                {'name': 'Bug', 'color': '#f56c6c'},
                {'name': 'Feature', 'color': '#409eff'},
                {'name': 'Urgent', 'color': '#e6a23c'},
                {'name': 'Enhancement', 'color': '#67c23a'}
            ]
            for tag in default_tags:
                Tag.objects.create(project=project, name=tag['name'], color=tag['color'])

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            project = Project.objects.get(pk=pk)

            if request.user.is_authenticated and project.owner != request.user:
                return Response(
                    {'detail': '无权删除'},
                    status=status.HTTP_403_FORBIDDEN
                )

            project.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Project.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


class ProjectInviteView(APIView):
    """
    项目成员邀请视图

    POST /api/projects/<id>/invite/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            project = Project.objects.get(pk=pk)

            if request.user.is_authenticated and project.owner != request.user:
                return Response(
                    {'detail': '只有项目负责人可以邀请成员'},
                    status=status.HTTP_403_FORBIDDEN
                )

            username = request.data.get('username')
            user_to_invite = User.objects.get(username=username)
            if user_to_invite == project.owner:
                return Response(
                    {'detail': '该用户已经是负责人'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            project.members.add(user_to_invite)

            # 创建 ProjectMember 记录并分配默认 Viewer 角色
            viewer_role = ProjectRole.objects.filter(
                project=project, key='viewer', is_system=True
            ).first()
            ProjectMember.objects.get_or_create(
                project=project,
                user=user_to_invite,
                defaults={'role': viewer_role}
            )

            return Response(
                {'detail': f'已邀请 {username} 加入项目'},
                status=status.HTTP_200_OK
            )

        except Project.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except User.DoesNotExist:
            return Response(
                {'detail': '用户不存在'},
                status=status.HTTP_404_NOT_FOUND
            )


class ProjectChatView(APIView):
    """
    RAG 智能项目问答助手

    接收用户问题，搜索相关任务，使用 AI 生成回答。

    POST /api/chat/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        question = request.data.get('question', '').strip()
        project_id = request.data.get('project_id', '').strip()

        if not question:
            return Response(
                {'detail': '问题不能为空'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not project_id:
            return Response(
                {'detail': '项目ID不能为空'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. 验证项目存在且用户有权限访问
            project = get_object_or_404(Project, pk=project_id)
            if request.user != project.owner and request.user not in project.members.all():
                return Response(
                    {'detail': '没有权限访问此项目'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # 2. 使用 Haystack 搜索相关任务
            search_results = SearchQuerySet().filter(
                project_id=project_id
            ).auto_query(question).models(Task)

            project_tasks = []
            for result in search_results:
                if result.object:
                    project_tasks.append({
                        'id': str(result.object.id),
                        'title': result.object.title,
                        'content': result.object.content or '',
                        'status': result.object.column.title,
                        'assignee': result.object.assignee.username if result.object.assignee else '未指派',
                        'tags': [tag.name for tag in result.object.tags.all()]
                    })
                    if len(project_tasks) >= 5:
                        break

            # 3. Fallback 机制：如果搜索结果不足，补充一些最近的任务
            if len(project_tasks) < 3:
                existing_ids = [t['id'] for t in project_tasks]
                fallback_tasks = Task.objects.filter(
                    column__project_id=project_id
                ).exclude(
                    id__in=existing_ids
                ).select_related('column', 'assignee').prefetch_related('tags').order_by('-position')[:5]

                for task in fallback_tasks:
                    project_tasks.append({
                        'id': str(task.id),
                        'title': task.title,
                        'content': task.content or '',
                        'status': task.column.title,
                        'assignee': task.assignee.username if task.assignee else '未指派',
                        'tags': [tag.name for tag in task.tags.all()]
                    })
                    if len(project_tasks) >= 8:
                        break

            # 4. 构建上下文并调用 AI
            context = format_task_context(project_tasks)
            answer = get_rag_answer(question, context)

            return Response({
                'answer': answer,
                'context_tasks': project_tasks,
                'question': question
            })

        except Exception as e:
            logger.error(f"RAG问答异常: {str(e)}", exc_info=True)
            return Response(
                {'detail': '处理问题时出现错误，请稍后重试'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
