"""测试失败自动创建 Bug 记录（接入 bug_tracker.Bug 模型）"""
import logging

from django.db.models import Q

from room.models import Notification

logger = logging.getLogger(__name__)


def _existing_open_bug(project_id: int, source_test_type: str, source_case_id: int):
    """查同一用例已有的未关闭 bug，避免重复建"""
    from bug_tracker.models import Bug
    return Bug.objects.filter(
        project_id=project_id,
        source_test_type=source_test_type,
        source_case_id=source_case_id,
    ).exclude(status__in=['closed', 'rejected']).first()


def create_bug_from_test_failure(test_case, test_result, error_message=''):
    """
    测试失败时自动创建 Bug 记录。

    Args:
        test_case: ApiAutoTestCase / PerformanceTestCase 实例（必须有 project、name 字段）
        test_result: ApiAutoTestCaseResult / PerformanceTestResult / TestResult 实例
        error_message: 错误详情

    Returns:
        Bug or None
    """
    from bug_tracker.models import Bug, BugTransition

    project = getattr(test_case, 'project', None)
    if project is None:
        logger.warning('[AutoBug] test_case 没有 project，跳过')
        return None

    # 推断来源类型
    source_test_type = 'api_auto'
    cls_name = type(test_case).__name__
    if 'Performance' in cls_name:
        source_test_type = 'performance'
    elif 'Ui' in cls_name:
        source_test_type = 'ui_auto'

    case_id = getattr(test_case, 'id', None)
    result_id = getattr(test_result, 'id', None)

    # 去重：同一用例已有 open bug 就不再建
    existing = _existing_open_bug(project.id, source_test_type, case_id)
    if existing:
        logger.info(f'[AutoBug] {test_case.name} 已有未关闭 Bug #{existing.id}，跳过')
        return existing

    # 构建描述
    desc_lines = [
        '## 测试失败自动生成',
        '',
        f'- **测试用例**: {test_case.name}',
        f'- **测试类型**: {source_test_type}',
    ]
    if hasattr(test_case, 'url') and test_case.url:
        desc_lines.append(f'- **接口地址**: {test_case.url}')
    if hasattr(test_case, 'method') and test_case.method:
        desc_lines.append(f'- **请求方法**: {test_case.method}')

    if error_message:
        desc_lines += ['', '### 错误详情', '```', error_message[:2000], '```']

    reporter = getattr(test_case, 'created_by', None)

    try:
        bug = Bug.objects.create(
            project=project,
            title=f'[测试失败] {test_case.name}',
            description='\n'.join(desc_lines),
            actual=error_message[:2000] if error_message else '',
            severity='major',
            priority='p1',
            status='new',
            reporter=reporter,
            assignee=reporter,  # 默认指给测试用例创建者
            source_test_type=source_test_type,
            source_case_id=case_id,
            source_result_id=result_id,
        )

        # 写一条创建流转记录
        BugTransition.objects.create(
            bug=bug, operator=reporter,
            from_status='', to_status='new',
            comment='测试失败自动创建',
        )

        # 通知 reporter
        if reporter:
            Notification.objects.create(
                user=reporter,
                title='测试失败 - Bug 已自动创建',
                message=f'测试用例 "{test_case.name}" 失败，已自动创建 Bug #{bug.id}',
                type='test_failure',
                project=project,
            )

            # WebSocket 广播
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        'system_broadcast',
                        {
                            'type': 'global_notification',
                            'message': f'测试失败: {test_case.name}，Bug #{bug.id} 已自动创建',
                            'level': 'warning',
                        },
                    )
            except Exception:
                pass

        logger.info(f'[AutoBug] 已创建 Bug #{bug.id}: {bug.title}')
        return bug

    except Exception as e:
        logger.error(f'[AutoBug] 创建 Bug 失败: {e}')
        return None
