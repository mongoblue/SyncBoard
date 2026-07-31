"""TestTask 协作取消测试：检查点停止执行 + 取消信号传播。"""
from unittest.mock import patch

import pytest
from django.utils import timezone

from qa_center.models import TestResult, TestTask


def _make_task(mock_project, mock_user, **kwargs):
    return TestTask.objects.create(
        name=kwargs.pop('name', 'Cancel Task'),
        test_type=kwargs.pop('test_type', 'api'),
        project=mock_project,
        created_by=mock_user,
        trigger_type=kwargs.pop('trigger_type', 'manual'),
        test_config=kwargs.pop('test_config', {'api_cases': [1]}),
        status=kwargs.pop('status', 'running'),
        **kwargs,
    )


@pytest.mark.django_db
def test_cancel_before_execution_stops_immediately(mock_project, mock_user):
    from qa_center.services.devops.test_execution_service import TestExecutionService

    task = _make_task(mock_project, mock_user)
    tr = TestResult.objects.create(
        test_type='api', name='placeholder', status='running',
        project=mock_project, executed_by=mock_user, source='devops',
        started_at=timezone.now(), task_id=str(task.id),
        aborted=True,  # 已在执行前被取消
    )

    svc = TestExecutionService()
    with patch.object(TestExecutionService, '_run_api_cases') as run_api, \
         patch.object(TestExecutionService, '_run_ui_cases') as run_ui, \
         patch.object(TestExecutionService, '_run_performance_cases') as run_perf:
        svc.execute_test_task(task, tr)

    run_api.assert_not_called()
    run_ui.assert_not_called()
    run_perf.assert_not_called()

    tr.refresh_from_db()
    assert tr.status == 'cancelled'
    task.refresh_from_db()
    assert task.status == 'cancelled'


@pytest.mark.django_db
def test_cancel_between_batches_skips_remaining(mock_project, mock_user):
    from qa_center.services.devops.test_execution_service import TestExecutionService

    task = _make_task(mock_project, mock_user, test_config={
        'api_cases': [1],
        'ui_cases': [2],
        'performance_cases': [3],
    })
    tr = TestResult.objects.create(
        test_type='api', name='placeholder', status='running',
        project=mock_project, executed_by=mock_user, source='devops',
        started_at=timezone.now(), task_id=str(task.id),
    )

    svc = TestExecutionService()

    def _fake_run_api(*args, **kwargs):
        # API 批次执行期间用户取消 → 置信号
        tr.refresh_from_db()
        tr.aborted = True
        tr.save(update_fields=['aborted'])
        return ([{'case_id': 1, 'passed': True}], 1, 0)

    with patch.object(TestExecutionService, '_run_api_cases', side_effect=_fake_run_api) as run_api, \
         patch.object(TestExecutionService, '_run_ui_cases') as run_ui, \
         patch.object(TestExecutionService, '_run_performance_cases') as run_perf:
        svc.execute_test_task(task, tr)

    run_api.assert_called_once()
    run_ui.assert_not_called()
    run_perf.assert_not_called()

    tr.refresh_from_db()
    assert tr.status == 'cancelled'
    task.refresh_from_db()
    assert task.status == 'cancelled'


@pytest.mark.django_db
def test_cancel_task_sets_signal_on_all_running_results(mock_project, mock_user):
    from qa_center.services.devops.test_execution_service import TestExecutionService

    task = _make_task(mock_project, mock_user)
    tr1 = TestResult.objects.create(
        test_type='api', name='r1', status='running',
        project=mock_project, executed_by=mock_user, source='devops',
        started_at=timezone.now(), task_id=str(task.id),
    )
    tr2 = TestResult.objects.create(
        test_type='performance', name='r2', status='running',
        project=mock_project, executed_by=mock_user, source='devops',
        started_at=timezone.now(), task_id=str(task.id),
    )
    # 已完成的结果不应被触碰
    TestResult.objects.create(
        test_type='api', name='done', status='passed',
        project=mock_project, executed_by=mock_user, source='devops',
        started_at=timezone.now(), task_id=str(task.id),
    )

    svc = TestExecutionService()
    result = svc.cancel_task(task)

    assert result['cancelled'] is True
    assert result['cancel_mode'] == 'cooperative'
    assert result['cancelled_results'] == 2

    tr1.refresh_from_db()
    tr2.refresh_from_db()
    assert tr1.aborted is True and tr1.status == 'cancelled'
    assert tr2.aborted is True and tr2.status == 'cancelled'
    assert TestResult.objects.get(name='done').status == 'passed'
