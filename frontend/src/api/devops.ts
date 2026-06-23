/**
 * DevOps 测试平台 API 封装。
 *
 * 后端映射：/api/qa/devops/*
 * 接口范围：仪表盘统计、CI/CD 配置 CRUD、测试任务 CRUD + 执行 + 状态 + 历史、
 *          流水线记录、快速测试、质量报告
 *
 * 类型定义在 @/types/devops.ts 中。配合 ws/qa/dashboard/ WS 监听执行进度。
 */
import service from '@/utils/request';
import type {
  DashboardStats,
  RecentExecution,
  CiCdConfig,
  CreateCiCdConfigRequest,
  TestTask,
  CreateTestTaskRequest,
  TaskStatusResponse,
  QuickTestRequest,
  TestType,
} from '@/types/devops';

const BASE_URL = '/qa/devops';

/**
 * 获取仪表板统计数据
 * @param days 统计天数，默认7天
 */
export const getDashboardStats = (days?: number): Promise<DashboardStats> => {
  return service.get(`${BASE_URL}/stats/`, {
    params: { days }
  }) as Promise<DashboardStats>;
};

/**
 * 获取最近执行记录
 * @param limit 限制数量，默认10条
 * @param test_type 测试类型筛选
 */
export const getRecentExecutions = (
  limit?: number,
  test_type?: TestType
): Promise<RecentExecution[]> => {
  return service.get(`${BASE_URL}/recent-executions/`, {
    params: { limit, test_type }
  }) as Promise<RecentExecution[]>;
};

// ==================== CI/CD 配置管理 ====================

/**
 * 获取 CI/CD 配置列表
 */
export const getCiCdConfigs = (): Promise<CiCdConfig[]> => {
  return service.get(`${BASE_URL}/cicd-config/`) as Promise<CiCdConfig[]>;
};

/**
 * 获取单个 CI/CD 配置
 * @param id 配置ID
 */
export const getCiCdConfig = (id: number): Promise<CiCdConfig> => {
  return service.get(`${BASE_URL}/cicd-config/${id}/`) as Promise<CiCdConfig>;
};

/**
 * 创建 CI/CD 配置
 * @param data 配置数据
 */
export const createCiCdConfig = (data: CreateCiCdConfigRequest): Promise<CiCdConfig> => {
  return service.post(`${BASE_URL}/cicd-config/`, data) as Promise<CiCdConfig>;
};

/**
 * 更新 CI/CD 配置
 * @param id 配置ID
 * @param data 配置数据
 */
export const updateCiCdConfig = (id: number, data: Partial<CreateCiCdConfigRequest>): Promise<CiCdConfig> => {
  return service.put(`${BASE_URL}/cicd-config/${id}/`, data) as Promise<CiCdConfig>;
};

/**
 * 删除 CI/CD 配置
 * @param id 配置ID
 */
export const deleteCiCdConfig = (id: number): Promise<{ message: string }> => {
  return service.delete(`${BASE_URL}/cicd-config/${id}/`) as Promise<{ message: string }>;
};

/**
 * 测试 CI/CD Webhook
 * @param id 配置ID
 */
export const testCiCdWebhook = (id: number): Promise<{ success: boolean; message: string }> => {
  return service.post(`${BASE_URL}/cicd-config/${id}/test/`) as Promise<{ success: boolean; message: string }>;
};

// ==================== 测试任务管理 ====================

/**
 * 获取测试任务列表
 * @param type 任务类型筛选
 * @param status 状态筛选
 */
export const getTestTasks = (type?: TestType, status?: string): Promise<TestTask[]> => {
  return service.get(`${BASE_URL}/tasks/`, {
    params: { type, status }
  }) as Promise<TestTask[]>;
};

/**
 * 获取单个测试任务
 * @param id 任务ID
 */
export const getTestTask = (id: number): Promise<TestTask> => {
  return service.get(`${BASE_URL}/tasks/${id}/`) as Promise<TestTask>;
};

/**
 * 创建测试任务
 * @param data 任务数据
 */
export const createTestTask = (data: CreateTestTaskRequest): Promise<TestTask> => {
  return service.post(`${BASE_URL}/tasks/`, data) as Promise<TestTask>;
};

/**
 * 更新测试任务
 * @param id 任务ID
 * @param data 任务数据
 */
