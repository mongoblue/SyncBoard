from django.urls import path
from .views import ColumnListView, TaskListView, TaskDetailView, UserListView, LoginView, LogoutView, CurrentUserView, \
    ProjectListView, ProjectInviteView

# 这里没有 DefaultRouter 的魔法了，全是显式的路径
urlpatterns = [
    path('columns/', ColumnListView.as_view()),
    path('tasks/', TaskListView.as_view()),
    path('tasks/<str:pk>/', TaskDetailView.as_view()),
    path('users/', UserListView.as_view()),
    path('auth/login/', LoginView.as_view()),
    path('auth/logout/', LogoutView.as_view()),
    path('auth/me/', CurrentUserView.as_view()),
    path('projects/', ProjectListView.as_view()),
    path('projects/<str:pk>/', ProjectListView.as_view()),
    path('projects/<str:pk>/invite/', ProjectInviteView.as_view()),
]