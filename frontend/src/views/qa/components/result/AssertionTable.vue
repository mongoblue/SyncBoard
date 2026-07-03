<template>
  <div class="assertion-table">
    <el-empty v-if="!assertions?.length" description="无断言" />
    <div v-else class="assertion-list">
      <div
        v-for="(a, i) in assertions"
        :key="i"
        class="assertion-row"
        :class="{ failed: !a.passed }"
      >
        <div class="assertion-head">
          <el-tag :type="a.passed ? 'success' : 'danger'" size="small">
            {{ a.passed ? '通过' : '失败' }}
          </el-tag>
          <code class="assertion-type">{{ a.assertion_type }}<span v-if="a.json_path"> @ {{ a.json_path }}</span></code>
          <span v-if="a.operator" class="assertion-operator">比较方式: {{ a.operator }}</span>
        </div>
        <div class="assertion-diff">
          <div class="diff-col">
            <div class="diff-label">期望值</div>
            <pre class="diff-value expected">{{ formatValue(a.expected_value) }}</pre>
          </div>
          <div class="diff-col">
            <div class="diff-label">实际值</div>
            <pre class="diff-value actual">{{ formatValue(a.actual_value) }}</pre>
          </div>
        </div>
        <div v-if="!a.passed && a.error_message" class="assertion-error">
          {{ a.error_message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AssertionDetail } from '@/api/autoresult';

defineProps<{ assertions: AssertionDetail[] | null | undefined }>();

const formatValue = (v: any) => {
  if (v === null || v === undefined) return '(空)';
  if (typeof v === 'object') {
    if (v && typeof v === 'object' && 'preview' in v) {
      return String((v as any).preview ?? '(空)');
    }
    return JSON.stringify(v, null, 2);
  }
  return String(v);
};
</script>

<style scoped>
.assertion-list { display: flex; flex-direction: column; gap: 10px; }
.assertion-row {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: 12px;
  background: var(--color-surface);
}
.assertion-row.failed {
  border-color: var(--color-danger);
  background: var(--color-danger-bg);
}
.assertion-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
  flex-wrap: wrap;
}
.assertion-type {
  font-family: var(--font-mono); font-size: 12px;
  color: var(--color-text-secondary);
}
.assertion-operator {
  font-size: 12px; color: var(--color-text-secondary);
}
.assertion-diff { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.diff-col { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.diff-label { font-size: 12px; color: var(--color-text-secondary); }
.diff-value {
  margin: 0; padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono); font-size: 12px;
  white-space: pre-wrap; word-break: break-all;
  max-height: 240px; overflow: auto;
}
.diff-value.expected { background: var(--color-success-bg); color: var(--color-success); }
.diff-value.actual { background: var(--color-danger-bg); color: var(--color-danger); }
.assertion-error {
  color: var(--color-danger); font-size: 12px; margin-top: 6px;
}
</style>
