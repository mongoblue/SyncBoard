"""Bug 演示数据 seed — 命令和 API 共用"""
from typing import List, TYPE_CHECKING
from django.db import transaction
from .models import Bug

if TYPE_CHECKING:
    from room.models import Project


# 8 条示例 Bug：覆盖 5 个状态 + 4 个严重度 + 4 个来源
_DEMO_BUGS: List[dict] = [
    {'title': '[DEMO] 登录页 500 错误',         'status': 'new',       'severity': 'blocker',  'source_test_type': 'manual',      'description': '服务端异常'},
    {'title': '[DEMO] 任务列表加载慢',          'status': 'confirmed', 'severity': 'major',    'source_test_type': 'performance', 'description': 'P95 > 2s'},
    {'title': '[DEMO] API 返回字段缺失',        'status': 'assigned',  'severity': 'critical', 'source_test_type': 'api_auto',    'description': 'data 字段为空'},
    {'title': '[DEMO] 邀请成员后未刷新',        'status': 'fixing',    'severity': 'major',    'source_test_type': 'ui_auto',     'description': '需手动刷新'},
    {'title': '[DEMO] 看板拖拽卡顿',            'status': 'fixed',     'severity': 'minor',    'source_test_type': 'ui_auto',     'description': 'GPU 占用高'},
    {'title': '[DEMO] 评论提交失败',            'status': 'verifying', 'severity': 'major',    'source_test_type': 'manual',      'description': '前端 400'},
    {'title': '[DEMO] 项目设置无法保存',        'status': 'closed',    'severity': 'minor',    'source_test_type': 'manual',      'description': '已修复'},
    {'title': '[DEMO] 性能报告 P95 抖动',       'status': 'reopened',  'severity': 'critical', 'source_test_type': 'performance', 'description': '重新出现'},
]

_PRIORITY_BY_STATUS = {
    'new': 'p1', 'confirmed': 'p1', 'assigned': 'p1', 'fixing': 'p2',
    'fixed': 'p3', 'verifying': 'p2', 'closed': 'p3', 'reopened': 'p0',
}


def seed_demo_bugs(project: 'Project') -> int:
    """为项目创建 8 条 [DEMO] 前缀的 Bug。返回新增条数。幂等。"""
    with transaction.atomic():
        if Bug.objects.filter(project=project, title__startswith='[DEMO]').exists():
            return 0
        members = list(project.members.all())
        if not members:
            members = [project.owner]
        owner = project.owner
        created = 0
        for spec in _DEMO_BUGS:
            Bug.objects.create(
                project=project,
                title=spec['title'],
                description=spec['description'],
                status=spec['status'],
                severity=spec['severity'],
                priority=_PRIORITY_BY_STATUS[spec['status']],
                source_test_type=spec['source_test_type'],
                reporter=owner,
                assignee=members[created % len(members)],
            )
            created += 1
        return created
