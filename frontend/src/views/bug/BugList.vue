<template>
  <div class="bug-list">
    <header class="page-header">
      <div>
        <h1 class="page-title">Bug 管理</h1>
        <p class="page-subtitle">报告、追踪、修复 Bug 的完整生命周期</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadStats">
          <el-icon><TrendCharts /></el-icon>
          统计概览
        </el-button>
        <el-button @click="loadList">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建 Bug
        </el-button>
      </div>
    </header>

    <!-- 统计卡片 -->
    <div class="statistics-cards" v-if="stats">
      <el-card class="stat-card">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">总 Bug 数</div>
      </el-card>
      <el-card class="stat-card warning">
        <div class="stat-value">{{ stats.open }}</div>
        <div class="stat-label">未关闭</div>
      </el-card>
      <el-card class="stat-card success">
        <div class="stat-value">{{ stats.closed }}</div>
        <div class="stat-label">已关闭</div>
      </el-card>
      <el-card class="stat-card danger">
        <div class="stat-value">{{ stats.by_severity_open?.blocker || 0 }}</div>
        <div class="stat-label">阻塞 (未关闭)</div>
      </el-card>
      <el-card class="stat-card danger">
        <div class="stat-value">{{ stats.by_severity_open?.critical || 0 }}</div>
        <div class="stat-label">严重 (未关闭)</div>
      </el-card>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filters.keyword"
        placeholder="搜索标题/描述"
        clearable
        style="width: 200px"
        @change="reload"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>

      <el-select
        v-model="filters.status"
        placeholder="状态"
        clearable multiple collapse-tags collapse-tags-tooltip
        style="width: 200px"
        @change="reload"
      >
        <el-option v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>

      <el-select
        v-model="filters.severity"
        placeholder="严重程度"
        clearable multiple collapse-tags
        style="width: 160px"
        @change="reload"
      >
        <el-option v-for="s in SEVERITY_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>

      <el-select
        v-model="filters.priority"
        placeholder="优先级"
        clearable multiple collapse-tags
        style="width: 130px"
        @change="reload"
      >
        <el-option v-for="p in PRIORITY_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
      </el-select>

      <el-select
        v-model="filters.source_test_type"
        placeholder="来源"
        clearable
        style="width: 140px"
        @change="reload"
      >
        <el-option label="手工" value="manual" />
        <el-option label="接口自动化" value="api_auto" />
        <el-option label="性能测试" value="performance" />
        <el-option label="UI 自动化" value="ui_auto" />
      </el-select>

      <el-select
        v-model="filters.assignee"
        placeholder="指派人"
        clearable filterable
        style="width: 160px"
        @change="reload"
      >
        <el-option
          v-for="m in projectMembers"
          :key="m.user_id"
          :label="m.username"
          :value="m.user_id"
        />
      </el-select>
    </div>

    <!-- 列表 -->
    <div v-if="!loading && bugs.length === 0 && isOwner" class="empty-demo-banner">
      <span>暂无 Bug 数据</span>
      <el-button size="small" type="primary" @click="handleSeedDemo">导入示例 Bug</el-button>
    </div>
    <el-table :data="bugs" v-loading="loading" stripe>
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column label="标题" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">
          <button class="bug-title-link" type="button" @click="goDetail(row)">
            {{ row.title }}
          </button>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-dropdown
            v-if="row.allowed_transitions?.length"
            trigger="click"
            @command="(cmd: BugStatus) => onQuickTransition(row, cmd)"
            @click.stop
          >
            <el-tag
              class="editable-tag"
              :type="STATUS_TAG_TYPE[row.status as keyof typeof STATUS_TAG_TYPE]"
              size="small"
            >
              {{ row.status_display }} <el-icon class="tag-arrow"><ArrowDown /></el-icon>
            </el-tag>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="s in row.allowed_transitions"
                  :key="s"
                  :command="s"
                >
                  → {{ STATUS_LABEL[s as BugStatus] }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tag v-else :type="STATUS_TAG_TYPE[row.status as keyof typeof STATUS_TAG_TYPE]" size="small">
            {{ row.status_display }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="严重度" width="120">
        <template #default="{ row }">
          <el-select
            v-model="row.severity"
            size="small"
            class="table-select"
            @change="(value: BugSeverity) => saveSeverity(row, value)"
            @click.stop
          >
            <el-option v-for="s in SEVERITY_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="110">
        <template #default="{ row }">
          <el-select
            v-model="row.priority"
            size="small"
            class="table-select"
            @change="(value: BugPriority) => savePriority(row, value)"
            @click.stop
          >
            <el-option v-for="p in PRIORITY_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="负责人" width="150">
        <template #default="{ row }">
          <el-select
            :model-value="row.assignee?.id || null"
            size="small"
            class="table-select"
            placeholder="未指派"
            filterable
            @change="(userId: number) => saveAssignee(row, userId)"
            @click.stop
          >
            <el-option
              v-for="m in projectMembers"
              :key="m.user_id"
              :label="m.username"
              :value="m.user_id"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="报告人" width="120">
        <template #default="{ row }">
          {{ row.reporter?.username || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="来源" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source_test_type === 'manual' ? 'info' : 'warning'">
            {{ sourceLabel(row.source_test_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="关联任务" width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.linked_task" :title="row.linked_task" class="linked-task-chip">
            #{{ row.linked_task.slice(0, 8) }}
          </span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <div class="row-actions" @click.stop>
            <el-popconfirm
              title="确认删除此 Bug？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="confirmDelete(row)"
            >
              <template #reference>
                <el-button size="small" type="danger" plain @click.stop>
                  <el-icon><Delete /></el-icon> 删除
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      class="pagination"
      @current-change="loadList"
    />

    <!-- 新建对话框 -->
    <el-dialog v-model="createDialogVisible" title="新建 Bug" width="640px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="标题" required>
          <el-input v-model="createForm.title" placeholder="简短描述问题" />
        </el-form-item>
        <el-form-item label="指派给">
          <el-select v-model="createForm.assignee_id" placeholder="（可选）" clearable filterable style="width: 100%">
            <el-option
              v-for="m in projectMembers"
              :key="m.user_id"
              :label="m.username"
              :value="m.user_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关联任务">
          <el-input v-model="createForm.linked_task" placeholder="（可选）任务 UUID" />
        </el-form-item>
        <el-form-item label="严重程度">
          <el-select v-model="createForm.severity" style="width: 100%">
            <el-option v-for="s in SEVERITY_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="createForm.priority" style="width: 100%">
            <el-option v-for="p in PRIORITY_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境">
          <el-input v-model="createForm.environment" placeholder="如：dev / staging / prod" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="复现步骤">
          <el-input v-model="createForm.steps_to_reproduce" type="textarea" :rows="4"
            placeholder="1. ...\n2. ...\n3. ..." />
        </el-form-item>
        <el-form-item label="预期结果">
          <el-input v-model="createForm.expected" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="实际结果">
          <el-input v-model="createForm.actual" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Plus, Refresh, Search, TrendCharts } from '@element-plus/icons-vue';
import { useBoardStore } from '@/stores/board';
import { useAuthStore } from '@/stores/Auth';
import {
  listBugs, createBug, deleteBug, transitionBug, getBugStats, seedDemoBugs,
  getProjectMembers, updateBug, assignBug,
  STATUS_TAG_TYPE, STATUS_LABEL,
  type BugListItem, type BugStats, type BugSeverity, type BugPriority,
  type BugStatus, type ProjectMemberBrief, type BugCreatePayload,
} from '@/api/bug';
import { ArrowDown, Delete } from '@element-plus/icons-vue';
import { extractErrorMessage } from '@/utils/error';

const boardStore = useBoardStore();
const authStore = useAuthStore();

const route = useRoute();
const router = useRouter();
const projectId = route.params.projectId as string;

const STATUS_OPTIONS = [
  { value: 'new', label: '新建' },
  { value: 'confirmed', label: '已确认' },
  { value: 'assigned', label: '已指派' },
  { value: 'fixing', label: '修复中' },
  { value: 'fixed', label: '已修复' },
  { value: 'verifying', label: '待验证' },
  { value: 'closed', label: '已关闭' },
  { value: 'reopened', label: '重新打开' },
  { value: 'rejected', label: '已拒绝' },
];
const SEVERITY_OPTIONS = [
  { value: 'blocker', label: '阻塞' },
  { value: 'critical', label: '严重' },
  { value: 'major', label: '一般' },
  { value: 'minor', label: '次要' },
  { value: 'trivial', label: '轻微' },
];
const PRIORITY_OPTIONS = [
  { value: 'p0', label: 'P0' },
  { value: 'p1', label: 'P1' },
  { value: 'p2', label: 'P2' },
  { value: 'p3', label: 'P3' },
];

const loading = ref(false);
const bugs = ref<BugListItem[]>([]);
const projectMembers = ref<ProjectMemberBrief[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const stats = ref<BugStats | null>(null);

const isOwner = computed(() =>
  boardStore.currentProject?.owner_details?.id === authStore.user?.id
);

interface Filters {
  keyword: string;
  status: string[];
  severity: string[];
  priority: string[];
  source_test_type: string;
  assignee: number | null;
}
const filters = reactive<Filters>({
  keyword: '',
  status: [],
  severity: [],
  priority: [],
  source_test_type: '',
  assignee: null,
});

const reload = () => { page.value = 1; loadList(); };

const loadList = async () => {
  loading.value = true;
  try {
    const params: Record<string, any> = {
      project: projectId,
      page: page.value,
      page_size: pageSize,
    };
    if (filters.keyword) params.keyword = filters.keyword;
    if (filters.status.length) params.status = filters.status.join(',');
    if (filters.severity.length) params.severity = filters.severity.join(',');
    if (filters.priority.length) params.priority = filters.priority.join(',');
    if (filters.source_test_type) params.source_test_type = filters.source_test_type;
    if (filters.assignee) params.assignee = filters.assignee;

    const res = await listBugs(params);
    bugs.value = res.results;
    total.value = res.count;
  } catch (e) {
    console.error(e);
    ElMessage.error(extractErrorMessage(e, '加载 Bug 列表失败'));
  } finally {
    loading.value = false;
  }
};

const loadStats = async () => {
  try {
    stats.value = await getBugStats(projectId);
  } catch (e) {
    console.error(e);
  }
};

const loadMembers = async () => {
  try {
    projectMembers.value = await getProjectMembers(projectId);
  } catch {
    // 指派人筛选不可用不影响主列表
  }
};

const handleSeedDemo = async () => {
  try {
    const res = await seedDemoBugs(projectId);
    ElMessage.success(`已导入 ${res.added} 条示例 Bug`);
    await loadList();
    await loadStats();
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '导入失败'));
  }
};

const createDialogVisible = ref(false);
const submitting = ref(false);
const createForm = reactive({
  title: '',
  description: '',
  steps_to_reproduce: '',
  expected: '',
  actual: '',
  environment: '',
  severity: 'major' as BugSeverity,
  priority: 'p2' as BugPriority,
  assignee_id: null as number | null,
  linked_task: '',
});

const openCreate = () => {
  Object.assign(createForm, {
    title: '', description: '', steps_to_reproduce: '',
    expected: '', actual: '', environment: '',
    severity: 'major', priority: 'p2',
    assignee_id: null, linked_task: '',
  });
  createDialogVisible.value = true;
};

const submitCreate = async () => {
  if (!createForm.title.trim()) {
    ElMessage.warning('请填写标题');
    return;
  }
  submitting.value = true;
  try {
    const payload: Record<string, any> = {
      project: projectId,
      title: createForm.title,
      description: createForm.description,
      steps_to_reproduce: createForm.steps_to_reproduce,
      expected: createForm.expected,
      actual: createForm.actual,
      environment: createForm.environment,
      severity: createForm.severity,
      priority: createForm.priority,
    };
    if (createForm.assignee_id) payload.assignee_id = createForm.assignee_id;
    if (createForm.linked_task.trim()) payload.linked_task = createForm.linked_task.trim();
    const bug = await createBug(payload as BugCreatePayload);
    ElMessage.success('Bug 已创建');
    createDialogVisible.value = false;
    router.push(`/projects/${projectId}/bugs/${bug.id}`);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '创建失败'));
  } finally {
    submitting.value = false;
  }
};

const confirmDelete = async (row: BugListItem) => {
  try {
    await deleteBug(row.id);
    ElMessage.success('已删除');
    await Promise.all([loadList(), loadStats()]);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '删除失败'));
  }
};

interface BugDetailLike {
  status?: BugStatus;
  status_display?: string;
  severity?: BugSeverity;
  severity_display?: string;
  priority?: BugPriority;
  priority_display?: string;
  assignee?: BugListItem['assignee'];
  allowed_transitions?: BugStatus[];
}

const applyBugUpdate = (row: BugListItem, updated: BugDetailLike) => {
  Object.assign(row, {
    status: updated.status ?? row.status,
    status_display: updated.status_display ?? row.status_display,
    severity: updated.severity ?? row.severity,
    severity_display: updated.severity_display ?? row.severity_display,
    priority: updated.priority ?? row.priority,
    priority_display: updated.priority_display ?? row.priority_display,
    assignee: updated.assignee ?? row.assignee,
    allowed_transitions: updated.allowed_transitions ?? row.allowed_transitions,
  });
};

const saveSeverity = async (row: BugListItem, severity: BugSeverity) => {
  try {
    const updated = await updateBug(row.id, { severity });
    applyBugUpdate(row, updated);
    ElMessage.success('严重度已更新');
    await loadStats();
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '保存严重度失败'));
    await loadList();
  }
};

