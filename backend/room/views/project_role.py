"""项目角色视图"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from ..models import Project, ProjectRole, ProjectMember
from ..serializers import ProjectRoleSerializer, ProjectMemberSerializer
from .mixins import ProjectAccessMixin


class ProjectRoleListView(ProjectAccessMixin, APIView):
    """GET/POST /api/projects/{project_id}/roles/"""

    permission_classes = [permissions.IsAuthenticated]

    def _check_owner(self, request, project):
        if project.owner != request.user:
            return Response({'detail': '只有项目负责人可以管理角色'}, status=status.HTTP_403_FORBIDDEN)
        return None

    def get(self, request, project_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        roles = ProjectRole.objects.filter(project=project)
        serializer = ProjectRoleSerializer(roles, many=True)
        return Response(serializer.data)

    def post(self, request, project_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        owner_check = self._check_owner(request, project)
        if owner_check:
            return owner_check

        data = request.data.copy()
        data['project'] = project_id
        serializer = ProjectRoleSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProjectRoleDetailView(ProjectAccessMixin, APIView):
    """PUT/DELETE /api/projects/{project_id}/roles/{role_id}/"""

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, project_id, role_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        if project.owner != request.user:
            return Response({'detail': '只有项目负责人可以修改角色'}, status=status.HTTP_403_FORBIDDEN)
        role = get_object_or_404(ProjectRole, pk=role_id, project=project)
        if role.is_system:
            return Response({'detail': '系统预置角色不可修改'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ProjectRoleSerializer(role, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, project_id, role_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        if project.owner != request.user:
            return Response({'detail': '只有项目负责人可以删除角色'}, status=status.HTTP_403_FORBIDDEN)
        role = get_object_or_404(ProjectRole, pk=role_id, project=project)
        if role.is_system:
            return Response({'detail': '系统预置角色不可删除'}, status=status.HTTP_400_BAD_REQUEST)
        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectMemberListView(ProjectAccessMixin, APIView):
    """GET /api/projects/{project_id}/members/  |  PUT/DELETE"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        members = ProjectMember.objects.filter(project=project).select_related('user', 'role')
        serializer = ProjectMemberSerializer(members, many=True)
        return Response(serializer.data)

    def put(self, request, project_id):
        """修改成员角色"""
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        if project.owner != request.user:
            return Response({'detail': '只有项目负责人可以修改成员角色'}, status=status.HTTP_403_FORBIDDEN)
        user_id = request.data.get('user_id')
        role_id = request.data.get('role_id')
        member = get_object_or_404(ProjectMember, project=project, user_id=user_id)
        if role_id:
            member.role = get_object_or_404(ProjectRole, pk=role_id, project=project)
        else:
            member.role = None
        member.save()
        serializer = ProjectMemberSerializer(member)
        return Response(serializer.data)

    def delete(self, request, project_id):
        """移除成员"""
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        if project.owner != request.user:
            return Response({'detail': '只有项目负责人可以移除成员'}, status=status.HTTP_403_FORBIDDEN)
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({'detail': '缺少 user_id 参数'}, status=status.HTTP_400_BAD_REQUEST)
        member = get_object_or_404(ProjectMember, project=project, user_id=user_id)
        member.delete()
        project.members.remove(member.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
