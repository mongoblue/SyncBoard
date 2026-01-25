import uuid
from django.db import models
from django.contrib.auth.models import User

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)  # 修正 typo: 2555 -> 255
    # 2. 关联真实用户，related_name 方便反向查询
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects')
    members = models.ManyToManyField(User, related_name='joined_projects', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name

    class Meta:
        db_table = 'project'
        verbose_name_plural = 'Projects'


class Column(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='columns')
    title = models.CharField(max_length=255)
    position = models.FloatField(default=65535)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'column'
        ordering = ['position']  # 3. 默认按 position 排序


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    column = models.ForeignKey(Column, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    position = models.FloatField(default=65535)
    # assignee 可以为空，因为任务可能还没分给谁
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')

    class Meta:
        db_table = 'task'
        ordering = ['position']