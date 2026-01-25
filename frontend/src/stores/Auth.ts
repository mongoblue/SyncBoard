import { defineStore } from 'pinia';
import { ref } from 'vue';
import service from '@/utils/request';
import { useRouter } from 'vue-router';

interface UserInfo {
  id: number;
  username: string;
  email: string;
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null);
  const router = useRouter();

  // 1. 登录动作
  const login = async (form: any) => {
    try {
      // 发送登录请求
      const data = await service.post<any, UserInfo>('/api/auth/login/', form);
      user.value = data;
      return true;
    } catch (error) {
      console.error('登录失败', error);
      return false;
    }
  };

  // 2. 检查登录状态 (刷新页面时调用)
  const checkAuth = async () => {
    try {
      const data = await service.get<any, UserInfo>('/api/auth/me/');
      user.value = data;
      return true;
    } catch (error) {
      user.value = null;
      return false;
    }
  };

  // 3. 登出
  const logout = async () => {
    await service.post('/api/auth/logout/');
    user.value = null;
    // 登出后这里不强制跳转，交给组件处理或路由守卫
  };

  return {
    user,
    login,
    checkAuth,
    logout
  };
});