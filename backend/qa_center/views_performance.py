"""
性能测试 API 视图。

execute 创建 TestResult 并通过 ExecutionEngine 执行：
- 生产环境（USE_CELERY_TASKS=True）：async_mode=True → Celery 异步
- 开发环境（USE_CELERY_TASKS=False）：async_mode=False → 后台线程同步
stop 通过把 TestResult.aborted 置为 True 通知 worker 退出。
"""

import threading
from typing import Optional
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import PerformanceTestCase, PerformanceTestResult, TestResult
from .serializers import (
    PerformanceTestCaseSerializer,
    PerformanceTestCaseListSerializer,
    PerformanceTestResultSerializer,
    PerformanceTestResultListSerializer,
)
from .execution.job import TestJob
from .execution.engine import ExecutionEngine
from .execution.lifecycle import LifecycleState, LIFECYCLE_LABELS
from qa_center import audit
from room.project_access import ensure_project_id_access, project_access_q


def _validate_perf_request(data: dict, user) -> Optional[Response]:
    """校验压测请求参数是否在允许范围内。

    Returns:
        None 表示通过，Response 表示校验失败。
    """
    from django.conf import settings

    users = int(data.get('users', 10))
    run_time_str = str(data.get('run_time', '60s')).lower().rstrip('s')
    try:
        duration = int(run_time_str)
    except (ValueError, TypeError):
        duration = 60

    body = str(data.get('body', '') or '')
    headers = data.get('headers', {}) or {}
    url = str(data.get('url', '') or '')

    max_users = getattr(settings, 'PERF_MAX_USERS_PER_TEST', 10000)
    max_duration = getattr(settings, 'PERF_MAX_DURATION_SECONDS', 3600)
    max_body = getattr(settings, 'PERF_MAX_BODY_BYTES', 1024 * 1024)
    max_headers = getattr(settings, 'PERF_MAX_HEADERS_COUNT', 50)

    if users > max_users:
        return Response(
            {'error': f'并发用户数超过上限 ({max_users})'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if duration > max_duration:
        return Response(
            {'error': f'持续时间超过上限 ({max_duration}s)'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(body.encode('utf-8')) > max_body:
        return Response(
            {'error': f'请求体大小超过上限 ({max_body} bytes)'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(headers, dict) and len(headers) > max_headers:
        return Response(
            {'error': f'请求头数量超过上限 ({max_headers})'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # URL scheme 校验
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return Response(
            {'error': f'不支持的 URL scheme: {parsed.scheme}（仅允许 http/https）'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None


def _execute_sync_in_thread(job: TestJob) -> None:
    """在后台线程中同步执行压测（开发环境 fallback）。

    线程内异常不传播到 Web 请求——错误已写入 TestResult.error_message。
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        engine = ExecutionEngine()
        engine.submit(job)
    except Exception as exc:
        logger.exception("后台线程压测异常 execution_id=%s", job.execution_id)


class PerformanceTestCaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = PerformanceTestCase.objects.filter(
            project_access_q('project', self.request.user)
        ).distinct()

        project_id = self.request.query_params.get('project')
        if project_id:
            ensure_project_id_access(self.request.user, project_id)
            queryset = queryset.filter(project_id=project_id)

        keyword = self.request.query_params.get('keyword')
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)

        return queryset.select_related('project', 'created_by')

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        obj = get_object_or_404(
            PerformanceTestCase.objects.select_related('project', 'created_by'),
            **{self.lookup_field: self.kwargs[lookup_url_kwarg]},
        )
        ensure_project_id_access(self.request.user, obj.project_id)
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        if self.action == 'list':
            return PerformanceTestCaseListSerializer
        return PerformanceTestCaseSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            ensure_project_id_access(self.request.user, project.id)
        serializer.save(created_by=self.request.user)

    def _get_case_execution(self, test_case, execution_id):
        try:
            test_result = TestResult.objects.get(id=execution_id)
        except TestResult.DoesNotExist:
            return None

        if test_result.test_type != 'performance' or test_result.project_id != test_case.project_id:
            raise PermissionDenied('无权访问该性能测试执行记录')

        test_params = test_result.test_params or {}
        test_case_id = test_params.get('test_case_id')
        if test_case_id is not None and str(test_case_id) != str(test_case.id):
            raise PermissionDenied('无权访问该性能测试执行记录')

        return test_result

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """启动性能测试。

        生产环境（USE_CELERY_TASKS=True）→ Celery 异步执行。
        开发环境（USE_CELERY_TASKS=False）→ 后台线程同步执行。
        """
        test_case = self.get_object()

        users = request.data.get('users', test_case.concurrent_users)
        spawn_rate = request.data.get('spawn_rate', max(1, int(users) // 10))
        run_time = request.data.get('run_time', f"{test_case.duration_seconds}s")

        # ── API 层参数校验 ────────────────────────────────────
        validation_error = _validate_perf_request({
            'users': users,
            'run_time': str(run_time),
            'body': test_case.body or '',
            'headers': test_case.headers or {},
            'url': test_case.url or '',
        }, request.user)
        if validation_error:
            return validation_error

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
                'test_case_id': test_case.id,
                'users': users,
                'spawn_rate': spawn_rate,
                'run_time': run_time,
                'url': test_case.url,
                'method': test_case.method,
            },
        )

        use_celery = getattr(settings, 'USE_CELERY_TASKS', False)

        if use_celery:
            # 生产路径：Celery 异步
            job = TestJob(
                test_case=test_case, host=host,
                users=int(users), spawn_rate=int(spawn_rate),
                run_time=str(run_time),
                async_mode=True,
                execution_id=test_result.id,
                project=test_case.project, user=request.user,
                source='single',
            )
            engine = ExecutionEngine()
            engine.submit(job)
        else:
            # 开发路径：后台线程同步执行（不阻塞 Web 响应）
            job = TestJob(
                test_case=test_case, host=host,
                users=int(users), spawn_rate=int(spawn_rate),
                run_time=str(run_time),
                async_mode=False,
                execution_id=test_result.id,
                project=test_case.project, user=request.user,
                source='single',
            )
            thread = threading.Thread(
                target=_execute_sync_in_thread,
                args=(job,),
                daemon=True,
            )
            thread.start()

        return Response({
            'message': '测试已启动',
            'execution_id': test_result.id,
            'status': 'running',
            'ws_channel': f'performance_test_{test_result.id}',
        })

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        test_case = self.get_object()
        execution_id = request.data.get('execution_id')
        if not execution_id:
            return Response({'error': '缺少 execution_id'}, status=status.HTTP_400_BAD_REQUEST)

        test_result = self._get_case_execution(test_case, execution_id)
        if test_result is None:
            return Response({'error': '未找到测试记录'}, status=status.HTTP_404_NOT_FOUND)

        if test_result.status in ('passed', 'failed', 'error') or test_result.aborted:
            return Response({'message': f'测试已处于终态：{test_result.status}'})

        test_result.aborted = True
        test_result.completed_at = timezone.now()
        if test_result.started_at:
            duration = (test_result.completed_at - test_result.started_at).total_seconds() * 1000
            test_result.duration_ms = int(duration)
        test_result.save()
        audit.log_test_stopped(
            execution_id=execution_id,
            user=str(request.user),
            reason='user_requested',
        )
        return Response({'message': '压力测试已停止'})

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        test_case = self.get_object()
        execution_id = request.query_params.get('execution_id')
        if not execution_id:
            return Response({'state': 'not_found', 'is_running': False})

        test_result = self._get_case_execution(test_case, execution_id)
        if test_result is None:
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

    @action(detail=True, methods=['get'], url_path='execution-logs')
    def execution_logs(self, request, pk=None):
        """获取某次执行的 Locust stdout/stderr 日志（最后 N 行）。

        仅接受已存在的 execution_id。用于前端展示诊断信息。
        """
        test_case = self.get_object()
        execution_id = request.query_params.get('execution_id')
        if not execution_id:
            return Response({'error': '缺少 execution_id'}, status=status.HTTP_400_BAD_REQUEST)

        test_result = self._get_case_execution(test_case, execution_id)
        if test_result is None:
            return Response({'error': '未找到测试记录'}, status=status.HTTP_404_NOT_FOUND)

        lines = int(request.query_params.get('lines', 100))
        log_type = request.query_params.get('type', 'both')  # stdout, stderr, both

        import os
        import tempfile

        base_temp = os.path.join(tempfile.gettempdir(), 'syncboard-locust')
        stdout_path = os.path.join(base_temp, f'locust_stdout_{execution_id}.log')
        stderr_path = os.path.join(base_temp, f'locust_stderr_{execution_id}.log')

        result = {}

        def _read_tail(path):
            if not os.path.exists(path):
                return None
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    all_lines = f.readlines()
                    return ''.join(all_lines[-lines:])
            except Exception:
                return None

        if log_type in ('stdout', 'both'):
            content = _read_tail(stdout_path)
            result['stdout'] = content
            result['stdout_path'] = stdout_path if content is not None else None

        if log_type in ('stderr', 'both'):
            content = _read_tail(stderr_path)
            result['stderr'] = content
            result['stderr_path'] = stderr_path if content is not None else None

        return Response(result)


# ── 独立 debug 视图：GET /qa/performance-runs/{execution_id}/debug/ ──

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def performance_run_debug(request, execution_id):
    """返回一次性能测试执行的完整诊断信息。

    URL: GET /qa/performance-runs/{execution_id}/debug/
    """
    from django.shortcuts import get_object_or_404
    from room.project_access import ensure_project_id_access

    test_result = get_object_or_404(
        TestResult.objects.select_related('project', 'executed_by'),
        id=execution_id,
        test_type='performance',
    )

    if test_result.project:
        ensure_project_id_access(request.user, test_result.project_id)
    elif not request.user.is_staff:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied('无权访问该执行记录')

    # ── 读取 Locust 日志 ─────────────────────────────────────────
    import os
    import tempfile

    base_temp = os.path.join(tempfile.gettempdir(), 'syncboard-locust')
    stdout_path = os.path.join(base_temp, f'locust_stdout_{execution_id}.log')
    stderr_path = os.path.join(base_temp, f'locust_stderr_{execution_id}.log')

    def _read_file(path):
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception:
            return None

    return Response({
        'execution_id': execution_id,
        'test_type': test_result.test_type,
        'name': test_result.name,
        'status': test_result.status,
        'lifecycle_state': test_result.lifecycle_state,
        'lifecycle_label': LIFECYCLE_LABELS.get(
            LifecycleState(test_result.lifecycle_state), test_result.lifecycle_state
        ) if test_result.lifecycle_state else None,
        'lifecycle_reason': test_result.lifecycle_reason,
        'error_message': test_result.error_message,
        'error_code': test_result.error_code,
        'started_at': test_result.started_at,
        'completed_at': test_result.completed_at,
        'duration_ms': test_result.duration_ms,
        'test_params': test_result.test_params,
        'throughput': test_result.throughput,
        'error_rate': test_result.error_rate,
        'response_time_ms': test_result.response_time_ms,
        'concurrent_users': test_result.concurrent_users,
        'aborted': test_result.aborted,
        'stdout_log': _read_file(stdout_path),
        'stderr_log': _read_file(stderr_path),
        'stdout_log_path': stdout_path,
        'stderr_log_path': stderr_path,
    })


class PerformanceTestResultViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PerformanceTestResultSerializer

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        obj = get_object_or_404(
            PerformanceTestResult.objects.select_related(
                'test_case', 'test_case__project', 'executed_by', 'test_result'
            ),
            **{self.lookup_field: self.kwargs[lookup_url_kwarg]},
        )
        ensure_project_id_access(self.request.user, obj.test_case.project_id)
        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        queryset = (
            PerformanceTestResult.objects
            .select_related('test_case', 'test_case__project', 'executed_by', 'test_result')
            .filter(project_access_q('test_case__project', self.request.user))
            .distinct()
        )

        test_case_id = self.request.query_params.get('test_case')
        if test_case_id:
            test_case = get_object_or_404(PerformanceTestCase, id=test_case_id)
            ensure_project_id_access(self.request.user, test_case.project_id)
            queryset = queryset.filter(test_case_id=test_case_id)

        project_id = self.request.query_params.get('project')
        if project_id:
            ensure_project_id_access(self.request.user, project_id)
            queryset = queryset.filter(test_case__project_id=project_id)

        return queryset
