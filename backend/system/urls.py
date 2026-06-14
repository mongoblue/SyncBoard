"""
RBAC 系统管理路由
"""
from django.urls import path
from . import views

urlpatterns = [
    # 菜单管理
    path('menus/', views.MenuListView.as_view(), name='menu-list'),
    path('menus/tree/', views.MenuTreeView.as_view(), name='menu-tree'),
    path('menus/<int:pk>/', views.MenuDetailView.as_view(), name='menu-detail'),

    # 角色管理
    path('roles/', views.RoleListView.as_view(), name='role-list'),
    path('roles/<int:pk>/', views.RoleDetailView.as_view(), name='role-detail'),

    # 用户管理
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/reset-password/', views.UserResetPasswordView.as_view(), name='user-reset-password'),

    # 当前用户权限
    path('user/permissions/', views.CurrentUserPermissionsView.as_view(), name='user-permissions'),
]
