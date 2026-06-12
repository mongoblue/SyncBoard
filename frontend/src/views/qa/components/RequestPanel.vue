<template>
  <div class="request-panel">
    <div class="row">
      <span class="label">Method</span>
      <el-tag :type="methodTagType" effect="dark">{{ method }}</el-tag>
    </div>
    <div class="row">
      <span class="label">URL</span>
      <code class="url">{{ url }}</code>
    </div>
    <div v-if="headers && Object.keys(headers).length" class="row">
      <span class="label">Headers</span>
      <pre class="headers">{{ JSON.stringify(headers, null, 2) }}</pre>
    </div>
    <div v-if="body !== null && body !== undefined" class="row">
      <span class="label">Body</span>
      <pre class="body"><code>{{ formatBody(body) }}</code></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  method: string
  url: string
  headers?: Record<string, string>
  body?: any
}>()

const methodTagType = computed(() => {
  const m = props.method?.toUpperCase()
  if (m === 'GET') return 'success'
  if (m === 'POST') return 'warning'
  if (m === 'DELETE') return 'danger'
  return 'info'
})

function formatBody(b: any): string {
  if (typeof b === 'string') return b
  return JSON.stringify(b, null, 2)
}
</script>

<style scoped>
.request-panel { padding: 16px; }
.row { margin-bottom: 16px; }
.label { display: block; color: #909399; font-size: 12px; margin-bottom: 4px; text-transform: uppercase; }
.url { background: #fafafa; padding: 6px 10px; border-radius: 4px; font-family: 'Menlo', monospace; font-size: 13px; display: inline-block; }
pre { background: #fafafa; padding: 12px; border-radius: 4px; font-size: 12px; max-height: 300px; overflow: auto; }
</style>
