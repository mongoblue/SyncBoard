<template>
  <div class="lifecycle-bar">
    <div class="lifecycle-steps">
      <div
        v-for="(step, idx) in steps"
        :key="step.status"
        class="lifecycle-step"
        :class="{
          'is-active': idx === activeStep,
          'is-done': idx < activeStep,
          'is-future': idx > activeStep,
        }"
      >
        <div class="step-dot">
          <el-icon v-if="idx < activeStep" :size="14"><Check /></el-icon>
          <span v-else-if="idx === activeStep" class="step-active-dot" />
          <span v-else class="step-empty-dot" />
        </div>
        <span class="step-label">{{ step.label }}</span>
        <div v-if="idx < steps.length - 1" class="step-connector" :class="{ done: idx < activeStep }" />
      </div>
    </div>

    <!-- rejected -->
    <div v-if="currentStatus === 'rejected'" class="special-state rejected">
      <el-tag color="#909399" effect="dark" size="small">已拒绝</el-tag>
      <span class="special-hint">该缺陷已被拒绝 / 终止处理</span>
    </div>

    <!-- reopened -->
    <div v-if="currentStatus === 'reopened'" class="special-state reopened">
      <el-tag color="#db2777" effect="dark" size="small">重新打开</el-tag>
      <span class="special-hint">缺陷已回到处理流程</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check } from '@element-plus/icons-vue'
import type { BugStatus } from '@/api/bug'

const props = defineProps<{
  currentStatus: BugStatus
}>()

const steps = [
  { status: 'new' as BugStatus, label: '新建' },
  { status: 'confirmed' as BugStatus, label: '已确认' },
  { status: 'assigned' as BugStatus, label: '已指派' },
  { status: 'fixing' as BugStatus, label: '修复中' },
  { status: 'fixed' as BugStatus, label: '已修复' },
  { status: 'verifying' as BugStatus, label: '待验证' },
  { status: 'closed' as BugStatus, label: '已关闭' },
]

const statusToStep: Record<string, number> = {
  new: 0,
  confirmed: 1,
  assigned: 2,
  fixing: 3,
  fixed: 4,
  verifying: 5,
  closed: 6,
  // rejected & reopened handled separately via special UI
  rejected: -1,
  reopened: 1, // show at confirmed position
}

const activeStep = computed(() => statusToStep[props.currentStatus] ?? -1)
</script>

<style scoped>
.lifecycle-bar {
  padding: 16px 0;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--color-border-light);
}
.lifecycle-steps {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.lifecycle-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  position: relative;
  flex: 1;
}
.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid var(--color-border);
  background: var(--color-surface);
  z-index: 1;
  position: relative;
}
.is-done .step-dot {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
  color: var(--color-primary);
}
.is-active .step-dot {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: #fff;
}
.is-future .step-dot {
  border-color: var(--color-border);
  background: var(--color-surface);
}

.step-active-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
}
.step-empty-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-border);
}
.step-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}
.is-done .step-label,
.is-active .step-label {
  color: var(--color-text);
  font-weight: 500;
}

.step-connector {
  position: absolute;
  top: 14px;
  left: calc(50% + 18px);
  right: calc(-50% + 18px);
  height: 2px;
  background: var(--color-border);
  z-index: 0;
}
.step-connector.done {
  background: var(--color-primary);
}

.special-state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
}
.special-state.rejected {
  background: #f5f5f5;
  color: var(--color-text-secondary);
}
.special-state.reopened {
  background: #fdf2f8;
  color: #9d174d;
}
.special-hint {
  font-size: 12px;
}
</style>
