<template>
  <div class="tests-panel">
    <div class="tests-summary">
      <span class="tests-count">
        通过 {{ passedCount }} / 共 {{ results.length }}
      </span>
      <span v-if="results.length > 0" :class="['tests-rate', allPassed ? 'pass' : 'fail']">
        {{ allPassed ? '✓ 全部通过' : '✗ 存在失败' }}
      </span>
    </div>
    <ul class="tests-list">
      <li v-for="(r, idx) in results" :key="idx" :class="['test-item', r.passed ? 'pass' : 'fail']">
        <div class="test-row" @click="toggle(idx)">
          <span class="test-icon">{{ r.passed ? '✓' : '✗' }}</span>
          <span class="test-desc">{{ describe(r) }}</span>
          <span class="test-toggle">{{ expanded[idx] ? '▾' : '▸' }}</span>
        </div>
        <div v-if="expanded[idx]" class="test-detail">
          <div class="detail-row">
            <span class="label">类型:</span>
            <span>{{ r.assertion_type }}</span>
          </div>
          <div class="detail-row" v-if="r.json_path">
            <span class="label">路径:</span>
            <code>{{ r.json_path }}</code>
          </div>
          <div class="detail-row" v-if="r.header_name">
            <span class="label">Header:</span>
            <code>{{ r.header_name }}</code>
          </div>
          <div class="detail-row">
            <span class="label">期望:</span>
            <code class="value">{{ formatValue(r.expected_value) }}</code>
          </div>
          <div class="detail-row">
            <span class="label">实际:</span>
            <code class="value">{{ formatValue(r.actual_value) }}</code>
          </div>
          <div v-if="!r.passed && r.error_message" class="detail-row error">
            <span class="label">错误:</span>
            <span>{{ r.error_message }}</span>
          </div>
        </div>
      </li>
    </ul>
    <div v-if="extractions && extractions.length > 0" class="extractions">
      <h4>变量提取</h4>
      <ul>
        <li v-for="(ex, i) in extractions" :key="i">
          <code>{{ ex.name }}</code>: <code>{{ ex.value_preview }}</code>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  results: any[]
  extractions?: { name: string; value_preview: string; is_none: boolean }[]
}>()

const expanded = ref<Record<number, boolean>>({})

const passedCount = computed(() => props.results.filter((r) => r.passed).length)
const allPassed = computed(() => passedCount.value === props.results.length)

function toggle(idx: number) {
  expanded.value[idx] = !expanded.value[idx]
}

function describe(r: any): string {
  const op = r.operator || '=='
  const ev = formatValue(r.expected_value)
  if (r.json_path) return `${r.json_path} ${op} ${ev}`
  if (r.header_name) return `${r.header_name} ${op} ${ev}`
  return `${r.assertion_type} ${op} ${ev}`
}

function formatValue(v: any): string {
  if (v === null) return 'null'
  if (v === undefined) return 'undefined'
  if (typeof v === 'string') return v.length > 100 ? v.slice(0, 100) + '...' : `"${v}"`
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>

<style scoped>
.tests-panel { padding: 16px; }
.tests-summary { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #ebeef5; }
.tests-count { font-weight: 600; }
.tests-rate.pass { color: #67c23a; }
.tests-rate.fail { color: #f56c6c; }
.tests-list { list-style: none; padding: 0; margin: 0; }
.test-item { padding: 8px 12px; border-radius: 4px; margin-bottom: 4px; }
.test-item.pass { background: #f0f9eb; }
.test-item.fail { background: #fef0f0; }
.test-row { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.test-icon { font-weight: bold; width: 20px; }
.test-item.pass .test-icon { color: #67c23a; }
.test-item.fail .test-icon { color: #f56c6c; }
.test-desc { flex: 1; font-family: 'Menlo', monospace; font-size: 13px; }
.test-detail { margin-top: 8px; padding: 12px; background: #fff; border-radius: 4px; }
.detail-row { display: flex; gap: 8px; padding: 4px 0; font-size: 13px; }
.detail-row .label { color: #909399; min-width: 60px; }
.detail-row code { font-family: 'Menlo', monospace; }
.detail-row.error { color: #f56c6c; }
.extractions { margin-top: 24px; padding-top: 16px; border-top: 1px solid #ebeef5; }
.extractions h4 { margin: 0 0 8px 0; }
.extractions ul { list-style: none; padding: 0; }
.extractions li { padding: 4px 0; font-size: 13px; }
</style>
