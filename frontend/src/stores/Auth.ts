import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import service from '@/utils/request';
import { useRouter } from 'vue-router';

// 菜单类型定义
export interface MenuItem {
  id: number;
  name: string;
  code?: string;
  path?: string;
  type: 'directory' | 'menu' | 'button';
  icon?: string;
  order: number;
  children?: MenuItem[];
}

// 用户信息类型
interface UserInfo {
  id: number;
  username: string;
  email: string;
  profile?: {
    avatar?: string;
  };
}

// 权限响应类型
interface PermissionsResponse {
  menus: MenuItem[];
  permissions: string[];
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null);
  const menus = ref<MenuItem[]>([]);
  const permissions = ref<string[]>([]);
  const router = useRouter();

  // 计算属性：权限检查
  const hasPermission = computed(() => {
    return (permission: string): boolean => {
      return permissions.value.includes(permission);
    };
  });

  // 1. 登录动作
  const login = async (form: any) => {
    try {
      const data = await service.post<any, UserInfo>('/auth/login/', form);
      user.value = data;
      // 登录成功后获取权限
      await fetchPermissions();
      return true;
    } catch (error) {
      console.error('登录失败', error);
      return false;
    }
  };

  // 2. 检查登录状态 (刷新页面时调用)
  const checkAuth = async () => {
    try {
      const data = await service.get<any, UserInfo>('/auth/me/');
      user.value = data;
      // 获取权限信息
      await fetchPermissions();
      return true;
    } catch (error) {
      user.value = null;
      menus.value = [];
      permissions.value = [];
      return false;
    }
  };

  // 3. 获取用户权限
  const fetchPermissions = async () => {
    try {
      const data = await service.get<any, PermissionsResponse>('/system/user/permissions/');
      menus.value = data.menus || [];
      permissions.value = data.permissions || [];
      return true;
    } catch (error) {
      console.error('获取权限失败', error);
      menus.value = [];
      permissions.value = [];
      return false;
    }
  };

  // 4. 登出
  const logout = async () => {
    await service.post('/auth/logout/');
    user.value = null;
    menus.value = [];
    permissions.value = [];
    // 登出后这里不强制跳转，交给组件处理或路由守卫
  };

  // 5. 更新用户头像
  const updateAvatar = (avatarUrl: string) => {
    if (user.value) {
      user.value = {
        ...user.value,
        profile: {
          ...user.value.profile,
          avatar: avatarUrl
        }
      };
    }
  };

  // 6. 检查是否有指定权限（方法形式）
  const checkPermission = (permission: string): boolean => {
    return permissions.value.includes(permission);
  };

  return {
    user,
    menus,
    permissions,
    hasPermission,
    login,
    checkAuth,
    fetchPermissions,
    logout,
    updateAvatar,
    checkPermission
  };
});
