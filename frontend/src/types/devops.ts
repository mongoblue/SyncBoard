/**
 * DevOps 测试平台类型定义
 */

// 测试类型
export type TestType = 'api' | 'ui' | 'performance' | 'regression';

// 测试状态
export type TestStatus = 'passed' | 'failed' | 'error' | 'running' | 'pending';

// 任务状态
export type TaskStatus = 'idle' | 'running' | 'completed' | 'failed';

// CI/CD 类型
export type CiCdType = 'jenkins' | 'gitlab' | 'github';

// 触发类型
export type TriggerType = 'manual' | 'scheduled' | 'webhook';

/**
 * 仪表板统计数据
 */
export interface DashboardStats {
  overview: {
    total_cases: number;
    api_cases: number;
    ui_cases: number;
    total_executions: number;
    today_executions: number;
    pass_rate: number;
    avg_response_time: number | null;
  };
  status_count: {
    passed: number;
    failed: number;
    error: number;
    running: number;
  };
  by_type: Record<TestType, number>;
  daily_trend: DailyStat[];
}

/**
 * 每日统计数据
 */
export interface DailyStat {
  date: string;
  total: number;
  passed: number;
  failed: number;
  error: number;
}

/**
 * 最近执行记录
 */
export interface RecentExecution {
  id: number;
  test_type: TestType;
  test_type_display: string;
  name: string;
  status: TestStatus;
  status_display: string;
  project: number | null;
  project_name: string | null;
  executed_by: number | null;
  executed_by_name: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  screenshot_count: number;
  created_at: string;
}

/**
 * CI/CD 集成配置
 */
export interface CiCdConfig {
  id: number;
  name: string;
  type: CiCdType;
  webhook_url: string;
  branch: string;
  enabled: boolean;
  auto_trigger: boolean;
  test_suite: number[];
  headers: Record<string, string>;
  created_at: string;
  updated_at: string;
  created_by: string;
  last_triggered: string | null;
  status: 'active' | 'inactive' | 'error';
}

/**
 * 创建 CI/CD 配置请求
 */
export interface CreateCiCdConfigRequest {
  name: string;
  type: CiCdType;
  webhook_url: string;
  branch?: string;
  enabled?: boolean;
  auto_trigger?: boolean;
  test_suite?: number[];
  headers?: Record<string, string>;
}

/**
 * 测试任务
 */
export interface TestTask {
  id: number;
  name: string;
  description: string;
  test_type: TestType;
  trigger_type: TriggerType;
  status: TaskStatus;
  project: number;
  project_name: string;
  created_by: number;
  created_by_name: string;
  cron_expression: string | null;
  webhook_url: string | null;
  test_config: {
    api_cases?: number[];
    ui_cases?: number[];
    environment?: string;
    parallel?: boolean;
  };
  execution_count: number;
  last_executed: string | null;
  last_result_summary: {
    id: number;
    status: string;
    passed: boolean;
    duration_ms: number;
    created_at: string;
  } | null;
  notify_on_success: boolean;
  notify_on_failure: boolean;
  notification_channels: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * 任务执行结果
 */
export interface TaskResult {
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
}

/**
 * 创建测试任务请求
 */
export interface CreateTestTaskRequest {
  name: string;
  description?: string;
  test_type: TestType;
  project: number;
  trigger_type?: TriggerType;
  cron_expression?: string;
  webhook_url?: string;
  test_config?: {
    api_cases?: number[];
    ui_cases?: number[];
    environment?: string;
    parallel?: boolean;
  };
  notify_on_success?: boolean;
  notify_on_failure?: boolean;
  notification_channels?: string[];
}

/**
 * 任务执行记录
 */
export interface TaskExecution {
  id: string;
  task_id: number;
  status: TaskStatus;
  started_at: string;
  completed_at: string | null;
  result: TaskResult | null;
  logs: ExecutionLog[];
  triggered_by: string;
}

/**
 * 执行日志
 */
export interface ExecutionLog {
  step: number;
  case: number | string;
  status: 'passed' | 'failed';
  timestamp: string;
}

/**
 * 任务状态响应
 */
export interface TaskStatusResponse {
  task: TestTask;
  current_execution: TaskExecution | null;
}

/**
 * 快速测试请求
 */
export interface QuickTestRequest {
  type: TestType;
  test_cases?: number[];
}

/**
 * API 响应包装
 */
export interface ApiResponse<T> {
  data?: T;
  error?: string;
  message?: string;
}
