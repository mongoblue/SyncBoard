"""
RBAC 权限管理系统模型
"""
from django.db import models
from django.contrib.auth.models import User


class Menu(models.Model):
    """菜单/权限点模型"""
    MENU_TYPE_CHOICES = [
        ('directory', '目录'),
        ('menu', '菜单'),
        ('button', '按钮'),
    ]

    name = models.CharField(max_length=100, verbose_name='名称')
    code = models.CharField(max_length=100, unique=True, verbose_name='权限标识', blank=True, null=True)
    path = models.CharField(max_length=200, verbose_name='前端路由路径', blank=True, null=True)
    type = models.CharField(max_length=20, choices=MENU_TYPE_CHOICES, verbose_name='类型')
    icon = models.CharField(max_length=50, verbose_name='图标', blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name='父菜单')
    order = models.IntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'system_menu'
        verbose_name = '菜单/权限'
        verbose_name_plural = '菜单/权限管理'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name

    def get_full_path(self):
        """获取完整路径"""
        if self.path:
            return self.path
        return None


class Role(models.Model):
    """角色模型"""
    name = models.CharField(max_length=100, verbose_name='角色名')
    key = models.CharField(max_length=50, unique=True, verbose_name='角色标识')
    menus = models.ManyToManyField(Menu, blank=True, related_name='roles', verbose_name='菜单权限')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'system_role'
        verbose_name = '角色'
        verbose_name_plural = '角色管理'

    def __str__(self):
        return self.name


class SystemUserProfile(models.Model):
    """
    系统用户扩展资料 - 用于 RBAC 权限管理

    注意：此模型与 room.models.UserProfile 不同，
    room 中的 UserProfile 用于头像等基础用户信息。
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='system_profile')
    roles = models.ManyToManyField(Role, blank=True, related_name='users', verbose_name='角色')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='手机号')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'system_user_profile'
        verbose_name = '系统用户扩展资料'
        verbose_name_plural = '系统用户扩展资料'

    def __str__(self):
        return f"{self.user.username} 的系统扩展资料"

    def get_all_permissions(self):
        """获取用户的所有权限编码"""
        permissions = set()
        for role in self.roles.filter(is_active=True):
            for menu in role.menus.filter(is_active=True):
                if menu.code:
                    permissions.add(menu.code)
        return list(permissions)

    def get_all_menus(self):
        """获取用户的所有菜单（树形结构）"""
        menu_ids = set()
        for role in self.roles.filter(is_active=True):
            for menu in role.menus.filter(is_active=True):
                menu_ids.add(menu.id)
                # 添加父菜单
                parent = menu.parent
                while parent:
                    menu_ids.add(parent.id)
                    parent = parent.parent

        # 获取所有相关菜单
        menus = Menu.objects.filter(id__in=menu_ids, is_active=True)
        return menus
