"""项目 API 文档管理"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from ..models import ProjectApiDoc, Project
from ..serializers import ProjectApiDocSerializer
from .mixins import ProjectAccessMixin


class ProjectApiDocListView(ProjectAccessMixin, APIView):
    """GET /api/projects/{pid}/api-docs/  |  POST"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        docs = ProjectApiDoc.objects.filter(project=project)
        serializer = ProjectApiDocSerializer(docs, many=True)
        return Response(serializer.data)

    def post(self, request, project_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        data = request.data.copy()
        data['project'] = project_id
        serializer = ProjectApiDocSerializer(data=data)
        if serializer.is_valid():
            doc = serializer.save(uploaded_by=request.user)
            return Response(ProjectApiDocSerializer(doc).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProjectApiDocDetailView(ProjectAccessMixin, APIView):
    """PUT/DELETE /api/projects/{pid}/api-docs/{doc_id}/"""

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, project_id, doc_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        doc = get_object_or_404(ProjectApiDoc, pk=doc_id, project=project)
        serializer = ProjectApiDocSerializer(doc, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, project_id, doc_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        doc = get_object_or_404(ProjectApiDoc, pk=doc_id, project=project)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
