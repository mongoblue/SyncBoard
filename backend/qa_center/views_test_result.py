"""
测试结果管理视图
支持测试结果的存储、查询、导出
"""

import base64
import os
import uuid
from datetime import datetime
from django.conf import settings
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from .models import TestResult, TestScreenshot, UiTestCase, ApiTestCase
from .serializers import (
    TestResultListSerializer,
    TestResultDetailSerializer,
    TestResultCreateSerializer,
    TestScreenshotSerializer
)
from room.project_access import ensure_project_id_access, project_access_q


class TestResultViewSet(viewsets.ModelViewSet):
    """测试结果 ViewSet"""

    permission_classes = [IsAuthenticated]

    def _ensure_result_access(self, test_result):
        if test_result.project_id:
            ensure_project_id_access(self.request.user, test_result.project_id)
            return
        if test_result.executed_by_id != self.request.user.id:
            raise PermissionDenied('无权访问该测试结果')

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        obj = get_object_or_404(
            TestResult.objects.select_related(
                'project', 'executed_by', 'api_test_case', 'ui_test_case'
            ).prefetch_related('screenshots'),
            **{self.lookup_field: self.kwargs[lookup_url_kwarg]},
        )
        self._ensure_result_access(obj)
        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        """根据条件过滤"""
        queryset = TestResult.objects.filter(
            project_access_q('project', self.request.user) |
            Q(project__isnull=True, executed_by=self.request.user)
        ).distinct()

        # 按测试类型筛选
        test_type = self.request.query_params.get('test_type')
        if test_type:
            queryset = queryset.filter(test_type=test_type)

        # 按结果来源筛选
        source = self.request.query_params.get('source')
        if source:
            queryset = queryset.filter(source=source)

        # 按项目筛选
        project_id = self.request.query_params.get('project')
        if project_id:
            ensure_project_id_access(self.request.user, project_id)
            queryset = queryset.filter(project_id=project_id)

        # 按状态筛选
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        # 按时间范围筛选
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        return queryset.select_related(
            'project', 'executed_by', 'api_test_case', 'ui_test_case'
        ).prefetch_related('screenshots')

    def get_serializer_class(self):
        """根据动作选择序列化器"""
        if self.action == 'list':
            return TestResultListSerializer
        elif self.action == 'create':
            return TestResultCreateSerializer
        return TestResultDetailSerializer

    def perform_create(self, serializer):
        """创建时设置执行者"""
        project = serializer.validated_data.get('project')
        api_case = serializer.validated_data.get('api_test_case')
        ui_case = serializer.validated_data.get('ui_test_case')
        effective_project = project

        if api_case:
            ensure_project_id_access(self.request.user, api_case.project_id)
            if effective_project and effective_project.id != api_case.project_id:
                raise ValidationError({'api_test_case': 'API用例不属于当前项目'})
            effective_project = api_case.project

        if ui_case:
            ensure_project_id_access(self.request.user, ui_case.project_id)
            if effective_project and effective_project.id != ui_case.project_id:
                raise ValidationError({'ui_test_case': 'UI用例不属于当前项目'})
            effective_project = ui_case.project

        if effective_project:
            ensure_project_id_access(self.request.user, effective_project.id)

        serializer.save(executed_by=self.request.user, project=effective_project)

    @action(detail=True, methods=['post'])
    def upload_screenshot(self, request, pk=None):
        """
        上传测试截图

        POST /api/qa/test-results/{id}/upload_screenshot/

        Request:
            - image: 图片文件 或 base64 字符串
            - name: 截图名称
            - description: 截图描述
            - step_index: 步骤序号
        """
        test_result = self.get_object()

        # 获取参数
        name = request.data.get('name', '')
        description = request.data.get('description', '')
        step_index = request.data.get('step_index')

        # 处理 Base64 图片
        base64_image = request.data.get('base64_image')
        if base64_image:
            # 从 base64 字符串创建图片文件
            try:
                # 移除 data:image/png;base64, 前缀
                if ',' in base64_image:
                    base64_image = base64_image.split(',')[1]

                image_data = base64.b64decode(base64_image)

                # 生成文件名
                filename = f"screenshot_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"

                # 保存到媒体目录
                screenshot_dir = os.path.join('test_screenshots', datetime.now().strftime('%Y/%m/%d'))
                full_dir = os.path.join(settings.MEDIA_ROOT, screenshot_dir)
                os.makedirs(full_dir, exist_ok=True)

                filepath = os.path.join(full_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_data)

                # 创建数据库记录
                screenshot = TestScreenshot.objects.create(
                    test_result=test_result,
                    name=name or '测试截图',
                    description=description,
                    image=os.path.join(screenshot_dir, filename),
                    step_index=step_index
                )

                serializer = TestScreenshotSerializer(screenshot, context={'request': request})
                return Response(serializer.data, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response(
                    {'error': f'保存截图失败: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 处理上传的文件
        image_file = request.FILES.get('image')
        if image_file:
            screenshot = TestScreenshot.objects.create(
                test_result=test_result,
                name=name or image_file.name,
                description=description,
                image=image_file,
                step_index=step_index
            )
            serializer = TestScreenshotSerializer(screenshot, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(
            {'error': '请提供图片文件或 base64_image'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        完成测试，更新结果

        POST /api/qa/test-results/{id}/complete/

        Request:
            - status: passed/failed/error
            - actual_result: 实际结果
            - error_message: 错误信息
            - test_log: 测试日志
            - duration_ms: 执行时长
        """
        test_result = self.get_object()

        test_result.status = request.data.get('status', 'completed')
        test_result.actual_result = request.data.get('actual_result', '')
        test_result.error_message = request.data.get('error_message', '')
        test_result.test_log = request.data.get('test_log', '')
        test_result.duration_ms = request.data.get('duration_ms')
        test_result.completed_at = timezone.now()

        # 性能指标
        test_result.response_time_ms = request.data.get('response_time_ms')
        test_result.throughput = request.data.get('throughput')
        test_result.error_rate = request.data.get('error_rate')
        test_result.concurrent_users = request.data.get('concurrent_users')

        test_result.save()

        serializer = TestResultDetailSerializer(test_result, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        获取测试统计信息

        GET /api/qa/test-results/statistics/

        Query Params:
            - project: 项目ID
            - start_date: 开始日期
            - end_date: 结束日期
        """
        queryset = self.get_queryset()

        # 按类型统计
        type_stats = {}
        test_type_choices = TestResult._meta.get_field('test_type').choices or []
        for test_type, _ in test_type_choices:
            type_count = queryset.filter(test_type=test_type).count()
            type_stats[test_type] = type_count

        # 按状态统计
        status_stats = {}
        status_choices = TestResult._meta.get_field('status').choices or []
        for status_code, _ in status_choices:
            status_count = queryset.filter(status=status_code).count()
            status_stats[status_code] = status_count

        # 总体统计
        total_count = queryset.count()
        passed_count = queryset.filter(status='passed').count()
        failed_count = queryset.filter(status='failed').count()
        error_count = queryset.filter(status='error').count()

        # 计算通过率
        completed_count = passed_count + failed_count + error_count
        pass_rate = (passed_count / completed_count * 100) if completed_count > 0 else 0

        return Response({
            'total': total_count,
            'passed': passed_count,
            'failed': failed_count,
            'error': error_count,
            'pass_rate': round(pass_rate, 2),
            'by_type': type_stats,
            'by_status': status_stats
        })

    @action(detail=False, methods=['post'])
    def create_from_ui_test(self, request):
        """
        从 UI 测试运行结果创建测试记录

        POST /api/qa/test-results/create_from_ui_test/

        Request:
            - ui_test_case_id: UI测试用例ID
            - run_result: 运行结果 {success, screenshot, logs, error}
        """
        ui_test_case_id = request.data.get('ui_test_case_id')
        run_result = request.data.get('run_result', {})

        try:
            ui_case = UiTestCase.objects.get(id=ui_test_case_id)
        except UiTestCase.DoesNotExist:
            return Response(
                {'error': 'UI测试用例不存在'},
                status=status.HTTP_404_NOT_FOUND
            )
        ensure_project_id_access(request.user, ui_case.project_id)

        # 创建测试结果记录
        test_result = TestResult.objects.create(
            test_type='ui',
            name=ui_case.name,
            project=ui_case.project,
            ui_test_case=ui_case,
            executed_by=request.user,
            status='passed' if run_result.get('success') else 'failed',
            test_steps=ui_case.steps,
            actual_result='测试完成' if run_result.get('success') else run_result.get('error', ''),
            error_message=run_result.get('error', ''),
            test_log='\n'.join(run_result.get('logs', [])),
            started_at=timezone.now(),
            completed_at=timezone.now()
        )

        # 保存截图
        screenshot_base64 = run_result.get('screenshot')
        if screenshot_base64:
            try:
                # 从 base64 字符串创建图片
                if ',' in screenshot_base64:
                    screenshot_base64 = screenshot_base64.split(',')[1]

                image_data = base64.b64decode(screenshot_base64)

                # 生成文件名
                filename = f"ui_test_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"

                # 保存到媒体目录
                screenshot_dir = os.path.join('test_screenshots', datetime.now().strftime('%Y/%m/%d'))
                full_dir = os.path.join(settings.MEDIA_ROOT, screenshot_dir)
                os.makedirs(full_dir, exist_ok=True)

                filepath = os.path.join(full_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_data)

                # 创建截图记录
                TestScreenshot.objects.create(
                    test_result=test_result,
                    name='UI测试截图',
                    description='自动化测试执行截图',
                    image=os.path.join(screenshot_dir, filename)
                )

            except Exception as e:
                print(f"保存截图失败: {e}")

        serializer = TestResultDetailSerializer(test_result, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def download_report(self, request, pk=None):
        """
        下载测试报告（预留接口，后续实现导出功能）

        GET /api/qa/test-results/{id}/download_report/
        """
        # TODO: 实现导出功能
        return Response(
            {'message': '导出功能开发中'},
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
