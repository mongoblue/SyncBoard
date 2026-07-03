/**
 * API 自动化测试结果（ApiAutoTestResult / 含 TestRunPlan 执行）API 客户端
 */
import service from '@/utils/request';
import { createBug } from '@/api/bug';

export type AutoResultStatus = 'pending' | 'running' | 'passed' | 'failed' | 'error';

export type FailureType =
  | ''
  | 'passed'
  | 'assertion_failed'
  | 'http_error'
  | 'network_error'
  | 'timeout'
  | 'ssl_error'
  | 'auth_error'
  | 'server_error'
  | 'framework_error'
  | 'config_error'
  | 'script_error'
  | 'schema_failed'
  | 'unknown_error';

export interface TextEnvelope {
  preview: string;
  preview_size: number;
  truncated: boolean;
  original_size: number;
  limit_bytes: number;
  content_type: string;
  encoding: string;
  is_binary: boolean;
  sha256: string;
  redacted: boolean;
  meta: Record<string, any>;
}

export interface FrameworkDiagnosis {
  framework: string;
  title: string;
  root_cause: string;
  suggested_fixes: string[];
  message: string;
}

export interface RequestSnapshot {
  snapshot_schema_version: number;
  rendered_url: string;
  url_template: string;
  headers: Record<string, any> | null;
  query_params: any[] | null;
  cookies: Record<string, any> | null;
  auth: { auth_type: string; redacted: boolean } | null;
  body_mode: string;
  body: TextEnvelope | null;
  files: any[];
  timeout: number;
  allow_redirects: boolean;
  trace_id: string;
}

export interface ResponseSnapshot {
  snapshot_schema_version: number;
  status_code: number;
  headers: Record<string, any> | null;
  cookies: Record<string, any> | null;
  content_type: string | null;
  content_encoding: string | null;
  body: TextEnvelope;
  body_size_raw: number;
  body_size_decoded: number;
  final_url: string;
  redirect_chain: any[];
  elapsed_ms: number;
}

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
  expectation_type?: 'success_response' | 'error_response';
  default_assertion_policy?: 'success_response' | 'expected_error_response' | 'custom';
  expected_status?: number | null;
  semantic_status?: string;
  semantic_label?: string;
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
  failure_type?: FailureType;
  raw_status?: string;
  trace_id?: string;
  request_snapshot?: RequestSnapshot | null;
  response_snapshot?: ResponseSnapshot | null;
  extracted_variables_preview?: Record<string, TextEnvelope> | null;
  result_metadata?: {
    summary?: string;
    diagnosis?: FrameworkDiagnosis | null;
    provider?: string;
    expectation_type?: 'success_response' | 'error_response';
    default_assertion_policy?: 'success_response' | 'expected_error_response' | 'custom';
    expected_status?: number | null;
    semantic_status?: string;
    semantic_label?: string;
    [key: string]: any;
  } | null;
  curl?: { preview: string } | null;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const FAILURE_TYPE_LABELS: Record<FailureType, string> = {
  '': '未知',
  passed: '通过',
  assertion_failed: '断言失败',
  http_error: 'HTTP 错误',
  network_error: '网络错误',
  timeout: '请求超时',
  ssl_error: 'SSL 错误',
  auth_error: '认证失败',
  server_error: '服务器错误',
  framework_error: '框架错误',
  config_error: '配置错误',
  script_error: '脚本错误',
  schema_failed: 'Schema 校验失败',
  unknown_error: '未知错误',
};

export const FAILURE_TYPE_TAG: Record<FailureType, '' | 'success' | 'warning' | 'danger' | 'info'> = {
  '': 'info',
  passed: 'success',
  assertion_failed: 'danger',
  http_error: 'warning',
  network_error: 'danger',
  timeout: 'warning',
  ssl_error: 'danger',
  auth_error: 'warning',
  server_error: 'danger',
  framework_error: 'danger',
  config_error: 'warning',
  script_error: 'danger',
  schema_failed: 'danger',
  unknown_error: 'info',
};

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
