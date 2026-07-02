<template>
  <el-tag
    :type="statusConfig[status]?.type || 'info'"
    :color="statusConfig[status]?.color"
    size="small"
    :style="statusConfig[status]?.color ? { backgroundColor: statusConfig[status]!.color, borderColor: statusConfig[status]!.color, color: '#fff' } : {}"
    :effect="statusConfig[status]?.color ? 'dark' : 'light'"
  >
    {{ statusConfig[status]?.label || status }}
  </el-tag>
</template>

<script setup lang="ts">
import type { BugStatus } from '@/api/bug'

defineProps<{
  status: BugStatus
}>()

const statusConfig: Record<BugStatus, { label: string; type: string; color?: string }> = {
  new:        { label: '新建',     type: '',      color: '#409eff' },
  confirmed:  { label: '已确认',   type: '',      color: '#a855f7' },
  assigned:   { label: '已指派',   type: '',      color: '#06b6d4' },
  fixing:     { label: '修复中',   type: 'warning' },
  fixed:      { label: '已修复',   type: '',      color: '#22c55e' },
  verifying:  { label: '待验证',   type: '',      color: '#eab308' },
  closed:     { label: '已关闭',   type: '',      color: '#6b8e6b' },
  reopened:   { label: '重新打开', type: '',      color: '#db2777' },
  rejected:   { label: '已拒绝',   type: 'info' },
}
</script>
