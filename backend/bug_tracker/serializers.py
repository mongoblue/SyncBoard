from rest_framework import serializers
from django.contrib.auth.models import User

from .models import Bug, BugTransition, BugComment
from .state_machine import allowed_next_statuses


class _UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']


class BugTransitionSerializer(serializers.ModelSerializer):
    operator = _UserBriefSerializer(read_only=True)

    class Meta:
        model = BugTransition
        fields = ['id', 'operator', 'from_status', 'to_status', 'comment', 'created_at']
        read_only_fields = fields


class BugCommentSerializer(serializers.ModelSerializer):
    author = _UserBriefSerializer(read_only=True)

    class Meta:
        model = BugComment
        fields = ['id', 'bug', 'author', 'content', 'created_at']
        read_only_fields = ['id', 'author', 'created_at']


class BugListSerializer(serializers.ModelSerializer):
    """列表用 - 字段精简"""
    reporter = _UserBriefSerializer(read_only=True)
    assignee = _UserBriefSerializer(read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    linked_task = serializers.SerializerMethodField()

    class Meta:
        model = Bug
        fields = [
            'id', 'project', 'project_name', 'title',
            'status', 'status_display', 'severity', 'severity_display',
            'priority', 'priority_display', 'reporter', 'assignee',
            'source_test_type', 'created_at', 'updated_at',
            'linked_task',
        ]

    def get_linked_task(self, obj):
        return str(obj.linked_task_id) if obj.linked_task_id else None


class BugDetailSerializer(serializers.ModelSerializer):
    """详情用 - 含全部字段 + 流转记录 + 评论 + 可流转目标"""
    reporter = _UserBriefSerializer(read_only=True)
    assignee = _UserBriefSerializer(read_only=True)
    fixer = _UserBriefSerializer(read_only=True)
    verifier = _UserBriefSerializer(read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    source_display = serializers.CharField(source='get_source_test_type_display', read_only=True)
    transitions = BugTransitionSerializer(many=True, read_only=True)
    comments = BugCommentSerializer(many=True, read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = Bug
        fields = [
            'id', 'project', 'project_name', 'title', 'description',
            'steps_to_reproduce', 'expected', 'actual', 'environment',
            'severity', 'severity_display', 'priority', 'priority_display',
            'status', 'status_display',
            'reporter', 'assignee', 'fixer', 'verifier',
            'source_test_type', 'source_display', 'source_case_id', 'source_result_id',
            'linked_task',
            'created_at', 'updated_at', 'closed_at',
            'transitions', 'comments', 'allowed_transitions',
        ]
        read_only_fields = ['reporter', 'status', 'created_at', 'updated_at', 'closed_at']

    def get_allowed_transitions(self, obj):
        return allowed_next_statuses(obj.status)


class BugCreateSerializer(serializers.ModelSerializer):
    """创建用 - 不允许直接指定 status，强制 new"""

    assignee_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Bug
        fields = [
            'project', 'title', 'description',
            'steps_to_reproduce', 'expected', 'actual', 'environment',
            'severity', 'priority', 'assignee_id',
            'source_test_type', 'source_case_id', 'source_result_id',
            'linked_task',
        ]

    def create(self, validated_data):
        assignee_id = validated_data.pop('assignee_id', None)
        if assignee_id:
            validated_data['assignee'] = User.objects.filter(pk=assignee_id).first()
        return super().create(validated_data)


class BugUpdateSerializer(serializers.ModelSerializer):
    """更新用 - status 必须通过 transition 接口改"""
    class Meta:
        model = Bug
        fields = [
            'title', 'description', 'steps_to_reproduce',
            'expected', 'actual', 'environment',
            'severity', 'priority', 'linked_task',
        ]
