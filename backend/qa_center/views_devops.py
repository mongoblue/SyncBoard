"""
DevOps 测试平台 API 视图
提供仪表板统计、最近执行记录、CI/CD集成配置、测试任务管理等功能
"""

import json
import hmac
import re
import threading
import time
from datetime import datetime, timedelta
from django.conf import settings
from django.db.models import Count, Q, Avg
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError

from room.project_access import ensure_project_id_access, project_access_q
from .models import (
    TestResult, ApiAutoTestCase, UiTestCase, TestTask, CiCdConfig,
    PipelineRun, PerformanceTestResult,
)
from .api_execution.runtime_guard import RuntimeGuard
from .feature_flags import use_unified_runner_for_async_triggers
from .webhooks import (
    verify_webhook_signature,
    check_webhook_dedup,
    check_webhook_rate_limit,
    compute_webhook_payload_hash,
    log_webhook_audit,
)
from .serializers import (
    TestResultListSerializer,
    TestTaskListSerializer, TestTaskDetailSerializer,
    TestTaskCreateSerializer, TestTaskUpdateSerializer,
    PerformanceTestResultSerializer, PerformanceTestResultListSerializer,
    CiCdConfigSerializer,
    validate_test_task_config_cases,
)
import logging

logger = logging.getLogger(__name__)


def _execute_api_cases_via_unified(case_ids, task_id='', parent_result=None):
    """通过 unified runner 执行 API 用例列表，返回结果 dict 列表。

    用于 DevOps 测试任务的后台执行路径（替代已删除的 execute_api_test_cases）。

    parent_result: 可选，传入后所有 case 的 ApiAutoTestCaseResult 归属到该父级，
    不在单个 case 级别调用 sync / mirror。最终由调用方对 parent_result 统一同步。
    """
    from .api_execution.orchestrators import create_api_auto_single_case_orchestrator
    from .models import ApiAutoTestResult, ApiAutoTestCaseResult, TestResult
    from .result_sink import mirror_to_test_result as _mirror, \
        sync_unified_run_from_auto_result as _sync_unified, _select_preferred_mirror

    is_batch = parent_result is not None
    results = []
    passed_count = 0
    failed_count = 0
    cases = list(ApiAutoTestCase.objects.filter(id__in=case_ids).select_related('project', 'environment', 'suite'))
    for case in cases:
        test_result = ApiAutoTestResult.objects.create(
            suite=case.suite,
            project=case.project or (case.suite.project if case.suite_id else None),
            name=f"{case.name}_devops_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
            status='running',
            total_cases=1,
            executed_by=None,
            started_at=timezone.now(),
        )
        try:
            orchestrator = create_api_auto_single_case_orchestrator(
                case=case, user=None, test_result=test_result, source='devops',
                skip_sync=is_batch,
            )
            outcome = orchestrator.execute()
            test_result = outcome.get('test_result') or test_result
            case_result = outcome.get('case_result')

            if is_batch and case_result is not None:
                case_result.test_result = parent_result
                case_result.save(update_fields=['test_result'])

            if case_result is not None:
                if case_result.passed:
                    passed_count += 1
                else:
                    failed_count += 1

            if not is_batch:
                mirrored = _select_preferred_mirror(auto_result=test_result, task_id=task_id)
                if mirrored is None:
                    _mirror(auto_result=test_result, source='devops', task_id=task_id)
                elif task_id and mirrored.task_id != task_id:
                    mirrored.task_id = task_id
                    mirrored.save(update_fields=['task_id'])

            results.append({
                'case_id': case.id,
                'case_name': case.name,
                'passed': case_result.passed if case_result else False,
                'status_code': case_result.status_code if case_result else 0,
                'response_time_ms': case_result.response_time_ms if case_result else 0,
                'error_message': case_result.error_message if case_result else '执行失败',
                'failure_type': case_result.failure_type if case_result else '',
            })
        except Exception as exc:
            logger.exception('DevOps API case execution failed: case_id=%s', case.id)
            test_result.status = 'error'
            test_result.error_message = str(exc)
            test_result.completed_at = timezone.now()
            test_result.save()
            failed_count += 1

            if is_batch:
                try:
                    from .models import ApiAutoTestCaseResult as AATCR
                    AATCR.objects.create(
                        test_result=parent_result,
                        case=case,
                        passed=False,
                        status_code=0,
                        response_time_ms=0,
                        error_message=str(exc),
                        failure_type='unknown_error',
                        executed_at=timezone.now(),
                    )
                except Exception:
                    logger.exception('创建异常用例的 ApiAutoTestCaseResult 失败')
            else:
                _sync_unified(auto_result=test_result, source='devops')
                mirrored = _select_preferred_mirror(auto_result=test_result, task_id=task_id)
                if mirrored is None:
                    _mirror(auto_result=test_result, source='devops', task_id=task_id)
                elif task_id and mirrored.task_id != task_id:
                    mirrored.task_id = task_id
                    mirrored.save(update_fields=['task_id'])

            results.append({
                'case_id': case.id,
                'case_name': case.name,
                'passed': False,
                'status_code': 0,
                'response_time_ms': 0,
                'error_message': str(exc),
                'failure_type': 'unknown_error',
            })

    if is_batch and parent_result is not None:
        total = passed_count + failed_count
        parent_result.total_cases = total
        parent_result.passed_cases = passed_count
        parent_result.failed_cases = failed_count
        parent_result.error_cases = 0
        parent_result.status = 'passed' if failed_count == 0 and total > 0 else 'failed'
        parent_result.completed_at = timezone.now()
        parent_result.duration_ms = int(
            (parent_result.completed_at - parent_result.started_at).total_seconds() * 1000
        ) if parent_result.started_at else 0
        parent_result.save()
        _sync_unified(auto_result=parent_result, source='devops')
        _mirror(auto_result=parent_result, source='devops', task_id=task_id)

    return results


