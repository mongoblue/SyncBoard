from rest_framework import serializers
from .models import (
    Project, Task, Column, Tag, UserProfile, Notification,
    ProjectRole, ProjectMember, TaskComment, TaskActivityLog,
    TaskAttachment, AuditLog, AIConversation, AIMessage,
    Sprint, SprintTask, ProjectApiDoc,
)
from django.contrib.auth.models import User

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['id', 'avatar']

class UsersSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'profile']

class TagSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        write_only=True
    )
    
    class Meta:
        model = Tag
        fields = ['id', 'project', 'name', 'color']

class TaskSerializer(serializers.ModelSerializer):
    tags_details = TagSerializer(source='tags', many=True, read_only=True)
    assignee_details = UsersSerializer(source='assignee', read_only=True)
    column_title = serializers.CharField(source='column.title', read_only=True)

    # 接收标签ID列表 (用于写)
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False
    )
    class Meta:
        model = Task
        fields = '__all__'

class ColumnSerializer(serializers.ModelSerializer):
    # 这一步做的很好！直接嵌套了
    tasks = TaskSerializer(many=True, read_only=True)
    class Meta:
        model = Column
        fields = '__all__'

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'type', 'is_read', 'created_at', 'project']


# ============== 项目角色序列化器 ==============

class ProjectRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectRole
        fields = ['id', 'project', 'name', 'key', 'permissions', 'is_system', 'created_at']
        read_only_fields = ['id', 'project', 'is_system', 'created_at']


class ProjectMemberSerializer(serializers.ModelSerializer):
    user_detail = UsersSerializer(source='user', read_only=True)
    role_detail = ProjectRoleSerializer(source='role', read_only=True)

    class Meta:
        model = ProjectMember
        fields = ['id', 'project', 'user', 'user_detail', 'role', 'role_detail', 'joined_at']
        read_only_fields = ['id', 'joined_at']

# ============== 协作序列化器 ==============

class TaskCommentSerializer(serializers.ModelSerializer):
    author_detail = UsersSerializer(source='author', read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ['id', 'task', 'author', 'author_detail', 'content', 'parent', 'replies', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']

    def get_replies(self, obj):
        if obj.parent is None:
            replies = obj.replies.all()[:10]
            return TaskCommentSerializer(replies, many=True).data
        return []


class TaskActivityLogSerializer(serializers.ModelSerializer):
    user_detail = UsersSerializer(source='user', read_only=True)

    class Meta:
        model = TaskActivityLog
        fields = ['id', 'task', 'user', 'user_detail', 'action', 'field_name', 'old_value', 'new_value', 'created_at']


class TaskAttachmentSerializer(serializers.ModelSerializer):
    uploader_detail = UsersSerializer(source='uploader', read_only=True)

    class Meta:
        model = TaskAttachment
        fields = ['id', 'task', 'uploader', 'uploader_detail', 'file', 'filename', 'file_size', 'content_type', 'created_at']
        read_only_fields = ['id', 'uploader', 'file_size', 'content_type', 'created_at']


# ============== 审计日志序列化器 ==============

class AuditLogSerializer(serializers.ModelSerializer):
    user_detail = UsersSerializer(source='user', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'user_detail', 'action', 'resource_type', 'resource_id', 'detail', 'ip_address', 'created_at']


# ============== AI 序列化器 ==============

class AIMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = ['id', 'conversation', 'role', 'content', 'tokens_used', 'references', 'created_at']
        read_only_fields = ['id', 'tokens_used', 'created_at']


class AIConversationSerializer(serializers.ModelSerializer):
    messages = AIMessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = AIConversation
        fields = ['id', 'user', 'project', 'title', 'message_count', 'messages', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_message_count(self, obj):
        return obj.messages.count()


# ============== Sprint 序列化器 ==============

class SprintTaskSerializer(serializers.ModelSerializer):
    task_detail = TaskSerializer(source='task', read_only=True)

    class Meta:
        model = SprintTask
        fields = ['id', 'sprint', 'task', 'task_detail', 'added_at']


class SprintSerializer(serializers.ModelSerializer):
    tasks = SprintTaskSerializer(source='sprint_tasks', many=True, read_only=True)
    task_count = serializers.SerializerMethodField()
    completed_count = serializers.SerializerMethodField()

    class Meta:
        model = Sprint
        fields = ['id', 'project', 'name', 'goal', 'start_date', 'end_date', 'is_active',
                  'task_count', 'completed_count', 'tasks', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_task_count(self, obj):
        return obj.sprint_tasks.count()

    def get_completed_count(self, obj):
        columns = list(Column.objects.filter(project=obj.project).order_by('position'))
        if not columns:
            return 0
        done_keywords = ['done', '完成', '已完成', 'closed', '已关闭', 'complete', 'finished']
        done_col = None
        for col in columns:
            if any(kw in col.title.lower() for kw in done_keywords):
                done_col = col
                break
        if not done_col:
            done_col = columns[-1]
        return obj.sprint_tasks.filter(task__column=done_col).count()


class ProjectApiDocSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = ProjectApiDoc
        fields = ['id', 'project', 'name', 'content', 'format', 'uploaded_by', 'uploaded_by_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'uploaded_by', 'created_at', 'updated_at']


class ProjectSerializer(serializers.ModelSerializer):
    owner_details = UsersSerializer(source='owner', read_only=True)
    members_details = UsersSerializer(source='members', many=True, read_only=True)
    available_tags = TagSerializer(source='tags', many=True, read_only=True)

    class Meta:
        model = Project
        fields = '__all__'
