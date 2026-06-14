/**
 * API 自动化测试结果（ApiAutoTestResult / 含 TestRunPlan 执行）API 客户端
 */
import service from '@/utils/request';
import { createBug } from '@/api/bug';

export type AutoResultStatus = 'pending' | 'running' | 'passed' | 'failed' | 'error';

export interface AssertionDetail {
  assertion_type: string;
  json_path?: string;
  expected_value?: any;
  actual_value?: any;
  operator?: string;
  passed: boolean;
  error_message?: string;
}

export interface AutoResultSummary {
  id: number;
  suite: number;
  name: string;
  status: AutoResultStatus;
  status_display: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  error_cases: number;
  duration_ms: number | null;
  executed_by: number | null;
  executed_by_name: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string;
  pass_rate?: number;
}

export interface AutoCaseResultBrief {
  id: number;
  case: number;
  case_name: string;
  case_url: string;
  case_method: string;
  status_code: number;
  response_time_ms: number;
  passed: boolean;
  assertion_total: number;
  assertion_passed: number;
  error_summary: string;
  executed_at: string;
}

export interface AutoCaseResultFull extends AutoCaseResultBrief {
  test_result: number;
  response_body: string;
  response_headers: Record<string, string>;
  assertion_details: AssertionDetail[];
  error_message: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

const BASE = '/qa/auto-results';

export const getAutoResult = (id: number): Promise<AutoResultSummary> =>
  service.get(`${BASE}/${id}/`) as Promise<AutoResultSummary>;

export interface ListCasesParams {
  passed?: boolean;
  search?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export const listAutoResultCases = (
  resultId: number,
  params: ListCasesParams = {},
): Promise<Paginated<AutoCaseResultBrief>> => {
  const p: Record<string, any> = { ...params };
  if (typeof params.passed === 'boolean') p.passed = String(params.passed);
  return service.get(`${BASE}/${resultId}/cases/`, { params: p }) as Promise<
    Paginated<AutoCaseResultBrief>
  >;
};

export const getAutoCaseResultDetail = (
  resultId: number,
  caseResultId: number,
): Promise<AutoCaseResultFull> =>
  service.get(`${BASE}/${resultId}/case_detail/`, {
    params: { case_result_id: caseResultId },
  }) as Promise<AutoCaseResultFull>;

/**
 * 为单条失败用例建 Bug。projectId 由前端从用例的 suite 反查或当前路由提供。
 */
export const createBugFromCaseResult = async (
  projectId: string | number,
  caseResult: AutoCaseResultBrief | AutoCaseResultFull,
): Promise<{ id: number }> => {
  const title = `[自动化失败] ${caseResult.case_name}`;
  const lines = [
    `测试用例: ${caseResult.case_name}`,
    `请求: ${caseResult.case_method} ${caseResult.case_url}`,
    `状态码: ${caseResult.status_code}`,
    `耗时: ${caseResult.response_time_ms}ms`,
  ];
  if (caseResult.error_summary) lines.push('', '错误:', caseResult.error_summary);
  const bug = await createBug({
    project: String(projectId),
    title,
    description: lines.join('\n'),
    actual: caseResult.error_summary,
    severity: 'major',
    priority: 'p1',
  });
  return { id: bug.id };
};
