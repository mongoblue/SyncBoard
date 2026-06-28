<template>
  <div class="my-bugs">
    <header class="page-header">
      <div>
        <h1 class="page-title">我的 Bug</h1>
        <p class="page-subtitle">查看与我相关的所有 Bug</p>
      </div>
    </header>

    <el-tabs v-model="activeRole" @tab-change="loadList">
      <el-tab-pane label="指派给我" name="assignee">
        <div class="tab-hint">需要我处理（被指派的）Bug</div>
      </el-tab-pane>
      <el-tab-pane label="我报告的" name="reporter">
        <div class="tab-hint">我作为报告人创建或提交的 Bug</div>
      </el-tab-pane>
      <el-tab-pane label="我修复的" name="fixer">
        <div class="tab-hint">由我标记为已修复的 Bug</div>
      </el-tab-pane>
      <el-tab-pane label="我验证的" name="verifier">
        <div class="tab-hint">由我验证关闭的 Bug</div>
      </el-tab-pane>
    </el-tabs>

    <el-table :data="bugs" v-loading="loading" stripe>
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column prop="project_name" label="项目" width="160" show-overflow-tooltip />
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
      <el-table-column label="报告人" width="120">
        <template #default="{ row }">{{ row.reporter?.username || '-' }}</template>
      </el-table-column>
      <el-table-column label="指派给" width="150">
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
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { ArrowDown, Delete } from '@element-plus/icons-vue';
import {
  listMyBugs, deleteBug, transitionBug, updateBug, assignBug, getProjectMembers,
  STATUS_TAG_TYPE, STATUS_LABEL,
  type BugListItem, type BugStatus, type BugSeverity, type BugPriority, type ProjectMemberBrief,
} from '@/api/bug';
import { extractErrorMessage } from '@/utils/error';

const route = useRoute();
const router = useRouter();
const projectId = route.params.projectId as string;

type Role = 'assignee' | 'reporter' | 'fixer' | 'verifier';
const activeRole = ref<Role>('assignee');

const loading = ref(false);
const bugs = ref<BugListItem[]>([]);
const projectMembers = ref<ProjectMemberBrief[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;

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

const loadList = async () => {
  loading.value = true;
  try {
    const res = await listMyBugs(activeRole.value, {
      project: projectId,
      page: page.value,
      page_size: pageSize,
    });
    bugs.value = res.results;
    total.value = res.count;
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '加载失败'));
  } finally {
    loading.value = false;
  }
};

const loadMembers = async () => {
  try {
    projectMembers.value = await getProjectMembers(projectId);
  } catch {
    // 指派人快捷编辑不可用不影响主列表
  }
};

const goDetail = (row: BugListItem) => {
  router.push(`/projects/${projectId}/bugs/${row.id}`);
};

const confirmDelete = async (row: BugListItem) => {
  try {
    await deleteBug(row.id);
    ElMessage.success('已删除');
    await loadList();
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
    await assignBug(row.id, userId, '');
    ElMessage.success('负责人已更新');
    await loadList();
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
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '流转失败'));
    await loadList();
  }
};

const formatTime = (t: string) => t ? new Date(t).toLocaleString() : '-';

onMounted(() => {
  loadList();
  loadMembers();
});
</script>

<style scoped>
.my-bugs { padding: 0; }
.tab-hint {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-bottom: 12px;
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
.linked-task-chip {
  color: var(--color-text-secondary);
  font-size: 13px;
}
.muted { color: var(--color-text-tertiary); }
</style>
