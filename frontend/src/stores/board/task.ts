/**
 * 任务管理 Store
 *
 * 提供任务的增删改查功能
 */

import { ref } from 'vue';
import { defineStore } from 'pinia';
import { ElMessage } from 'element-plus';
import service from '@/utils/request';
import type { TaskCard } from '@/types/kanban';
import { DEFAULT_POSITION } from '@/types/kanban';
import type { CreateTaskExtra, UpdateTaskPayload } from './types';

export const useTaskStore = defineStore('boardTask', () => {
  // ============ State ============
  const isLoading = ref(false);

  // ============ Actions ============

  /**
   * 创建任务
   */
  const createTask = async (
    columnId: string,
    title: string,
    extra?: CreateTaskExtra
  ): Promise<boolean> => {
    try {
      const payload: any = {
        column: columnId,
        title: title,
        content: extra?.content || '',
        position: 0,
      };

      if (extra?.assignee !== undefined && extra.assignee !== null) {
        payload.assignee = extra.assignee;
      }
      if (extra?.tags && extra.tags.length > 0) {
        payload.tags = extra.tags;
      }

      await service.post('/tasks/', payload);
      console.log('任务创建指令已发送');
      return true;
    } catch (error) {
      console.error('创建任务失败:', error);
      ElMessage.error('创建任务失败');
      return false;
    }
  };

  /**
   * 更新任务
   */
  const updateTask = async (
    taskId: string,
    payload: UpdateTaskPayload
  ): Promise<boolean> => {
    try {
      await service.patch(`/tasks/${taskId}/`, payload);
      console.log(`任务 ${taskId} 更新成功`);
      return true;
    } catch (error) {
      console.error('更新任务失败:', error);
      ElMessage.error('更新任务失败');
      return false;
    }
  };

  /**
   * 删除任务
   */
  const deleteTask = async (taskId: string): Promise<boolean> => {
    try {
      await service.delete(`/tasks/${taskId}/`);
      console.log(`任务 ${taskId} 删除指令已发送`);
      return true;
    } catch (error) {
      console.error('删除任务失败:', error);
      ElMessage.error('删除任务失败');
      return false;
    }
  };

  /**
   * 批量删除任务
   */
  const batchDeleteTasks = async (taskIds: string[]): Promise<boolean> => {
    try {
      await service.post('/tasks/batch-delete/', { task_ids: taskIds });
      ElMessage.success(`成功批量删除 ${taskIds.length} 个任务`);
      return true;
    } catch (error) {
      console.error('批量删除失败:', error);
      ElMessage.error('批量删除失败');
      return false;
    }
  };

  /**
   * 计算任务新位置
   */
  const calculatePosition = (tasks: TaskCard[], newIndex: number): number => {
    const prevTask = tasks[newIndex - 1];
    const nextTask = tasks[newIndex + 1];

    if (!prevTask && !nextTask) return DEFAULT_POSITION;
    if (!prevTask && nextTask) return nextTask.position / 2;
    if (!nextTask && prevTask) return prevTask.position + DEFAULT_POSITION;
    if (prevTask && nextTask) return (prevTask.position + nextTask.position) / 2;
    return DEFAULT_POSITION;
  };

  return {
    // State
    isLoading,
    // Actions
    createTask,
    updateTask,
    deleteTask,
    batchDeleteTasks,
    calculatePosition,
  };
});
