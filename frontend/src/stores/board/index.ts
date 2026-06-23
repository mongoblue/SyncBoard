/**
 * 看板聚合 Store。
 *
 * 内部组合 4 个子 Store：
 *  - columnStore（看板列 CRUD）
 *  - taskStore（任务卡片 CRUD + 拖拽排序）
 *  - tagStore（标签 CRUD）
 *  - userStore（看板用户列表）
 *
 * 同时管理 WebSocket 连接（useWebSocket.ts），
 * 收到消息后根据 action 类型分发到对应子 Store 刷新数据。
 *
 * 对外暴露 Columns / Users 等 computed 保持与旧版大 Store 兼容。
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import service from '@/utils/request';
import { useWebSocket } from '@/stores/composables/useWebSocket';
import { useColumnStore } from './column';
import { useTaskStore } from './task';
import { useTagStore } from './tag';
import { useUserStore } from './user';
import type { BoardColumn, TaskCard, User } from '@/types/kanban';
import type { CreateTaskExtra, WebSocketMessage } from './types';

export const useBoardStore = defineStore('board', () => {
  // ---- 子 Store ----
  const columnStore = useColumnStore();
  const taskStore = useTaskStore();
  const tagStore = useTagStore();
  const userStore = useUserStore();

  // ---- 共享状态 ----
  const currentProjectId = ref<string>('');
  const currentProject = ref<any>(null);

  // ---- WebSocket ----
  const { connect, addMessageListener, isConnected } = useWebSocket();

  // ---- 向后兼容的别名 ----
  const Columns = computed(() => columnStore.columns);
  const Users = computed(() => userStore.users);

  // ---- 项目信息 ----
  const fetchProjectInfo = async (projectId: string): Promise<void> => {
    try {
      const projects = await service.get<any, any[]>('/projects/');
      const projectArray = Array.isArray(projects) ? projects : [];
      const found = projectArray.find(
        (p: any) => p.id == projectId || p.id == Number(projectId)
      );
      if (found) {
        currentProject.value = found;
      }
    } catch (e) {
      console.error('获取项目信息失败:', e);
    }
  };

  // ---- WebSocket 消息处理 ----
  const handleSocketMessage = (payload: WebSocketMessage): void => {
    const { action, user } = payload.data || payload;

    if (action === 'user_joined') {
      ElMessage.success(`${user.username} 进入了看板`);
    }
    if (action === 'refresh') {
      fetchColumns(currentProjectId.value);
    }
  };

  const initSocket = (projectId: string): void => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    connect(`${protocol}//${host}/ws/board/${projectId}/`);
    addMessageListener(handleSocketMessage);
  };

  // ---- 列管理 ----
  const fetchColumns = async (projectId: string): Promise<void> => {
    currentProjectId.value = projectId;
    await columnStore.fetchColumns(projectId);
  };

  const createColumn = async (projectId: string, title: string): Promise<boolean> => {
    return columnStore.createColumn(projectId, title);
  };

  const renameColumn = async (columnId: string, title: string, position?: number): Promise<boolean> => {
    const ok = await columnStore.updateColumn(columnId, title, position);
    if (ok) {
      await fetchColumns(currentProjectId.value);
    }
    return ok;
  };

  const deleteColumn = async (columnId: string): Promise<boolean> => {
    return columnStore.deleteColumn(columnId, currentProjectId.value);
  };

  // ---- 任务管理 ----
  const createTask = async (columnId: string, title: string, extra?: CreateTaskExtra): Promise<boolean> => {
    return taskStore.createTask(columnId, title, extra);
  };

  const updateTask = async (taskId: string, payload: Partial<TaskCard>): Promise<boolean> => {
    return taskStore.updateTask(taskId, payload);
  };

  const deleteTask = async (taskId: string): Promise<boolean> => {
    return taskStore.deleteTask(taskId);
  };

  const batchDeleteTasks = async (taskIds: string[]): Promise<boolean> => {
    return taskStore.batchDeleteTasks(taskIds);
  };

  // ---- 用户管理 ----
  const fetchUsers = async (): Promise<void> => {
    await userStore.fetchUsers();
  };

  // ---- 标签管理 ----
  const createTag = async (projectId: string, name: string, color: string): Promise<boolean> => {
    const ok = await tagStore.createTag(projectId, name, color);
    if (ok) {
      await fetchProjectInfo(projectId);
    }
    return ok;
  };

  const deleteTag = async (tagId: number): Promise<boolean> => {
    const ok = await tagStore.deleteTag(tagId, currentProjectId.value);
    if (ok) {
      await fetchProjectInfo(currentProjectId.value);
    }
    return ok;
  };

  return {
    // State
    Columns,
    Users,
    isConnected,
    currentProjectId,
    currentProject,
    // Actions
    fetchColumns,
    fetchUsers,
    fetchProjectInfo,
    initSocket,
    createTask,
    updateTask,
    deleteTask,
    batchDeleteTasks,
    createColumn,
    deleteColumn,
    renameColumn,
    createTag,
    deleteTag,
  };
});
