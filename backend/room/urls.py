"""
Room 应用 URL 路由配置

所有视图统一使用 APIView 风格实现。
"""

from django.urls import path
from .views import (
    # 认证
    LoginView,
    LogoutView,
    CurrentUserView,
    # 项目
    ProjectListView,
    ProjectInviteView,
    ProjectChatView,
    # 看板
    ColumnListView,
    ColumnDetailView,
    TaskListView,
    TaskDetailView,
    TaskBatchDeleteView,
    # 标签
    TagListView,
    TagDetailView,
    # 通知
    NotificationListView,
    NotificationReadView,
    NotificationMarkAllReadView,
    # 用户
    UserListView,
)
from .views.comment import TaskCommentListView, TaskCommentDetailView
from .views.activity import TaskActivityListView
from .views.project_role import (
    ProjectRoleListView, ProjectRoleDetailView, ProjectMemberListView,
)
from .views_avatar import AvatarUploadView
from .views_search import TaskSearchView
from qa_center.views_test_link import TaskLinkedTestsView
from .views.ai import (
    AIConversationListView, AIConversationDetailView, AIChatView,
    AIStreamChatView, AIProjectHealthView, AIWeeklyReportView,
    AIRiskIdentificationView, AISprintSummaryView,
)
from .views.attachment import TaskAttachmentListView, TaskAttachmentDeleteView
from .views.sprint import (
    SprintListView, SprintDetailView, SprintTaskView, SprintBurndownView,
)
from .views.api_docs import ProjectApiDocListView, ProjectApiDocDetailView


urlpatterns = [
    # 看板列
    path('columns/', ColumnListView.as_view(), name='column-list'),
    path('columns/<str:pk>/', ColumnDetailView.as_view(), name='column-detail'),

    # 任务
    path('tasks/', TaskListView.as_view(), name='task-list'),
    path('tasks/batch-delete/', TaskBatchDeleteView.as_view(), name='task-batch-delete'),
    path('tasks/search/', TaskSearchView.as_view(), name='task-search'),
    path('tasks/<str:pk>/', TaskDetailView.as_view(), name='task-detail'),

    # 标签
    path('tags/', TagListView.as_view(), name='tag-list'),
    path('tags/<int:pk>/', TagDetailView.as_view(), name='tag-detail'),

    # 用户
    path('users/', UserListView.as_view(), name='user-list'),

    # 认证
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/me/', CurrentUserView.as_view(), name='current-user'),

    # 项目
    path('projects/', ProjectListView.as_view(), name='project-list'),
    path('projects/<str:pk>/', ProjectListView.as_view(), name='project-detail'),
    path('projects/<str:pk>/invite/', ProjectInviteView.as_view(), name='project-invite'),

    # 头像上传
    path('users/avatar/', AvatarUploadView.as_view(), name='avatar-upload'),

    # AI 助手
    path('ai/conversations/', AIConversationListView.as_view(), name='ai-conversation-list'),
    path('ai/conversations/<int:conversation_id>/', AIConversationDetailView.as_view(), name='ai-conversation-detail'),
    path('ai/chat/', AIChatView.as_view(), name='ai-chat'),
    path('ai/chat/stream/', AIStreamChatView.as_view(), name='ai-chat-stream'),
    path('ai/analyze/health/', AIProjectHealthView.as_view(), name='ai-health'),
    path('ai/analyze/weekly/', AIWeeklyReportView.as_view(), name='ai-weekly'),
    path('ai/analyze/risks/', AIRiskIdentificationView.as_view(), name='ai-risks'),
    path('ai/analyze/sprint-summary/', AISprintSummaryView.as_view(), name='ai-sprint-summary'),

    # RAG 智能问答助手 (兼容旧接口)
    path('chat/', ProjectChatView.as_view(), name='project-chat'),

    # 任务评论
    path('tasks/<str:task_id>/comments/', TaskCommentListView.as_view(), name='task-comment-list'),
    path('tasks/<str:task_id>/comments/<int:comment_id>/', TaskCommentDetailView.as_view(), name='task-comment-detail'),

    # 任务关联测试用例
    path('tasks/<str:task_id>/linked-tests/', TaskLinkedTestsView.as_view(), name='task-linked-tests'),

    # 任务附件
    path('tasks/<str:task_id>/attachments/', TaskAttachmentListView.as_view(), name='task-attachment-list'),
    path('tasks/<str:task_id>/attachments/<int:aid>/', TaskAttachmentDeleteView.as_view(), name='task-attachment-delete'),

    # 任务动态
    path('tasks/<str:task_id>/activities/', TaskActivityListView.as_view(), name='task-activity-list'),

    # 迭代/Sprint
    path('projects/<str:project_id>/sprints/', SprintListView.as_view(), name='sprint-list'),
    path('projects/<str:project_id>/sprints/<int:sprint_id>/', SprintDetailView.as_view(), name='sprint-detail'),
    path('projects/<str:project_id>/sprints/<int:sprint_id>/tasks/', SprintTaskView.as_view(), name='sprint-task'),
    path('projects/<str:project_id>/sprints/<int:sprint_id>/burndown/', SprintBurndownView.as_view(), name='sprint-burndown'),

    # API 文档
    path('projects/<str:project_id>/api-docs/', ProjectApiDocListView.as_view(), name='project-api-doc-list'),
    path('projects/<str:project_id>/api-docs/<int:doc_id>/', ProjectApiDocDetailView.as_view(), name='project-api-doc-detail'),

    # 项目角色
    path('projects/<str:project_id>/roles/', ProjectRoleListView.as_view(), name='project-role-list'),
    path('projects/<str:project_id>/roles/<int:role_id>/', ProjectRoleDetailView.as_view(), name='project-role-detail'),
    path('projects/<str:project_id>/members/', ProjectMemberListView.as_view(), name='project-member-list'),

    # 通知管理
    path('notifications/', NotificationListView.as_view(), name='notification-list'),
    path('notifications/<int:pk>/read/', NotificationReadView.as_view(), name='notification-read'),
    path('notifications/mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
]
