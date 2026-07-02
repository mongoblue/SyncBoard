<template>
  <div class="bug-filter-bar">
    <el-input
      v-model="keywordLocal"
      placeholder="搜索标题/描述（回车搜索）"
      clearable
      style="width: 200px"
      @keyup.enter="commitKeyword"
      @blur="commitKeywordSilent"
      @clear="clearKeyword"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>

    <el-select
      :model-value="modelValue.status"
      placeholder="状态"
      clearable
      multiple
      collapse-tags
      collapse-tags-tooltip
      style="width: 180px"
      @change="(val: string[]) => update('status', val)"
    >
      <el-option
        v-for="s in STATUS_OPTIONS"
        :key="s.value"
        :label="s.label"
        :value="s.value"
      />
    </el-select>

    <el-select
      :model-value="modelValue.severity"
      placeholder="严重程度"
      clearable
      multiple
      collapse-tags
      style="width: 150px"
      @change="(val: string[]) => update('severity', val)"
    >
      <el-option
        v-for="s in SEVERITY_OPTIONS"
        :key="s.value"
        :label="s.label"
        :value="s.value"
      />
    </el-select>

    <el-select
      :model-value="modelValue.priority"
      placeholder="优先级"
      clearable
      multiple
      collapse-tags
      style="width: 120px"
      @change="(val: string[]) => update('priority', val)"
    >
      <el-option
        v-for="p in PRIORITY_OPTIONS"
        :key="p.value"
        :label="p.label"
        :value="p.value"
      />
    </el-select>

    <el-select
      :model-value="modelValue.source_test_type"
      placeholder="来源"
      clearable
      style="width: 130px"
      @change="(val: string) => update('source_test_type', val)"
    >
      <el-option label="手工" value="manual" />
      <el-option label="接口自动化" value="api_auto" />
      <el-option label="性能测试" value="performance" />
      <el-option label="UI 自动化" value="ui_auto" />
    </el-select>

    <el-select
      :model-value="modelValue.assignee"
      placeholder="负责人"
      clearable
      filterable
      style="width: 150px"
      @change="(val: number | null) => update('assignee', val)"
    >
      <el-option
        v-for="m in projectMembers"
        :key="m.user_id"
        :label="m.username"
        :value="m.user_id"
      />
    </el-select>

    <el-button link type="primary" @click="$emit('clear')">清空筛选</el-button>
  </div>
</template>

<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { ref, watch } from 'vue'
import type { ProjectMemberBrief } from '@/api/bug'

export interface BugFilters {
  keyword: string
  status: string[]
  severity: string[]
  priority: string[]
  source_test_type: string
  assignee: number | null
}

const props = defineProps<{
  modelValue: BugFilters
  projectMembers: ProjectMemberBrief[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: BugFilters): void
  (e: 'search'): void
  (e: 'clear'): void
}>()

// ── Keyword: local state to avoid API call on every keystroke ──
const keywordLocal = ref(props.modelValue.keyword)

// Sync parent → local when filters are reset externally
watch(() => props.modelValue.keyword, (val) => {
  keywordLocal.value = val
})

const commitKeyword = () => {
  const v = keywordLocal.value
  if (v !== props.modelValue.keyword) {
    emit('update:modelValue', { ...props.modelValue, keyword: v })
  }
  // update:modelValue already triggers reload via parent's updateFilters
}

const commitKeywordSilent = () => {
  // On blur: sync keyword to model without triggering a separate search.
  // The reload will happen if another filter is changed afterwards.
  const v = keywordLocal.value
  if (v !== props.modelValue.keyword) {
    emit('update:modelValue', { ...props.modelValue, keyword: v })
  }
}

const clearKeyword = () => {
  keywordLocal.value = ''
  if ('' !== props.modelValue.keyword) {
    emit('update:modelValue', { ...props.modelValue, keyword: '' })
  }
  // update:modelValue already triggers reload
}

// ── Select filters: auto-commit on change ──

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
]

const SEVERITY_OPTIONS = [
  { value: 'blocker', label: '阻塞' },
  { value: 'critical', label: '严重' },
  { value: 'major', label: '一般' },
  { value: 'minor', label: '次要' },
  { value: 'trivial', label: '轻微' },
]

const PRIORITY_OPTIONS = [
  { value: 'p0', label: 'P0' },
  { value: 'p1', label: 'P1' },
  { value: 'p2', label: 'P2' },
  { value: 'p3', label: 'P3' },
]

const update = (key: string, value: any) => {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<style scoped>
.bug-filter-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
