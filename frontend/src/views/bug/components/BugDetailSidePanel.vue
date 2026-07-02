<template>
  <el-card class="side-panel">
    <template #header><strong>属性</strong></template>

    <div class="prop-row">
      <span class="prop-label">报告人</span>
      <span>{{ bug.reporter?.username || '-' }}</span>
    </div>

    <div class="prop-row">
      <span class="prop-label">负责人</span>
      <div class="prop-value-with-action">
        <span>{{ bug.assignee?.username || '未指派' }}</span>
        <el-button link size="small" type="primary" @click="$emit('open-assign')">
          更换负责人
        </el-button>
      </div>
    </div>

    <div class="prop-row">
      <span class="prop-label">修复人</span>
      <span>{{ bug.fixer?.username || '-' }}</span>
    </div>

    <div class="prop-row">
      <span class="prop-label">验证人</span>
      <span>{{ bug.verifier?.username || '-' }}</span>
    </div>

    <el-divider />

    <div class="prop-row">
      <span class="prop-label">严重度</span>
      <el-select
        :model-value="bug.severity"
        size="small"
        style="width: 130px"
        @change="(v: string) => $emit('save-field', 'severity', v)"
      >
        <el-option
          v-for="s in SEVERITY_OPTIONS"
          :key="s.value"
          :label="s.label"
          :value="s.value"
        />
      </el-select>
    </div>

    <div class="prop-row">
      <span class="prop-label">优先级</span>
      <el-select
        :model-value="bug.priority"
        size="small"
        style="width: 130px"
        @change="(v: string) => $emit('save-field', 'priority', v)"
      >
        <el-option
          v-for="p in PRIORITY_OPTIONS"
          :key="p.value"
          :label="p.label"
          :value="p.value"
        />
      </el-select>
    </div>

    <div class="prop-row">
      <span class="prop-label">环境</span>
      <el-input
        :model-value="bug.environment"
        size="small"
        style="width: 150px"
        placeholder="未指定"
        @change="(v: string) => $emit('save-field', 'environment', v)"
      />
    </div>

    <el-divider />

    <div class="prop-row">
      <span class="prop-label">创建时间</span>
      <span class="time-text">{{ formatTime(bug.created_at) }}</span>
    </div>
    <div class="prop-row">
      <span class="prop-label">更新时间</span>
      <span class="time-text">{{ formatTime(bug.updated_at) }}</span>
    </div>
    <div class="prop-row" v-if="bug.closed_at">
      <span class="prop-label">关闭时间</span>
      <span class="time-text">{{ formatTime(bug.closed_at) }}</span>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { BugDetail } from '@/api/bug'

defineProps<{
  bug: BugDetail
}>()

defineEmits<{
  (e: 'save-field', field: string, value: any): void
  (e: 'open-assign'): void
}>()

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

const formatTime = (t: string) => (t ? new Date(t).toLocaleString() : '-')
</script>

<style scoped>
.side-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}
.prop-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
  color: var(--color-text);
}
.prop-label {
  color: var(--color-text-secondary);
}
.prop-value-with-action {
  display: flex;
  align-items: center;
  gap: 8px;
}
.time-text {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