def _execute_ui_cases_safe(ui_case_ids):
    """Execute UI test cases safely, returning structured results.

    Returns (results_list, passed_count, failed_count).  If the UI executor
    module is not available or any case fails, the error is captured as a
    failed result rather than throwing an unhandled ImportError.
    """
    results = []
    passed_count = 0
    failed_count = 0

    try:
        from .views_ui_test import execute_ui_test_cases
    except ImportError:
        for cid in ui_case_ids:
            results.append({
                'case_id': cid,
                'case_name': f'UI用例 #{cid}',
                'passed': False,
                'status_code': 0,
                'response_time_ms': 0,
                'error_message': 'UI 测试执行器未配置或不可用',
                'failure_type': 'config_error',
            })
            failed_count += 1
        return results, passed_count, failed_count

    ui_results = execute_ui_test_cases(ui_case_ids)
    for result in ui_results:
        if 'case_name' not in result:
            result['case_name'] = f"用例 #{result.get('case_id', '?')}"
        results.append(result)
        if result.get('passed'):
            passed_count += 1
        else:
            failed_count += 1

    return results, passed_count, failed_count


def _get_requested_project_id(request):
    return request.query_params.get('project_id') or request.query_params.get('project')


def _accessible_test_results(user):
    return TestResult.objects.filter(
        project_access_q('project', user) |
        Q(project__isnull=True, executed_by=user)
    ).distinct()


def _apply_project_filter(request, queryset, project_path='project'):
    project_id = _get_requested_project_id(request)
    if not project_id:
        return queryset
    ensure_project_id_access(request.user, project_id)
    return queryset.filter(**{f'{project_path}_id': project_id})


def _accessible_test_tasks(user):
    return TestTask.objects.filter(project_access_q('project', user)).distinct()


def _get_accessible_test_task(user, task_id):
    try:
        task = TestTask.objects.select_related(
            'project', 'created_by', 'last_result'
        ).get(id=task_id)
    except TestTask.DoesNotExist:
        return None

    if not task.project_id:
        raise PermissionDenied('无权访问该测试任务')
    ensure_project_id_access(user, task.project_id)
    return task


def _accessible_cicd_configs(user):
    return CiCdConfig.objects.filter(project_access_q('project', user)).distinct()


def _get_accessible_cicd_config(user, config_id, active_only=False):
    queryset = CiCdConfig.objects.select_related('project', 'created_by')
    if active_only:
        queryset = queryset.filter(is_active=True)

    try:
        config = queryset.get(pk=config_id)
    except CiCdConfig.DoesNotExist:
        return None

    ensure_project_id_access(user, config.project_id)
    return config


def _accessible_pipeline_runs(user):
    return PipelineRun.objects.filter(project_access_q('project', user)).distinct()


def _get_accessible_pipeline_run(user, run_id):
    try:
        run = PipelineRun.objects.select_related('cicd_config', 'project').get(pk=run_id)
    except PipelineRun.DoesNotExist:
        return None

    ensure_project_id_access(user, run.project_id)
    return run


def _send_notification(project, ntype, message):
    """广播通知到 WebSocket 并保存到数据库 — 仅发送给项目成员"""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from room.models import Notification

        project_id = str(project.id) if project else None

        # WebSocket: target project-scoped group (not global broadcast)
        if project_id:
            channel_layer = get_channel_layer()
            if channel_layer:
                group_name = f"project_{project_id}_qa"
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'project_notification',
                        'message': message,
                        'project_id': project_id,
                        'level': 'warning' if '失败' in message else 'success',
                    }
                )

        # Database: only notify project members (owner + members)
        if project_id:
            from room.models import ProjectMember, Project
            try:
                member_user_ids = list(
                    ProjectMember.objects
                    .filter(project_id=project_id)
                    .values_list('user_id', flat=True)
                )
                # Always include the project owner even if not in members table
                owner_id = Project.objects.filter(pk=project_id).values_list('owner_id', flat=True).first()
                if owner_id and owner_id not in member_user_ids:
                    member_user_ids.append(owner_id)

                from django.contrib.auth.models import User
                for user in User.objects.filter(
                    id__in=member_user_ids,
                    is_active=True,
                )[:50]:
                    Notification.objects.create(
                        user=user, title='QA通知', message=message,
                        type=ntype, project=project,
                    )
            except Exception:
                logger.debug('Could not resolve project members for notification, skipping DB save')
    except Exception as e:
        logger.warning(f'发送通知失败: {e}')


