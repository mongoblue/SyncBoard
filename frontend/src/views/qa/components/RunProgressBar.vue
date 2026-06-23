<template>
  <div class="run-progress">
    <div class="progress-text">
      <span>进度 {{ done }} / {{ total }}</span>
      <span class="pass">✓ {{ passedCount }}</span>
      <span class="fail">✗ {{ failedCount }}</span>
      <span class="err">! {{ errorCount }}</span>
      <span class="time">⏱ {{ durationText }}</span>
    </div>
    <el-progress
      :percentage="percentage"
      :status="progressStatus"
      :stroke-width="16"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  total: number
  passedCount: number
  failedCount: number
  errorCount: number
  durationMs?: number | null
}>()

const done = computed(() => props.passedCount + props.failedCount + props.errorCount)
const percentage = computed(() =>
  props.total > 0 ? Math.round((done.value / props.total) * 100) : 0
)
const progressStatus = computed(() => {
  if (done.value < props.total) return undefined
  if (props.failedCount === 0 && props.errorCount === 0) return 'success'
  if (props.errorCount > 0) return 'exception'
  return 'warning'
})
const durationText = computed(() => {
  if (!props.durationMs) return '--'
  if (props.durationMs < 1000) return `${props.durationMs}ms`
  return `${(props.durationMs / 1000).toFixed(2)}s`
})
</script>

<style scoped>
.run-progress {
  padding: 12px 16px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}
.progress-text {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--color-text);
}
.pass { color: var(--color-success); }
.fail { color: var(--color-danger); }
.err { color: var(--color-warning); }
.time { color: var(--color-text-tertiary); margin-left: auto; }
</style>
