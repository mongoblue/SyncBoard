<template>
  <div v-if="snapshot" class="request-snapshot-panel">
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="请求方法">
        <span class="method-tag" :class="(snapshot.body_mode || '').toLowerCase()">{{ methodDisplay }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="Body 类型">{{ bodyModeLabel }}</el-descriptions-item>
      <el-descriptions-item label="渲染后 URL" :span="2">
        <code class="url-code">{{ snapshot.rendered_url || '-' }}</code>
      </el-descriptions-item>
      <el-descriptions-item v-if="snapshot.url_template && snapshot.url_template !== snapshot.rendered_url" label="URL 模板" :span="2">
        <code class="url-template">{{ snapshot.url_template }}</code>
      </el-descriptions-item>
      <el-descriptions-item label="超时(秒)">{{ snapshot.timeout ?? '-' }}</el-descriptions-item>
      <el-descriptions-item label="允许重定向">{{ snapshot.allow_redirects ? '是' : '否' }}</el-descriptions-item>
      <el-descriptions-item v-if="snapshot.auth" label="认证" :span="2">
        <el-tag size="small" type="info">{{ authTypeLabel }}</el-tag>
        <span class="auth-hint">（已脱敏）</span>
      </el-descriptions-item>
    </el-descriptions>

    <el-collapse v-model="activeNames" class="snap-collapse">
      <el-collapse-item v-if="snapshot.headers && hasContent(snapshot.headers)" name="headers" title="请求头">
        <pre class="code-block"><code v-html="highlightedHeaders" /></pre>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.query_params && snapshot.query_params.length" name="query" title="查询参数">
        <pre class="code-block"><code v-html="highlightedQuery" /></pre>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.cookies && hasContent(snapshot.cookies)" name="cookies" title="Cookies">
        <pre class="code-block"><code v-html="highlightedCookies" /></pre>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.body && snapshot.body.preview" name="body" :title="bodyTitle">
        <div class="body-envelope-meta">
          <el-tag v-if="snapshot.body.truncated" size="small" type="warning">已截断</el-tag>
          <el-tag v-if="snapshot.body.redacted" size="small" type="info">已脱敏</el-tag>
          <span class="meta-text">{{ envelopeSizeText(snapshot.body) }}</span>
        </div>
        <pre class="code-block"><code v-html="highlightedBody" /></pre>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.files && snapshot.files.length" name="files" title="上传文件">
        <el-table :data="snapshot.files" size="small" border>
          <el-table-column prop="field_name" label="字段名" />
          <el-table-column prop="filename" label="文件名" />
          <el-table-column prop="content_type" label="类型" />
          <el-table-column label="大小" width="120">
            <template #default="{ row }">{{ formatBytes(row.size_bytes) }}</template>
          </el-table-column>
          <el-table-column label="截断" width="80">
            <template #default="{ row }">{{ row.truncated ? '是' : '否' }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </div>
  <el-empty v-else description="无请求快照" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import hljs from 'highlight.js';
import type { RequestSnapshot, TextEnvelope } from '@/api/autoresult';

const props = defineProps<{ snapshot: RequestSnapshot | null | undefined }>();

const activeNames = ref<string[]>(['body']);

const methodDisplay = computed(() => {
  // body_mode 字段实际存的是 HTTP 方法（runner 兼容历史命名）
  return (props.snapshot?.body_mode || '').toUpperCase() || '-';
});

const bodyModeLabel = computed(() => {
  // snapshot 没有单独 body_mode 字段时回退到 'none'
  return 'JSON';
});

const authTypeLabel = computed(() => {
  const t = props.snapshot?.auth?.auth_type;
  if (!t) return '自定义';
  const map: Record<string, string> = {
    bearer: 'Bearer Token',
    basic: 'Basic Auth',
    api_key: 'API Key',
    cookie: 'Cookie',
    oauth2: 'OAuth2',
    custom: '自定义',
  };
  return map[t] || t;
});

const bodyTitle = computed(() => {
  const env = props.snapshot?.body;
  if (!env) return '请求体';
  return `请求体 (${env.content_type || 'text/plain'})`;
});

const hasContent = (obj: Record<string, any> | null | undefined) =>
  !!obj && Object.keys(obj).length > 0;

const highlightJson = (data: any) => {
  if (data == null) return '';
  let json: string;
  if (typeof data === 'string') {
    try { json = JSON.stringify(JSON.parse(data), null, 2); } catch { return escapeHtml(data); }
  } else {
    json = JSON.stringify(data, null, 2);
  }
  try {
    return hljs.highlight(json, { language: 'json' }).value;
  } catch {
    return escapeHtml(json);
  }
};

const highlightedHeaders = computed(() => highlightJson(props.snapshot?.headers));
const highlightedQuery = computed(() => highlightJson(props.snapshot?.query_params));
const highlightedCookies = computed(() => highlightJson(props.snapshot?.cookies));
const highlightedBody = computed(() => {
  const preview = props.snapshot?.body?.preview;
  if (!preview) return '';
  // body 可能不是 JSON（如 form/urlencoded/raw），尝试 JSON 高亮失败则按纯文本
  try {
    const parsed = JSON.parse(preview);
    return highlightJson(parsed);
  } catch {
    return escapeHtml(preview);
  }
});

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const envelopeSizeText = (env: TextEnvelope) => {
  const parts: string[] = [];
  parts.push(`预览 ${env.preview_size} 字节`);
  if (env.truncated) parts.push(`原始 ${env.original_size} 字节`);
  if (env.encoding) parts.push(`编码 ${env.encoding}`);
  return parts.join(' · ');
};

const formatBytes = (n: number) => {
  if (n == null) return '-';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
};
</script>

<style scoped>
.request-snapshot-panel { display: flex; flex-direction: column; gap: 12px; }
.method-tag {
  font-weight: 600; font-size: 11px; padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-sunken); color: var(--color-text-secondary);
}
.method-tag.get { background: var(--color-info-bg); color: var(--color-info); }
.method-tag.post { background: var(--color-success-bg); color: var(--color-success); }
.method-tag.put { background: var(--color-warning-bg); color: var(--color-warning); }
.method-tag.patch { background: var(--color-primary-bg); color: var(--color-primary); }
.method-tag.delete { background: var(--color-danger-bg); color: var(--color-danger); }

.url-code, .url-template {
  font-family: var(--font-mono); font-size: 12px;
  word-break: break-all; color: var(--color-text);
}
.url-template { color: var(--color-text-secondary); }

.auth-hint { font-size: 11px; color: var(--color-text-secondary); margin-left: 4px; }

.snap-collapse :deep(.el-collapse-item__header) { font-weight: 600; }

.body-envelope-meta {
  display: flex; gap: 6px; align-items: center; margin-bottom: 6px;
}
.meta-text { font-size: 12px; color: var(--color-text-secondary); }

.code-block {
  margin: 0; padding: 12px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  font-family: var(--font-mono); font-size: 12px;
  max-height: 320px; overflow: auto;
}
.code-block code { white-space: pre-wrap; word-break: break-all; }
</style>
