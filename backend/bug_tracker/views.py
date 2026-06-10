"""Bug 跟踪 API 视图"""
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Bug, BugComment, BugTransition
from .seed import seed_demo_bugs
from .serializers import (
    BugCommentSerializer,
    BugCreateSerializer,
    BugDetailSerializer,
    BugListSerializer,
    BugUpdateSerializer,
)
from .state_machine import TERMINAL_STATUSES, TransitionError, validate_transition


class BugViewSet(viewsets.ModelViewSet):
    """
    Bug CRUD
    GET    /api/bugs/                                列表 + 筛选
    POST   /api/bugs/                                创建
    GET    /api/bugs/{id}/                           详情
    PATCH  /api/bugs/{id}/                           改字段（不含 status）
    DELETE /api/bugs/{id}/                           删除
    POST   /api/bugs/{id}/transition/                状态流转
    POST   /api/bugs/{id}/assign/                    指派
    GET    /api/bugs/{id}/comments/                  评论列表
    POST   /api/bugs/{id}/comments/                  加评论
    GET    /api/bugs/my/?role=assignee|reporter|...  我相关的
    """

    permission_classes = [IsAuthenticated]
    queryset = Bug.objects.all()

    def get_serializer_class(self):
        if self.action == 'list' or self.action == 'my':
            return BugListSerializer
        if self.action == 'create':
            return BugCreateSerializer
        if self.action in ('update', 'partial_update'):
            return BugUpdateSerializer
        return BugDetailSerializer

    def get_queryset(self):
        qs = Bug.objects.select_related(
            'project', 'reporter', 'assignee', 'fixer', 'verifier'
        )
        params = self.request.query_params

        project_id = params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)

        status_filter = params.get('status')
        if status_filter:
            qs = qs.filter(status__in=status_filter.split(','))

        severity = params.get('severity')
        if severity:
            qs = qs.filter(severity__in=severity.split(','))

        priority = params.get('priority')
        if priority:
            qs = qs.filter(priority__in=priority.split(','))

        assignee = params.get('assignee')
        if assignee:
            qs = qs.filter(assignee_id=assignee)

        reporter = params.get('reporter')
        if reporter:
            qs = qs.filter(reporter_id=reporter)

        source = params.get('source_test_type')
        if source:
            qs = qs.filter(source_test_type=source)

        keyword = params.get('keyword')
        if keyword:
            qs = qs.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))

        return qs

    def perform_create(self, serializer):
        bug = serializer.save(reporter=self.request.user)
        BugTransition.objects.create(
            bug=bug, operator=self.request.user,
            from_status='', to_status=bug.status,
            comment='创建 Bug',
        )

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        """状态流转：{to_status, comment?}"""
        bug = self.get_object()
        to_status = request.data.get('to_status')
        comment = request.data.get('comment', '')

        if not to_status:
            return Response({'error': '缺少 to_status'}, status=status.HTTP_400_BAD_REQUEST)

        from_status = bug.status
        try:
            validate_transition(from_status, to_status)
        except TransitionError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        bug.status = to_status

        # 角色自动记录
        user = request.user
        if to_status == 'fixed' and not bug.fixer:
            bug.fixer = user
        elif to_status in ('closed', 'verifying') and not bug.verifier:
            # 关闭/进入验证时记录验证者；closed 同时设 closed_at
            if to_status == 'closed' and not bug.verifier:
                bug.verifier = user

        if to_status in TERMINAL_STATUSES:
            bug.closed_at = timezone.now()
        elif from_status in TERMINAL_STATUSES and to_status == 'reopened':
            bug.closed_at = None

        bug.save()

        BugTransition.objects.create(
            bug=bug, operator=user,
            from_status=from_status, to_status=to_status,
            comment=comment,
        )

        return Response(BugDetailSerializer(bug).data)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """指派：{user_id, comment?}"""
        bug = self.get_object()
        user_id = request.data.get('user_id')
        comment = request.data.get('comment', '')

        if not user_id:
            return Response({'error': '缺少 user_id'}, status=status.HTTP_400_BAD_REQUEST)

        target = User.objects.filter(pk=user_id).first()
        if not target:
            return Response({'error': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        old_assignee = bug.assignee
        bug.assignee = target

        # 如果当前状态是 new/confirmed，指派后自动流转到 assigned
        from_status = bug.status
        if bug.status in ('new', 'confirmed'):
            bug.status = 'assigned'
            bug.save()
            BugTransition.objects.create(
                bug=bug, operator=request.user,
                from_status=from_status, to_status='assigned',
                comment=f'指派给 {target.username}' + (f': {comment}' if comment else ''),
            )
        else:
            bug.save()
            BugTransition.objects.create(
                bug=bug, operator=request.user,
                from_status=from_status, to_status=from_status,
                comment=f'重新指派: {old_assignee.username if old_assignee else "无"} → {target.username}'
                        + (f' ({comment})' if comment else ''),
            )

        return Response(BugDetailSerializer(bug).data)

    @action(detail=True, methods=['get', 'post'], url_path='comments')
    def comments(self, request, pk=None):
        bug = self.get_object()
        if request.method == 'GET':
            qs = bug.comments.select_related('author').all()
            return Response(BugCommentSerializer(qs, many=True).data)

        content = request.data.get('content', '').strip()
        if not content:
            return Response({'error': '评论内容不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        c = BugComment.objects.create(bug=bug, author=request.user, content=content)
        return Response(BugCommentSerializer(c).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def my(self, request):
        """
        我相关的 Bug
        GET /api/bugs/my/?role=assignee|reporter|fixer|verifier
        """
        role = request.query_params.get('role', 'assignee')
        user = request.user

        role_field = {
            'assignee': 'assignee',
            'reporter': 'reporter',
            'fixer': 'fixer',
            'verifier': 'verifier',
        }.get(role)

        if not role_field:
            return Response({'error': f'无效 role: {role}'}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(**{role_field: user})
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(BugListSerializer(page, many=True).data)
        return Response(BugListSerializer(qs, many=True).data)


class BugStatsView(APIView):
    """项目级 Bug 看板统计：未关闭数 / 严重度分布 / 状态分布"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project')
        qs = Bug.objects.all()
        if project_id:
            qs = qs.filter(project_id=project_id)

        open_qs = qs.exclude(status__in=TERMINAL_STATUSES)

        status_counts = {}
        for s, _ in Bug.STATUS_CHOICES:
            status_counts[s] = qs.filter(status=s).count()

        severity_counts = {}
        for s, _ in Bug.SEVERITY_CHOICES:
            severity_counts[s] = open_qs.filter(severity=s).count()

        return Response({
            'total': qs.count(),
            'open': open_qs.count(),
            'closed': qs.filter(status='closed').count(),
            'by_status': status_counts,
            'by_severity_open': severity_counts,
        })


class BugSeedDemoView(APIView):
    """POST /api/bugs/seed-demo/?project_id=X  — 仅 owner 允许"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from room.models import Project
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({'error': '缺少 project_id'}, status=status.HTTP_400_BAD_REQUEST)
        project = get_object_or_404(Project, pk=project_id)
        if project.owner != request.user:
            return Response({'error': '只有项目负责人可以导入示例 Bug'}, status=status.HTTP_403_FORBIDDEN)
        added = seed_demo_bugs(project)
        return Response({'added': added, 'total': project.bugs.count()})
