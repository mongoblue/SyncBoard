from django.db import models
from django.contrib.auth.models import User
from room.models import Project, Task


class Bug(models.Model):
    """Bug 主模型 - 独立于 Task，承载完整生命周期"""

    STATUS_CHOICES = [
        ('new', '新建'),
        ('confirmed', '已确认'),
        ('assigned', '已指派'),
        ('fixing', '修复中'),
        ('fixed', '已修复'),
        ('verifying', '待验证'),
        ('closed', '已关闭'),
        ('reopened', '重新打开'),
        ('rejected', '已拒绝'),
    ]

    SEVERITY_CHOICES = [
        ('blocker', '阻塞'),
        ('critical', '严重'),
        ('major', '一般'),
        ('minor', '次要'),
        ('trivial', '轻微'),
    ]

    PRIORITY_CHOICES = [
        ('p0', 'P0'),
        ('p1', 'P1'),
        ('p2', 'P2'),
        ('p3', 'P3'),
    ]

    SOURCE_CHOICES = [
        ('manual', '手工'),
        ('api_auto', '接口自动化'),
        ('performance', '性能测试'),
        ('ui_auto', 'UI 自动化'),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE,
        related_name='bugs', verbose_name='所属项目'
    )

    title = models.CharField(max_length=255, verbose_name='标题')
    description = models.TextField(blank=True, verbose_name='描述')
    steps_to_reproduce = models.TextField(blank=True, verbose_name='复现步骤')
    expected = models.TextField(blank=True, verbose_name='预期结果')
    actual = models.TextField(blank=True, verbose_name='实际结果')
    environment = models.CharField(max_length=100, blank=True, verbose_name='环境')

    severity = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, default='major', verbose_name='严重程度'
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default='p2', verbose_name='优先级'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='new', verbose_name='状态'
    )

    reporter = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='reported_bugs', verbose_name='报告人'
    )
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_bugs', verbose_name='当前负责人'
    )
    fixer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fixed_bugs', verbose_name='修复人'
    )
    verifier = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_bugs', verbose_name='验证人'
    )

    # 测试来源（手动建的 bug 留空 / manual）
    source_test_type = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default='manual', verbose_name='来源类型'
    )
    source_case_id = models.IntegerField(null=True, blank=True, verbose_name='来源用例ID')
    source_result_id = models.IntegerField(null=True, blank=True, verbose_name='来源结果ID')

    # 可选关联看板任务
    linked_task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='linked_bugs', verbose_name='关联任务'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='关闭时间')

    class Meta:
        db_table = 'bug'
        ordering = ['-created_at']
        verbose_name = 'Bug'
        verbose_name_plural = 'Bug'
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['reporter', '-created_at']),
            models.Index(fields=['source_test_type', 'source_case_id']),
        ]

    def __str__(self):
        return f'[{self.get_status_display()}] {self.title}'


class BugTransition(models.Model):
    """Bug 状态流转记录"""

    bug = models.ForeignKey(
        Bug, on_delete=models.CASCADE,
        related_name='transitions', verbose_name='Bug'
    )
    operator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='bug_transitions', verbose_name='操作人'
    )
    from_status = models.CharField(max_length=20, verbose_name='原状态')
    to_status = models.CharField(max_length=20, verbose_name='新状态')
    comment = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='时间')

    class Meta:
        db_table = 'bug_transition'
        ordering = ['-created_at']
        verbose_name = 'Bug 流转记录'
        verbose_name_plural = 'Bug 流转记录'
        indexes = [models.Index(fields=['bug', '-created_at'])]


class BugComment(models.Model):
    """Bug 评论"""

    bug = models.ForeignKey(
        Bug, on_delete=models.CASCADE,
        related_name='comments', verbose_name='Bug'
    )
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='bug_comments', verbose_name='作者'
    )
    content = models.TextField(verbose_name='内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'bug_comment'
        ordering = ['created_at']
        verbose_name = 'Bug 评论'
        verbose_name_plural = 'Bug 评论'
        indexes = [models.Index(fields=['bug', 'created_at'])]
