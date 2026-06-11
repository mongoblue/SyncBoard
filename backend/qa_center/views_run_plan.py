"""TestRunPlan ViewSet — 批量执行计划增删改查 + 触发执行。"""
import threading
import logging

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import TestRunPlan, ApiAutoTestCase
from .serializers import TestRunPlanSerializer, TestRunPlanExecuteSerializer
from .run_plan_executor import run_plan

logger = logging.getLogger(__name__)


class TestRunPlanViewSet(viewsets.ModelViewSet):
    """批量执行计划。

    GET    /api/qa/run-plans/                列表（支持 project / search）
    POST   /api/qa/run-plans/                创建
    GET    /api/qa/run-plans/{id}/           详情
    PATCH  /api/qa/run-plans/{id}/           更新
    DELETE /api/qa/run-plans/{id}/           删除
    POST   /api/qa/run-plans/{id}/execute/   触发执行（异步线程）
    GET    /api/qa/run-plans/cases/?project= 列出项目下可选用例（轻量）
    """

    serializer_class = TestRunPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = TestRunPlan.objects.select_related('project', 'created_by').all()
        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        plan = self.get_object()
        ser = TestRunPlanExecuteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        overrides = ser.validated_data

        # 异步执行，立即返回 result_id 占位会比较复杂；这里同步创建 ApiAutoTestResult，
        # 然后在线程里跑实际请求。前端通过 WebSocket 跟进进度。
        # 不过为了简化先实现：开线程后立刻返回 202，前端订阅 run_plan_progress。
        user = request.user if request.user.is_authenticated else None

        def _runner():
            try:
                run_plan(
                    plan.id, user=user,
                    parallel=overrides.get('parallel'),
                    max_workers=overrides.get('max_workers'),
                    stop_on_failure=overrides.get('stop_on_failure'),
                    environment_id=overrides.get('environment_id'),
                )
            except Exception as e:  # pragma: no cover
                logger.exception('[RunPlan] background execute failed: %s', e)

        t = threading.Thread(target=_runner, name=f'runplan-{plan.id}', daemon=True)
        t.start()

        return Response(
            {
                'detail': '已开始执行，请通过 WebSocket /ws/qa/dashboard/ 订阅 run_plan_progress 事件',
                'plan_id': plan.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=['get'])
    def cases(self, request):
        """供前端"批量勾选"用：返回项目下所有启用的 ApiAutoTestCase 轻量列表。"""
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'detail': 'project 必填'}, status=400)
        search = request.query_params.get('search', '').strip()
        qs = (
            ApiAutoTestCase.objects
            .filter(suite__project_id=project_id, is_active=True)
            .select_related('suite')
            .order_by('suite__name', 'sort_order', 'id')
        )
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(url__icontains=search))
        data = [
            {
                'id': c.id,
                'name': c.name,
                'method': c.method,
                'url': c.url,
                'suite_id': c.suite_id,
                'suite_name': c.suite.name,
            }
            for c in qs[:500]
        ]
        return Response({'count': len(data), 'results': data})
