"""
RBAC 序列化器
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Menu, Role, SystemUserProfile


class MenuSerializer(serializers.ModelSerializer):
    """菜单序列化器"""
    children = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True)

    class Meta:
        model = Menu
        fields = ['id', 'name', 'code', 'path', 'type', 'icon', 'parent', 'parent_name', 'order', 'is_active', 'children', 'created_at', 'updated_at']

    def get_children(self, obj):
        """递归获取子菜单"""
        children = obj.children.filter(is_active=True).order_by('order', 'id')
        return MenuSerializer(children, many=True).data


class MenuTreeSerializer(serializers.ModelSerializer):
    """菜单树序列化器 - 用于权限树"""
    children = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ['id', 'name', 'code', 'path', 'type', 'icon', 'order', 'children']

    def get_children(self, obj):
        children = obj.children.filter(is_active=True).order_by('order', 'id')
        return MenuTreeSerializer(children, many=True).data


class RoleSerializer(serializers.ModelSerializer):
    """角色序列化器"""
    menu_ids = serializers.ListField(write_only=True, required=False)
    menus = MenuSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = ['id', 'name', 'key', 'menus', 'menu_ids', 'is_active', 'created_at', 'updated_at']

    def create(self, validated_data):
        menu_ids = validated_data.pop('menu_ids', [])
        role = Role.objects.create(**validated_data)
        if menu_ids:
            role.menus.set(Menu.objects.filter(id__in=menu_ids))
        return role

    def update(self, instance, validated_data):
        menu_ids = validated_data.pop('menu_ids', None)
        # key 字段创建后不可修改
        validated_data.pop('key', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if menu_ids is not None:
            instance.menus.set(Menu.objects.filter(id__in=menu_ids))
        return instance


class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    roles = serializers.SerializerMethodField()
    role_ids = serializers.ListField(write_only=True, required=False)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'roles', 'role_ids', 'avatar', 'date_joined']

    def get_roles(self, obj):
        """获取用户角色"""
        # 确保用户有 system_profile
        if not hasattr(obj, 'system_profile'):
            SystemUserProfile.objects.get_or_create(user=obj)
        return [{'id': role.id, 'name': role.name, 'key': role.key} for role in obj.system_profile.roles.filter(is_active=True)]

    def get_avatar(self, obj):
        """获取用户头像"""
        if hasattr(obj, 'profile') and obj.profile.avatar:
            return obj.profile.avatar.url
        return None

    def update(self, instance, validated_data):
        role_ids = validated_data.pop('role_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # 确保用户有 system_profile，然后设置角色
        if role_ids is not None:
            profile, _ = SystemUserProfile.objects.get_or_create(user=instance)
            profile.roles.set(Role.objects.filter(id__in=role_ids))

        return instance


class UserPermissionSerializer(serializers.Serializer):
    """用户权限序列化器"""
    menus = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_menus(self, obj):
        """获取用户的菜单树"""
        if hasattr(obj, 'system_profile'):
            menus = obj.system_profile.get_all_menus()
            # 只返回顶级菜单
            top_menus = menus.filter(parent__isnull=True).order_by('order', 'id')
            return MenuTreeSerializer(top_menus, many=True).data
        return []

    def get_permissions(self, obj):
        """获取用户的权限编码列表"""
        if hasattr(obj, 'system_profile'):
            return obj.system_profile.get_all_permissions()
        return []


class UserCreateSerializer(serializers.ModelSerializer):
    """创建用户序列化器"""
    password = serializers.CharField(write_only=True)
    role_ids = serializers.ListField(required=False, default=list)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 'is_active', 'role_ids']

    def create(self, validated_data):
        role_ids = validated_data.pop('role_ids', [])
        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()

        # 创建用户扩展资料
        profile, _ = SystemUserProfile.objects.get_or_create(user=user)
        if role_ids:
            profile.roles.set(Role.objects.filter(id__in=role_ids))

        return user