class DashboardStatsView(APIView):
    """
    DevOps 仪表板统计数据 API
    GET /api/qa/devops/stats/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 获取时间范围参数
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)

        api_cases = _apply_project_filter(
            request,
            ApiAutoTestCase.objects.filter(project_access_q('project', request.user)).distinct(),
        )
        ui_cases = _apply_project_filter(
            request,
            UiTestCase.objects.filter(project_access_q('project', request.user)).distinct(),
        )
        results_queryset = _apply_project_filter(
            request,
            _accessible_test_results(request.user),
        )

        # 基础统计
        api_cases_count = api_cases.count()
        ui_cases_count = ui_cases.count()
        total_cases = api_cases_count + ui_cases_count

        # 测试结果统计
        recent_results = results_queryset.filter(created_at__gte=start_date)
        total_executions = recent_results.count()
        passed_count = recent_results.filter(status='passed').count()
        failed_count = recent_results.filter(status='failed').count()
        error_count = recent_results.filter(status='error').count()
        running_count = recent_results.filter(status='running').count()

        # 计算通过率
        completed_count = passed_count + failed_count + error_count
        pass_rate = round((passed_count / completed_count * 100), 2) if completed_count > 0 else 0

        # 今日执行数
        today = timezone.now().date()
        today_executions = results_queryset.filter(
            created_at__date=today
        ).count()

        # 按类型统计
        type_stats = {}
        test_type_choices = TestResult._meta.get_field('test_type').choices or []
        for test_type, _ in test_type_choices:
            type_stats[test_type] = recent_results.filter(test_type=test_type).count()

        # 按天统计趋势
        daily_stats = []
        for i in range(days):
            date = (timezone.now() - timedelta(days=i)).date()
            day_results = results_queryset.filter(created_at__date=date)
            daily_stats.append({
                'date': date.isoformat(),
                'total': day_results.count(),
                'passed': day_results.filter(status='passed').count(),
                'failed': day_results.filter(status='failed').count(),
                'error': day_results.filter(status='error').count(),
            })
        daily_stats.reverse()

        # 平均响应时间（性能测试）
        avg_response_time = recent_results.filter(
            response_time_ms__isnull=False
        ).aggregate(avg=Avg('response_time_ms'))['avg']

        return Response({
            'overview': {
                'total_cases': total_cases,
                'api_cases': api_cases_count,
                'ui_cases': ui_cases_count,
                'total_executions': total_executions,
                'today_executions': today_executions,
                'pass_rate': pass_rate,
                'avg_response_time': round(avg_response_time, 2) if avg_response_time else None,
            },
            'status_count': {
                'passed': passed_count,
                'failed': failed_count,
                'error': error_count,
                'running': running_count,
            },
            'by_type': type_stats,
            'daily_trend': daily_stats,
        })


class RecentExecutionsView(APIView):
    """
    最近测试执行记录 API
    GET /api/qa/devops/recent-executions/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 10))
        test_type = request.query_params.get('test_type')

        queryset = _apply_project_filter(
            request,
            _accessible_test_results(request.user).select_related(
                'project', 'executed_by', 'ui_test_case'
            ),
        ).order_by('-created_at')

        if test_type:
            queryset = queryset.filter(test_type=test_type)

        results = queryset[:limit]
        serializer = TestResultListSerializer(results, many=True)

        return Response(serializer.data)


class CiCdIntegrationView(APIView):
    """CI/CD 集成配置管理 — uses CiCdConfigSerializer for unified serialization"""
    permission_classes = [IsAuthenticated]

    def get(self, request, config_id=None):
        if config_id:
            config = _get_accessible_cicd_config(request.user, config_id)
            if config is None:
                return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)
            ser = CiCdConfigSerializer(config, context={'request': request})
            return Response(ser.data)

        project_id = request.query_params.get('project_id')
        queryset = _accessible_cicd_configs(request.user).filter(is_active=True)
        if project_id:
            ensure_project_id_access(request.user, project_id)
            queryset = queryset.filter(project_id=project_id)
        ser = CiCdConfigSerializer(queryset, many=True, context={'request': request})
        return Response(ser.data)

    def post(self, request):
        payload = request.data.copy()
        project_id = payload.get('write_only_project_id') or payload.get('project_id')
        if project_id is not None:
            ensure_project_id_access(request.user, project_id)
            payload['write_only_project_id'] = project_id
        ser = CiCdConfigSerializer(data=payload, context={'request': request})
        ser.is_valid(raise_exception=True)
        config = ser.save()
        out = CiCdConfigSerializer(config, context={'request': request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    def put(self, request, config_id):
        config = _get_accessible_cicd_config(request.user, config_id)
        if config is None:
            return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)

        ser = CiCdConfigSerializer(config, data=request.data, partial=True,
                                    context={'request': request})
        ser.is_valid(raise_exception=True)
        config = ser.save()
        out = CiCdConfigSerializer(config, context={'request': request})
        return Response(out.data)

    def delete(self, request, config_id):
        config = _get_accessible_cicd_config(request.user, config_id)
        if config is None:
            return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)
        config.is_active = False
        config.save()
        return Response({'message': '删除成功'})


