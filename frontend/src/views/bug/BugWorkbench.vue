<template>
  <div class="bug-workbench">
    <!-- Header -->
    <BugWorkbenchHeader
      @create="openCreateDialog"
      @refresh="refresh"
    />

    <!-- Stats Cards -->
    <BugStatsCards
      :stats="stats"
      :loading="statsLoading"
      :active-view="view"
      @select-view="changeView"
    />

    <!-- View Tabs -->
    <BugViewTabs
      :model-value="view"
      @update:model-value="changeView"
    />

    <!-- Filter Bar -->
    <BugFilterBar
      :model-value="filters"
      :project-members="projectMembers"
      @update:model-value="updateFilters"
      @clear="resetFilters"
    />

    <!-- Empty state with demo seed -->
    <div
      v-if="!loading && bugs.length === 0 && isOwner && view === 'all' && !hasActiveFilters"
      class="empty-demo-banner"
    >
      <span>暂无缺陷数据</span>
      <el-button size="small" type="primary" @click="handleSeedDemo">
        导入示例缺陷
      </el-button>
    </div>

    <!-- Empty state text -->
    <div v-else-if="!loading && bugs.length === 0" class="empty-state">
      <el-icon :size="48" color="var(--color-text-tertiary)"><Warning /></el-icon>
      <p>{{ emptyText }}</p>
    </div>

    <!-- Table -->
    <BugTable
      v-else
      :bugs="bugs"
      :loading="loading"
      :project-members="projectMembers"
      @open-detail="goDetail"
      @change-severity="handleUpdateSeverity"
      @change-priority="handleUpdatePriority"
      @open-transition="openTransitionDialog"
      @open-assign="(bug: BugListItem, userId?: number) => openAssignDialog(bug, userId)"
      @delete="(bug: BugListItem) => handleDelete(bug.id)"
    />

    <!-- Pagination -->
    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      class="pagination"
      @current-change="loadBugs"
    />

    <!-- Create Dialog -->
    <BugCreateDialog
      v-model:visible="createDialogVisible"
      :project-members="projectMembers"
      :project-id="projectId"
      @created="onBugCreated"
    />

    <!-- Transition Dialog -->
    <BugTransitionDialog
      v-model:visible="transitionDialogVisible"
      :bug="selectedBug"
      :pre-selected-status="preSelectedStatus"
      @confirmed="onTransitionConfirmed"
    />

    <!-- Assign Dialog -->
    <BugAssignDialog
      v-model:visible="assignDialogVisible"
      :project-members="projectMembers"
      :pre-selected-user-id="preSelectedUserId"
      @confirmed="onAssignConfirmed"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Warning } from '@element-plus/icons-vue'
import { useBugWorkbench } from './composables/useBugWorkbench'
import type { BugListItem } from '@/api/bug'

import BugWorkbenchHeader from './components/BugWorkbenchHeader.vue'
import BugStatsCards from './components/BugStatsCards.vue'
import BugViewTabs from './components/BugViewTabs.vue'
import BugFilterBar from './components/BugFilterBar.vue'
import BugTable from './components/BugTable.vue'
import BugCreateDialog from './components/BugCreateDialog.vue'
import BugTransitionDialog from './components/BugTransitionDialog.vue'
import BugAssignDialog from './components/BugAssignDialog.vue'

const props = defineProps<{
  defaultView?: string
}>()

const route = useRoute()
const router = useRouter()
const projectId = route.params.projectId as string

const {
  view,
  filters,
  page,
  pageSize,
  total,
  bugs,
  stats,
  loading,
  statsLoading,
  projectMembers,
  isOwner,
  emptyText,
  loadBugs,
  refresh,
  reload,
  changeView,
  updateFilters,
  resetFilters,
  handleUpdateSeverity,
  handleUpdatePriority,
  handleAssign,
  handleTransition,
  handleDelete,
  handleSeedDemo,
} = useBugWorkbench({ defaultView: props.defaultView || 'all', projectId })

// ── Dialog state ──
const createDialogVisible = ref(false)
const transitionDialogVisible = ref(false)
const assignDialogVisible = ref(false)
const selectedBug = ref<BugListItem | null>(null)
const assignTargetBugId = ref<number | null>(null)
const preSelectedUserId = ref<number | null>(null)
const preSelectedStatus = ref<string | undefined>(undefined)

const hasActiveFilters = computed(() =>
  filters.keyword ||
  filters.status.length > 0 ||
  filters.severity.length > 0 ||
  filters.priority.length > 0 ||
  filters.source_test_type ||
  filters.assignee
)

// ── Dialog handlers ──
const openCreateDialog = () => {
  createDialogVisible.value = true
}

const onBugCreated = async (bug: any) => {
  createDialogVisible.value = false
  router.push(`/projects/${projectId}/bugs/${bug.id}`)
}

const openTransitionDialog = (bug: BugListItem, toStatus?: string) => {
  selectedBug.value = bug
  preSelectedStatus.value = toStatus
  transitionDialogVisible.value = true
}

const onTransitionConfirmed = async (toStatus: string, comment: string) => {
  if (!selectedBug.value) return
  await handleTransition(selectedBug.value.id, toStatus, comment)
  transitionDialogVisible.value = false
  selectedBug.value = null
  preSelectedStatus.value = undefined
}

const openAssignDialog = (bug: BugListItem, userId?: number) => {
  selectedBug.value = bug
  assignTargetBugId.value = bug.id
  preSelectedUserId.value = userId ?? null
  assignDialogVisible.value = true
}

const onAssignConfirmed = async (userId: number, comment: string) => {
  if (!assignTargetBugId.value) return
  await handleAssign(assignTargetBugId.value, userId, comment)
  assignDialogVisible.value = false
  selectedBug.value = null
  assignTargetBugId.value = null
}

// ── Navigation ──
const goDetail = (bug: BugListItem) => {
  router.push(`/projects/${projectId}/bugs/${bug.id}`)
}
</script>

<style scoped>
.bug-workbench {
  padding: 0;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
  display: flex;
}
.empty-demo-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-surface-sunken);
  margin-bottom: 12px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 0;
  color: var(--color-text-tertiary);
  gap: 12px;
}
.empty-state p {
  margin: 0;
  font-size: 14px;
}
</style>
