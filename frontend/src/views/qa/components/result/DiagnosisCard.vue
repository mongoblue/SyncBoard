<template>
  <el-alert
    v-if="diagnosis"
    type="error"
    :closable="false"
    show-icon
    class="diagnosis-card"
  >
    <template #title>
      <div class="diag-title">
        <span class="diag-framework">{{ frameworkLabel }}</span>
        <span class="diag-name">{{ diagnosis.title }}</span>
      </div>
    </template>
    <div class="diag-body">
      <div class="diag-section">
        <div class="diag-section-title">根因</div>
        <div class="diag-section-text">{{ diagnosis.root_cause }}</div>
      </div>
      <div v-if="diagnosis.suggested_fixes?.length" class="diag-section">
        <div class="diag-section-title">建议修复</div>
        <ul class="diag-fixes">
          <li v-for="(fix, i) in diagnosis.suggested_fixes" :key="i">{{ fix }}</li>
        </ul>
      </div>
      <div v-if="diagnosis.message" class="diag-section">
        <div class="diag-section-title">证据片段</div>
        <pre class="diag-message">{{ diagnosis.message }}</pre>
      </div>
    </div>
  </el-alert>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { FrameworkDiagnosis } from '@/api/autoresult';

const props = defineProps<{ diagnosis: FrameworkDiagnosis | null | undefined }>();

const frameworkLabel = computed(() => {
  const f = props.diagnosis?.framework;
  if (!f) return '';
  const map: Record<string, string> = {
    django: 'Django',
    flask: 'Flask',
    spring: 'Spring',
    node: 'Node.js',
    config: '配置',
  };
  return map[f] || f;
});
</script>

<style scoped>
.diagnosis-card { margin-bottom: 12px; }
.diag-title { display: flex; align-items: center; gap: 8px; }
.diag-framework {
  font-size: 11px; font-weight: 700; padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.2); color: #fff;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.diag-name { font-weight: 600; font-size: 14px; }

.diag-body { margin-top: 8px; display: flex; flex-direction: column; gap: 10px; }
.diag-section { display: flex; flex-direction: column; gap: 4px; }
.diag-section-title {
  font-size: 12px; font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px;
}
.diag-section-text { font-size: 13px; line-height: 1.6; color: var(--color-text); }
.diag-fixes { margin: 0; padding-left: 18px; }
.diag-fixes li { font-size: 13px; line-height: 1.7; color: var(--color-text); }
.diag-message {
  margin: 0; padding: 8px 10px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono); font-size: 12px;
  white-space: pre-wrap; word-break: break-all;
  max-height: 200px; overflow: auto;
  color: var(--color-text);
}
</style>
