<template>
  <div v-if="snapshot" class="response-snapshot-panel">
    <div class="response-summary">
      <el-tag :type="statusTagType" effect="dark">状态码 {{ snapshot.status_code || '-' }}</el-tag>
      <span class="metric">耗时 {{ snapshot.elapsed_ms ?? 0 }}ms</span>
      <span class="metric">原始大小 {{ formatBytes(snapshot.body_size_raw) }}</span>
      <span v-if="snapshot.body?.truncated" class="metric warning">已截断</span>
      <span v-if="snapshot.body?.redacted" class="metric info">已脱敏</span>
      <span v-if="snapshot.content_type" class="metric">{{ snapshot.content_type }}</span>
    </div>

    <el-collapse v-model="activeNames" class="snap-collapse">
      <el-collapse-item name="headers" title="响应头">
        <pre class="code-block"><code v-html="highlightedHeaders" /></pre>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.cookies && hasContent(snapshot.cookies)" name="cookies" title="Cookies">
        <pre class="code-block"><code v-html="highlightedCookies" /></pre>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.redirect_chain && snapshot.redirect_chain.length" name="redirects" title="重定向链">
        <pre class="code-block"><code v-html="highlightedRedirects" /></pre>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.final_url" name="final_url" title="最终 URL">
        <code class="url-code">{{ snapshot.final_url }}</code>
      </el-collapse-item>
      <el-collapse-item v-if="snapshot.body && snapshot.body.preview" name="body" title="响应体">
        <div class="body-envelope-meta">
          <span class="meta-text">{{ envelopeSizeText(snapshot.body) }}</span>
        </div>
        <pre class="code-block"><code v-html="highlightedBody" /></pre>
      </el-collapse-item>
    </el-collapse>
  </div>
  <el-empty v-else description="无响应快照" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import hljs from 'highlight.js';
import type { ResponseSnapshot, TextEnvelope } from '@/api/autoresult';

const props = defineProps<{ snapshot: ResponseSnapshot | null | undefined }>();

const activeNames = ref<string[]>(['body']);

const statusTagType = computed(() => {
  const c = props.snapshot?.status_code || 0;
  if (c >= 500) return 'danger';
  if (c >= 400) return 'warning';
  if (c >= 300) return 'info';
  if (c >= 200) return 'success';
  return 'info';
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
const highlightedCookies = computed(() => highlightJson(props.snapshot?.cookies));
const highlightedRedirects = computed(() => highlightJson(props.snapshot?.redirect_chain));
const highlightedBody = computed(() => {
  const preview = props.snapshot?.body?.preview;
  if (!preview) return '';
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
.response-snapshot-panel { display: flex; flex-direction: column; gap: 12px; }
.response-summary {
  display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  padding: 8px 0;
}
.metric { color: var(--color-text-secondary); font-size: 13px; }
.metric.warning { color: var(--color-warning); }
.metric.info { color: var(--color-info); }

.snap-collapse :deep(.el-collapse-item__header) { font-weight: 600; }

.body-envelope-meta { margin-bottom: 6px; }
.meta-text { font-size: 12px; color: var(--color-text-secondary); }

.url-code {
  font-family: var(--font-mono); font-size: 12px;
  word-break: break-all; color: var(--color-text);
  display: block; padding: 8px 10px;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-sm);
}

.code-block {
  margin: 0; padding: 12px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  font-family: var(--font-mono); font-size: 12px;
  max-height: 400px; overflow: auto;
}
.code-block code { white-space: pre-wrap; word-break: break-all; }
</style>
