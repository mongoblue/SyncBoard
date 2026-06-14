/**
 * 标签管理 Store
 *
 * 提供项目标签的增删改查功能
 */

import { ref } from 'vue';
import { defineStore } from 'pinia';
import { ElMessage } from 'element-plus';
import service from '@/utils/request';

export interface Tag {
  id: number;
  name: string;
  color: string;
}

export const useTagStore = defineStore('boardTag', () => {
  // ============ State ============
  const tags = ref<Tag[]>([]);
  const isLoading = ref(false);

  // ============ Actions ============

  /**
   * 获取项目标签列表
   */
  const fetchTags = async (projectId: string): Promise<Tag[]> => {
    isLoading.value = true;
    try {
      const data = await service.get<any, Tag[]>(`/tags/?project=${projectId}`);
      tags.value = data;
      return data;
    } catch (error) {
      console.error('获取标签失败:', error);
      return [];
    } finally {
      isLoading.value = false;
    }
  };

  /**
   * 创建标签
   */
  const createTag = async (
    projectId: string,
    name: string,
    color: string
  ): Promise<boolean> => {
    try {
      await service.post('/tags/', { project: projectId, name, color });
      ElMessage.success('标签创建成功');
      await fetchTags(projectId);
      return true;
    } catch (error) {
      console.error('创建标签失败:', error);
      ElMessage.error('创建标签失败');
      return false;
    }
  };

  /**
   * 更新标签
   */
  const updateTag = async (
    tagId: number,
    name: string,
    color: string
  ): Promise<boolean> => {
    try {
      await service.patch(`/tags/${tagId}/`, { name, color });
      ElMessage.success('标签更新成功');
      return true;
    } catch (error) {
      console.error('更新标签失败:', error);
      ElMessage.error('更新标签失败');
      return false;
    }
  };

  /**
   * 删除标签
   */
  const deleteTag = async (tagId: number, projectId: string): Promise<boolean> => {
    try {
      await service.delete(`/tags/${tagId}/`);
      ElMessage.success('标签已删除');
      await fetchTags(projectId);
      return true;
    } catch (error) {
      console.error('删除标签失败:', error);
      ElMessage.error('删除标签失败');
      return false;
    }
  };

  return {
    // State
    tags,
    isLoading,
    // Actions
    fetchTags,
    createTag,
    updateTag,
    deleteTag,
  };
});
