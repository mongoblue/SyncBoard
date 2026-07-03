from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
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
from .api_execution.orchestrators import (
    create_api_auto_single_case_orchestrator,
    create_api_auto_suite_orchestrator,
)
from .api_execution.runtime_guard import RuntimeGuard
from .feature_flags import (
    use_unified_runner_for_api_auto_case,
    use_unified_runner_for_api_auto_suite,
)
from room.project_access import ensure_project_id_access, project_access_q


def _create_single_case_test_result(*, case, user):
    project = case.project or (case.suite.project if case.suite_id else None)
    return ApiAutoTestResult.objects.create(
        suite=case.suite,
        project=project,
        name=f"{case.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
        status='running',
        total_cases=1,
        executed_by=user,
        started_at=timezone.now()
    )


def _execute_single_case_unified(*, case, user):
    test_result = _create_single_case_test_result(case=case, user=user)
    orchestrator = create_api_auto_single_case_orchestrator(
        case=case,
        user=user,
        test_result=test_result,
    )
    return orchestrator.execute()


def _execute_suite_unified(*, suite, user):
    orchestrator = create_api_auto_suite_orchestrator(
        suite=suite,
        user=user,
    )
    return orchestrator.execute()


class ProjectScopedViewSetMixin:
    permission_classes = [IsAuthenticated]

    def _accessible_project_q(self, project_path='project'):
        return project_access_q(project_path, self.request.user)

    def _ensure_query_project_access(self):
        project_id = self.request.query_params.get('project')
        if project_id:
            ensure_project_id_access(self.request.user, project_id)


