"""TestRun 操作端点 (cancel 等)"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from .models import TestRun, TestRunCaseResult
from room.project_access import ensure_project_id_access, project_access_q

logger = logging.getLogger(__name__)


def _ensure_run_project_access(request, run):
    ensure_project_id_access(request.user, run.project_id)

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
        run = TestRun.objects.select_related('project').get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)
    _ensure_run_project_access(request, run)

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
    qs = TestRun.objects.select_related('project', 'triggered_by').filter(
        project_access_q('project', request.user)
    ).distinct()
    project_id = request.query_params.get('project')
    if project_id:
        ensure_project_id_access(request.user, project_id)
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
    _ensure_run_project_access(request, run)
    data = _serialize_run(run)
    data['case_count'] = run.case_results.count()
    data['summary'] = run.summary
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_run_cases(request, run_id):
    try:
        run = TestRun.objects.select_related('project').get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)
    _ensure_run_project_access(request, run)

    qs = run.case_results.select_related('api_auto_case', 'ui_test_case').order_by('sequence')
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
            'test_run__project', 'api_auto_case', 'ui_test_case'
        ).get(id=case_result_id, test_run_id=run_id)
    except TestRunCaseResult.DoesNotExist:
        return Response({'error': 'CaseResult 不存在'}, status=status.HTTP_404_NOT_FOUND)
    _ensure_run_project_access(request, case_result.test_run)
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


def _result_semantics(case_result):
    payload = case_result.result_metadata if isinstance(case_result.result_metadata, dict) else {}
    expectation_type = payload.get('expectation_type') or 'success_response'
    default_assertion_policy = payload.get('default_assertion_policy') or (
        'expected_error_response' if expectation_type == 'error_response' else 'success_response'
    )
    expected_status = payload.get('expected_status')
    provider = payload.get('provider') or 'http'
    semantic_status = payload.get('semantic_status')
    semantic_label = payload.get('semantic_label')

    passed = case_result.status == 'passed'
    failure_like = case_result.status == 'failed'
    if not semantic_status or not semantic_label:
        if expectation_type == 'error_response':
            if passed:
                semantic_status = 'expected_error_matched'
                semantic_label = '预期错误响应且匹配成功'
            elif failure_like:
                semantic_status = 'expected_error_unmatched'
                semantic_label = '预期错误响应但未匹配'
            else:
                semantic_status = 'expected_error_execution_error'
                semantic_label = '预期错误场景执行异常'
        else:
            if passed:
                semantic_status = 'success_response_passed'
                semantic_label = '成功响应断言通过'
            else:
                semantic_status = 'success_response_failed'
                semantic_label = '测试失败'

    return {
        'provider': provider,
        'expectation_type': expectation_type,
        'default_assertion_policy': default_assertion_policy,
        'expected_status': expected_status,
        'semantic_status': semantic_status,
        'semantic_label': semantic_label,
    }


def _serialize_case_result(r, full=False):
    semantics = _result_semantics(r)
    base = {
        'id': r.id,
        'test_run_id': r.test_run_id,
        'case_type': r.case_type,
        'sequence': r.sequence,
        'api_auto_case_id': r.api_auto_case_id,
        'ui_test_case_id': r.ui_test_case_id,
        'name': r.api_auto_case.name if r.api_auto_case else (r.ui_test_case.name if r.ui_test_case else ''),
        'status': r.status,
        'duration_ms': r.duration_ms,
        'status_code': r.status_code,
        'error_message': r.error_message,
        'provider': semantics['provider'],
        'expectation_type': semantics['expectation_type'],
        'default_assertion_policy': semantics['default_assertion_policy'],
        'expected_status': semantics['expected_status'],
        'semantic_status': semantics['semantic_status'],
        'semantic_label': semantics['semantic_label'],
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
            'trace_id': r.trace_id,
            'raw_status': r.raw_status,
            'error_code': r.error_code,
            'response_snapshot': r.response_snapshot,
            'extracted_variables_preview': r.extracted_variables_preview,
            'result_metadata': r.result_metadata,
        })
    return base


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rerun_test_run(request, run_id):
    """重跑 TestRun。

    P1 重构后：legacy API 用例模型（ApiTestCase）已删除，基于它的重跑链路不再支持。
    请通过 API 用例页面的 execute 入口重新执行用例。
    """
    try:
        old_run = TestRun.objects.select_related('project').get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)
    _ensure_run_project_access(request, old_run)
    return Response(
        {
            'detail': 'Legacy API 用例重跑已废弃。请从 API 用例页面重新执行。',
            'error_code': 'rerun_deprecated',
            'old_run_id': old_run.id,
        },
        status=status.HTTP_410_GONE,
    )
