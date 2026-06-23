<template>
  <div class="tests-panel">
    <div class="tests-summary">
      <span class="tests-count">
        通过 {{ passedCount }} / 共 {{ assertionResults.length }}
      </span>
      <span v-if="assertionResults.length > 0" :class="['tests-rate', allPassed ? 'pass' : 'fail']">
        {{ allPassed ? '✓ 全部通过' : '✗ 存在失败' }}
      </span>
    </div>
    <ul class="tests-list">
      <li v-for="(r, idx) in assertionResults" :key="idx" :class="['test-item', r.passed ? 'pass' : 'fail']">
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
    <div v-if="allExtractions && allExtractions.length > 0" class="extractions">
      <h4>变量提取</h4>
      <ul>
        <li v-for="(ex, i) in allExtractions" :key="i">
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

// 后端在单条 run 时把 {'extractions': [...]} 追加到 assertion_results 末尾,
// 这里过滤出真正的断言项;extractions 通过单独的 prop 传入。
const assertionResults = computed(() =>
  (props.results || []).filter((r) => r && !('extractions' in r) && 'passed' in r)
)
const inlineExtractions = computed(() => {
  const block = (props.results || []).find((r) => r && 'extractions' in r)
  return block?.extractions
})
const allExtractions = computed(() => props.extractions || inlineExtractions.value || [])

const passedCount = computed(() => assertionResults.value.filter((r) => r.passed).length)
const allPassed = computed(() => passedCount.value === assertionResults.value.length)

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
.tests-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border-light);
}
.tests-count {
  font-family: var(--font-heading);
  font-weight: 600;
  color: var(--color-text);
}
.tests-rate.pass { color: var(--color-success); }
.tests-rate.fail { color: var(--color-danger); }
.tests-list { list-style: none; padding: 0; margin: 0; }
.test-item {
  padding: 8px 12px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  margin-bottom: 6px;
  background: var(--color-surface);
}
.test-item.pass { background: var(--color-success-bg); border-color: transparent; }
.test-item.fail { background: var(--color-danger-bg); border-color: transparent; }
.test-row { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.test-icon { font-weight: 600; width: 20px; }
.test-item.pass .test-icon { color: var(--color-success); }
.test-item.fail .test-icon { color: var(--color-danger); }
.test-desc { flex: 1; font-family: var(--font-mono); font-size: 12px; color: var(--color-text); }
.test-detail {
  margin-top: 8px;
  padding: 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
}
.detail-row { display: flex; gap: 8px; padding: 4px 0; font-size: 13px; color: var(--color-text); }
.detail-row .label { color: var(--color-text-secondary); min-width: 60px; }
.detail-row code { font-family: var(--font-mono); font-size: 12px; }
.detail-row.error { color: var(--color-danger); }
.extractions { margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--color-border-light); }
.extractions h4 {
  margin: 0 0 8px 0;
  font: 600 14px/1.3 var(--font-heading);
  color: var(--color-text);
}
.extractions ul { list-style: none; padding: 0; }
.extractions li { padding: 4px 0; font-size: 13px; color: var(--color-text); }
.extractions code { font-family: var(--font-mono); }
</style>