class _CaseResultsPagination(PageNumberPagination):
    """允许 ?page_size=N 覆盖默认值,用于 cases 明细分页。"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


class ApiAutoTestSuiteViewSet(ProjectScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ApiAutoTestSuite.objects.all()
    serializer_class = ApiAutoTestSuiteSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(self._accessible_project_q('project')).distinct()
        project_id = self.request.query_params.get('project')
        if project_id:
            self._ensure_query_project_access()
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
        ensure_project_id_access(self.request.user, serializer.validated_data['project'].id)
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        suite = self.get_object()
        guard = RuntimeGuard()
        outcome = _execute_suite_unified(suite=suite, user=request.user)
        serializer = ApiAutoTestResultSerializer(outcome["test_result"])
        return Response({
            'message': 'Test execution completed',
            'runtime_mode': outcome.get('runtime_mode', 'real'),
            'result': serializer.data
        })

    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        suite = self.get_object()
        results = suite.test_results.all()[:50]
        serializer = ApiAutoTestResultListSerializer(results, many=True)
        return Response(serializer.data)


class ApiAutoTestCaseViewSet(ProjectScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ApiAutoTestCase.objects.all()
    serializer_class = ApiAutoTestCaseSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(
            self._accessible_project_q('project') | self._accessible_project_q('suite__project')
        ).distinct()
        suite_id = self.request.query_params.get('suite')
        if suite_id:
            queryset = queryset.filter(suite_id=suite_id)
        project_id = self.request.query_params.get('project')
        if project_id:
            self._ensure_query_project_access()
            queryset = queryset.filter(Q(project_id=project_id) | Q(suite__project_id=project_id))
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
        project = serializer.validated_data.get('project')
        if project is None:
            suite = serializer.validated_data.get('suite')
            if suite is not None:
                project = suite.project
        if project is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError('project 或 suite 至少需要提供一个')
        ensure_project_id_access(self.request.user, project.id)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        project = serializer.validated_data.get('project') or serializer.instance.project
        if project is None and serializer.instance.suite_id:
            project = serializer.instance.suite.project
        if project is not None:
            ensure_project_id_access(self.request.user, project.id)
        serializer.save()

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        case = self.get_object()
        outcome = _execute_single_case_unified(case=case, user=request.user)
        test_result = outcome.get('test_result')
        case_result = outcome.get('case_result')
        return Response({
            'message': 'Test execution completed',
            'runtime_mode': outcome.get('runtime_mode'),
            'result_id': test_result.id if test_result else None,
            'case_result_id': case_result.id if case_result else None,
            'status': test_result.status if test_result else None,
        })

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        deleted_count = self.get_queryset().filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted_count})

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        ordering = request.data.get('ordering', [])
        accessible = self.get_queryset()
        for item in ordering:
            accessible.filter(id=item['id']).update(sort_order=item.get('sort_order', 0))
        return Response({'message': 'Ordering updated'})


class ApiAutoTestAssertionViewSet(ProjectScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ApiAutoTestAssertion.objects.all()
    serializer_class = ApiAutoTestAssertionSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(
            self._accessible_project_q('case__project') | self._accessible_project_q('case__suite__project')
        ).distinct()
        case_id = self.request.query_params.get('case')
        if case_id:
            queryset = queryset.filter(case_id=case_id)
        assertion_type = self.request.query_params.get('assertion_type')
        if assertion_type:
            queryset = queryset.filter(assertion_type=assertion_type)
        return queryset.order_by('sort_order', 'id')

    def perform_create(self, serializer):
        case = serializer.validated_data['case']
        project = case.project or (case.suite.project if case.suite_id else None)
        ensure_project_id_access(self.request.user, project.id)
        serializer.save()

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        deleted_count = self.get_queryset().filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted_count})

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        ordering = request.data.get('ordering', [])
        accessible = self.get_queryset()
        for item in ordering:
            accessible.filter(id=item['id']).update(sort_order=item.get('sort_order', 0))
        return Response({'message': 'Ordering updated'})


class ApiAutoTestExtractorViewSet(ProjectScopedViewSetMixin, viewsets.ModelViewSet):
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
        qs = super().get_queryset().filter(
            self._accessible_project_q('case__project') | self._accessible_project_q('case__suite__project')
        ).distinct()
        case_id = self.request.query_params.get('case')
        if case_id:
            qs = qs.filter(case_id=case_id)
        source = self.request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)
        return qs.order_by('sort_order', 'id')

    def perform_create(self, serializer):
        case = serializer.validated_data['case']
        project = case.project or (case.suite.project if case.suite_id else None)
        ensure_project_id_access(self.request.user, project.id)
        serializer.save()

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        deleted = self.get_queryset().filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted})

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        ordering = request.data.get('ordering', [])
        accessible = self.get_queryset()
        for item in ordering:
            accessible.filter(id=item['id']).update(sort_order=item.get('sort_order', 0))
        return Response({'message': 'Ordering updated'})


class ApiAutoTestResultViewSet(ProjectScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ApiAutoTestResult.objects.all()
    serializer_class = ApiAutoTestResultSerializer

    @property
    def paginator(self):
        # cases action 用自定义分页器(允许 ?page_size=N)
        if getattr(self, 'action', None) == 'cases':
            if not hasattr(self, '_cases_paginator'):
                self._cases_paginator = _CaseResultsPagination()
            return self._cases_paginator
        return super().paginator

    def get_queryset(self):
        from django.db.models import Q
        # P1 后 result 直接挂 project，但也可能走 suite（批次执行）。两者都查。
        q = self._accessible_project_q('project') | self._accessible_project_q('suite__project')
        queryset = super().get_queryset().filter(q).distinct()
        suite_id = self.request.query_params.get('suite')
        if suite_id:
            queryset = queryset.filter(suite_id=suite_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        project_id = self.request.query_params.get('project')
        if project_id:
            self._ensure_query_project_access()
            queryset = queryset.filter(Q(project_id=project_id) | Q(suite__project_id=project_id))
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
        - search=xxx         指case_name / case_url 模糊匹配
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
        deleted_count = self.get_queryset().filter(id__in=ids).delete()[0]
        return Response({'deleted': deleted_count})


class ApiAutoTestExecuteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ApiAutoTestExecuteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        suite_id = serializer.validated_data['suite_id']
        try:
            suite = ApiAutoTestSuite.objects.select_related('project').get(id=suite_id, is_active=True)
            ensure_project_id_access(request.user, suite.project_id)
            guard = RuntimeGuard()
            if not use_unified_runner_for_api_auto_suite() and guard.is_strict():
                return Response(
                    {
                        'detail': 'Unified runner is required for this entrypoint in strict environments',
                        'error_code': 'runner_required',
                        'runtime_mode': guard.build_runtime_mode(guarded_rejected=True),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            outcome = _execute_suite_unified(suite=suite, user=request.user)
            result_serializer = ApiAutoTestResultSerializer(outcome["test_result"])
            return Response({
                'message': 'Test execution completed',
                'runtime_mode': outcome.get('runtime_mode', 'real'),
                'result': result_serializer.data
            })
        except Exception as e:
            return Response({
                'message': 'Test execution failed',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApiAutoTestCaseResultViewSet(ProjectScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ApiAutoTestCaseResult.objects.all()
    serializer_class = ApiAutoTestCaseResultSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(self._accessible_project_q('test_result__project')).distinct()
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
