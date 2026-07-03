import request from '@/utils/request'

export interface TestRun {
  id: number
  project_id: number
  project_name: string
  name: string
  trigger: 'manual' | 'scheduled' | 'cicd' | 'regression'
  test_type: 'api' | 'ui' | 'performance' | 'mixed'
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'cancelled'
  total_count: number
  passed_count: number
  failed_count: number
  error_count: number
  pass_rate: number
  duration_ms: number | null
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface TestRunCaseResult {
  id: number
  test_run_id: number
  case_type: 'api' | 'ui' | 'performance'
  sequence: number
  api_auto_case_id: number | null
  name: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'skipped'
  duration_ms: number | null
  status_code: number | null
  error_message: string
  provider?: string
  expectation_type?: 'success_response' | 'error_response'
  default_assertion_policy?: 'success_response' | 'expected_error_response' | 'custom'
  expected_status?: number | null
  semantic_status?: string
  semantic_label?: string
  started_at: string | null
  completed_at: string | null
  // full=true 时:
  response_body?: string
  response_headers?: Record<string, string>
  assertion_results?: any[]
  request_snapshot?: any
  curl?: string
  trace_id?: string
  raw_status?: string
  error_code?: string
  response_snapshot?: any
  extracted_variables_preview?: any
  result_metadata?: any
}

export interface PaginatedResponse<T> {
  count: number
  page: number
  page_size: number
  results: T[]
}

export const testRunApi = {
  list(params: { project?: number; status?: string; test_type?: string; page?: number; page_size?: number } = {}) {
    return request.get<PaginatedResponse<TestRun>>('/qa/runs/', { params })
  },
  detail(id: number) {
    return request.get<TestRun>(`/qa/runs/${id}/`)
  },
  cases(runId: number, params: { status?: string; page?: number; page_size?: number } = {}) {
    return request.get<PaginatedResponse<TestRunCaseResult>>(`/qa/runs/${runId}/cases/`, { params })
  },
  caseDetail(runId: number, caseResultId: number) {
    return request.get<TestRunCaseResult>(`/qa/runs/${runId}/cases/${caseResultId}/`)
  },
  cancel(id: number) {
    return request.post(`/qa/runs/${id}/cancel/`)
  },
  // P1 后 rerun 已废弃（后端返回 410 Gone）；保留方法以让调用方显式处理
  rerun(id: number) {
    return request.post<{ run_id: number; total_count: number }>(`/qa/runs/${id}/rerun/`)
  },
}
