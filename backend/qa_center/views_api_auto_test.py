from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django.utils import timezone
import json

from .models import (
    ApiAutoTestSuite, ApiAutoTestCase, ApiAutoTestAssertion,
    ApiAutoTestResult, ApiAutoTestCaseResult,
    ApiAutoTestExtractor,
)
from .serializers import (
    ApiAutoTestSuiteSerializer, ApiAutoTestSuiteListSerializer,
    ApiAutoTestCaseSerializer, ApiAutoTestCaseListSerializer,
    ApiAutoTestAssertionSerializer,
    ApiAutoTestResultSerializer, ApiAutoTestResultListSerializer,
    ApiAutoTestCaseResultSerializer, ApiAutoTestCaseResultBriefSerializer,
    ApiAutoTestExecuteSerializer,
    ApiAutoTestExtractorSerializer,
)
from .api_auto_executor import run_api_auto_test


class ApiAutoTestSuiteViewSet(viewsets.ModelViewSet):
    queryset = ApiAutoTestSuite.objects.all()
    serializer_class = ApiAutoTestSuiteSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ApiAutoTestSuiteListSerializer
        return ApiAutoTestSuiteSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        suite = self.get_object()
        executor = run_api_auto_test(suite.id, request.user)
        serializer = ApiAutoTestResultSerializer(executor)
        return Response({
            'message': 'Test execution completed',
            'result': serializer.data
        })

    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        suite = self.get_object()
        results = suite.test_results.all()[:50]
        serializer = ApiAutoTestResultListSerializer(results, many=True)
        return Response(serializer.data)


class ApiAutoTestCaseViewSet(viewsets.ModelViewSet):
    queryset = ApiAutoTestCase.objects.all()
    serializer_class = ApiAutoTestCaseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        suite_id = self.request.query_params.get('suite')
        if suite_id:
            queryset = queryset.filter(suite_id=suite_id)
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(url__icontains=search))
        return queryset.order_by('sort_order', '-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ApiAutoTestCaseListSerializer
        return ApiAutoTestCaseSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        case = self.get_object()
        from .api_auto_executor import ApiAutoTestExecutor
        from .models import ApiAutoTestResult

        suite = case.suite
        test_result = ApiAutoTestResult.objects.create(
            suite=suite,
            name=f"{case.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
            status='running',
            total_cases=1,
            executed_by=request.user,
            started_at=timezone.now()
        )

        executor = ApiAutoTestExecutor(suite.id, request.user)
        executor.test_result = test_result
        case_result = executor._execute_case(case)

        test_result.passed_cases = 1 if case_result.passed else 0
        test_result.failed_cases = 0 if case_result.passed else 1
        test_result.duration_ms = case_result.response_time_ms
        test_result.status = 'passed' if case_result.passed else 'failed'
        test_result.completed_at = timezone.now()
        test_result.save()

        serializer = ApiAutoTestCaseResultSerializer(case_result)
        return Response({
            'message': 'Case execution completed',
            'result': serializer.data
        })

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        deleted_count = ApiAutoTestCase.objects.filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted_count})

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        ordering = request.data.get('ordering', [])
        for item in ordering:
            ApiAutoTestCase.objects.filter(id=item['id']).update(sort_order=item.get('sort_order', 0))
        return Response({'message': 'Ordering updated'})


class ApiAutoTestAssertionViewSet(viewsets.ModelViewSet):
    queryset = ApiAutoTestAssertion.objects.all()
    serializer_class = ApiAutoTestAssertionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        case_id = self.request.query_params.get('case')
        if case_id:
            queryset = queryset.filter(case_id=case_id)
        assertion_type = self.request.query_params.get('assertion_type')
        if assertion_type:
            queryset = queryset.filter(assertion_type=assertion_type)
        return queryset.order_by('sort_order', 'id')

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        deleted_count = ApiAutoTestAssertion.objects.filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted_count})

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        ordering = request.data.get('ordering', [])
        for item in ordering:
            ApiAutoTestAssertion.objects.filter(id=item['id']).update(sort_order=item.get('sort_order', 0))
        return Response({'message': 'Ordering updated'})