const savePriority = async (row: BugListItem, priority: BugPriority) => {
  try {
    const updated = await updateBug(row.id, { priority });
    applyBugUpdate(row, updated);
    ElMessage.success('优先级已更新');
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '保存优先级失败'));
    await loadList();
  }
};

const saveAssignee = async (row: BugListItem, userId: number) => {
  try {
    const updated = await assignBug(row.id, userId, '');
    applyBugUpdate(row, updated);
    ElMessage.success('负责人已更新');
    await loadStats();
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '指派失败'));
    await loadList();
  }
};

const onQuickTransition = async (row: BugListItem, to: BugStatus) => {
  try {
    const updated = await transitionBug(row.id, to, '');
    applyBugUpdate(row, updated);
    ElMessage.success(`已流转到 ${STATUS_LABEL[to]}`);
    await loadStats();
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '流转失败'));
    await loadList();
  }
};

const goDetail = (row: BugListItem) => {
  router.push(`/projects/${projectId}/bugs/${row.id}`);
};

const sourceLabel = (s: string) => ({
  manual: '手工', api_auto: '接口自动化',
  performance: '性能', ui_auto: 'UI 自动化',
} as Record<string, string>)[s] || s;

const formatTime = (t: string) => t ? new Date(t).toLocaleString() : '-';

