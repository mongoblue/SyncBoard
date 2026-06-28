"""
性能测试 API 视图。

execute 仅创建 TestResult 行并投递 Celery 任务（qa_center.tasks.run_performance_test），
真正的 Locust 子进程在 worker 中跑。stop 通过把 TestResult.aborted 置为 True 通知 worker 退出。
"""

from urllib.parse import urlparse

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import PerformanceTestCase, PerformanceTestResult, TestResult
from .serializers import (
    PerformanceTestCaseSerializer,
    PerformanceTestCaseListSerializer,
    PerformanceTestResultSerializer,
    PerformanceTestResultListSerializer,
)
from .tasks import run_performance_test


class PerformanceTestCaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = PerformanceTestCase.objects.all()

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        keyword = self.request.query_params.get('keyword')
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)

        return queryset.select_related('project', 'created_by')

    def get_serializer_class(self):
        if self.action == 'list':
            return PerformanceTestCaseListSerializer
        return PerformanceTestCaseSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        test_case = self.get_object()

        users = request.data.get('users', test_case.concurrent_users)
        spawn_rate = request.data.get('spawn_rate', max(1, int(users) // 10))
        run_time = request.data.get('run_time', f"{test_case.duration_seconds}s")

        parsed_url = urlparse(test_case.url)
        host = f"{parsed_url.scheme}://{parsed_url.netloc}" or test_case.url

        test_result = TestResult.objects.create(
            test_type='performance',
            name=test_case.name,
            project=test_case.project,
            status='running',
            executed_by=request.user,
            started_at=timezone.now(),
            concurrent_users=users,
            test_params={
                'users': users,
                'spawn_rate': spawn_rate,
                'run_time': run_time,
                'url': test_case.url,
                'method': test_case.method,
            },
        )

        run_performance_test.delay(
            execution_id=test_result.id,
            test_case_id=test_case.id,
            host=host,
            users=int(users),
            spawn_rate=int(spawn_rate),
            run_time=str(run_time),
        )

        return Response({
            'message': '测试已启动',
            'execution_id': test_result.id,
            'status': 'running',
            'ws_channel': f'performance_test_{test_result.id}',
        })

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        execution_id = request.data.get('execution_id')
        if not execution_id:
            return Response({'error': '缺少 execution_id'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            test_result = TestResult.objects.get(id=execution_id)
        except TestResult.DoesNotExist:
            return Response({'error': '未找到测试记录'}, status=status.HTTP_404_NOT_FOUND)

        if test_result.status in ('passed', 'failed', 'error') or test_result.aborted:
            return Response({'message': f'测试已处于终态：{test_result.status}'})

        test_result.aborted = True
        test_result.completed_at = timezone.now()
        if test_result.started_at:
            duration = (test_result.completed_at - test_result.started_at).total_seconds() * 1000
            test_result.duration_ms = int(duration)
        test_result.save()
        return Response({'message': '压力测试已停止'})

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        execution_id = request.query_params.get('execution_id')
        if not execution_id:
            return Response({'state': 'not_found', 'is_running': False})

        try:
            test_result = TestResult.objects.get(id=execution_id)
        except TestResult.DoesNotExist:
            return Response({
                'execution_id': execution_id,
                'state': 'not_found',
                'is_running': False,
            })

        return Response({
            'execution_id': execution_id,
            'state': test_result.status,
            'is_running': test_result.status == 'running',
            'avg_response_time': test_result.response_time_ms,
            'throughput': test_result.throughput,
            'error_rate': test_result.error_rate,
        })

    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        test_case = self.get_object()
        results = PerformanceTestResult.objects.filter(test_case=test_case)

        limit = int(request.query_params.get('limit', 20))
        results = results[:limit]

        serializer = PerformanceTestResultListSerializer(results, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='linked-tasks')
    def linked_tasks(self, request, pk=None):
        test_case = self.get_object()
        tasks = test_case.related_tasks.select_related('column', 'assignee').prefetch_related('tags')
        from room.serializers import TaskSerializer
        return Response(TaskSerializer(tasks, many=True).data)


class PerformanceTestResultViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PerformanceTestResultSerializer

    def get_queryset(self):
        queryset = PerformanceTestResult.objects.all()

        test_case_id = self.request.query_params.get('test_case')
        if test_case_id:
            queryset = queryset.filter(test_case_id=test_case_id)

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(test_case__project_id=project_id)

        return queryset.select_related('test_case', 'executed_by')
