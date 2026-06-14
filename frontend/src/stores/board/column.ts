/**
 * 看板列管理 Store
 *
 * 提供看板列的增删改查功能
 */

import { ref } from 'vue';
import { defineStore } from 'pinia';
import { ElMessage } from 'element-plus';
import service from '@/utils/request';
import type { BoardColumn } from '@/types/kanban';

export const useColumnStore = defineStore('boardColumn', () => {
  // ============ State ============
  const columns = ref<BoardColumn[]>([]);
  const isLoading = ref(false);

  // ============ Actions ============

  /**
   * 获取看板列列表
   */
  const fetchColumns = async (projectId: string): Promise<BoardColumn[]> => {
    isLoading.value = true;
    try {
      const data = await service.get<any, BoardColumn[]>(`/columns/?project=${projectId}`);
      columns.value = data;
      return data;
    } catch (error) {
      console.error('获取看板列失败:', error);
      ElMessage.error('获取看板列失败');
      return [];
    } finally {
      isLoading.value = false;
    }
  };

  /**
   * 创建看板列
   */
  const createColumn = async (projectId: string, title: string): Promise<boolean> => {
    try {
      await service.post('/columns/', { project: projectId, title });
      ElMessage.success('列创建成功');
      await fetchColumns(projectId);
      return true;
    } catch (error) {
      console.error('创建列失败:', error);
      ElMessage.error('创建列失败');
      return false;
    }
  };

  /**
   * 更新看板列
   */
  const updateColumn = async (
    columnId: string,
    title: string,
    position?: number
  ): Promise<boolean> => {
    try {
      const payload: any = { title };
      if (position !== undefined) {
        payload.position = position;
      }
      await service.patch(`/columns/${columnId}/`, payload);
      return true;
    } catch (error) {
      console.error('更新列失败:', error);
      ElMessage.error('更新列失败');
      return false;
    }
  };

  /**
   * 删除看板列
   */
  const deleteColumn = async (columnId: string, projectId: string): Promise<boolean> => {
    try {
      await service.delete(`/columns/${columnId}/`);
      ElMessage.success('列删除成功');
      await fetchColumns(projectId);
      return true;
    } catch (error: any) {
      const msg = error.response?.data?.detail || '删除列失败';
      ElMessage.error(msg);
      return false;
    }
  };

  /**
   * 重新排序列（本地更新）
   */
  const reorderColumns = (newColumns: BoardColumn[]) => {
    columns.value = newColumns;
  };

  return {
    // State
    columns,
    isLoading,
    // Actions
    fetchColumns,
    createColumn,
    updateColumn,
    deleteColumn,
    reorderColumns,
  };
});
