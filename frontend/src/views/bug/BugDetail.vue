<template>
  <div class="bug-detail" v-loading="loading">
    <div v-if="bug" class="detail-wrapper">
      <!-- Header -->
      <BugDetailHeader
        :bug="bug"
        :loading="loading"
        @save-title="(t) => saveField('title', t)"
        @open-transition="openTransition"
        @open-assign="assignDialogVisible = true"
        @delete="confirmDelete"
        @refresh="loadDetail"
      />

      <!-- Lifecycle Bar -->
      <BugLifecycleBar :current-status="bug.status" />

      <!-- Content Grid -->
      <div class="content-grid">
        <!-- Left: Fields + Activity -->
        <div class="left-pane">
          <BugDetailFields :bug="bug" @save-field="saveField" />
          <BugActivityTimeline
            :comments="bug.comments"
            :transitions="bug.transitions"
            @add-comment="submitComment"
          />
        </div>

        <!-- Right: Side Panel -->
        <div class="right-pane">
          <BugDetailSidePanel
            :bug="bug"
            @save-field="saveField"
            @open-assign="assignDialogVisible = true"
          />
        </div>
      </div>
    </div>

    <!-- Transition Dialog (reused from Phase 1) -->
    <BugTransitionDialog
      v-model:visible="transitionDialogVisible"
      :bug="bug"
      :pre-selected-status="preSelectedStatus"
      @confirmed="confirmTransition"
    />

    <!-- Assign Dialog (reused from Phase 1) -->
    <BugAssignDialog
      v-model:visible="assignDialogVisible"
      :project-members="members"
      @confirmed="confirmAssign"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getBug,
  updateBug,
  deleteBug,
  transitionBug,
  assignBug,
  addBugComment,
  getProjectMembers,
  type BugDetail,
  type BugStatus,
  type ProjectMemberBrief,
} from '@/api/bug'
import { extractErrorMessage } from '@/utils/error'

import BugDetailHeader from './components/BugDetailHeader.vue'
import BugLifecycleBar from './components/BugLifecycleBar.vue'
import BugDetailFields from './components/BugDetailFields.vue'
import BugDetailSidePanel from './components/BugDetailSidePanel.vue'
import BugActivityTimeline from './components/BugActivityTimeline.vue'
import BugTransitionDialog from './components/BugTransitionDialog.vue'
import BugAssignDialog from './components/BugAssignDialog.vue'

const route = useRoute()
const router = useRouter()
const bugId = Number(route.params.id)
const projectId = route.params.projectId as string

// ── State ──
const loading = ref(false)
const bug = ref<BugDetail | null>(null)
const members = ref<ProjectMemberBrief[]>([])

// ── Data Loading ──
const loadDetail = async () => {
  loading.value = true
  try {
    bug.value = await getBug(bugId)
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '加载缺陷详情失败'))
  } finally {
    loading.value = false
  }
}

const loadMembers = async () => {
  try {
    members.value = await getProjectMembers(projectId)
  } catch {
    // Non-critical
  }
}

// ── Field Save (updateBug) ──
const saveField = async (field: string, value: any) => {
  if (!bug.value) return
  try {
    await updateBug(bugId, { [field]: value })
    ElMessage.success('已保存')
    // Refresh to get updated display values
    await loadDetail()
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
    // Rollback: reload detail to restore old value
    await loadDetail()
  }
}

// ── Transition (transitionBug only) ──
const transitionDialogVisible = ref(false)
const preSelectedStatus = ref<string | undefined>(undefined)

const openTransition = (toStatus?: string) => {
  preSelectedStatus.value = toStatus
  transitionDialogVisible.value = true
}

const confirmTransition = async (toStatus: string, comment: string) => {
  try {
    bug.value = await transitionBug(bugId, toStatus as BugStatus, comment)
    ElMessage.success('状态已更新')
    transitionDialogVisible.value = false
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '流转失败'))
    await loadDetail()
  }
}

// ── Assign (assignBug only) ──
const assignDialogVisible = ref(false)

const confirmAssign = async (userId: number, comment: string) => {
  try {
    bug.value = await assignBug(bugId, userId, comment)
    ElMessage.success('已指派')
    assignDialogVisible.value = false
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '指派失败'))
    await loadDetail()
  }
}

// ── Comment (addBugComment) ──
const submitComment = async (content: string) => {
  try {
    await addBugComment(bugId, content)
    ElMessage.success('评论已发表')
    await loadDetail()
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '发表失败'))
  }
}

// ── Delete ──
const confirmDelete = async () => {
  try {
    await deleteBug(bugId)
    ElMessage.success('已删除')
    router.push(`/projects/${projectId}/bugs`)
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '删除失败'))
  }
}

// ── Init ──
onMounted(() => {
  loadDetail()
  loadMembers()
})
</script>

<style scoped>
.bug-detail {
  padding: 0;
}
.detail-wrapper {
  max-width: 1100px;
}
.content-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  margin-top: 8px;
}
.left-pane,
.right-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
@media (max-width: 1000px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
