"""
用户管理视图

提供用户列表查询功能。
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.contrib.auth.models import User
from ..serializers import UsersSerializer


class UserListView(APIView):
    """
    用户列表视图

    GET /api/users/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        users = User.objects.all()
        serializer = UsersSerializer(users, many=True)
        return Response(serializer.data)
