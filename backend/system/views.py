"""
RBAC 权限管理 APIViews

所有系统管理视图现在强制检查操作级权限。
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Menu, Role, SystemUserProfile
from .serializers import (
    MenuSerializer, MenuTreeSerializer, RoleSerializer,
    UserSerializer, UserPermissionSerializer, UserCreateSerializer
)
from .permissions import HasSystemPermission


class MenuListView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasSystemPermission('sys:menu:list')]
        if self.request.method == 'POST':
            return [IsAuthenticated(), HasSystemPermission('sys:menu:add')]
        return [IsAuthenticated()]

    def get(self, request):
        menus = Menu.objects.filter(parent__isnull=True, is_active=True).order_by('order', 'id')
        serializer = MenuSerializer(menus, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MenuSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MenuDetailView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasSystemPermission('sys:menu:list')]
        if self.request.method in ('PUT', 'PATCH'):
            return [IsAuthenticated(), HasSystemPermission('sys:menu:edit')]
        if self.request.method == 'DELETE':
            return [IsAuthenticated(), HasSystemPermission('sys:menu:delete')]
        return [IsAuthenticated()]

    def get_object(self, pk):
        try:
            return Menu.objects.get(pk=pk)
        except Menu.DoesNotExist:
            return None

    def get(self, request, pk):
        menu = self.get_object(pk)
        if not menu:
            return Response({'detail': '菜单不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MenuSerializer(menu)
        return Response(serializer.data)

    def put(self, request, pk):
        menu = self.get_object(pk)
        if not menu:
            return Response({'detail': '菜单不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MenuSerializer(menu, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        menu = self.get_object(pk)
        if not menu:
            return Response({'detail': '菜单不存在'}, status=status.HTTP_404_NOT_FOUND)
        menu.is_active = False
        menu.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuTreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        menus = Menu.objects.filter(parent__isnull=True, is_active=True).order_by('order', 'id')
        serializer = MenuTreeSerializer(menus, many=True)
        return Response(serializer.data)


class RoleListView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasSystemPermission('sys:role:list')]
        if self.request.method == 'POST':
            return [IsAuthenticated(), HasSystemPermission('sys:role:add')]
        return [IsAuthenticated()]

    def get(self, request):
        roles = Role.objects.filter(is_active=True)
        serializer = RoleSerializer(roles, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = RoleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleDetailView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasSystemPermission('sys:role:list')]
        if self.request.method in ('PUT', 'PATCH'):
            if 'menus' in self.request.data:
                return [IsAuthenticated(), HasSystemPermission('sys:role:permission')]
            return [IsAuthenticated(), HasSystemPermission('sys:role:edit')]
        if self.request.method == 'DELETE':
            return [IsAuthenticated(), HasSystemPermission('sys:role:delete')]
        return [IsAuthenticated()]

    def get_object(self, pk):
        try:
            return Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            return None

    def get(self, request, pk):
        role = self.get_object(pk)
        if not role:
            return Response({'detail': '角色不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = RoleSerializer(role)
        return Response(serializer.data)

    def put(self, request, pk):
        role = self.get_object(pk)
        if not role:
            return Response({'detail': '角色不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = RoleSerializer(role, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        role = self.get_object(pk)
        if not role:
            return Response({'detail': '角色不存在'}, status=status.HTTP_404_NOT_FOUND)
        role.is_active = False
        role.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserListView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasSystemPermission('sys:user:list')]
        if self.request.method == 'POST':
            return [IsAuthenticated(), HasSystemPermission('sys:user:add')]
        return [IsAuthenticated()]

    def get(self, request):
        keyword = request.query_params.get('keyword', '')
        users = User.objects.filter(is_active=True)
        if keyword:
            users = users.filter(
                Q(username__icontains=keyword) |
                Q(email__icontains=keyword)
            )
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetailView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasSystemPermission('sys:user:list')]
        if self.request.method in ('PUT', 'PATCH'):
            if 'roles' in self.request.data:
                return [IsAuthenticated(), HasSystemPermission('sys:user:role')]
            return [IsAuthenticated(), HasSystemPermission('sys:user:edit')]
        if self.request.method == 'DELETE':
            return [IsAuthenticated(), HasSystemPermission('sys:user:delete')]
        return [IsAuthenticated()]

    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def put(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        user = self.get_object(pk)
        if not user:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        user.is_active = False
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserPermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        SystemUserProfile.objects.get_or_create(user=request.user)
        serializer = UserPermissionSerializer(request.user)
        return Response(serializer.data)


class UserResetPasswordView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), HasSystemPermission('sys:user:reset-password')]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        new_password = request.data.get('password')
        if not new_password:
            return Response({'detail': '请提供新密码'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({'detail': '密码重置成功'})
