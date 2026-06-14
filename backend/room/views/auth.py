"""
用户认证视图

提供登录、登出和当前用户信息获取功能。
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login, logout
from backend.throttles import LoginRateThrottle
from ..serializers import UsersSerializer


class LoginView(APIView):
    """
    用户登录视图

    POST /api/auth/login/
    """
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            serializer = UsersSerializer(user)
            return Response(serializer.data)
        else:
            return Response(
                {'detail': '用户名或密码错误'},
                status=status.HTTP_401_UNAUTHORIZED
            )


class LogoutView(APIView):
    """
    用户登出视图

    POST /api/auth/logout/
    """

    def post(self, request):
        logout(request)
        return Response({'detail': '注销成功'})


class CurrentUserView(APIView):
    """
    获取当前登录用户信息

    GET /api/auth/me/
    """

    def get(self, request):
        if request.user.is_authenticated:
            serializer = UsersSerializer(request.user)
            return Response(serializer.data)
        else:
            return Response(
                {'detail': '未登录'},
                status=status.HTTP_401_UNAUTHORIZED
            )
