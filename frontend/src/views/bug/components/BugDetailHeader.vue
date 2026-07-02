<template>
  <div class="detail-header" v-loading="loading">
    <div class="header-left">
      <el-button link @click="goBack" class="back-btn">
        <el-icon><ArrowLeft /></el-icon> 返回列表
      </el-button>

      <div class="title-row">
        <span class="bug-id">#{{ bug.id }}</span>
        <h2 v-if="!editingTitle" class="bug-title" @dblclick="startEdit">
          {{ bug.title }}
        </h2>
        <el-input
          v-else
          ref="titleInputRef"
          v-model="editTitleValue"
          size="large"
          class="title-input"
          @blur="saveTitle"
          @keyup.enter="saveTitle"
          @keyup.escape="cancelEdit"
        />
      </div>

      <div class="meta-row">
        <BugStatusTag :status="bug.status" />
        <BugSeverityTag :severity="bug.severity" />
        <BugPriorityTag :priority="bug.priority" />
        <el-tag size="small" type="info">来源: {{ bug.source_display }}</el-tag>
      </div>
    </div>

    <div class="header-actions">
      <!-- 状态流转 -->
      <el-dropdown
        v-if="bug.allowed_transitions?.length"
        trigger="click"
        @command="(s: string) => $emit('open-transition', s)"
      >
        <el-button type="primary">
          流转状态 <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="s in bug.allowed_transitions"
              :key="s"
              :command="s"
            >
              → {{ STATUS_LABEL[s as BugStatus] }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 指派 -->
      <el-button @click="$emit('open-assign')">
        <el-icon><User /></el-icon> 指派
      </el-button>

      <!-- 刷新 -->
      <el-button @click="$emit('refresh')">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>

      <!-- 删除（弱化） -->
      <el-popconfirm
        title="删除后不可恢复，是否确认删除该缺陷？"
        confirm-button-text="确认删除"
        cancel-button-text="取消"
        confirm-button-type="danger"
        @confirm="$emit('delete')"
      >
        <template #reference>
          <el-button type="danger" plain>
            <el-icon><Delete /></el-icon> 删除
          </el-button>
        </template>
      </el-popconfirm>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowDown, Refresh, User, Delete } from '@element-plus/icons-vue'
import { STATUS_LABEL, type BugDetail, type BugStatus } from '@/api/bug'
import BugStatusTag from './BugStatusTag.vue'
import BugSeverityTag from './BugSeverityTag.vue'
import BugPriorityTag from './BugPriorityTag.vue'

const props = defineProps<{
  bug: BugDetail
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'save-title', title: string): void
  (e: 'open-transition', toStatus?: string): void
  (e: 'open-assign'): void
  (e: 'delete'): void
  (e: 'refresh'): void
}>()

const router = useRouter()

const goBack = () => {
  // Navigate back to bug list for the current project
  const projectId = router.currentRoute.value.params.projectId
  router.push(`/projects/${projectId}/bugs`)
}

// Title editing
const editingTitle = ref(false)
const editTitleValue = ref('')
const titleInputRef = ref<InstanceType<typeof import('element-plus').ElInput> | null>(null)

const startEdit = async () => {
  editTitleValue.value = props.bug.title
  editingTitle.value = true
  await nextTick()
  // Focus the input
  const inputEl = document.querySelector('.title-input input') as HTMLInputElement
  inputEl?.focus()
}

const saveTitle = () => {
  if (!editingTitle.value) return
  editingTitle.value = false
  const newTitle = editTitleValue.value.trim()
  if (!newTitle || newTitle === props.bug.title) return
  emit('save-title', newTitle)
}

const cancelEdit = () => {
  editingTitle.value = false
}
</script>

<style scoped>
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 16px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--color-border-light);
}
.header-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.back-btn {
  align-self: flex-start;
  padding: 0;
  color: var(--color-text-secondary);
}
.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}
.bug-id {
  font-size: 14px;
  color: var(--color-text-tertiary);
  font-weight: 500;
  font-family: var(--font-mono, monospace);
}
.bug-title {
  margin: 0;
  font: 600 20px/1.3 var(--font-heading);
  color: var(--color-text);
  cursor: pointer;
}
.bug-title:hover {
  color: var(--color-primary);
}
.title-input {
  width: 480px;
}
.meta-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
