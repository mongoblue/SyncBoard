"""系统级权限验证"""
from rest_framework.permissions import BasePermission


class HasSystemPermission(BasePermission):
    """检查用户是否拥有指定系统权限码"""

    def __init__(self, permission_code):
        self.permission_code = permission_code

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        try:
            profile = request.user.system_profile
            return self.permission_code in profile.get_all_permissions()
        except Exception:
            return False

    def __call__(self):
        return self


def require_permission(code):
    """工厂函数，方便在视图类中使用"""
    return type(
        f'HasSystemPermission_{code.replace(":", "_")}',
        (HasSystemPermission,),
        {},
    )(code)
