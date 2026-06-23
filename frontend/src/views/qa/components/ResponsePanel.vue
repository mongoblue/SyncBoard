<template>
  <div class="response-panel">
    <div class="response-summary">
      <el-tag :type="statusTagType" effect="dark">Status {{ statusCode }}</el-tag>
      <span class="metric">⏱ {{ duration }}ms</span>
      <span class="metric">📦 {{ bodySize }} bytes</span>
    </div>
    <el-collapse>
      <el-collapse-item title="响应头" name="headers">
        <pre class="headers">{{ JSON.stringify(headers, null, 2) }}</pre>
      </el-collapse-item>
    </el-collapse>
    <div class="body">
      <h4>响应体</h4>
      <pre v-if="parsedJson" class="json"><code v-html="highlightedJson" /></pre>
      <pre v-else class="raw">{{ body }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  statusCode: number
  duration: number
  body: string
  headers: Record<string, string>
}>()

const parsedJson = computed(() => {
  try { return JSON.parse(props.body) } catch { return null }
})

const bodySize = computed(() => new Blob([props.body || '']).size)

const statusTagType = computed(() => {
  const c = props.statusCode
  if (c >= 500) return 'danger'
  if (c >= 400) return 'warning'
  if (c >= 300) return 'info'
  if (c >= 200) return 'success'
  return 'info'
})

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const highlightedJson = computed(() => {
  if (!parsedJson.value) return ''
  const json = JSON.stringify(parsedJson.value, null, 2)
  return escapeHtml(json)
    .replace(/"([^"]+)":/g, '<span class="key">"$1"</span>:')
    .replace(/: "([^"]*)"/g, ': <span class="string">"$1"</span>')
    .replace(/: (-?\d+\.?\d*)/g, ': <span class="number">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="bool">$1</span>')
})
</script>

<style scoped>
.response-panel { padding: 16px; }
.response-summary { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; }
.metric { color: var(--color-text-secondary); font-size: 13px; }
.body h4 {
  margin: 16px 0 8px 0;
  font: 600 14px/1.3 var(--font-heading);
  color: var(--color-text);
}
pre {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  padding: 12px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text);
}
:deep(.key) { color: var(--color-info); }
:deep(.string) { color: var(--color-danger); }
:deep(.number) { color: var(--color-primary); }
:deep(.bool) { color: var(--color-warning); }
.headers { white-space: pre-wrap; }
</style>
