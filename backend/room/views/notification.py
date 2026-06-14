"""
通知管理视图

提供用户通知的查询、标记已读等功能。
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination
from ..models import Notification
from ..serializers import NotificationSerializer


class NotificationListView(APIView):
    """
    通知列表视图

    GET /api/notifications/?project=<id>&page=<n>&page_size=<n>
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project')

        queryset = Notification.objects.filter(user=request.user)
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = NotificationSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = NotificationSerializer(queryset, many=True)
        return Response(serializer.data)


class NotificationReadView(APIView):
    """
    标记通知已读视图

    POST /api/notifications/<id>/read/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
            notification.is_read = True
            notification.save()
            return Response({'detail': '已标记为已读'})
        except Notification.DoesNotExist:
            return Response(
                {'detail': '通知不存在'},
                status=status.HTTP_404_NOT_FOUND
            )


class NotificationMarkAllReadView(APIView):
    """
    全部标记已读视图

    POST /api/notifications/mark-all-read/?project=<id>
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        project_id = request.query_params.get('project')

        # 基础查询：当前用户的未读通知
        notifications = Notification.objects.filter(user=request.user, is_read=False)

        # 如果指定了项目，筛选该项目相关的通知
        if project_id:
            notifications = notifications.filter(project_id=project_id)

        count = notifications.count()
        notifications.update(is_read=True)

        return Response({
            'detail': f'已标记 {count} 条通知为已读',
            'count': count,
        })
