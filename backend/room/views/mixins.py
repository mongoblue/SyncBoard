"""
项目访问权限校验 Mixin

提供统一的项目访问权限校验逻辑，避免在各视图中重复编写权限检查代码。
"""

from rest_framework import status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404


class ProjectAccessMixin:
    """
    项目访问权限校验 Mixin

    使用方式：
    class MyView(ProjectAccessMixin, APIView):
        def get(self, request):
            project, error_response = self.get_project_with_access(request, project_id)
            if error_response:
                return error_response
            # project 是有效的项目对象
    """

    def get_project_with_access(self, request, project_id, project_model=None):
        """
        验证用户是否有权访问指定项目

        Args:
            request: DRF 请求对象
            project_id: 项目 ID
            project_model: 项目模型类，默认为 Project

        Returns:
            tuple: (project, None) 如果有权访问
                   (None, error_response) 如果无权访问或项目不存在
        """
        if project_model is None:
            from room.models import Project
            project_model = Project

        try:
            project = project_model.objects.get(pk=project_id)
        except project_model.DoesNotExist:
            return None, Response(
                {'detail': '项目不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.user != project.owner and request.user not in project.members.all():
            return None, Response(
                {'detail': '无权访问此项目'},
                status=status.HTTP_403_FORBIDDEN
            )

        return project, None

    def get_column_with_project_access(self, request, column_id):
        """
        验证用户是否有权访问指定列所属的项目

        Args:
            request: DRF 请求对象
            column_id: 列 ID

        Returns:
            tuple: (column, None) 如果有权访问
                   (None, error_response) 如果无权访问或列不存在
        """
        from room.models import Column
        from django.core.exceptions import ValidationError

        try:
            column = Column.objects.select_related('project').get(pk=column_id)
        except (Column.DoesNotExist, ValidationError, ValueError, TypeError):
            return None, Response(
                {'detail': '列不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.user != column.project.owner and request.user not in column.project.members.all():
            return None, Response(
                {'detail': '无权访问此项目'},
                status=status.HTTP_403_FORBIDDEN
            )

        return column, None

    def get_task_with_project_access(self, request, task_id):
        """
        验证用户是否有权访问指定任务所属的项目

        Args:
            request: DRF 请求对象
            task_id: 任务 ID

        Returns:
            tuple: (task, None) 如果有权访问
                   (None, error_response) 如果无权访问或任务不存在
        """
        from room.models import Task

        try:
            task = Task.objects.select_related('column__project').get(pk=task_id)
        except Task.DoesNotExist:
            return None, Response(
                {'detail': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        project = task.column.project
        if request.user != project.owner and request.user not in project.members.all():
            return None, Response(
                {'detail': '无权访问此项目'},
                status=status.HTTP_403_FORBIDDEN
            )

        return task, None