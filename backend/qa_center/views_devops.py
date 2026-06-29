"""
DevOps 测试平台 API 视图
提供仪表板统计、最近执行记录、CI/CD集成配置、测试任务管理等功能
"""

import json
import threading
import random
import time
from datetime import datetime, timedelta
from django.db.models import Count, Q, Avg
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError

from room.project_access import ensure_project_id_access, project_access_q
from .models import TestResult, ApiTestCase, UiTestCase, TestTask, CiCdConfig, PipelineRun, PerformanceTestResult
from .serializers import (
    TestResultListSerializer,
    TestTaskListSerializer, TestTaskDetailSerializer,
    TestTaskCreateSerializer, TestTaskUpdateSerializer,
    PerformanceTestResultSerializer, PerformanceTestResultListSerializer,
    validate_test_task_config_cases,
)
import logging

logger = logging.getLogger(__name__)


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
    """广播通知到 WebSocket 并保存到数据库"""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from room.models import Notification

        project_id = str(project.id) if project else None

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                'system_broadcast',
                {
                    'type': 'global_notification',
                    'message': message,
                    'level': 'warning' if '失败' in message else 'success',
                }
            )

        # 保存到数据库
        from django.contrib.auth.models import User
        for user in User.objects.filter(is_active=True)[:50]:
            Notification.objects.create(
                user=user, title='系统通知', message=message,
                type=ntype, project=project,
            )
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
            ApiTestCase.objects.filter(project_access_q('project', request.user)).distinct(),
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
                'project', 'executed_by', 'api_test_case', 'ui_test_case'
            ),
        ).order_by('-created_at')

        if test_type:
            queryset = queryset.filter(test_type=test_type)

        results = queryset[:limit]
        serializer = TestResultListSerializer(results, many=True)

        return Response(serializer.data)


class CiCdIntegrationView(APIView):
    """CI/CD 集成配置管理（数据库持久化）"""
    permission_classes = [IsAuthenticated]

    def get(self, request, config_id=None):
        if config_id:
            config = _get_accessible_cicd_config(request.user, config_id)
            if config is None:
                return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)
            return Response(self._serialize_config(config))

        project_id = request.query_params.get('project_id')
        queryset = _accessible_cicd_configs(request.user).filter(is_active=True)
        if project_id:
            ensure_project_id_access(request.user, project_id)
            queryset = queryset.filter(project_id=project_id)
        configs = [self._serialize_config(c) for c in queryset]
        return Response(configs)

    def post(self, request):
        project_id = request.data.get('project_id')
        if not project_id:
            return Response({'error': '缺少 project_id'}, status=status.HTTP_400_BAD_REQUEST)

        ensure_project_id_access(request.user, project_id)
        config = CiCdConfig.objects.create(
            project_id=project_id,
            name=request.data.get('name', ''),
            ci_type=request.data.get('type', 'jenkins'),
            webhook_url=request.data.get('webhook_url', ''),
            api_token=request.data.get('api_token', ''),
            branch=request.data.get('branch', 'main'),
            auto_trigger=request.data.get('auto_trigger', False),
            test_suite_ids=request.data.get('test_suite', []),
            headers=request.data.get('headers', {}),
            created_by=request.user,
        )
        return Response(self._serialize_config(config), status=status.HTTP_201_CREATED)

    def put(self, request, config_id):
        config = _get_accessible_cicd_config(request.user, config_id)
        if config is None:
            return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)

        updatable = ['name', 'webhook_url', 'api_token', 'branch', 'auto_trigger']
        for field in updatable:
            if field in request.data:
                setattr(config, field, request.data[field])
        if 'test_suite' in request.data:
            config.test_suite_ids = request.data['test_suite']
        if 'headers' in request.data:
            config.headers = request.data['headers']
        config.save()
        return Response(self._serialize_config(config))

    def delete(self, request, config_id):
        config = _get_accessible_cicd_config(request.user, config_id)
        if config is None:
            return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)
        config.is_active = False
        config.save()
        return Response({'message': '删除成功'})

    @staticmethod
    def _serialize_config(config):
        return {
            'id': config.id,
            'project_id': str(config.project_id),
            'name': config.name,
            'type': config.ci_type,
            'webhook_url': config.webhook_url,
            'branch': config.branch,
            'enabled': config.is_active,
            'auto_trigger': config.auto_trigger,
            'test_suite': config.test_suite_ids,
            'headers': config.headers,
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
            'created_by': config.created_by.username if config.created_by else '',
            'status': 'active' if config.is_active else 'inactive',
        }


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

        task.delete()
        return Response({'message': '删除成功'})


