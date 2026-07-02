<template>
  <div class="bug-stats-cards" v-loading="loading">
    <div
      v-for="card in cards"
      :key="card.view"
      class="stat-card"
      :class="{ active: card.view === activeView }"
      @click="$emit('select-view', card.view)"
    >
      <div class="stat-icon">
        <el-icon :size="18"><component :is="card.icon" /></el-icon>
      </div>
      <div class="stat-body">
        <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
        <div class="stat-label">{{ card.label }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  List, Warning, User, CircleCheck, SortUp, CircleClose,
} from '@element-plus/icons-vue'
import type { BugStats } from '@/api/bug'

const props = defineProps<{
  stats: BugStats | null
  loading: boolean
  activeView?: string
}>()

defineEmits<{
  (e: 'select-view', view: string): void
}>()

const cards = computed(() => {
  const s = props.stats
  return [
    {
      view: 'all',
      label: '全部缺陷',
      value: s?.total ?? '-',
      color: 'var(--color-text)',
      icon: List,
    },
    {
      view: 'my_pending',
      label: '未关闭',
      value: s?.open ?? '-',
      color: 'var(--color-warning)',
      icon: Warning,
    },
    {
      view: 'my_pending',
      label: '待我处理',
      value: s?.my_pending ?? '-',
      color: 'var(--color-primary)',
      icon: User,
    },
    {
      view: 'verifying',
      label: '待验证',
      value: s?.verifying ?? s?.by_status?.verifying ?? '-',
      color: '#eab308',
      icon: CircleCheck,
    },
    {
      view: 'high_risk',
      label: '高风险',
      value: s?.high_risk ?? '-',
      color: 'var(--color-danger)',
      icon: SortUp,
    },
    {
      view: 'closed',
      label: '已关闭',
      value: s?.closed ?? '-',
      color: '#6b8e6b',
      icon: CircleClose,
    },
  ]
})
</script>

<style scoped>
.bug-stats-cards {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.stat-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}
.stat-card.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}
.stat-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-md);
  flex-shrink: 0;
}
.stat-body {
  display: flex;
  flex-direction: column;
}
.stat-value {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}
.stat-label {
  color: var(--color-text-secondary);
  font-size: 12px;
  margin-top: 2px;
}
</style>
