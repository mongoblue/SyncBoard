/**
 * 用户管理 Store
 *
 * 提供用户列表查询功能
 */

import { ref } from 'vue';
import { defineStore } from 'pinia';
import service from '@/utils/request';
import type { User } from '@/types/kanban';

export const useUserStore = defineStore('boardUser', () => {
  // ============ State ============
  const users = ref<User[]>([]);
  const isLoading = ref(false);

  // ============ Actions ============

  /**
   * 获取用户列表
   */
  const fetchUsers = async (): Promise<User[]> => {
    isLoading.value = true;
    try {
      const data = await service.get<any, User[]>('/users/');
      users.value = data;
      return data;
    } catch (error) {
      console.error('获取用户列表失败:', error);
      return [];
    } finally {
      isLoading.value = false;
    }
  };

  /**
   * 根据 ID 获取用户信息
   */
  const getUserById = (userId: number): User | undefined => {
    return users.value.find((u) => u.id === userId);
  };

  return {
    // State
    users,
    isLoading,
    // Actions
    fetchUsers,
    getUserById,
  };
});
