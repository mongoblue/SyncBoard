import uuid
from django.db import models
from django.contrib.auth.models import User

# ============== 常量定义 ==============
DEFAULT_POSITION = 65535  # 任务/列默认位置值
MAX_POSITION_GAP = 1000   # 自动生成任务时的位置增量


def get_avatar_upload_path(instance, filename):
    return f'avatars/user_{instance.user.id}/{filename}'

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to=get_avatar_upload_path, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects')
    members = models.ManyToManyField(User, related_name='joined_projects', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name

    class Meta:
        db_table = 'project'
        verbose_name_plural = 'Projects'

class Tag(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=20)
    color = models.CharField(max_length=7)
    def __str__(self):
        return self.name

class Column(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='columns')
    title = models.CharField(max_length=255)
    position = models.FloatField(default=DEFAULT_POSITION)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'column'
        ordering = ['position']

class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    column = models.ForeignKey(Column, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    position = models.FloatField(default=DEFAULT_POSITION)
    tags = models.ManyToManyField(Tag, blank=True, related_name='tasks')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    class Meta:
        db_table = 'task'
        ordering = ['position']

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('task', '任务'),
        ('member', '成员'),
        ('system', '系统'),
        ('success', '成功'),
        ('warning', '警告'),
        ('test_failure', '测试失败'),
        ('deploy_success', '部署成功'),
        ('quality_risk', '质量风险'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default='system')
    is_read = models.BooleanField(default=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notification'
        ordering = ['-created_at']
        verbose_name = '通知'
        verbose_name_plural = '通知'
    
    def __str__(self):
        return f"{self.user.username}: {self.title}"

# ============== 项目级角色系统 ==============

class ProjectRole(models.Model):
    """项目级角色"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=50)
    key = models.CharField(max_length=30)
    permissions = models.JSONField(default=list)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_role'
        unique_together = ['project', 'key']
        ordering = ['-is_system', 'created_at']

    def __str__(self):
        return f'{self.project.name} / {self.name}'


class ProjectMember(models.Model):
    """项目成员（带角色）"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_memberships')
    role = models.ForeignKey(ProjectRole, on_delete=models.SET_NULL, null=True, related_name='members')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'project_member'
        unique_together = ['project', 'user']


# ============== 协作模型 ==============

class TaskComment(models.Model):
    """任务评论"""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_comments')
    content = models.TextField()
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_comment'
        ordering = ['created_at']
        indexes = [models.Index(fields=['task', 'created_at'])]


class TaskActivityLog(models.Model):
    """任务变更日志"""
    ACTION_CHOICES = [
        ('created', '创建'),
        ('updated', '更新'),
        ('deleted', '删除'),
        ('moved', '移动'),
        ('assigned', '分配'),
        ('commented', '评论'),
    ]
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='task_activities')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    field_name = models.CharField(max_length=50, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'task_activity_log'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['task', '-created_at'])]


class TaskAttachment(models.Model):
    """任务附件"""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    uploader = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    file = models.FileField(upload_to='attachments/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'task_attachment'
        ordering = ['-created_at']


# ============== 审计日志 ==============

class AuditLog(models.Model):
    """通用审计日志"""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=100, blank=True)
    detail = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['action', '-created_at']),
        ]


# ============== AI 对话模型 ==============

class AIConversation(models.Model):
    """AI 对话会话"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_conversations')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, related_name='ai_conversations')
    title = models.CharField(max_length=255, default='新对话')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_conversation'
        ordering = ['-updated_at']


class AIMessage(models.Model):
    """AI 对话消息"""
    ROLE_CHOICES = [('user', '用户'), ('assistant', '助手'), ('system', '系统')]
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_used = models.PositiveIntegerField(default=0)
    references = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_message'
        ordering = ['created_at']


# ============== 迭代/Sprint 模型 ==============

class Sprint(models.Model):
    """迭代/冲刺"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sprints')
    name = models.CharField(max_length=255)
    goal = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sprint'
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.name}'


class SprintTask(models.Model):
    """迭代-任务关联"""
    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name='sprint_tasks')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='sprints')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sprint_task'
        unique_together = ['sprint', 'task']


class ProjectApiDoc(models.Model):
    """项目 API 文档 — 供 AI 解析并生成测试用例"""
    FORMAT_CHOICES = [
        ('markdown', 'Markdown'),
        ('openapi_json', 'OpenAPI JSON'),
        ('text', '纯文本'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='api_docs')
    name = models.CharField(max_length=255)
    content = models.TextField()
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='markdown')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_docs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_api_doc'
        ordering = ['-created_at']


from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


# ============== 用户资料信号 ==============

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

# ============== 任务活动日志信号 ==============

@receiver(post_save, sender=Task)
def log_task_created(sender, instance, created, **kwargs):
    if created:
        TaskActivityLog.objects.create(
            task=instance, user=None, action='created',
            field_name='task', new_value=instance.title
        )


@receiver(pre_save, sender=Task)
def log_task_updated(sender, instance, **kwargs):
    if instance.pk is None:
        return  # handled by post_save created
    try:
        old = Task.objects.get(pk=instance.pk)
    except Task.DoesNotExist:
        return

    changes = []
    if old.title != instance.title:
        changes.append(('title', old.title, instance.title))
    if old.column_id != instance.column_id:
        old_col = Column.objects.filter(pk=old.column_id).values_list('title', flat=True).first()
        new_col = Column.objects.filter(pk=instance.column_id).values_list('title', flat=True).first()
        changes.append(('column', old_col or str(old.column_id), new_col or str(instance.column_id)))
    if old.assignee_id != instance.assignee_id:
        old_name = User.objects.filter(pk=old.assignee_id).values_list('username', flat=True).first() if old.assignee_id else None
        new_name = User.objects.filter(pk=instance.assignee_id).values_list('username', flat=True).first() if instance.assignee_id else None
        changes.append(('assignee', old_name or '未分配', new_name or '未分配'))

    for field, old_val, new_val in changes:
        action = 'moved' if field == 'column' else 'assigned' if field == 'assignee' else 'updated'
        TaskActivityLog.objects.create(
            task=instance, user=None, action=action,
            field_name=field, old_value=old_val, new_value=new_val
        )


# post_delete on Task is handled manually in TaskDetailView.delete() and
# TaskBatchDeleteView.post() to avoid FK integrity errors on MySQL.

# ============== 项目创建: 自动生成默认角色 ==============

DEFAULT_PROJECT_ROLES = [
    {'name': 'Owner', 'key': 'owner', 'permissions': ['task:create','task:edit','task:delete','task:move','member:invite','member:remove','role:manage','project:delete','project:settings'], 'is_system': True},
    {'name': 'Admin', 'key': 'admin', 'permissions': ['task:create','task:edit','task:delete','task:move','member:invite','member:remove','project:settings'], 'is_system': True},
    {'name': 'Editor', 'key': 'editor', 'permissions': ['task:create','task:edit','task:move'], 'is_system': True},
    {'name': 'Viewer', 'key': 'viewer', 'permissions': [], 'is_system': True},
]


@receiver(post_save, sender=Project)
def create_default_project_roles(sender, instance, created, **kwargs):
    if created:
        for role_data in DEFAULT_PROJECT_ROLES:
            role_data_copy = role_data.copy()
            role_data_copy.pop('is_system')
            ProjectRole.objects.create(project=instance, is_system=True, **role_data_copy)
