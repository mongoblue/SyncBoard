"""
QA Center Celery 任务：性能压测异步执行。

将 Locust 子进程的生命周期与 Django 进程解耦：
- views_performance.execute 提交 run_performance_test.delay(...)
- worker 拉起 LocustRunner、阻塞等待结束、写入 PerformanceTestResult、通过 channels 推送实时指标
- stop 通过把 TestResult.status 置为 'stopped' 来通知 worker 中的轮询循环退出
"""

import json
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .locust_runner import LocustRunner


def _ws_send(execution_id: int, payload: dict) -> None:
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"performance_test_{execution_id}",
            {"type": "test_update", "data": payload},
        )
    except Exception as exc:
        print(f"[perf-task] WS push failed: {exc}")


def _should_stop(execution_id: int) -> bool:
    """检查 DB 中是否被标记为 stopped（由 views.stop 设置）。"""
    from .models import TestResult
    try:
        return TestResult.objects.filter(id=execution_id, status='stopped').exists()
    except Exception:
        return False


@shared_task(bind=True, name='qa_center.run_performance_test')
def run_performance_test(
    self,
    execution_id: int,
    test_case_id: int,
    host: str,
    users: int,
    spawn_rate: int,
    run_time: str,
) -> dict:
    """在 worker 中跑 Locust 子进程，写回 TestResult + PerformanceTestResult。"""
    from .models import PerformanceTestCase, PerformanceTestResult, TestResult

    try:
        test_result = TestResult.objects.get(id=execution_id)
        test_case = PerformanceTestCase.objects.get(id=test_case_id)
    except (TestResult.DoesNotExist, PerformanceTestCase.DoesNotExist) as exc:
        print(f"[perf-task] missing record: {exc}")
        return {'ok': False, 'error': 'record_not_found'}

    runner = LocustRunner(execution_id=execution_id)

    def on_metrics(_metrics):
        stats = runner.get_current_stats()
        stats['execution_id'] = execution_id
        stats['test_case_id'] = test_case_id
        _ws_send(execution_id, stats)

    runner.register_callback(on_metrics)

    started = runner.start_test(
        test_case=test_case,
        host=host,
        users=users,
        spawn_rate=spawn_rate,
        run_time=run_time,
    )
    if not started:
        test_result.status = 'error'
        test_result.error_message = '启动 Locust 测试失败'
        test_result.completed_at = timezone.now()
        test_result.save()
        _ws_send(execution_id, {'state': 'error', 'execution_id': execution_id})
        return {'ok': False, 'error': 'start_failed'}

    stopped_by_user = False
    while runner.is_running():
        if _should_stop(execution_id):
            stopped_by_user = True
            runner.stop_test()
            break
        time.sleep(0.5)

    # 拉一次完整 payload（含时间序列、分布）
    payload = runner.get_full_payload()
    final_stats = runner.get_current_stats()

    completed_at = timezone.now()
    duration_ms: Optional[int] = None
    if test_result.started_at:
        duration_ms = int((completed_at - test_result.started_at).total_seconds() * 1000)

    error_rate = final_stats.get('error_rate', 0) or 0
    if stopped_by_user:
        final_status = 'stopped'
    elif error_rate < (test_case.expected_error_rate or 5.0):
        final_status = 'completed'
    else:
        final_status = 'failed'

    test_result.status = final_status
    test_result.response_time_ms = final_stats.get('avg_response_time', 0)
    test_result.throughput = final_stats.get('throughput', 0)
    test_result.error_rate = error_rate
    test_result.completed_at = completed_at
    if duration_ms is not None:
        test_result.duration_ms = duration_ms

    execution_log = {
        'summary': {
            'total': 1,
            'passed': 1 if final_status == 'completed' else 0,
            'failed': 0 if final_status == 'completed' else 1,
            'pass_rate': 100 if final_status == 'completed' else 0,
        },
        'results': [{
            'case_id': test_case.id,
            'case_name': test_case.name,
            'type': 'performance',
            'passed': final_status == 'completed',
            'response_time_ms': final_stats.get('avg_response_time', 0),
            'message': (
                f"RPS: {final_stats.get('throughput', 0):.1f}, "
                f"平均响应时间: {final_stats.get('avg_response_time', 0):.0f}ms, "
                f"错误率: {error_rate:.2f}%"
            ),
            'request': {
                'method': test_case.method,
                'url': test_case.url,
                'headers': test_case.headers,
                'body': test_case.body,
            },
            'state': final_status,
            'start_time': final_stats.get('start_time'),
        }],
    }
    test_result.test_log = json.dumps(execution_log, ensure_ascii=False)
    test_result.save()

    # 持久化结构化指标
    try:
        PerformanceTestResult.objects.create(
            test_case=test_case,
            test_result=test_result,
            executed_by=test_result.executed_by,
            total_requests=final_stats.get('total_requests', 0),
            successful_requests=final_stats.get('successful_requests', 0),
            failed_requests=final_stats.get('failed_requests', 0),
            avg_response_time_ms=final_stats.get('avg_response_time', 0) or 0,
            min_response_time_ms=final_stats.get('min_response_time', 0) or 0,
            max_response_time_ms=final_stats.get('max_response_time', 0) or 0,
            p50_response_time_ms=final_stats.get('p50_response_time', 0) or 0,
            p90_response_time_ms=final_stats.get('p90_response_time', 0) or 0,
            p95_response_time_ms=final_stats.get('p95_response_time', 0) or 0,
            p99_response_time_ms=final_stats.get('p99_response_time', 0) or 0,
            throughput=final_stats.get('throughput', 0) or 0,
            error_rate=error_rate,
            response_time_distribution=payload.get('response_time_distribution', {}) or {},
            throughput_over_time=payload.get('throughput_over_time', []) or [],
            response_time_over_time=payload.get('response_time_over_time', []) or [],
            error_details=final_stats.get('errors', []) or [],
        )
    except Exception as exc:
        # 持久化失败不阻塞主流程：TestResult 已经保存，前端仍可看到
        print(f"[perf-task] PerformanceTestResult.create failed: {exc}")

    # 推送最终态
    final_payload = dict(final_stats)
    final_payload['state'] = final_status
    final_payload['execution_id'] = execution_id
    _ws_send(execution_id, final_payload)

    return {'ok': True, 'status': final_status, 'execution_id': execution_id}
