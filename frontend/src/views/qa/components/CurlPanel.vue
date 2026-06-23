<template>
  <div class="curl-panel">
    <div class="curl-header">
      <span class="curl-title">cURL</span>
      <el-button-group>
        <el-button size="small" @click="copy" :icon="DocumentCopy">{{ copied ? '已复制' : '复制' }}</el-button>
        <el-button size="small" @click="download" :icon="Download">下载 .sh</el-button>
      </el-button-group>
    </div>
    <pre class="curl-body"><code>{{ curl }}</code></pre>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DocumentCopy, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{ curl: string }>()
const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(props.curl)
    copied.value = true
    ElMessage.success('已复制到剪贴板')
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    ElMessage.error('复制失败')
  }
}

function download() {
  const blob = new Blob([`#!/bin/bash\n${props.curl}\n`], { type: 'text/x-shellscript' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `request-${Date.now()}.sh`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.curl-panel {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: 16px;
}
.curl-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.curl-title {
  font-family: var(--font-heading);
  color: var(--color-text);
  font-weight: 600;
  font-size: 13px;
}
.curl-body {
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