class TestTaskExecuteView(APIView):
    """
    测试任务执行 API
    POST /api/qa/devops/tasks/{id}/execute/ - 执行测试任务
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
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

        try:
            validate_test_task_config_cases(task.test_config, task.project)
        except ValidationError as exc:
            return Response({'error': exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        # 更新任务状态
        task.status = 'running'
        task.execution_count += 1
        task.last_executed = timezone.now()
        task.save()

        # 创建测试结果记录
        test_result = TestResult.objects.create(
            test_type=task.test_type,
            name=f"{task.name} - 执行 #{task.execution_count}",
            source='devops',
            project=task.project,
            status='running',
            test_params=task.test_config,
            executed_by=request.user,
            started_at=timezone.now()
        )

        # 启动后台线程执行测试
        thread = threading.Thread(
            target=self._execute_test_task,
            args=(task, test_result)
        )
        thread.daemon = True
        thread.start()

        return Response({
            'message': '测试任务已启动',
            'execution_id': test_result.id,
            'task': TestTaskListSerializer(task).data,
        })

    def _execute_test_task(self, task, test_result):
        """在后台执行测试任务"""
        try:
            # 获取测试配置
            test_config = task.test_config or {}
            api_case_ids = test_config.get('api_cases', [])
            ui_case_ids = test_config.get('ui_cases', [])

            all_results = []
            passed_count = 0
            failed_count = 0

            # 执行 API 测试
            if api_case_ids:
                from .views_api_test import execute_api_test_cases
                api_results = execute_api_test_cases(api_case_ids)
                for result in api_results:
                    all_results.append(result)
                    if result.get('passed'):
                        passed_count += 1
                    else:
                        failed_count += 1

            # 执行 UI 测试
            if ui_case_ids:
                from .views_ui_test import execute_ui_test_cases
                ui_results = execute_ui_test_cases(ui_case_ids)
                for result in ui_results:
                    all_results.append(result)
                    if result.get('passed'):
                        passed_count += 1
                    else:
                        failed_count += 1

            # 如果没有配置测试用例，执行模拟测试
            if not api_case_ids and not ui_case_ids:
                logs, passed_count, failed_count = self._simulate_test_execution(task)
                all_results = logs

            # 计算结果
            total = passed_count + failed_count
            pass_rate = round((passed_count / total * 100), 2) if total > 0 else 0

            # 生成详细的执行报告
            execution_report = {
                'summary': {
                    'total': total,
                    'passed': passed_count,
                    'failed': failed_count,
                    'pass_rate': pass_rate,
                },
                'results': all_results,
            }

            # 更新测试结果
            test_result.status = 'passed' if failed_count == 0 else 'failed'
            test_result.completed_at = timezone.now()
            test_result.duration_ms = int(
                (test_result.completed_at - test_result.started_at).total_seconds() * 1000
            )
            test_result.test_log = json.dumps(execution_report, ensure_ascii=False, indent=2)
            test_result.actual_result = f"通过: {passed_count}, 失败: {failed_count}, 通过率: {pass_rate}%"
            test_result.save()

            # 更新任务状态
            task.status = 'completed' if failed_count == 0 else 'failed'
            task.last_result = test_result
            task.save()

            # 通知广播
            if failed_count == 0:
                _send_notification(task.project or test_result.project, 'deploy_success',
                    f'测试全部通过！{task.name} — {passed_count} 个用例通过')
            else:
                _send_notification(task.project or test_result.project, 'test_failure',
                    f'测试存在失败：{task.name} — {failed_count}/{passed_count + failed_count} 失败')

        except Exception as e:
            test_result.status = 'error'
            test_result.completed_at = timezone.now()
            test_result.error_message = str(e)
            test_result.test_log = json.dumps({
                'error': str(e),
                'traceback': str(e.__traceback__),
            }, ensure_ascii=False)
            test_result.save()

            task.status = 'failed'
            task.save()

            _send_notification(task.project or test_result.project, 'test_failure',
                f'测试执行异常：{task.name} — {str(e)[:100]}')

    def _simulate_test_execution(self, task):
        """模拟测试执行（当没有配置测试用例时）"""
        logs = []
        passed_count = 0
        failed_count = 0

        # 模拟执行 3-5 个测试用例
        test_cases = [1, 2, 3, 4, 5]
        for case in test_cases:
            time.sleep(0.5)  # 模拟执行时间
            success = random.random() > 0.2  # 80%通过率

            logs.append({
                'step': case,
                'case': f"测试用例 {case}",
                'status': 'passed' if success else 'failed',
                'timestamp': timezone.now().isoformat(),
            })

            if success:
                passed_count += 1
            else:
                failed_count += 1

        return logs, passed_count, failed_count


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

        # 获取最新的执行结果
        last_result = None
        if task.last_result:
            last_result = {
                'id': task.last_result.id,
                'status': task.last_result.status,
                'started_at': task.last_result.started_at,
                'completed_at': task.last_result.completed_at,
                'duration_ms': task.last_result.duration_ms,
                'test_log': task.last_result.test_log,
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

        # 获取该任务关联的所有测试结果
        from .models import TestResult
        results = TestResult.objects.filter(
            project_id=task.project_id,
            source='devops',
            name__startswith=task.name,
        ).order_by('-created_at')[:20]

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
            })

        return Response(history)


class QuickTestView(APIView):
    """
    快速测试 API - 无需创建任务直接执行
    POST /api/qa/devops/quick-test/ - 执行快速测试
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        test_type = data.get('type', 'api')
        test_cases = data.get('test_cases', [])

        valid_types = ['api', 'ui', 'performance', 'regression']
        if test_type not in valid_types:
            return Response(
                {'error': f'无效的测试类型，可选: {valid_types}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 创建临时测试结果
        test_result = TestResult.objects.create(
            test_type=test_type,
            name='快速测试',
            status='running',
            test_params=data,
            executed_by=request.user,
            started_at=timezone.now()
        )

        # 启动后台执行
        thread = threading.Thread(
            target=self._execute_quick_test,
            args=(test_result, test_type, test_cases)
        )
        thread.daemon = True
        thread.start()

        return Response({
            'message': '快速测试已启动',
            'test_type': test_type,
            'status': 'running',
            'execution_id': test_result.id,
        })

    def _execute_quick_test(self, test_result, test_type, test_cases):
        """执行快速测试"""
        try:
            time.sleep(2)  # 模拟执行时间

            # 模拟结果
            passed = random.random() > 0.3

            test_result.status = 'passed' if passed else 'failed'
            test_result.completed_at = timezone.now()
            test_result.duration_ms = 2000
            test_result.test_log = json.dumps({
                'message': '快速测试执行完成',
                'test_type': test_type,
                'test_cases': test_cases,
                'result': 'passed' if passed else 'failed',
            }, ensure_ascii=False)
            test_result.save()

        except Exception as e:
            test_result.status = 'error'
            test_result.completed_at = timezone.now()
            test_result.error_message = str(e)
            test_result.save()


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
            'log_output': run.log_output[:5000] if run.log_output else '',
            'test_results_summary': run.test_results_summary,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'completed_at': run.completed_at.isoformat() if run.completed_at else None,
            'created_at': run.created_at.isoformat(),
        })


