"""TestRun 操作端点 (cancel 等)"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db import close_old_connections

from .models import TestRun, TestRunCaseResult, ApiTestCase

logger = logging.getLogger(__name__)


def _parse_pagination(request, default_size=20, max_size=100):
    """解析 page / page_size,失败返回 400 Response。"""
    try:
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(
            max_size,
            max(1, int(request.query_params.get('page_size', default_size))),
        )
    except (ValueError, TypeError):
        return None, None, Response(
            {'error': 'invalid page or page_size'}, status=400,
        )
    return page, page_size, None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_test_run(request, run_id):
    """取消一个 running/pending 的 TestRun。

    - pending case 立即变 skipped
    - running case 继续跑完
    - 跑完后 TestRun.status 变 cancelled
    """
    try:
        run = TestRun.objects.get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)

    if run.status not in ('pending', 'running'):
        return Response(
            {'error': f'TestRun 当前状态 {run.status},不可取消'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 把所有 pending 的 case 变 skipped
    TestRunCaseResult.objects.filter(
        test_run=run, status='pending',
    ).update(status='skipped', completed_at=timezone.now())

    # 仅标记 DB status='cancelled'。已在跑的 worker 会继续完成,
    # 后台 finalizer 重读 DB status 后会尊重 'cancelled',不再覆盖。
    # 用 update 防止覆盖后台线程对 count/pass_rate 的写。
    TestRun.objects.filter(id=run.id).update(
        status='cancelled', completed_at=timezone.now(),
    )
    return Response({'status': 'cancelled', 'run_id': run.id})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_test_runs(request):
    """GET /api/qa/runs/?project=&status=&test_type=&page=&page_size="""
    qs = TestRun.objects.select_related('project', 'triggered_by')
    project_id = request.query_params.get('project')
    if project_id:
        qs = qs.filter(project_id=project_id)
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    test_type = request.query_params.get('test_type')
    if test_type:
        qs = qs.filter(test_type=test_type)

    page, page_size, err = _parse_pagination(request, default_size=20, max_size=100)
    if err:
        return err
    total = qs.count()
    start = (page - 1) * page_size
    items = qs[start:start + page_size]

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': [_serialize_run(r) for r in items],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_run_detail(request, run_id):
    try:
        run = TestRun.objects.select_related('project', 'triggered_by').get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)
    data = _serialize_run(run)
    data['case_count'] = run.case_results.count()
    data['summary'] = run.summary
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_run_cases(request, run_id):
    try:
        run = TestRun.objects.get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)

    qs = run.case_results.select_related('api_test_case', 'ui_test_case').order_by('sequence')
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    page, page_size, err = _parse_pagination(request, default_size=50, max_size=200)
    if err:
        return err
    total = qs.count()
    start = (page - 1) * page_size
    items = qs[start:start + page_size]

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': [_serialize_case_result(r) for r in items],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_run_case_detail(request, run_id, case_result_id):
    try:
        case_result = TestRunCaseResult.objects.select_related(
            'test_run', 'api_test_case', 'ui_test_case'
        ).get(id=case_result_id, test_run_id=run_id)
    except TestRunCaseResult.DoesNotExist:
        return Response({'error': 'CaseResult 不存在'}, status=status.HTTP_404_NOT_FOUND)
    return Response(_serialize_case_result(case_result, full=True))


def _serialize_run(run):
    return {
        'id': run.id,
        'project_id': run.project_id,
        'project_name': run.project.name if run.project else '',
        'name': run.name,
        'trigger': run.trigger,
        'test_type': run.test_type,
        'status': run.status,
        'total_count': run.total_count,
        'passed_count': run.passed_count,
        'failed_count': run.failed_count,
        'error_count': run.error_count,
        'pass_rate': float(run.pass_rate) if run.pass_rate is not None else 0.0,
        'duration_ms': run.duration_ms,
        'triggered_by': run.triggered_by.username if run.triggered_by else None,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'created_at': run.created_at.isoformat() if run.created_at else None,
    }


def _serialize_case_result(r, full=False):
    base = {
        'id': r.id,
        'test_run_id': r.test_run_id,
        'case_type': r.case_type,
        'sequence': r.sequence,
        'api_test_case_id': r.api_test_case_id,
        'ui_test_case_id': r.ui_test_case_id,
        'name': r.api_test_case.name if r.api_test_case else (r.ui_test_case.name if r.ui_test_case else ''),
        'status': r.status,
        'duration_ms': r.duration_ms,
        'status_code': r.status_code,
        'error_message': r.error_message,
        'started_at': r.started_at.isoformat() if r.started_at else None,
        'completed_at': r.completed_at.isoformat() if r.completed_at else None,
    }
    if full:
        base.update({
            'response_body': r.response_body,
            'response_headers': r.response_headers,
            'assertion_results': r.assertion_results,
            'request_snapshot': r.request_snapshot,
            'curl': r.curl,
        })
    return base


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rerun_test_run(request, run_id):
    """用 config_snapshot 重新执行一个 TestRun。

    创建新 TestRun,继承原 run 的 case_ids / max_workers / environment_id,
    在后台线程里跑完后更新 status。
    """
    from .views_api_test import execute_single_api_case

    try:
        old_run = TestRun.objects.get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)

    config = old_run.config_snapshot or {}
    case_ids = config.get('case_ids', [])
    if not case_ids:
        # 兼容老的单条 run: 用 api_test_case 找原 case
        first_cr = old_run.case_results.filter(api_test_case__isnull=False).first()
        if first_cr:
            case_ids = [first_cr.api_test_case_id]

    if not case_ids:
        return Response(
            {'error': '原 TestRun 没有可重跑的 case'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cases = list(ApiTestCase.objects.filter(id__in=case_ids))
    if not cases:
        return Response(
            {'error': '原 case 已被删除,无法重跑'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    max_workers = int(config.get('max_workers', 4))
    triggered_user = request.user

    new_run = TestRun.objects.create(
        project=old_run.project,
        name=f"{old_run.name} (重跑)",
        trigger='manual',
        test_type=old_run.test_type,
        status='running',
        total_count=len(cases),
        started_at=timezone.now(),
        triggered_by=triggered_user,
        config_snapshot={
            **config,
            'rerun_from': old_run.id,
            'case_ids': [c.id for c in cases],
        },
    )

    def _background():
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(execute_single_api_case, case, new_run, idx + 1, triggered_user)
                    for idx, case in enumerate(cases)
                ]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        logger.exception('Rerun case error')
        finally:
            close_old_connections()
            new_run.refresh_from_db()
            new_run.recompute_pass_rate()
            current = TestRun.objects.filter(id=new_run.id).values_list('status', flat=True).first()
            if current == 'cancelled':
                new_run.completed_at = timezone.now()
                if new_run.started_at:
                    new_run.duration_ms = int((new_run.completed_at - new_run.started_at).total_seconds() * 1000)
                new_run.save(update_fields=['pass_rate', 'completed_at', 'duration_ms'])
                return
            if new_run.failed_count == 0 and new_run.error_count == 0:
                new_run.status = 'passed'
            elif new_run.error_count > 0:
                new_run.status = 'error'
            else:
                new_run.status = 'failed'
            new_run.completed_at = timezone.now()
            if new_run.started_at:
                new_run.duration_ms = int((new_run.completed_at - new_run.started_at).total_seconds() * 1000)
            new_run.save(update_fields=['status', 'completed_at', 'duration_ms', 'pass_rate'])

    thread = threading.Thread(target=_background)
    thread.daemon = True
    thread.start()

    return Response({'new_run_id': new_run.id}, status=status.HTTP_202_ACCEPTED)