export const updateTestTask = (id: number, data: Partial<CreateTestTaskRequest>): Promise<TestTask> => {
  return service.put(`${BASE_URL}/tasks/${id}/`, data) as Promise<TestTask>;
};

/**
 * 删除测试任务
 * @param id 任务ID
 */
export const deleteTestTask = (id: number): Promise<{ message: string }> => {
  return service.delete(`${BASE_URL}/tasks/${id}/`) as Promise<{ message: string }>;
};

/**
 * 执行测试任务
 * @param id 任务ID
 */
export const executeTestTask = (id: number): Promise<{
  message: string;
  execution_id: string;
  task: TestTask;
}> => {
  return service.post(`${BASE_URL}/tasks/${id}/execute/`) as Promise<{
    message: string;
    execution_id: string;
    task: TestTask;
  }>;
};

/**
 * 获取测试任务状态
 * @param id 任务ID
 */
export const getTestTaskStatus = (id: number): Promise<TaskStatusResponse> => {
  return service.get(`${BASE_URL}/tasks/${id}/status/`) as Promise<TaskStatusResponse>;
};

/**
 * 获取测试任务执行历史
 * @param id 任务ID
 */
export const getTestTaskHistory = (id: number): Promise<any[]> => {
  return service.get(`${BASE_URL}/tasks/${id}/history/`) as Promise<any[]>;
};

// ==================== 快速测试 ====================

/**
 * 执行快速测试
 * @param data 测试数据
 */
export const runQuickTest = (data: QuickTestRequest): Promise<{
  message: string;
  test_type: TestType;
  status: string;
}> => {
  return service.post(`${BASE_URL}/quick-test/`, data) as Promise<{
    message: string;
    test_type: TestType;
    status: string;
  }>;
};

// ==================== 工具函数 ====================

/**
 * 获取状态标签类型（用于 Element Plus 标签）
 * @param status 测试状态
 */
export const getStatusType = (status: string): 'success' | 'danger' | 'warning' | 'info' => {
  const typeMap: Record<string, 'success' | 'danger' | 'warning' | 'info'> = {
    'passed': 'success',
    'failed': 'danger',
    'error': 'warning',
    'running': 'info',
    'pending': 'info',
    'idle': 'info',
    'completed': 'success',
  };
  return typeMap[status] || 'info';
};

/**
 * 获取状态显示文本
 * @param status 测试状态
 */
export const getStatusText = (status: string): string => {
  const textMap: Record<string, string> = {
    'passed': '通过',
    'failed': '失败',
    'error': '错误',
    'running': '运行中',
    'pending': '待执行',
    'idle': '空闲',
    'completed': '已完成',
  };
  return textMap[status] || status;
};

/**
 * 获取测试类型标签类型
 * @param type 测试类型
 */
export const getTestTypeType = (type: TestType): 'primary' | 'success' | 'warning' | 'info' => {
  const typeMap: Record<TestType, 'primary' | 'success' | 'warning' | 'info'> = {
    'api': 'primary',
    'ui': 'success',
    'performance': 'warning',
    'regression': 'info',
  };
  return typeMap[type] || 'info';
};

/**
 * 获取测试类型显示文本
 * @param type 测试类型
 */
export const getTestTypeText = (type: TestType): string => {
  const textMap: Record<TestType, string> = {
    'api': '接口测试',
    'ui': 'UI测试',
    'performance': '性能测试',
    'regression': '回归测试',
  };
  return textMap[type] || type;
};

/**
 * 获取 CI/CD 类型显示文本
 * @param type CI/CD 类型
 */
export const getCiCdTypeText = (type: string): string => {
  const textMap: Record<string, string> = {
    'jenkins': 'Jenkins',
    'gitlab': 'GitLab CI',
    'github': 'GitHub Actions',
  };
  return textMap[type] || type;
};

/**
 * 格式化时长
 * @param ms 毫秒数
 */
export const formatDuration = (ms: number): string => {
  if (ms < 1000) {
    return `${ms}ms`;
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`;
  } else {
    return `${(ms / 60000).toFixed(1)}m`;
  }
};

/**
 * 格式化日期时间
 * @param dateString ISO 日期字符串
 */
export const formatDateTime = (dateString: string | null): string => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};
