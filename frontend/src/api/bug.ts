/**
 * Bug 跟踪 API 服务
 */
import service from '@/utils/request';

export type BugStatus =
  | 'new' | 'confirmed' | 'assigned' | 'fixing'
  | 'fixed' | 'verifying' | 'closed' | 'reopened' | 'rejected';

export type BugSeverity = 'blocker' | 'critical' | 'major' | 'minor' | 'trivial';
export type BugPriority = 'p0' | 'p1' | 'p2' | 'p3';
export type BugSource = 'manual' | 'api_auto' | 'performance' | 'ui_auto';

export interface UserBrief {
  id: number;
  username: string;
}

export interface BugListItem {
  id: number;
  project: string;
  project_name: string;
  title: string;
  status: BugStatus;
  status_display: string;
  severity: BugSeverity;
  severity_display: string;
  priority: BugPriority;
  priority_display: string;
  reporter: UserBrief | null;
  assignee: UserBrief | null;
  source_test_type: BugSource;
  created_at: string;
  updated_at: string;
  linked_task: string | null;
  allowed_transitions?: BugStatus[];
}

export interface BugTransition {
  id: number;
  operator: UserBrief | null;
  from_status: string;
  to_status: string;
  comment: string;
  created_at: string;
}

export interface BugComment {
  id: number;
  bug: number;
  author: UserBrief | null;
  content: string;
  created_at: string;
}

export interface BugDetail extends BugListItem {
  description: string;
  steps_to_reproduce: string;
  expected: string;
  actual: string;
  environment: string;
  fixer: UserBrief | null;
  verifier: UserBrief | null;
  source_display: string;
  source_case_id: number | null;
  source_result_id: number | null;
  linked_task: string | null;
  closed_at: string | null;
  transitions: BugTransition[];
  comments: BugComment[];
  allowed_transitions: BugStatus[];
}

export interface BugCreatePayload {
  project: string;
  title: string;
  description?: string;
  steps_to_reproduce?: string;
  expected?: string;
  actual?: string;
  environment?: string;
  severity?: BugSeverity;
  priority?: BugPriority;
  assignee_id?: number | null;
  linked_task?: string | null;
}

export interface BugListParams {
  project?: string;
  status?: string;       // comma-separated
  severity?: string;
  priority?: string;
  risk?: 'high';          // OR query: severity=blocker,critical OR priority=p0,p1
  assignee?: number;
  reporter?: number;
  source_test_type?: BugSource;
  keyword?: string;
  has_linked_task?: 'true' | 'false';
  created_after?: string;
  created_before?: string;
  updated_after?: string;
  updated_before?: string;
  page?: number;
  page_size?: number;
}

export interface BugListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: BugListItem[];
}

export interface BugStats {
  total: number;
  open: number;
  closed: number;
  by_status: Record<BugStatus, number>;
  by_severity_open: Record<BugSeverity, number>;
  // New fields (Phase 3)
  my_pending?: number;
  my_reported_open?: number;
  verifying?: number;
  high_risk?: number;
}

const BASE = '/bugs';

export const listBugs = (params: BugListParams = {}): Promise<BugListResponse> =>
  service.get(`${BASE}/`, { params }) as Promise<BugListResponse>;

export const getBug = (id: number): Promise<BugDetail> =>
  service.get(`${BASE}/${id}/`) as Promise<BugDetail>;

export const createBug = (payload: BugCreatePayload): Promise<BugDetail> =>
  service.post(`${BASE}/`, payload) as Promise<BugDetail>;

export type BugUpdatePayload = Partial<Omit<BugCreatePayload, 'project'>>

export const updateBug = (id: number, payload: BugUpdatePayload): Promise<BugDetail> =>
  service.patch(`${BASE}/${id}/`, payload) as Promise<BugDetail>;

export const deleteBug = (id: number): Promise<void> =>
  service.delete(`${BASE}/${id}/`) as Promise<void>;

export const transitionBug = (
  id: number, to_status: BugStatus, comment = ''
): Promise<BugDetail> =>
  service.post(`${BASE}/${id}/transition/`, { to_status, comment }) as Promise<BugDetail>;

export const assignBug = (id: number, user_id: number, comment = ''): Promise<BugDetail> =>
  service.post(`${BASE}/${id}/assign/`, { user_id, comment }) as Promise<BugDetail>;

export const listBugComments = (id: number): Promise<BugComment[]> =>
  service.get(`${BASE}/${id}/comments/`) as Promise<BugComment[]>;

export const addBugComment = (id: number, content: string): Promise<BugComment> =>
  service.post(`${BASE}/${id}/comments/`, { content }) as Promise<BugComment>;

export const listMyBugs = (
  role: 'assignee' | 'reporter' | 'fixer' | 'verifier',
  params: Omit<BugListParams, 'assignee' | 'reporter'> = {},
): Promise<BugListResponse> =>
  service.get(`${BASE}/my/`, { params: { role, ...params } }) as Promise<BugListResponse>;

export const getBugStats = (project?: string): Promise<BugStats> =>
  service.get(`${BASE}/stats/`, { params: { project } }) as Promise<BugStats>;

export const seedDemoBugs = (projectId: string): Promise<{ added: number; total: number }> =>
  service.post(`/bugs/seed-demo/`, null, { params: { project_id: projectId } }) as Promise<{ added: number; total: number }>;

export interface ProjectMemberBrief {
  user_id: number;
  username: string;
}

export const getProjectMembers = async (projectId: string): Promise<ProjectMemberBrief[]> => {
  const res: any = await service.get(`/projects/${projectId}/members/`)
  const list = Array.isArray(res) ? res : (res?.results || [])
  return list.map((m: any) => ({
    user_id: m.user_id || m.user?.id || m.user_detail?.id || m.id,
    username: m.username || m.user?.username || m.user_detail?.username || '',
  }))
}

// 状态、严重度、优先级显示工具
export const STATUS_TAG_TYPE: Record<BugStatus, 'info' | 'warning' | 'primary' | 'success' | 'danger' | ''> = {
  new: 'info',
  confirmed: 'warning',
  assigned: 'primary',
  fixing: 'warning',
  fixed: 'primary',
  verifying: 'warning',
  closed: 'success',
  reopened: 'danger',
  rejected: '',
};

export const SEVERITY_TAG_TYPE: Record<BugSeverity, 'danger' | 'warning' | 'primary' | 'info' | ''> = {
  blocker: 'danger',
  critical: 'danger',
  major: 'warning',
  minor: 'primary',
  trivial: 'info',
};

export const PRIORITY_TAG_TYPE: Record<BugPriority, 'danger' | 'warning' | 'primary' | 'info'> = {
  p0: 'danger',
  p1: 'warning',
  p2: 'primary',
  p3: 'info',
};

export const STATUS_LABEL: Record<BugStatus, string> = {
  new: '新建',
  confirmed: '已确认',
  assigned: '已指派',
  fixing: '修复中',
  fixed: '已修复',
  verifying: '待验证',
  closed: '已关闭',
  reopened: '重新打开',
  rejected: '已拒绝',
};
