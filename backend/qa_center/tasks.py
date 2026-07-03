"""
QA Center Celery 任务：性能压测异步执行。

Celery 任务作为薄壳，实际执行逻辑统一委托给 ExecutionEngine._execute_sync()。
"""

from celery import shared_task


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
    """在 Celery worker 中同步执行压测，写回 TestResult + PerformanceTestResult。

    所有执行逻辑已统一到 ExecutionEngine._execute_sync()，
    此任务仅负责从 DB 加载用例并构建 TestJob。
    """
    from .models import PerformanceTestCase
    from .execution.job import TestJob
    from .execution.engine import ExecutionEngine

    try:
        test_case = PerformanceTestCase.objects.get(id=test_case_id)
    except PerformanceTestCase.DoesNotExist as exc:
        return {'ok': False, 'error': f'性能用例不存在: {exc}'}

    job = TestJob(
        test_case=test_case,
        host=host,
        users=users,
        spawn_rate=spawn_rate,
        run_time=run_time,
        async_mode=False,          # Celery worker 内走同步路径
        execution_id=execution_id,
    )

    engine = ExecutionEngine()
    result = engine.submit(job)

    return {
        'ok': result.ok,
        'status': result.status,
        'execution_id': execution_id,
    }
