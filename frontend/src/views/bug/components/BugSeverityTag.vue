<template>
  <el-tag
    :type="severityConfig[severity]?.type || 'info'"
    :color="severityConfig[severity]?.color"
    size="small"
    :style="severityConfig[severity]?.color ? { backgroundColor: severityConfig[severity]!.color, borderColor: severityConfig[severity]!.color, color: '#fff' } : {}"
    :effect="severityConfig[severity]?.color ? 'dark' : 'light'"
  >
    {{ severityConfig[severity]?.label || severity }}
  </el-tag>
</template>

<script setup lang="ts">
import type { BugSeverity } from '@/api/bug'

defineProps<{
  severity: BugSeverity
}>()

const severityConfig: Record<BugSeverity, { label: string; type: string; color?: string }> = {
  blocker:  { label: '阻塞', type: '',  color: '#b91c1c' },
  critical: { label: '严重', type: 'danger' },
  major:    { label: '一般', type: 'warning' },
  minor:    { label: '次要', type: '',  color: '#409eff' },
  trivial:  { label: '轻微', type: 'info' },
}
</script>
