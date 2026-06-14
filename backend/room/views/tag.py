"""
标签管理视图

提供项目标签的增删改查功能。
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from ..models import Tag, Project
from ..serializers import TagSerializer
from .mixins import ProjectAccessMixin


class TagListView(ProjectAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project')
        if not project_id:
            return Response(
                {'detail': '缺少 project 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )
        project, error_response = self.get_project_with_access(request, project_id)
        if error_response:
            return error_response
        tags = Tag.objects.filter(project_id=project_id)
        serializer = TagSerializer(tags, many=True)
        return Response(serializer.data)

    def post(self, request):
        project_id = request.data.get('project')
        if project_id:
            project, error_response = self.get_project_with_access(request, str(project_id))
            if error_response:
                return error_response
        serializer = TagSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TagDetailView(ProjectAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Tag, pk=pk)

    def patch(self, request, pk):
        tag = self.get_object(pk)
        project, error_response = self.get_project_with_access(request, str(tag.project_id))
        if error_response:
            return error_response
        serializer = TagSerializer(tag, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        tag = self.get_object(pk)
        project, error_response = self.get_project_with_access(request, str(tag.project_id))
        if error_response:
            return error_response
        tag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
