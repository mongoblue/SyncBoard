"""
性能测试 API 视图 - Headless 模式
使用 Locust Python API 直接控制测试，不启动 Web 界面
实时推送测试结果到前端
"""

import os
import sys
import json
import time
import socket
from datetime import datetime
from urllib.parse import urlparse

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import PerformanceTestCase, PerformanceTestResult, TestResult
from .serializers import (
    PerformanceTestCaseSerializer,
    PerformanceTestCaseListSerializer,
    PerformanceTestResultSerializer,
    PerformanceTestResultListSerializer,
)
from .locust_runner import LocustRunner


class PerformanceTestCaseViewSet(viewsets.ModelViewSet):
    """性能测试用例 ViewSet - Headless 模式"""

    permission_classes = [IsAuthenticated]

    # 存储运行中的 locust 实例
    _locust_runners = {}

    def get_queryset(self):
        """根据条件过滤"""
        queryset = PerformanceTestCase.objects.all()

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        keyword = self.request.query_params.get('keyword')
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)

        return queryset.select_related('project', 'created_by')

    def get_serializer_class(self):
        """根据动作选择序列化器"""
        if self.action == 'list':
            return PerformanceTestCaseListSerializer
        return PerformanceTestCaseSerializer

    def perform_create(self, serializer):
        """创建时设置创建者"""
        serializer.save(created_by=self.request.user)

    def _send_ws_update(self, execution_id: int, data: dict):
        """发送 WebSocket 更新"""
        try:
            print(f"[WebSocket] 准备发送数据到 performance_test_{execution_id}: {data}")
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"performance_test_{execution_id}",
                {
                    "type": "test_update",
                    "data": data
                }
            )
            print(f"[WebSocket] 数据发送成功")
        except Exception as e:
            print(f"[WebSocket] 发送失败: {e}")
            import traceback
            traceback.print_exc()

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """
        执行性能测试 - Headless 模式
        不启动 Locust Web 界面，直接获取结果
        """
        test_case = self.get_object()

        # 1. 准备参数
        users = request.data.get('users', test_case.concurrent_users)
        spawn_rate = request.data.get('spawn_rate', max(1, users // 10))
        run_time = request.data.get('run_time', f"{test_case.duration_seconds}s")

        # 解析 URL 获取 host
        parsed_url = urlparse(test_case.url)
        host = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if not host:
            host = test_case.url

        # 2. 记录数据库
        test_result = TestResult.objects.create(
            test_type='performance',
            name=f"{test_case.name}",
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
            }
        )

        # 3. 创建 LocustRunner
        runner = LocustRunner()

        # 4. 注册回调函数，实时推送数据
        def on_metrics_update(metrics):
            stats = runner.get_current_stats()
            stats['execution_id'] = test_result.id
            stats['test_case_id'] = test_case.id
            self._send_ws_update(test_result.id, stats)

        runner.register_callback(on_metrics_update)

        # 5. 启动测试
        success = runner.start_test(
            test_case=test_case,
            host=host,
            users=users,
            spawn_rate=spawn_rate,
            run_time=run_time
        )

        if not success:
            test_result.status = 'error'
            test_result.error_message = '启动 Locust 测试失败'
            test_result.save()
            return Response({'error': '启动测试失败'}, status=500)

        # 6. 保存 runner 实例
        self._locust_runners[test_result.id] = runner

        # 7. 启动后台线程监控测试结束
        import threading
        def monitor_test():
            while runner.is_running():
                time.sleep(1)
            
            # 测试结束，保存结果
            final_stats = runner.get_current_stats()
            test_result.status = 'completed' if final_stats['error_rate'] < 5 else 'failed'
            test_result.response_time_ms = final_stats['avg_response_time']
            test_result.throughput = final_stats['throughput']
            test_result.error_rate = final_stats['error_rate']
            test_result.completed_at = timezone.now()
            
            # 计算持续时间
            if test_result.started_at:
                duration = (test_result.completed_at - test_result.started_at).total_seconds() * 1000
                test_result.duration_ms = int(duration)
            
            # 保存完整的性能指标到 test_log
            execution_log = {
                'summary': {
                    'total': 1,
                    'passed': 1 if final_stats['error_rate'] < 5 else 0,
                    'failed': 0 if final_stats['error_rate'] < 5 else 1,
                    'pass_rate': 100 if final_stats['error_rate'] < 5 else 0
                },
                'results': [{
                    'case_id': test_case.id,
                    'case_name': test_case.name,
                    'type': 'performance',
                    'passed': final_stats['error_rate'] < 5,
                    'response_time_ms': final_stats['avg_response_time'],
                    'message': f"RPS: {final_stats['throughput']:.1f}, 平均响应时间: {final_stats['avg_response_time']:.0f}ms, 错误率: {final_stats['error_rate']:.2f}%",
                    'request': {
                        'method': test_case.method,
                        'url': test_case.url,
                        'headers': test_case.headers,
                        'body': test_case.body
                    },
                    'response': {
                        'status_code': 200 if final_stats['error_rate'] < 5 else 500,
                        'headers': {},
                        'body': ''
                    },
                    # 性能测试专用指标
                    'throughput': final_stats['throughput'],
                    'avg_response_time': final_stats['avg_response_time'],
                    'min_response_time': final_stats['min_response_time'],
                    'max_response_time': final_stats['max_response_time'],
                    'p50_response_time': final_stats['p50_response_time'],
                    'p90_response_time': final_stats['p90_response_time'],
                    'p95_response_time': final_stats['p95_response_time'],
                    'p99_response_time': final_stats['p99_response_time'],
                    'total_requests': final_stats['total_requests'],
                    'successful_requests': final_stats['successful_requests'],
                    'failed_requests': final_stats['failed_requests'],
                    'error_rate': final_stats['error_rate'],
                    'errors': final_stats['errors'],
                    'state': 'completed',
                    'start_time': final_stats['start_time']
                }]
            }
            test_result.test_log = json.dumps(execution_log, ensure_ascii=False)
            
            test_result.save()
            
            # 发送最终更新
            final_stats['state'] = 'completed'
            self._send_ws_update(test_result.id, final_stats)
            
            # 清理
            if test_result.id in self._locust_runners:
                del self._locust_runners[test_result.id]

        threading.Thread(target=monitor_test, daemon=True).start()

        return Response({
            'message': '测试已启动',
            'execution_id': test_result.id,
            'status': 'running',
            'ws_channel': f'performance_test_{test_result.id}'
        })

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """
        停止性能测试
        """
        execution_id = request.data.get('execution_id')
        print(f"[Performance Stop] 收到停止请求: execution_id={execution_id}")
        print(f"[Performance Stop] 当前内存中的 runners: {list(self._locust_runners.keys())}")

        # 1. 先检查内存中是否有运行的测试
        if execution_id in self._locust_runners:
            print(f"[Performance Stop] 在内存中找到 runner，正在停止...")
            runner = self._locust_runners[execution_id]
            runner.stop_test()
            del self._locust_runners[execution_id]

            # 更新测试结果
            try:
                test_result = TestResult.objects.get(id=execution_id)
                test_result.status = 'stopped'
                test_result.completed_at = timezone.now()
                if test_result.started_at:
                    duration = (test_result.completed_at - test_result.started_at).total_seconds() * 1000
                    test_result.duration_ms = int(duration)
                test_result.save()
                print(f"[Performance Stop] 数据库状态已更新为 stopped")
            except Exception as e:
                print(f"[Performance Stop] 更新数据库失败: {e}")

            return Response({'message': '压力测试已停止'})

        # 2. 如果内存中没有，检查数据库中是否有正在运行的测试
        print(f"[Performance Stop] 内存中未找到，检查数据库...")
        try:
            test_result = TestResult.objects.get(id=execution_id)
            print(f"[Performance Stop] 数据库中找到测试，当前状态: {test_result.status}")

            if test_result.status == 'running':
                # 数据库显示正在运行，但内存中没有，可能是服务器重启了
                test_result.status = 'stopped'
                test_result.completed_at = timezone.now()
                if test_result.started_at:
                    duration = (test_result.completed_at - test_result.started_at).total_seconds() * 1000
                    test_result.duration_ms = int(duration)
                test_result.save()
                print(f"[Performance Stop] 数据库状态已更新为 stopped")
                return Response({'message': '压力测试已停止（数据库状态已更新）'})
            elif test_result.status == 'stopped':
                return Response({'message': '测试已经停止'})
            elif test_result.status == 'completed':
                return Response({'message': '测试已完成'})
        except TestResult.DoesNotExist:
            print(f"[Performance Stop] 数据库中未找到测试记录")
        except Exception as e:
            print(f"[Performance Stop] 查询数据库失败: {e}")

        return Response(
            {'error': '未找到运行中的测试'},
            status=status.HTTP_404_NOT_FOUND
        )

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        获取测试状态
        """
        execution_id = request.query_params.get('execution_id')

        if execution_id in self._locust_runners:
            runner = self._locust_runners[execution_id]
            stats = runner.get_current_stats()
            stats['execution_id'] = execution_id
            return Response(stats)

        # 检查是否已完成的测试
        try:
            test_result = TestResult.objects.get(id=execution_id)
            return Response({
                'execution_id': execution_id,
                'state': test_result.status,
                'is_running': False,
                'avg_response_time': test_result.response_time_ms,
                'throughput': test_result.throughput,
                'error_rate': test_result.error_rate,
            })
        except:
            pass

        return Response({
            'execution_id': execution_id,
            'state': 'not_found',
            'is_running': False
        })

    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        """
        获取性能测试用例的执行历史
        """
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
    """性能测试结果 ViewSet（只读）"""

    permission_classes = [IsAuthenticated]
    serializer_class = PerformanceTestResultSerializer

    def get_queryset(self):
        """根据条件过滤"""
        queryset = PerformanceTestResult.objects.all()

        test_case_id = self.request.query_params.get('test_case')
        if test_case_id:
            queryset = queryset.filter(test_case_id=test_case_id)

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(test_case__project_id=project_id)

        return queryset.select_related('test_case', 'executed_by')
