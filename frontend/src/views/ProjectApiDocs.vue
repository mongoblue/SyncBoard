<template>
  <div class="api-docs-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">API 文档</h1>
        <p class="page-subtitle">上传项目的 API 文档，AI 助手可自动解析并生成测试用例</p>
      </div>
      <el-button type="primary" @click="showForm = true">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        上传文档
      </el-button>
    </header>

    <el-row :gutter="16" v-loading="loading">
      <el-col :span="16">
        <el-card v-if="docs.length" class="doc-list-card" shadow="never">
          <div v-for="doc in docs" :key="doc.id" class="doc-item">
            <div class="doc-header">
              <span class="doc-name">{{ doc.name }}</span>
              <el-tag size="small" :type="formatTag(doc.format)">{{ doc.format_label }}</el-tag>
            </div>
            <div class="doc-meta">
              <span>上传者：{{ doc.uploaded_by_name }}</span>
              <span>{{ formatDate(doc.created_at) }}</span>
            </div>
            <div class="doc-actions">
              <el-button size="small" @click="viewDoc(doc)">查看</el-button>
              <el-button size="small" type="danger" plain @click="deleteDoc(doc)">删除</el-button>
            </div>
          </div>
        </el-card>
        <el-empty v-else description="暂无 API 文档，点击右上角上传">
          <template #image><el-icon :size="48" color="var(--color-text-tertiary)"><Document /></el-icon></template>
        </el-empty>
      </el-col>

      <el-col :span="8">
        <el-card class="tips-card" shadow="never">
          <template #header><span>AI 生成提示</span></template>
          <p>上传文档后，在 AI 助手中输入：</p>
          <el-alert type="info" :closable="false" style="margin-top: 8px">
            "根据项目的 API 文档生成测试用例"
          </el-alert>
          <el-divider />
          <p class="tip-text">支持的文档格式：</p>
          <ul>
            <li><strong>Markdown</strong> — 接口描述文档</li>
            <li><strong>OpenAPI JSON</strong> — Swagger 导出的 JSON</li>
            <li><strong>纯文本</strong> — 简单列出接口</li>
          </ul>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="showForm" title="上传 API 文档" width="700px" destroy-on-close>
      <el-form :model="form" label-position="top">
        <div class="form-field">
          <label class="form-label">文档名称</label>
          <el-input v-model="form.name" placeholder="如：用户模块 API 文档" />
        </div>
        <div class="form-field">
          <label class="form-label">文档格式</label>
          <el-select v-model="form.format" style="width: 100%">
            <el-option label="Markdown" value="markdown" />
            <el-option label="OpenAPI JSON" value="openapi_json" />
            <el-option label="纯文本" value="text" />
          </el-select>
        </div>
        <div class="form-field">
          <label class="form-label">文档内容</label>
          <el-input v-model="form.content" type="textarea" :rows="16"
            placeholder="粘贴 API 文档内容..." />
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDoc">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showViewer" title="文档内容" width="700px">
      <pre class="doc-content">{{ viewingDoc?.content }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Document } from '@element-plus/icons-vue';
import service from '@/utils/request';

const route = useRoute();
const projectId = computed(() => route.params.projectId as string);

const loading = ref(false);
const saving = ref(false);
const docs = ref<any[]>([]);
const showForm = ref(false);
const showViewer = ref(false);
const viewingDoc = ref<any>(null);

const form = ref({ name: '', format: 'markdown', content: '' });

const formatTag = (f: string) => f === 'openapi_json' ? 'success' : f === 'markdown' ? '' : 'info';
const formatDate = (d: string) => d ? new Date(d).toLocaleDateString('zh-CN') : '';

const loadDocs = async () => {
  loading.value = true;
  try {
    const res = await service.get(`/projects/${projectId.value}/api-docs/`);
    docs.value = Array.isArray(res) ? res : (res as any).results || [];
    docs.value.forEach(d => {
      d.format_label = d.format === 'openapi_json' ? 'OpenAPI' : d.format === 'markdown' ? 'Markdown' : '文本';
    });
  } catch { docs.value = []; }
  finally { loading.value = false; }
};

const saveDoc = async () => {
  if (!form.value.name.trim() || !form.value.content.trim()) {
    ElMessage.warning('请填写文档名称和内容'); return;
  }
  saving.value = true;
  try {
    await service.post(`/projects/${projectId.value}/api-docs/`, form.value);
    ElMessage.success('文档已保存');
    showForm.value = false;
    form.value = { name: '', format: 'markdown', content: '' };
    loadDocs();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败');
  } finally { saving.value = false; }
};

const viewDoc = (doc: any) => { viewingDoc.value = doc; showViewer.value = true; };

const deleteDoc = async (doc: any) => {
  try {
    await ElMessageBox.confirm(`确定要删除文档 "${doc.name}" 吗？`, '确认删除', { type: 'warning' });
    await service.delete(`/projects/${projectId.value}/api-docs/${doc.id}/`);
    ElMessage.success('已删除');
    loadDocs();
  } catch { /* cancelled */ }
};

onMounted(loadDocs);
</script>

<style scoped>
.api-docs-page { padding: 0; }
.doc-list-card { margin-bottom: 20px; }
.doc-item { padding: 12px 0; border-bottom: 1px solid var(--color-border-light); display: flex; align-items: center; gap: 16px; }
.doc-item:last-child { border-bottom: none; }
.doc-header { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.doc-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-meta { display: flex; gap: 12px; font-size: 12px; color: var(--color-text-tertiary); }
.doc-actions { display: flex; gap: 4px; }
.doc-content { white-space: pre-wrap; font-family: 'Consolas', monospace; font-size: 13px; max-height: 500px; overflow-y: auto; background: var(--color-bg); padding: 16px; border-radius: 8px; }
.tips-card { font-size: 13px; }
.tip-text { color: var(--color-text-secondary); margin: 4px 0; }
</style>