onMounted(() => {
  loadList();
  loadStats();
  loadMembers();
});
</script>

<style scoped>
.bug-list { padding: 0; }
.header-actions { display: flex; gap: 8px; }

.statistics-cards {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;
  margin-bottom: 20px;
}
.stat-card { text-align: center; border: 1px solid var(--color-border); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); }
.stat-value { font-family: var(--font-heading); font-size: 24px; font-weight: 600; color: var(--color-text); }
.stat-card.success .stat-value { color: var(--color-success); }
.stat-card.warning .stat-value { color: var(--color-warning); }
.stat-card.danger .stat-value { color: var(--color-danger); }
.stat-label { color: var(--color-text-secondary); margin-top: 4px; font-size: 13px; }

.filter-bar {
  display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;
}
.bug-title-link {
  max-width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-primary);
  cursor: pointer;
  font: inherit;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bug-title-link:hover { text-decoration: underline; }
.table-select { width: 100%; }
.editable-tag { cursor: pointer; }
.tag-arrow { margin-left: 4px; vertical-align: -1px; }
.row-actions { display: flex; align-items: center; gap: 8px; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }

.empty-demo-banner {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: var(--color-surface-sunken);
  margin-bottom: 12px; border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
}

.linked-task-chip {
  color: var(--color-text-secondary);
  font-size: 13px;
}
.muted { color: var(--color-text-tertiary); }
</style>