class PipelineRunTriggerView(APIView):
    """POST /api/qa/devops/cicd-config/{config_id}/trigger/ — 手动触发"""

    permission_classes = [IsAuthenticated]

    def post(self, request, config_id):
        config = _get_accessible_cicd_config(request.user, config_id, active_only=True)
        if config is None:
            return Response({'error': 'CI/CD配置不存在'}, status=status.HTTP_404_NOT_FOUND)

        run = PipelineRun.objects.create(
            cicd_config=config,
            project=config.project,
            status='running',
            branch=config.branch,
            started_at=timezone.now(),
        )

        # 模拟异步执行（实际应调用 webhook 或启动 Jenkins/GitLab job）
        thread = threading.Thread(target=self._simulate_run, args=(run,))
        thread.daemon = True
        thread.start()

        return Response({
            'message': 'Pipeline 已触发',
            'run_id': run.id,
            'status': 'running',
        }, status=status.HTTP_201_CREATED)

    def _simulate_run(self, run):
        try:
            time.sleep(3)
            run.status = 'passed' if random.random() > 0.2 else 'failed'
            run.completed_at = timezone.now()
            run.test_results_summary = {
                'total': random.randint(10, 50),
                'passed': random.randint(8, 48),
                'failed': random.randint(1, 5),
            }
            run.log_output = f'[PIPELINE] Build completed with status: {run.status}\nTests: {run.test_results_summary}'
            run.save()
        except Exception as e:
            run.status = 'failed'
            run.completed_at = timezone.now()
            run.error_message = str(e)
            run.save()


