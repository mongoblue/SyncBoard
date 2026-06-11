"""TestRun 操作端点 (cancel 等)"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from .models import TestRun, TestRunCaseResult


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

    # 标记 cancelled (临时属性,后台执行器会读取)
    run.cancelled = True
    # 用 update 防止覆盖后台线程对 count/pass_rate 的写
    TestRun.objects.filter(id=run.id).update(
        status='cancelled', completed_at=timezone.now(),
    )
    return Response({'status': 'cancelled', 'run_id': run.id})
