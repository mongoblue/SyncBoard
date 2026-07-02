<template>
  <el-tag
    :type="priorityConfig[priority]?.type || 'info'"
    :color="priorityConfig[priority]?.color"
    size="small"
    :style="priorityConfig[priority]?.color ? { backgroundColor: priorityConfig[priority]!.color, borderColor: priorityConfig[priority]!.color, color: '#fff' } : {}"
    :effect="priorityConfig[priority]?.color ? 'dark' : 'light'"
  >
    {{ priorityConfig[priority]?.label || priority }}
  </el-tag>
</template>

<script setup lang="ts">
import type { BugPriority } from '@/api/bug'

defineProps<{
  priority: BugPriority
}>()

const priorityConfig: Record<BugPriority, { label: string; type: string; color?: string }> = {
  p0: { label: 'P0', type: '',      color: '#dc2626' },
  p1: { label: 'P1', type: 'warning' },
  p2: { label: 'P2', type: '',      color: '#409eff' },
  p3: { label: 'P3', type: 'info' },
}
</script>