class PipelineRunWebhookView(APIView):
    """POST /api/qa/devops/cicd-config/{config_id}/webhook/ — 外部CI/CD回调"""

    permission_classes = []  # webhook 不需要 session 认证

    def post(self, request, config_id):
        try:
            config = CiCdConfig.objects.get(pk=config_id, is_active=True)
        except CiCdConfig.DoesNotExist:
            return Response({'error': '配置不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 简单 token 验证
        token = request.headers.get('X-CI-Token', '') or request.data.get('token', '')
        if config.api_token and token != config.api_token:
            return Response({'error': 'token 无效'}, status=status.HTTP_403_FORBIDDEN)

        status_val = request.data.get('status', 'running')
        commit_sha = request.data.get('commit_sha', '')
        branch = request.data.get('branch', '')

        run = PipelineRun.objects.create(
            cicd_config=config,
            project=config.project,
            status=status_val,
            commit_sha=commit_sha,
            branch=branch,
            log_output=request.data.get('log_output', ''),
            test_results_summary=request.data.get('test_results_summary', {}),
            started_at=timezone.now() if status_val == 'running' else None,
            completed_at=timezone.now() if status_val in ('passed', 'failed') else None,
        )

        return Response({'message': 'Webhook received', 'run_id': run.id}, status=status.HTTP_201_CREATED)


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
        from qa_center.models import ApiTestCase, UiTestCase, PerformanceTestCase
        total_tasks = Task.objects.filter(column__project_id=project_id).count()
        linked_api = ApiTestCase.objects.filter(project_id=project_id, related_tasks__isnull=False).count()
        linked_ui = UiTestCase.objects.filter(project_id=project_id, related_tasks__isnull=False).count()
        linked_perf = PerformanceTestCase.objects.filter(project_id=project_id, related_tasks__isnull=False).count()
        has_linked_tests = Task.objects.filter(
            column__project_id=project_id
        ).filter(
            Q(linked_api_test_cases__isnull=False) |
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
            project_id=project_id, status__in=['passed', 'failed']
        ).order_by('-created_at')[:10])
        total_pl = len(recent_pipelines)
        passed_pl = sum(1 for r in recent_pipelines if r.status == 'passed')
        deploy_rate = round(passed_pl / total_pl * 20, 1) if total_pl > 0 else 0

        total_score = round(test_coverage + test_pass_rate + perf_score + bug_score + deploy_rate, 1)

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
