/**
 * 看板 Store 类型定义
 */

import type { BoardColumn, TaskCard, User } from '@/types/kanban';

// 创建任务时的额外参数
export interface CreateTaskExtra {
  content?: string;
  assignee?: number | null;
  tags?: number[];
}

// 更新任务时的参数
export interface UpdateTaskPayload {
  title?: string;
  content?: string;
  column?: string;
  position?: number;
  assignee?: number | null;
  tags?: number[];
}

// 看板 Store 状态
export interface BoardState {
  columns: BoardColumn[];
  users: User[];
  currentProjectId: string;
  currentProject: any;
}

// WebSocket 消息类型
export interface WebSocketMessage {
  action?: string;
  task_id?: string;
  title?: string;
  user_action?: string;
  data?: any;
}
