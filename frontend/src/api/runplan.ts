/**
 * TestRunPlan（批量执行计划）API 封装。
 *
 * 后端映射：/api/qa/run-plans/
 * 核心操作：获取计划列表/详情 → 触发执行 → 监听 ws/qa/dashboard/ 进度
 *
 * 与 BatchRunExecuteDialog.vue 配合使用。
 * 执行结果详情跳转到 AutoResultDetail.vue 查看。
 */
import service from '@/utils/request';

export interface RunPlanCaseBrief {
  id: number;
  name: string;
  method: string;
  url: string;
  suite_id: number;
  suite_name: string;
}

export interface RunPlan {
  id: number;
  project: number;
  name: string;
  description?: string;
  case_ids: number[];
  parallel: boolean;
  max_workers: number;
  stop_on_failure: boolean;
  case_timeout_seconds: number;
  created_by: number | null;
  created_by_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunPlanCreatePayload {
  project: number | string;
  name: string;
  description?: string;
  case_ids: number[];
  parallel?: boolean;
  max_workers?: number;
  stop_on_failure?: boolean;
  case_timeout_seconds?: number;
}

export interface RunPlanExecuteOverrides {
  parallel?: boolean;
  max_workers?: number;
  stop_on_failure?: boolean;
}

export interface RunPlanExecuteResponse {
  detail: string;
  plan_id: number;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** WebSocket 事件 schema —— 与 run_plan_executor.py 严格对齐。 */
export type RunPlanProgressPhase = 'started' | 'case_done' | 'finished';

export interface RunPlanProgressEvent {
  type: 'run_plan_progress';
  phase: RunPlanProgressPhase;
  plan_id: number;
  result_id: number | null;
  total: number;
  completed?: number;
  passed?: number;
  failed?: number;
  error?: number;
  // case_done 专属
  case_id?: number;
  case_name?: string;
  case_passed?: boolean;
  case_error?: string;
  // finished 专属
  status?: 'passed' | 'failed' | 'error';
}

const BASE = '/qa/run-plans';

export const listRunPlans = (params: { project?: number | string; search?: string } = {}) =>
  service.get(`${BASE}/`, { params }) as Promise<Paginated<RunPlan> | RunPlan[]>;

export const createRunPlan = (payload: RunPlanCreatePayload) =>
  service.post(`${BASE}/`, payload) as Promise<RunPlan>;

export const deleteRunPlan = (id: number) => service.delete(`${BASE}/${id}/`);

export const executeRunPlan = (id: number, overrides: RunPlanExecuteOverrides = {}) =>
  service.post(`${BASE}/${id}/execute/`, overrides) as Promise<RunPlanExecuteResponse>;

export const listSelectableCases = (
  projectId: number | string,
  search?: string,
): Promise<{ count: number; results: RunPlanCaseBrief[] }> =>
  service.get(`${BASE}/cases/`, { params: { project: projectId, ...(search ? { search } : {}) } }) as Promise<{
    count: number;
    results: RunPlanCaseBrief[];
  }>;