class CiCdTestConnectionView(APIView):
    """POST /api/qa/devops/cicd-config/{config_id}/test/ — test CI connectivity"""
    permission_classes = [IsAuthenticated]

    def post(self, request, config_id):
        guard = RuntimeGuard()
        config = _get_accessible_cicd_config(request.user, config_id, active_only=True)
        if config is None:
            return Response({'error': 'CI/CD配置不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not settings.USE_REAL_CI and guard.is_strict():
            return Response(
                {'reachable': False, 'latency_ms': None,
                 'error': 'Mock CI is not allowed in this environment',
                 'runtime_mode': guard.build_runtime_mode(guarded_rejected=True)},
                status=status.HTTP_409_CONFLICT,
            )

        from .pipeline import get_client
        client = get_client(config)
        start = time.monotonic()
        result = client.ping()
        latency_ms = round((time.monotonic() - start) * 1000)

        return Response({
            'reachable': result.get('ok', False),
            'latency_ms': latency_ms,
            'error': result.get('detail') if not result.get('ok') else None,
        })


class TestTaskView(APIView):
    """
    测试任务管理 API - 使用数据库存储
    GET /api/qa/devops/tasks/ - 获取任务列表
    POST /api/qa/devops/tasks/ - 创建任务
    GET /api/qa/devops/tasks/{id}/ - 获取任务详情
    PUT /api/qa/devops/tasks/{id}/ - 更新任务
    DELETE /api/qa/devops/tasks/{id}/ - 删除任务
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id=None):
        """获取测试任务列表或单个任务详情"""
        if task_id:
            task = _get_accessible_test_task(request.user, task_id)
            if task is None:
                return Response(
                    {'error': '任务不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            serializer = TestTaskDetailSerializer(task)
            return Response(serializer.data)

        # 支持筛选
        queryset = _apply_project_filter(
            request,
            _accessible_test_tasks(request.user).select_related(
                'project', 'created_by', 'last_result'
            ),
        ).order_by('-created_at')

        task_type = request.query_params.get('type')
        status_filter = request.query_params.get('status')

        if task_type:
            queryset = queryset.filter(test_type=task_type)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        serializer = TestTaskListSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        """创建测试任务"""
        serializer = TestTaskCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            project = serializer.validated_data.get('project')
            if project:
                ensure_project_id_access(request.user, project.id)
            task = serializer.save()

            # 定时任务：校验 cron 并注册 celery-beat PeriodicTask
            if task.trigger_type == 'scheduled':
                from .services.devops.test_execution_service import TestExecutionService
                svc = TestExecutionService()
                viability = svc.check_scheduled_task_viability(task)
                if viability:
                    task.delete()
                    return Response(
                        {'error': viability},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                register_error = svc.register_scheduled_task(task)
                if register_error:
                    task.delete()
                    return Response(
                        {'error': register_error},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            return Response(
                TestTaskListSerializer(task).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, task_id):
        """更新测试任务"""
        task = _get_accessible_test_task(request.user, task_id)
        if task is None:
            return Response(
                {'error': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        if task.status == 'running':
            return Response(
                {'error': '任务正在执行中，无法修改'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = TestTaskUpdateSerializer(task, data=request.data, partial=True)
        if serializer.is_valid():
            task = serializer.save()

            # 同步定时调度：scheduled → 注册/更新；其他触发方式 → 清理旧调度
            from .services.devops.test_execution_service import TestExecutionService
            svc = TestExecutionService()
            if task.trigger_type == 'scheduled':
                viability = svc.check_scheduled_task_viability(task)
                if viability:
                    return Response(
                        {'error': viability},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                register_error = svc.register_scheduled_task(task)
                if register_error:
                    return Response(
                        {'error': register_error},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                svc.unregister_scheduled_task(task)

            return Response(TestTaskDetailSerializer(task).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, task_id):
        """删除测试任务"""
        task = _get_accessible_test_task(request.user, task_id)
        if task is None:
            return Response(
                {'error': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        if task.status == 'running':
            return Response(
                {'error': '任务正在执行中，无法删除'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 删除前清理定时调度
        if task.trigger_type == 'scheduled':
            from .services.devops.test_execution_service import TestExecutionService
            TestExecutionService().unregister_scheduled_task(task)

        task.delete()
        return Response({'message': '删除成功'})


class TestTaskExecuteView(APIView):
    """
    测试任务执行 API
    POST /api/qa/devops/tasks/{id}/execute/ - 执行测试任务
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        guard = RuntimeGuard()
        task = _get_accessible_test_task(request.user, task_id)
        if task is None:
            return Response(
                {'error': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        if task.status == 'running':
            return Response(
                {'error': '任务已在执行中'},
                status=status.HTTP_400_BAD_REQUEST
            )

        test_config = task.test_config or {}
        api_case_ids = test_config.get('api_cases', [])
        ui_case_ids = test_config.get('ui_cases', [])

        try:
            validate_test_task_config_cases(task.test_config, task.project)
        except ValidationError as exc:
            return Response({'error': exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        # Require at least one real test case — refuse to execute empty tasks
        if not api_case_ids and not ui_case_ids:
            return Response(
                {'error': '该任务未绑定任何真实测试用例，不能执行'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 更新任务状态
        task.status = 'running'
        task.execution_count += 1
        task.last_executed = timezone.now()
        task.save()

        test_result = None
        execution_id = None

        if settings.USE_CELERY_TASKS:
            from .tasks_test_exec import execute_test_task as execute_test_task_task

            execute_test_task_task.apply_async(args=[task.id], queue='qa_long')
            runtime_mode = guard.build_runtime_mode(
                celery_eager=getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)
            )
        else:
            # 创建测试结果记录
            test_result = TestResult.objects.create(
                test_type=task.test_type,
                name=f"{task.name} - 执行 #{task.execution_count}",
                source='devops',
                project=task.project,
                status='running',
                test_params=task.test_config,
                executed_by=request.user,
                started_at=timezone.now(),
                task_id=str(task.id),
            )
            execution_id = test_result.id
            if guard.require_celery_for_runtime_entrypoint():
                return Response(
                    {
                        'detail': 'Celery is required for this runtime entrypoint in strict environments',
                        'error_code': 'runner_required',
                        'runtime_mode': guard.build_runtime_mode(guarded_rejected=True),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # 启动后台线程执行测试
            thread = threading.Thread(
                target=self._execute_test_task,
                args=(task, test_result)
            )
            thread.daemon = True
            thread.start()
            runtime_mode = guard.build_runtime_mode(thread_fallback=True)

        return Response({
            'message': '测试任务已启动',
            'execution_id': execution_id,
            'task': TestTaskListSerializer(task).data,
            'runtime_mode': runtime_mode,
        })

    def _execute_test_task(self, task, test_result):
        """在后台执行测试任务 — delegates to TestExecutionService."""
        from .services.devops.test_execution_service import TestExecutionService
        svc = TestExecutionService()
        try:
            svc.execute_test_task(task, test_result)
        except Exception as e:
            test_result.status = 'error'
            test_result.completed_at = timezone.now()
            test_result.error_message = str(e)[:500]
            test_result.test_log = json.dumps({
                'error': str(e)[:500],
            }, ensure_ascii=False)
            test_result.save()

            task.status = 'failed'
            task.save()

            _send_notification(task.project or test_result.project, 'test_failure',
                f'测试执行异常：{task.name} — {str(e)[:100]}')


class TestTaskStatusView(APIView):
    """
    测试任务状态查询 API
    GET /api/qa/devops/tasks/{id}/status/ - 获取任务执行状态
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        task = _get_accessible_test_task(request.user, task_id)
        if task is None:
            return Response(
                {'error': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        from .services.devops.test_execution_service import TestExecutionService
        svc = TestExecutionService()
        resolved_result = svc._resolve_task_result(task)
        last_result = None
        if resolved_result:
            last_result = {
                'id': resolved_result.id,
                'status': resolved_result.status,
                'started_at': resolved_result.started_at,
                'completed_at': resolved_result.completed_at,
                'duration_ms': resolved_result.duration_ms,
                'test_log': resolved_result.test_log,
                'test_run_id': (resolved_result.test_params or {}).get('test_run_id'),
                'api_auto_result_id': resolved_result.api_auto_result_id,
            }

        return Response({
            'task': TestTaskListSerializer(task).data,
            'current_execution': last_result,
        })


class TestTaskHistoryView(APIView):
    """
    测试任务执行历史 API
    GET /api/qa/devops/tasks/{id}/history/ - 获取任务执行历史
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        task = _get_accessible_test_task(request.user, task_id)
        if task is None:
            return Response(
                {'error': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 获取该任务关联的所有测试结果，优先包含真实关联的 last_result，
        # 同时兼容旧的按名称前缀归档的历史结果。
        from .services.devops.test_execution_service import TestExecutionService
        svc = TestExecutionService()
        resolved_result = svc._resolve_task_result(task)
        result_filter = Q(
            project_id=task.project_id,
            task_id=str(task.id),
        )
        if resolved_result is not None:
            result_filter |= Q(
                id=resolved_result.id,
                project_id=task.project_id,
            )
        result_filter |= Q(
            project_id=task.project_id,
            source='devops',
            name__regex=rf'^{re.escape(task.name)} - 执行 #\d+$',
        )
        results = TestResult.objects.filter(result_filter).order_by('-created_at')[:20]

        history = []
        for result in results:
            history.append({
                'id': result.id,
                'status': result.status,
                'started_at': result.started_at,
                'completed_at': result.completed_at,
                'duration_ms': result.duration_ms,
                'test_log': result.test_log,
                'created_at': result.created_at,
                'test_run_id': (result.test_params or {}).get('test_run_id'),
                'api_auto_result_id': result.api_auto_result_id,
            })

        return Response(history)


class TestTaskLogsView(APIView):
    """GET /api/qa/devops/tasks/{id}/logs/ — 结构化执行日志"""
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        task = _get_accessible_test_task(request.user, task_id)
        if task is None:
            return Response(
                {'error': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .services.devops.test_execution_service import TestExecutionService
        svc = TestExecutionService()
        logs = svc.get_task_logs(task)
        if logs is None:
            return Response(
                {'error': '暂无执行日志'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(logs)


class TestTaskCancelView(APIView):
    """POST /api/qa/devops/tasks/{id}/cancel/ — 取消执行中的任务"""
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        task = _get_accessible_test_task(request.user, task_id)
        if task is None:
            return Response(
                {'error': '任务不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .services.devops.test_execution_service import TestExecutionService
        svc = TestExecutionService()
        result = svc.cancel_task(task)
        if result.get('cancelled'):
            return Response(result)
        return Response(
            result,
            status=status.HTTP_400_BAD_REQUEST,
        )


class RuntimeModeView(APIView):
    """GET /api/qa/devops/runtime-mode/ — 返回当前运行时环境配置摘要

    不暴露 token、secret 等敏感信息。
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard = RuntimeGuard()
        return Response(guard.get_runtime_summary())


class QuickTestView(APIView):
    """
    快速测试 API - 真实执行器
    POST /api/qa/devops/quick-test/ - 执行快速测试
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        test_type = data.get('type', 'api')
        test_cases = data.get('test_cases', [])
        project_id = data.get('project_id') or data.get('project')

        valid_types = ['api', 'ui', 'performance', 'regression']
        if test_type not in valid_types:
            return Response(
                {'error': f'无效的测试类型，可选: {valid_types}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not project_id:
            return Response(
                {'error': '缺少 project_id'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not test_cases or not isinstance(test_cases, list):
            return Response(
                {'error': '缺少 test_cases 或格式无效'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Permission: project access check
        ensure_project_id_access(request.user, project_id)

        # Permission: validate test_cases belong to the requested project
        from .services.devops.test_execution_service import TestExecutionService
        svc = TestExecutionService()
        try:
            svc.validate_cases_for_project(test_cases, project_id, test_type=test_type)
        except ValueError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delegate to real execution service
        try:
            test_result = svc.execute_quick_test(
                test_type=test_type,
                case_ids=test_cases,
                project_id=project_id,
                user=request.user,
            )
        except RuntimeError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        return Response({
            'message': 'QuickTest completed',
            'test_type': test_type,
            'status': test_result.status,
            'execution_id': test_result.id,
        })


# ============== PipelineRun 视图 ==============

class PipelineRunListView(APIView):
    """GET /api/qa/devops/pipeline-runs/?project_id=X"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project_id')
        cicd_config_id = request.query_params.get('cicd_config_id')
        if not project_id and not cicd_config_id:
            return Response({'error': '需要 project_id 或 cicd_config_id'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = _accessible_pipeline_runs(request.user).select_related('cicd_config', 'project')

        if project_id:
            ensure_project_id_access(request.user, project_id)
            queryset = queryset.filter(project_id=project_id)
        if cicd_config_id:
            config = _get_accessible_cicd_config(request.user, cicd_config_id)
            if config is None:
                return Response({'error': 'CI/CD配置不存在'}, status=status.HTTP_404_NOT_FOUND)
            queryset = queryset.filter(cicd_config_id=cicd_config_id)

        queryset = queryset.order_by('-created_at')[:50]

        data = []
        for run in queryset:
            data.append({
                'id': run.id,
                'cicd_config_id': run.cicd_config_id,
                'cicd_config_name': run.cicd_config.name,
                'project_id': str(run.project_id),
                'status': run.status,
                'commit_sha': run.commit_sha,
                'branch': run.branch,
                'test_results_summary': run.test_results_summary,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                'external_url': run.external_url or '',
                'external_run_id': run.external_run_id or '',
                'is_mock': run.is_mock,
                'error_message': run.error_message or '',
                'jobs_summary': run.jobs_summary or [],
                'created_at': run.created_at.isoformat(),
            })
        return Response({'results': data, 'count': len(data)})


class PipelineRunDetailView(APIView):
    """GET /api/qa/devops/pipeline-runs/{id}/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = _get_accessible_pipeline_run(request.user, run_id)
        if run is None:
            return Response({'error': '执行记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'id': run.id,
            'cicd_config_id': run.cicd_config_id,
            'cicd_config_name': run.cicd_config.name,
            'ci_type': run.cicd_config.ci_type,
            'project_id': str(run.project_id),
            'project_name': run.project.name,
            'status': run.status,
            'commit_sha': run.commit_sha,
            'branch': run.branch,
            'external_url': run.external_url or '',
            'external_run_id': run.external_run_id or '',
            'external_queue_id': run.external_queue_id or '',
            'is_mock': run.is_mock,
            'error_message': run.error_message or '',
            'jobs_summary': run.jobs_summary or [],
            'log_output': run.log_output[:5000] if run.log_output else '',
            'test_results_summary': run.test_results_summary,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'completed_at': run.completed_at.isoformat() if run.completed_at else None,
            'created_at': run.created_at.isoformat(),
        })


class PipelineRunCancelView(APIView):
    """POST /api/qa/devops/pipeline-runs/{id}/cancel/ — 取消 Pipeline 执行"""
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        run = _get_accessible_pipeline_run(request.user, run_id)
        if run is None:
            return Response({'error': '执行记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        cancellable = {'pending', 'queued', 'running'}
        if run.status not in cancellable:
            return Response(
                {'error': f'当前状态 {run.status} 不允许取消'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .pipeline import get_client
        client = get_client(run.cicd_config)
        success = client.cancel(run)
        run.status = 'cancelled'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'completed_at'])

        return Response({
            'cancelled': success,
            'status': run.status,
        })


class PipelineRunLogsView(APIView):
    """GET /api/qa/devops/pipeline-runs/{id}/logs/ — 获取 Pipeline 构建日志"""
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = _get_accessible_pipeline_run(request.user, run_id)
        if run is None:
            return Response({'error': '执行记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        from .pipeline import get_client
        client = get_client(run.cicd_config)
        logs = client.get_logs(run)

        from .pipeline.sanitize import sanitize_logs
        sanitized = sanitize_logs(logs)

        return Response({
            'log_output': sanitized,
            'truncated': len(logs) >= 65536,
        })


class PipelineRunTriggerView(APIView):
    """POST /api/qa/devops/cicd-config/{config_id}/trigger/ — 手动触发"""

    permission_classes = [IsAuthenticated]

    # Canonical status values allowed for PipelineRun
    CANONICAL_STATUSES = frozenset({
        'pending', 'queued', 'running', 'passed', 'failed', 'cancelled', 'skipped',
    })

    def post(self, request, config_id):
        guard = RuntimeGuard()
        config = _get_accessible_cicd_config(request.user, config_id, active_only=True)
        if config is None:
            return Response({'error': 'CI/CD配置不存在'}, status=status.HTTP_404_NOT_FOUND)

        # Dedup: prevent double-trigger within TTL
        dedup_key = f"manual-{int(time.time() // 30)}"
        if check_webhook_dedup(config.id, dedup_key):
            return Response(
                {'error': '触发过于频繁，请稍后再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not settings.USE_REAL_CI and guard.is_strict():
            return Response(
                {
                    'detail': 'Mock CI fallback is not allowed in strict environments',
                    'error_code': 'runner_required',
                    'runtime_mode': guard.build_runtime_mode(guarded_rejected=True),
                },
                status=status.HTTP_409_CONFLICT,
            )

        run = PipelineRun.objects.create(
            cicd_config=config,
            project=config.project,
            status='running',
            branch=config.branch,
            is_mock=not settings.USE_REAL_CI,
            started_at=timezone.now(),
        )

        # Generate trace_id for full-chain correlation
        from .metrics import generate_trace_id
        run.trace_id = generate_trace_id()
        run.save(update_fields=['trace_id'])

        # Trigger pipeline (real CI or mock based on feature flag)
        if settings.USE_REAL_CI:
            from .pipeline import get_client
            from .tasks_test_exec import poll_pipeline_status

            try:
                client = get_client(config)
                result = client.trigger(
                    config,
                    ref=config.branch or 'main',
                    trigger_source='qa_center',
                    variables={'TRACE_ID': run.trace_id},
                )
                run.ci_type = config.ci_type
                run.external_queue_id = result.external_queue_id
                run.external_run_id = result.external_run_id
                run.external_url = result.external_url
                run.status = 'queued'
                run.save()
                poll_pipeline_status.apply_async(
                    args=[run.id], kwargs={'trace_id': run.trace_id}, queue='qa_pipeline'
                )
            except Exception as exc:
                run.status = 'failed'
                run.error_message = str(exc)[:500]
                run.save(update_fields=['status', 'error_message'])
            runtime_mode = guard.build_runtime_mode(is_mock=False)
        else:
            thread = threading.Thread(target=self._simulate_run, args=(run,))
            thread.daemon = True
            thread.start()
            runtime_mode = guard.build_runtime_mode(thread_fallback=True)

        return Response({
            'message': 'Pipeline 已触发',
            'run_id': run.id,
            'status': 'running',
            'runtime_mode': runtime_mode,
            'is_mock': run.is_mock,
        }, status=status.HTTP_201_CREATED)

    def _simulate_run(self, run):
        """Deterministic simulated pipeline run for dev/local environments only.

        Always marks is_mock=True (already set at creation time).
        Uses fixed status values — never random — so it cannot produce
        misleading data that could be mistaken for real CI results.
        """
        try:
            time.sleep(3)
            # Deterministic result: simulated pipelines always "passed" with
            # the is_mock flag set, so consumers can distinguish them.
            run.status = 'passed'
            run.completed_at = timezone.now()
            run.test_results_summary = {
                'total': 0,
                'passed': 0,
                'failed': 0,
            }
            run.log_output = '[MOCK] Simulated pipeline run (USE_REAL_CI=False). No real CI was triggered.'
            run.save()
        except Exception as e:
            run.status = 'failed'
            run.completed_at = timezone.now()
            run.error_message = str(e)
            run.save()


class PipelineRunWebhookView(APIView):
    """POST /api/qa/devops/cicd-config/{config_id}/webhook/ — 外部CI/CD回调"""

    permission_classes = []  # webhook 不需要 session 认证

    # Canonical status values accepted from external CI platforms
    CANONICAL_STATUSES = frozenset({
        'pending', 'queued', 'running', 'passed', 'failed', 'cancelled', 'skipped',
    })

    def post(self, request, config_id):
        guard = RuntimeGuard()
        strict = guard.is_strict()

        # --- Body size limit (fail early) ---
        max_bytes = getattr(settings, 'DEVOPS_WEBHOOK_MAX_BODY_BYTES', 256 * 1024)
        body = request.body
        if len(body) > max_bytes:
            log_webhook_audit("body_too_large", config_id,
                              body_bytes=len(body), limit=max_bytes)
            return Response(
                {'error': 'Request body too large'},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # --- Look up config ---
        try:
            config = CiCdConfig.objects.get(pk=config_id, is_active=True)
        except CiCdConfig.DoesNotExist:
            return Response(
                {'error': 'CI/CD configuration not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- Rate limit (with shared-cache guard for strict envs) ---
        if strict and not guard.cache_is_shared():
            log_webhook_audit("no_shared_cache_strict", config_id)
            return Response(
                {'error': 'Webhook rate limiting requires a shared cache in this environment'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        blocked, count = check_webhook_rate_limit(config_id)
        if blocked:
            log_webhook_audit("rate_limited", config_id,
                              count=count, limit=5, window_sec=60)
            return Response(
                {'error': 'Too many requests'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # === Authentication: signature + token (fail-closed) ===

        ci_token_configured = bool((config.ci_token or '').strip())
        api_token_configured = bool((config.api_token or '').strip())

        # --- Signature verification ---
        sig_header = (
            request.headers.get('X-Hub-Signature-256', '') or
            request.headers.get('X-Gitlab-Token', '')
        )

        if ci_token_configured:
            if not sig_header:
                log_webhook_audit("missing_signature_header", config_id,
                                  reason="ci_token_configured_but_no_sig_header")
                return Response(
                    {'error': 'Missing signature header'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not verify_webhook_signature(
                body,
                sig_header,
                config.ci_token,
                header_prefix='sha256=' if 'sha256=' in sig_header else '',
            ):
                log_webhook_audit("invalid_signature", config_id)
                return Response(
                    {'error': 'Invalid signature'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif strict:
            # Strict environments MUST have ci_token configured for webhooks
            log_webhook_audit("missing_ci_token_strict", config_id)
            return Response(
                {'error': 'Webhook signature verification is required in this environment'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # --- Token auth (constant-time compare, always required) ---
        expected_token = (config.api_token or '').strip()
        provided_token = request.headers.get('X-CI-Token', '').strip()
        if (
            not expected_token
            or not provided_token
            or not hmac.compare_digest(provided_token, expected_token)
        ):
            log_webhook_audit(
                "invalid_token", config_id,
                reason="missing" if not expected_token else "mismatch",
            )
            return Response(
                {'error': 'Invalid token'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # --- Parse payload ---
        # DRF already parsed JSON into request.data, but body is raw bytes.
        external_run_id = (
            request.data.get('external_run_id', '') or
            request.data.get('pipeline_id', '')
        )

        # --- Dedup check (with payload-hash fallback) ---
        if check_webhook_dedup(config_id, external_run_id, payload_body=body):
            return Response(
                {'message': 'duplicate', 'run_id': None},
                status=status.HTTP_200_OK,
            )

        # --- Status whitelist validation ---
        status_val = request.data.get('status', 'running')
        if status_val not in self.CANONICAL_STATUSES:
            log_webhook_audit("invalid_status", config_id,
                              received_status=str(status_val)[:50])
            return Response(
                {'error': f'Invalid pipeline status: {status_val}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        commit_sha = request.data.get('commit_sha', '')
        branch = request.data.get('branch', '')

        run = PipelineRun.objects.create(
            cicd_config=config,
            project=config.project,
            status=status_val,
            commit_sha=commit_sha,
            branch=branch,
            external_run_id=external_run_id,
            external_url=request.data.get('external_url', ''),
            jobs_summary=request.data.get('jobs_summary', []),
            is_mock=False,
            log_output=request.data.get('log_output', ''),
            test_results_summary=request.data.get('test_results_summary', {}),
            started_at=timezone.now() if status_val == 'running' else None,
            completed_at=timezone.now() if status_val in ('passed', 'failed') else None,
        )

        log_webhook_audit("accepted", config_id,
                          run_id=run.id, status=status_val,
                          external_run_id=str(external_run_id)[:60])

        return Response(
            {'message': 'Webhook received', 'run_id': run.id},
            status=status.HTTP_201_CREATED,
        )


# ============== 项目质量报告 ==============

class ProjectQualityReportView(APIView):
    """GET /api/qa/devops/quality-report/?project_id=X"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({'error': '缺少 project_id'}, status=status.HTTP_400_BAD_REQUEST)
        ensure_project_id_access(request.user, project_id)

        # 1. 测试覆盖率：有关联测试用例的任务数 / 总任务数
        from room.models import Task
        from qa_center.models import ApiAutoTestCase, UiTestCase, PerformanceTestCase
        total_tasks = Task.objects.filter(column__project_id=project_id).count()
        linked_api = ApiAutoTestCase.objects.filter(project_id=project_id).count()
        linked_ui = UiTestCase.objects.filter(project_id=project_id, related_tasks__isnull=False).count()
        linked_perf = PerformanceTestCase.objects.filter(project_id=project_id, related_tasks__isnull=False).count()
        has_linked_tests = Task.objects.filter(
            column__project_id=project_id
        ).filter(
            Q(linked_ui_test_cases__isnull=False) |
            Q(linked_performance_test_cases__isnull=False)
        ).distinct().count()
        test_coverage = round(has_linked_tests / total_tasks * 20, 1) if total_tasks > 0 else 0

        # 2. 测试通过率：最近 10 次测试结果
        recent_tests = list(TestResult.objects.filter(
            project_id=project_id, status__in=['passed', 'failed']
        ).order_by('-created_at')[:10])
        total_recent = len(recent_tests)
        passed_recent = sum(1 for r in recent_tests if r.status == 'passed')
        test_pass_rate = round(passed_recent / total_recent * 20, 1) if total_recent > 0 else 0

        # 3. 性能指标
        perf_results = list(PerformanceTestResult.objects.filter(
            test_case__project_id=project_id
        ).order_by('-executed_at')[:5])
        if perf_results:
            avg_p95 = sum(
                r.p95_response_time_ms or r.p99_response_time_ms or 0
                for r in perf_results
            ) / len(perf_results)
            perf_score = 20 if avg_p95 < 500 else (15 if avg_p95 < 1000 else (10 if avg_p95 < 2000 else 5))
        else:
            avg_p95 = 0
            perf_score = 0

        # 4. Bug 密度：基于 bug_tracker.Bug 模型统计
        from bug_tracker.models import Bug
        bug_count = Bug.objects.filter(project_id=project_id).count()
        bug_density = round(bug_count / total_tasks * 100, 1) if total_tasks > 0 else 0
        bug_score = 20 if bug_density < 10 else (15 if bug_density < 20 else (10 if bug_density < 30 else 5))

        # 5. 部署成功率
        recent_pipelines = list(PipelineRun.objects.filter(
            project_id=project_id,
            status__in=['passed', 'failed'],
            is_mock=False,
        ).order_by('-created_at')[:10])
        total_pl = len(recent_pipelines)
        if total_pl == 0:
            deploy_rate = None  # No real data
            passed_pl = 0
        else:
            passed_pl = sum(1 for r in recent_pipelines if r.status == 'passed')
            deploy_rate = round(passed_pl / total_pl * 20, 1)

        total_score = round(test_coverage + test_pass_rate + perf_score + bug_score + (deploy_rate or 0), 1)

        # 30 天趋势
        from django.utils import timezone as dj_timezone
        thirty_days_ago = dj_timezone.now() - timedelta(days=30)
        daily_data = TestResult.objects.filter(
            project_id=project_id, created_at__gte=thirty_days_ago
        ).extra({'day': "date(created_at)"}).values('day').annotate(
            total=Count('id'), passed=Count('id', filter=Q(status='passed'))
        ).order_by('day')

        trend = []
        for d in daily_data:
            trend.append({
                'date': str(d['day']),
                'total': d['total'],
                'passed': d['passed'],
                'rate': round(d['passed'] / d['total'] * 100, 1) if d['total'] > 0 else 0,
            })

        return Response({
            'project_id': project_id,
            'total_score': total_score,
            'dimensions': [
                {'name': '测试覆盖', 'score': test_coverage, 'max': 20, 'detail': f'{has_linked_tests}/{total_tasks} 任务有关联测试'},
                {'name': '测试通过率', 'score': test_pass_rate, 'max': 20, 'detail': f'{passed_recent}/{total_recent} 通过'},
                {'name': '性能指标', 'score': perf_score, 'max': 20, 'detail': f'P95: {avg_p95:.0f}ms'},
                {'name': 'Bug密度', 'score': bug_score, 'max': 20, 'detail': f'{bug_count} 个 Bug / {total_tasks} 任务 ({bug_density}%)'},
                {'name': '部署成功率', 'score': deploy_rate, 'max': 20, 'detail': f'{passed_pl}/{total_pl} 成功'},
            ],
            'trend': trend,
            'summary': {
                'total_tasks': total_tasks,
                'bug_count': bug_count,
                'recent_pipelines': total_pl,
                'has_perf_data': bool(perf_results),
            }
        })
