"""
Room 应用视图模块

本模块包含所有与项目管理、看板、任务相关的 API 视图。
所有视图统一使用 APIView 风格实现。
"""

from .auth import LoginView, LogoutView, CurrentUserView
from .project import (
    ProjectListView,
    ProjectInviteView,
    ProjectChatView,
)
from .board import (
    ColumnListView,
    ColumnDetailView,
    TaskListView,
    TaskDetailView,
    TaskBatchDeleteView,
)
from .tag import TagListView, TagDetailView
from .notification import (
    NotificationListView,
    NotificationReadView,
    NotificationMarkAllReadView,
)
from .user import UserListView

__all__ = [
    # 认证
    'LoginView',
    'LogoutView',
    'CurrentUserView',
    # 项目
    'ProjectListView',
    'ProjectInviteView',
    'ProjectChatView',
    # 看板
    'ColumnListView',
    'ColumnDetailView',
    'TaskListView',
    'TaskDetailView',
    'TaskBatchDeleteView',
    # 标签
    'TagListView',
    'TagDetailView',
    # 通知
    'NotificationListView',
    'NotificationReadView',
    'NotificationMarkAllReadView',
    # 用户
    'UserListView',
]
