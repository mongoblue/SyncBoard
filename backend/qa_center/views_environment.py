"""测试环境 + 全局变量 ViewSets —— M3.2。"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import TestEnvironment, TestGlobalVar
from .serializers import TestEnvironmentSerializer, TestGlobalVarSerializer


class TestEnvironmentViewSet(viewsets.ModelViewSet):
    """测试环境管理。

    GET    /api/qa/environments/?project=        列表（必传 project）
    POST   /api/qa/environments/                 创建
    GET    /api/qa/environments/{id}/            详情
    PATCH  /api/qa/environments/{id}/            更新
    DELETE /api/qa/environments/{id}/            删除
    POST   /api/qa/environments/{id}/set_default/  把当前环境设为项目默认
    """

    serializer_class = TestEnvironmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = TestEnvironment.objects.select_related('project', 'created_by').all()
        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return qs.order_by('-is_default', 'name')

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        # 项目下还没有默认环境时，自动把第一条设为默认
        if not TestEnvironment.objects.filter(
            project=instance.project, is_default=True,
        ).exclude(pk=instance.pk).exists() and not instance.is_default:
            instance.is_default = True
            instance.save(update_fields=['is_default'])
        elif instance.is_default:
            # 显式声明默认时，互斥
            TestEnvironment.objects.filter(
                project=instance.project, is_default=True,
            ).exclude(pk=instance.pk).update(is_default=False)

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.is_default:
            TestEnvironment.objects.filter(
                project=instance.project, is_default=True,
            ).exclude(pk=instance.pk).update(is_default=False)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def set_default(self, request, pk=None):
        env = self.get_object()
        TestEnvironment.objects.filter(
            project=env.project, is_default=True,
        ).exclude(pk=env.pk).update(is_default=False)
        if not env.is_default:
            env.is_default = True
            env.save(update_fields=['is_default'])
        return Response(self.get_serializer(env).data)


class TestGlobalVarViewSet(viewsets.ModelViewSet):
    """项目全局变量管理。

    GET    /api/qa/global-vars/?project=     列表（必传 project）
    POST   /api/qa/global-vars/              创建
    PATCH  /api/qa/global-vars/{id}/         更新
    DELETE /api/qa/global-vars/{id}/         删除
    """

    serializer_class = TestGlobalVarSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = TestGlobalVar.objects.select_related('project', 'created_by').all()
        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(key__icontains=search) | Q(description__icontains=search))
        return qs.order_by('key')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