class ApiAutoTestExtractorViewSet(viewsets.ModelViewSet):
    """变量抽取器 ViewSet —— M3.3。

    GET    /api/qa/auto-extractors/?case=<id>   列出某用例的抽取器
    POST   /api/qa/auto-extractors/             创建
    PATCH  /api/qa/auto-extractors/{id}/        更新
    DELETE /api/qa/auto-extractors/{id}/        删除
    POST   /api/qa/auto-extractors/bulk_delete/ 批量删除
    POST   /api/qa/auto-extractors/reorder/     调整顺序
    """
    queryset = ApiAutoTestExtractor.objects.all()
    serializer_class = ApiAutoTestExtractorSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        source = self.request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)
        return qs.order_by('sort_order', 'id')

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        deleted = ApiAutoTestExtractor.objects.filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted})

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        ordering = request.data.get('ordering', [])
        for item in ordering:
            ApiAutoTestExtractor.objects.filter(id=item['id']).update(sort_order=item.get('sort_order', 0))
        return Response({'message': 'Ordering updated'})


class ApiAutoTestResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApiAutoTestResult.objects.all()
    serializer_class = ApiAutoTestResultSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        suite_id = self.request.query_params.get('suite')
        if suite_id:
            queryset = queryset.filter(suite_id=suite_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(suite__project_id=project_id)
        return queryset.select_related('suite', 'executed_by').order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ApiAutoTestResultListSerializer
        return ApiAutoTestResultSerializer

    @action(detail=True, methods=['get'])
    def details(self, request, pk=None):
        result = self.get_object()
        case_results = result.case_results.select_related('case').all()
        serializer = ApiAutoTestCaseResultSerializer(case_results, many=True)
        return Response({
            'summary': ApiAutoTestResultSerializer(result).data,
            'case_results': serializer.data
        })

    @action(detail=True, methods=['get'])
    def cases(self, request, pk=None):
        """分页 + 过滤 + 排序的用例结果明细。

        Query params:
        - passed=true|false  按通过/失败过滤
        - search=xxx         按 case_name / case_url 模糊匹配
        - ordering=-response_time_ms / executed_at  排序字段
        - page=N / page_size=M
        """
        result = self.get_object()
        qs = result.case_results.select_related('case')

        passed = request.query_params.get('passed')
        if passed is not None and passed != '':
            qs = qs.filter(passed=passed.lower() == 'true')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(case__name__icontains=search) | Q(case__url__icontains=search))

        ordering = request.query_params.get('ordering', 'executed_at')
        allowed = {
            'executed_at', '-executed_at',
            'response_time_ms', '-response_time_ms',
            'status_code', '-status_code',
            'passed', '-passed',
        }
        if ordering in allowed:
            qs = qs.order_by(ordering)
        else:
            qs = qs.order_by('executed_at')

        page = self.paginate_queryset(qs)
        if page is not None:
            data = ApiAutoTestCaseResultBriefSerializer(page, many=True).data
            return self.get_paginated_response(data)
        return Response(ApiAutoTestCaseResultBriefSerializer(qs, many=True).data)

    @action(detail=True, methods=['get'])
    def case_detail(self, request, pk=None):
        """获取某一条 case_result 的完整详情（含 response_body / headers / 全部断言）。

        ?case_result_id=... 必填。放在 detail action 下是为了校验它属于该 result。
        """
        result = self.get_object()
        case_result_id = request.query_params.get('case_result_id')
        if not case_result_id:
            return Response({'detail': 'case_result_id 必填'}, status=400)
        try:
            cr = result.case_results.select_related('case').get(id=case_result_id)
        except ApiAutoTestCaseResult.DoesNotExist:
            return Response({'detail': '未找到'}, status=404)
        return Response(ApiAutoTestCaseResultSerializer(cr).data)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        deleted_count = ApiAutoTestResult.objects.filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted_count})


class ApiAutoTestExecuteView(APIView):
    def post(self, request):
        serializer = ApiAutoTestExecuteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        suite_id = serializer.validated_data['suite_id']
        try:
            test_result = run_api_auto_test(suite_id, request.user)
            result_serializer = ApiAutoTestResultSerializer(test_result)
            return Response({
                'message': 'Test execution completed',
                'result': result_serializer.data
            })
        except Exception as e:
            return Response({
                'message': 'Test execution failed',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApiAutoTestCaseResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApiAutoTestCaseResult.objects.all()
    serializer_class = ApiAutoTestCaseResultSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        test_result_id = self.request.query_params.get('test_result')
        if test_result_id:
            queryset = queryset.filter(test_result_id=test_result_id)
        case_id = self.request.query_params.get('case')
        if case_id:
            queryset = queryset.filter(case_id=case_id)
        passed = self.request.query_params.get('passed')
        if passed is not None:
            queryset = queryset.filter(passed=passed.lower() == 'true')
        return queryset.select_related('case', 'test_result').order_by('executed_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ApiAutoTestCaseResultSerializer
        return ApiAutoTestCaseResultSerializer
