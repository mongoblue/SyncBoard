<template>
  <el-collapse v-model="activeNames" class="collapsible-raw-json">
    <el-collapse-item :name="name">
      <template #title>
        <div class="title-row">
          <el-icon><Document /></el-icon>
          <span>{{ label }}</span>
          <el-tag v-if="!defaultOpen" size="small" type="info">默认收起</el-tag>
          <el-tag v-if="truncated" size="small" type="warning">数据较大</el-tag>
        </div>
      </template>
      <div class="json-meta">
        <span class="meta-text">字段数 {{ fieldCount }}</span>
        <el-button size="small" text @click.stop="copy">
          <el-icon><CopyDocument /></el-icon>
          复制
        </el-button>
      </div>
      <pre class="code-block"><code v-html="highlighted" /></pre>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { Document, CopyDocument } from '@element-plus/icons-vue';
import hljs from 'highlight.js';

const props = withDefaults(
  defineProps<{
    data: any;
    label?: string;
    defaultOpen?: boolean;
    name?: string;
  }>(),
  {
    label: '原始 JSON（高级）',
    defaultOpen: false,
    name: 'raw',
  },
);

const activeNames = ref<string[]>(props.defaultOpen ? [props.name] : []);

watch(
  () => props.defaultOpen,
  (open) => {
    activeNames.value = open ? [props.name] : [];
  },
);

const jsonString = computed(() => {
  if (props.data == null) return '';
  if (typeof props.data === 'string') {
    try { return JSON.stringify(JSON.parse(props.data), null, 2); } catch { return props.data; }
  }
  return JSON.stringify(props.data, null, 2);
});

const highlighted = computed(() => {
  if (!jsonString.value) return '';
  try {
    return hljs.highlight(jsonString.value, { language: 'json' }).value;
  } catch {
    return escapeHtml(jsonString.value);
  }
});

const truncated = computed(() => jsonString.value.length > 50 * 1024);

const fieldCount = computed(() => {
  const d = props.data;
  if (d == null) return 0;
  if (typeof d === 'string') {
    try {
      const p = JSON.parse(d);
      return Array.isArray(p) ? p.length : typeof p === 'object' ? Object.keys(p).length : 1;
    } catch { return 1; }
  }
  if (Array.isArray(d)) return d.length;
  if (typeof d === 'object') return Object.keys(d).length;
  return 1;
});

const copy = async () => {
  try {
    await navigator.clipboard.writeText(jsonString.value);
    ElMessage.success('已复制到剪贴板');
  } catch {
    ElMessage.error('复制失败');
  }
};

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
</script>

<style scoped>
.collapsible-raw-json :deep(.el-collapse-item__header) { font-weight: 600; }
.title-row {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px;
}
.json-meta {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px;
}
.meta-text { font-size: 12px; color: var(--color-text-secondary); }

.code-block {
  margin: 0; padding: 12px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  font-family: var(--font-mono); font-size: 12px;
  max-height: 480px; overflow: auto;
  white-space: pre-wrap; word-break: break-all;
}
.code-block code { white-space: pre-wrap; word-break: break-all; }
</style>
