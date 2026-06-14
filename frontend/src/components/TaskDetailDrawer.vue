<template>
  <el-drawer
    v-model="drawerVisible"
    size="440px"
    @close="$emit('close')"
    :with-header="false"
    class="task-drawer"
  >
    <div v-if="task" class="task-detail">
      <!-- 自定义头部 -->
      <div class="detail-header">
        <div class="header-top">
          <span class="column-badge">
            <span class="badge-dot"></span>
            {{ columnTitle }}
          </span>
          <div class="header-actions">
            <el-button v-if="!isEditing" type="primary" size="small" @click="startEdit">
              <el-icon><Edit /></el-icon>
              编辑
            </el-button>
            <template v-else>
              <el-button size="small" @click="cancelEdit">取消</el-button>
              <el-button type="primary" size="small" :loading="saving" @click="saveEdit">
                保存
              </el-button>
            </template>
          </div>
        </div>
        <h2 class="task-title">{{ task.title }}</h2>
      </div>

      <!-- 元数据区域 —— 查看模式 -->
      <div v-if="!isEditing" class="meta-panel">
        <div class="meta-row">
          <div class="meta-item">
            <span class="meta-label">负责人</span>
            <span class="meta-value" :class="{ unassigned: !task.assignee_details }">
              <el-icon :size="14"><User /></el-icon>
              {{ task.assignee_details?.username || '未分配' }}
            </span>
          </div>
          <div class="meta-item" v-if="task.created_at">
            <span class="meta-label">创建时间</span>
            <span class="meta-value meta-date">
              <el-icon :size="14"><Calendar /></el-icon>
              {{ formatDate(task.created_at) }}
            </span>
          </div>
        </div>
        <div class="meta-row" v-if="task.tags_details?.length">
          <div class="meta-item full-width">
            <span class="meta-label">标签</span>
            <div class="tags-row">
              <span
                v-for="tag in task.tags_details"
                :key="tag.id"
                class="tag-chip"
                :style="{ background: tag.color + '18', color: tag.color, borderColor: tag.color + '40' }"
              >
                {{ tag.name }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 编辑模式 -->
      <el-form v-else :model="editForm" label-position="top" size="default" class="edit-form">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="editForm.assignee" placeholder="选择负责人" clearable style="width:100%">
            <el-option v-for="u in boardStore.Users" :key="u.id" :label="u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="editForm.tags" multiple placeholder="选择标签" collapse-tags style="width:100%">
            <el-option
              v-for="tag in boardStore.currentProject?.available_tags || []"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <span :style="{ color: tag.color }">{{ tag.name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="editForm.content" type="textarea" :rows="5" />
        </el-form-item>
      </el-form>

      <!-- 任务描述 -->
      <div v-if="!isEditing && task.content" class="content-body">
        <p>{{ task.content }}</p>
      </div>
      <div v-else-if="!isEditing && !task.content" class="content-body empty">
        暂无描述
      </div>

      <!-- 关联测试 -->
      <div class="section">
        <div class="section-header">
          <h4>关联测试</h4>
          <span class="section-count">{{ linkedTests.length }}</span>
          <el-button type="primary" link size="small" @click="openLinkDialog">
            <el-icon><Plus /></el-icon>
            关联
          </el-button>
        </div>
        <div v-if="linkedTests.length" class="linked-list">
          <div v-for="t in linkedTests" :key="`${t.test_type}-${t.id}`" class="linked-row">
            <span class="linked-type" :class="'type-' + t.test_type">{{ labelForType(t.test_type) }}</span>
            <el-link :underline="false" @click="navigateToTestCase(t)" class="linked-name">{{ t.name }}</el-link>
            <el-button link type="danger" size="small" @click="handleUnlinkTest(t)" :loading="unlinkingKey === `${t.test_type}-${t.id}`">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        <div v-else class="empty-hint">暂无关联测试用例</div>
      </div>

      <!-- 附件 -->
      <div class="section">
        <div class="section-header">
          <h4>附件</h4>
          <span class="section-count">{{ attachments.length }}</span>
        </div>
        <div v-if="attachments.length" class="attachment-list">
          <div v-for="a in attachments" :key="a.id" class="attachment-row">
            <el-icon :size="16" color="var(--color-text-tertiary)"><Document /></el-icon>
            <a :href="a.file" target="_blank" class="att-name">{{ a.filename }}</a>
            <span class="att-size">{{ formatSize(a.file_size) }}</span>
            <el-button link type="danger" size="small" @click="deleteAttachment(a.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        <div v-else class="empty-hint">暂无附件</div>
        <el-upload
          :action="`/api/tasks/${task?.id}/attachments/`"
          :headers="uploadHeaders"
          :on-success="onUploadSuccess"
          :show-file-list="false"
          accept="*"
          style="margin-top:10px"
        >
          <el-button size="small" text>
            <el-icon><Upload /></el-icon>
            上传附件
          </el-button>
        </el-upload>
      </div>

      <!-- 变更记录 -->
      <div class="section">
        <div class="section-header">
          <h4>变更记录</h4>
          <span class="section-count">{{ activities.length }}</span>
        </div>
        <div v-if="activities.length" class="activity-list">
          <div v-for="a in activities" :key="a.id" class="activity-item">
            <span class="activity-user">{{ a.user_detail?.username || '系统' }}</span>
            <span class="activity-action">{{ actionLabel(a.action) }}</span>
            <span v-if="a.field_name" class="activity-field">{{ a.field_name }}</span>
            <span v-if="a.old_value && a.new_value" class="activity-change">{{ a.old_value }} → {{ a.new_value }}</span>
            <span class="activity-time">{{ formatTime(a.created_at) }}</span>
          </div>
        </div>
        <div v-else class="empty-hint">暂无变更记录</div>
      </div>

      <!-- 评论区 -->
      <div class="section">
        <div class="section-header">
          <h4>评论</h4>
          <span class="section-count">{{ comments.length }}</span>
        </div>
        <div v-if="comments.length" class="comment-list">
          <div v-for="c in comments" :key="c.id" class="comment-item">
            <div class="comment-header">
              <strong>{{ c.author_detail?.username }}</strong>
              <span class="comment-time">{{ formatTime(c.created_at) }}</span>
            </div>
            <div class="comment-content">{{ c.content }}</div>
            <div v-if="c.replies?.length" class="comment-replies">
              <div v-for="r in c.replies" :key="r.id" class="reply-item">
                <strong>{{ r.author_detail?.username }}</strong>
                <span>{{ r.content }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty-hint">暂无评论</div>
        <div class="comment-input">
          <el-input
            v-model="commentText"
            type="textarea"
            :rows="2"
            placeholder="添加评论..."
            @keydown.ctrl.enter="addComment"
          />
          <el-button type="primary" size="small" @click="addComment" :loading="commentLoading">发送</el-button>
        </div>
      </div>
    </div>

    <!-- 关联测试对话框 -->
    <el-dialog v-model="linkDialogVisible" title="关联测试用例" width="800px" destroy-on-close>
      <el-tabs v-model="linkType" @tab-change="loadAvailableTests">
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="API 测试" name="api" />
        <el-tab-pane label="UI 测试" name="ui" />
      </el-tabs>
      <el-input
        v-model="linkSearch"
        placeholder="搜索测试用例名称..."
        clearable
        size="small"
        style="margin-bottom: 12px"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-table :data="filteredAvailableTests" v-loading="linkLoading" max-height="400px" size="small">
        <el-table-column label="类型" width="70">
          <template #default="{ row }">
            <span class="linked-type" :class="'type-' + row.test_type" style="font-size:11px">{{ labelForType(row.test_type) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="名称" prop="name" min-width="200" show-overflow-tooltip />
        <el-table-column label="URL" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.url || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <template v-if="isTestLinked(row)">
              <el-button size="small" type="danger" plain @click="toggleLink(row, 'unlink')" :loading="linkPendingKey === `${row.test_type}-${row.id}`">
                取消关联
              </el-button>
            </template>
            <template v-else>
              <el-button size="small" type="primary" @click="toggleLink(row, 'link')" :loading="linkPendingKey === `${row.test_type}-${row.id}`">
                关联
              </el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!linkLoading && filteredAvailableTests.length === 0" description="暂无匹配的测试用例" :image-size="60" />
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useRouter } from 'vue-router';
import service from '@/utils/request';
import { useBoardStore } from '@/stores/board';
import { ElMessage } from 'element-plus';
import { Upload, Document, Edit, Plus, Delete, Search, User, Calendar } from '@element-plus/icons-vue';

const props = defineProps<{ task: any; visible: boolean }>();
const emit = defineEmits(['close', 'updated']);
const boardStore = useBoardStore();
const router = useRouter();

const drawerVisible = ref(props.visible);
watch(() => props.visible, (v) => { drawerVisible.value = v; });
watch(drawerVisible, (v) => { if (!v) emit('close'); });

const comments = ref<any[]>([]);
const activities = ref<any[]>([]);
const linkedTests = ref<any[]>([]);
const attachments = ref<any[]>([]);
const uploadHeaders = ref<Record<string, string>>({});

const formatSize = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
};

const formatDate = (ts: string) => {
  if (!ts) return '';
  return new Date(ts).toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' });
};

const commentText = ref('');
const commentLoading = ref(false);
const isEditing = ref(false);
const saving = ref(false);
const editForm = ref({ title: '', assignee: null as number | null, tags: [] as number[], content: '' });

const startEdit = () => {
  editForm.value = {
    title: props.task?.title || '',
    assignee: props.task?.assignee || null,
    tags: props.task?.tags || [],
    content: props.task?.content || '',
  };
  isEditing.value = true;
};

const cancelEdit = () => {
  isEditing.value = false;
};

const saveEdit = async () => {
  if (!props.task?.id) return;
  saving.value = true;
  try {
    await boardStore.updateTask(props.task.id, editForm.value);
    ElMessage.success('任务已更新');
    isEditing.value = false;
    emit('updated');
  } catch {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
};

const columnTitle = computed(() => {
  return props.task?.column_title || props.task?.column?.title || '未知';
});

const labelForType = (t: string) => t === 'api' ? 'API' : t === 'ui' ? 'UI' : '性能';

// ---------- link test ----------
const linkDialogVisible = ref(false);
const linkType = ref('all');
const linkSearch = ref('');
const linkLoading = ref(false);
const linkPendingKey = ref<string | null>(null);
const unlinkingKey = ref<string | null>(null);
const allTestCases = ref<any[]>([]);
const linkedTestIds = computed(() => new Set(linkedTests.value.map((t: any) => `${t.test_type}-${t.id}`)));

const TEST_LIST_URLS: Record<string, string> = {
  api: '/qa/api-cases/',
  ui: '/qa/ui-cases/',
};

const loadAvailableTests = async () => {
  linkLoading.value = true;
  const projectId = boardStore.currentProjectId;
  const types = linkType.value === 'all' ? ['api', 'ui'] : [linkType.value];
  const results: any[] = [];
  try {
    for (const t of types) {
      const res = await service.get(TEST_LIST_URLS[t]!, { params: { project: projectId } });
      const items = (res.results || res).map((item: any) => ({ ...item, test_type: t }));
      results.push(...items);
    }
    allTestCases.value = results;
  } catch {
    ElMessage.error('加载测试用例失败');
  } finally {
    linkLoading.value = false;
  }
};

const filteredAvailableTests = computed(() => {
  let list = allTestCases.value;
  if (linkSearch.value) {
    const kw = linkSearch.value.toLowerCase();
    list = list.filter((t: any) => (t.name || '').toLowerCase().includes(kw));
  }
  return list;
});

const isTestLinked = (test: any) => linkedTestIds.value.has(`${test.test_type}-${test.id}`);

const openLinkDialog = () => {
  linkDialogVisible.value = true;
  linkType.value = 'all';
  linkSearch.value = '';
  loadAvailableTests();
};

const toggleLink = async (test: any, action: 'link' | 'unlink') => {
  const key = `${test.test_type}-${test.id}`;
  linkPendingKey.value = key;
  try {
    await service.post(`/qa/${action}-task/`, { test_type: test.test_type, case_id: test.id, task_id: props.task?.id });
    ElMessage.success(action === 'link' ? '关联成功' : '取消关联成功');
    await reloadLinkedTests();
  } catch (e: any) {
    ElMessage.error(e?.detail || '操作失败');
  } finally {
    linkPendingKey.value = null;
  }
};

const handleUnlinkTest = async (test: any) => {
  unlinkingKey.value = `${test.test_type}-${test.id}`;
  try {
    await service.post('/qa/unlink-task/', { test_type: test.test_type, case_id: test.id, task_id: props.task?.id });
    ElMessage.success('取消关联成功');
    await reloadLinkedTests();
  } catch (e: any) {
    ElMessage.error(e?.detail || '取消关联失败');
  } finally {
    unlinkingKey.value = null;
  }
};

const reloadLinkedTests = async () => {
  try {
    const res = await service.get(`/tasks/${props.task?.id}/linked-tests/`);
    linkedTests.value = (res as any).linked_tests || [];
  } catch { /* silent */ }
};

const navigateToTestCase = (test: any) => {
  const projectId = boardStore.currentProjectId;
  if (test.test_type === 'api') {
    router.push({ name: 'ApiCaseDetail', params: { id: test.id, projectId } });
  } else if (test.test_type === 'ui') {
    router.push({ name: 'UiCaseDetail', params: { id: test.id, projectId } });
  }
};

const actionLabel = (a: string) => {
  const map: Record<string, string> = { created: '创建了', updated: '更新了', deleted: '删除了', moved: '移动了', assigned: '分配了', commented: '评论了' };
  return map[a] || a;
};

const formatTime = (ts: string) => {
  if (!ts) return '';
  return new Date(ts).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const getCsrfToken = (): string => {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match?.[1] ?? '';
};

const fetchAll = async (taskId: string) => {
  const [cRes, aRes, tRes, attRes] = await Promise.allSettled([
    service.get(`/tasks/${taskId}/comments/`),
    service.get(`/tasks/${taskId}/activities/`),
    service.get(`/tasks/${taskId}/linked-tests/`),
    service.get(`/tasks/${taskId}/attachments/`),
  ]);
  if (cRes.status === 'fulfilled') {
    const data = cRes.value as any;
    comments.value = Array.isArray(data) ? data : (data?.results || []);
  } else { comments.value = []; }
  if (aRes.status === 'fulfilled') {
    const data = aRes.value as any;
    activities.value = Array.isArray(data) ? data : (data?.results || []);
  } else { activities.value = []; }
  if (tRes.status === 'fulfilled') {
    linkedTests.value = (tRes.value as any)?.linked_tests || [];
  } else { linkedTests.value = []; }
  if (attRes.status === 'fulfilled') {
    const data = attRes.value as any;
    attachments.value = Array.isArray(data) ? data : (data?.results || []);
  } else { attachments.value = []; }
  uploadHeaders.value = { 'X-CSRFToken': getCsrfToken() };
};

const onUploadSuccess = () => {
  ElMessage.success('上传成功');
  if (props.task?.id) fetchAll(props.task.id);
};

const deleteAttachment = async (aid: number) => {
  try {
    await service.delete(`/tasks/${props.task?.id}/attachments/${aid}/`);
    ElMessage.success('已删除');
    fetchAll(props.task?.id);
  } catch { ElMessage.error('删除失败'); }
};

const addComment = async () => {
  const text = commentText.value.trim();
  if (!text || !props.task) return;
  commentLoading.value = true;
  try {
    await service.post(`/tasks/${props.task.id}/comments/`, { content: text });
    commentText.value = '';
    ElMessage.success('评论已发送');
    fetchAll(props.task.id);
  } catch (e: any) {
    const respData = e?.response?.data;
    let msg = '评论失败';
    if (respData?.detail) msg = respData.detail;
    else if (respData?.content) msg = Array.isArray(respData.content) ? respData.content[0] : respData.content;
    else if (typeof respData === 'object') {
      const firstKey = Object.keys(respData)[0];
      if (firstKey) msg = Array.isArray(respData[firstKey]) ? respData[firstKey][0] : respData[firstKey];
    }
    ElMessage.error(msg);
  } finally {
    commentLoading.value = false;
  }
};

watch(() => props.visible, (v) => {
  if (v && props.task?.id) {
    fetchAll(props.task.id);
  }
});
</script>

<style scoped>
.task-detail {
  padding: 0;
}

/* ── Custom header ── */
.detail-header {
  padding: 0 0 20px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 24px;
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.column-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 500 10px/1 var(--font-mono);
  color: var(--color-text-secondary);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 4px 0;
}

.badge-dot {
  width: 6px;
  height: 6px;
  background: var(--color-accent);
}

.header-actions {
  display: flex;
  gap: 4px;
}

.header-actions :deep(.el-button) {
  border-radius: 0;
  height: 28px;
  padding: 0 12px;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.header-actions :deep(.el-button--primary) {
  background: var(--color-text);
  border-color: var(--color-text);
  color: var(--color-text-inverse);
}

.header-actions :deep(.el-button--primary:hover) {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.task-title {
  font: 600 22px/1.25 var(--font-heading);
  color: var(--color-text);
  letter-spacing: -0.01em;
  margin: 0;
}

/* ── Meta panel ── */
.meta-panel {
  margin-bottom: 24px;
}

.meta-row {
  display: flex;
  gap: 32px;
  padding: 10px 0;
}

.meta-row + .meta-row {
  border-top: 1px solid var(--color-border-light);
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.meta-item.full-width {
  flex: 1;
}

.meta-label {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.meta-value {
  font: 500 13px/1.4 var(--font-heading);
  color: var(--color-text);
  display: flex;
  align-items: center;
  gap: 6px;
}

.meta-value.unassigned {
  color: var(--color-text-tertiary);
}

.meta-date {
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
}

.tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.tag-chip {
  display: inline-block;
  padding: 2px 8px;
  font: 500 10px/1.4 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
  border: 1px solid;
}

/* ── Edit form — Swiss bottom-line inputs ── */
.edit-form {
  margin-bottom: 24px;
}

.edit-form :deep(.el-form-item) {
  margin-bottom: 20px;
}

.edit-form :deep(.el-form-item__label) {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  padding-bottom: 8px;
}

.edit-form :deep(.el-input__wrapper),
.edit-form :deep(.el-textarea__wrapper) {
  border-radius: 0;
  box-shadow: 0 1px 0 0 var(--color-border);
  background: transparent;
  padding-left: 0;
  padding-right: 0;
  transition: box-shadow var(--transition-fast);
}

.edit-form :deep(.el-input__wrapper:hover),
.edit-form :deep(.el-textarea__wrapper:hover) {
  box-shadow: 0 1px 0 0 var(--color-text-tertiary);
}

.edit-form :deep(.el-input__wrapper.is-focus),
.edit-form :deep(.el-textarea__wrapper.is-focus) {
  box-shadow: 0 1px 0 0 var(--color-text);
}

.edit-form :deep(.el-input__inner),
.edit-form :deep(.el-textarea__inner) {
  font-variant-numeric: tabular-nums;
}

/* ── Content body ── */
.content-body {
  padding: 16px 0;
  font: 400 14px/1.7 var(--font-body);
  color: var(--color-text);
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 4px;
}

.content-body.empty {
  color: var(--color-text-tertiary);
  font-style: italic;
}

/* ── Section (Related / Comments / Activities / Attachments) ── */
.section {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--color-border);
}

.section:first-of-type {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.section-header h4 {
  margin: 0;
  font: 600 11px/1 var(--font-heading);
  color: var(--color-text);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.section-count {
  font: 500 10px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  padding: 3px 6px;
  border: 1px solid var(--color-border);
  min-width: 22px;
  text-align: center;
}

.section-header .el-button {
  margin-left: auto;
  font: 500 10px/1 var(--font-heading);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.empty-hint {
  font: 400 12px/1.5 var(--font-body);
  color: var(--color-text-tertiary);
  padding: 12px 0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* ── Linked tests ── */
.linked-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--color-border-light);
}
.linked-row:last-child { border-bottom: none; }

.linked-type {
  font: 600 9px/1 var(--font-mono);
  padding: 3px 6px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}
.linked-type.type-api   { background: transparent; color: var(--color-primary); border: 1px solid var(--color-primary); }
.linked-type.type-ui    { background: transparent; color: var(--color-accent); border: 1px solid var(--color-accent); }
.linked-type.type-perf  { background: transparent; color: var(--color-warning); border: 1px solid var(--color-warning); }

.linked-name { flex: 1; font-size: 13px; justify-content: flex-start; }

/* ── Attachments ── */
.attachment-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--color-border-light);
}
.attachment-row:last-child { border-bottom: none; }
.att-name { color: var(--color-text); text-decoration: none; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border-bottom: 1px solid var(--color-border-light); padding-bottom: 2px; transition: border-color var(--transition-fast); }
.att-name:hover { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.att-size { color: var(--color-text-tertiary); font: 500 11px/1 var(--font-mono); font-variant-numeric: tabular-nums; }

/* ── Activity log ── */
.activity-list { max-height: 240px; overflow-y: auto; font-size: 12px; }
.activity-item { padding: 8px 0; border-bottom: 1px solid var(--color-border-light); line-height: 1.6; display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
.activity-item:last-child { border-bottom: none; }
.activity-user { color: var(--color-text); font-weight: 600; font-size: 12px; }
.activity-action { color: var(--color-text-secondary); }
.activity-field { color: var(--color-text); font-weight: 500; font: 500 11px/1 var(--font-mono); text-transform: uppercase; letter-spacing: 0.06em; }
.activity-change { color: var(--color-accent); font: 500 11px/1 var(--font-mono); font-variant-numeric: tabular-nums; }
.activity-time { margin-left: auto; color: var(--color-text-tertiary); font: 500 10px/1 var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: 0.04em; }

/* ── Comments ── */
.comment-list { max-height: 360px; overflow-y: auto; }
.comment-item { padding: 14px 0; border-bottom: 1px solid var(--color-border-light); }
.comment-item:last-child { border-bottom: none; }
.comment-header { margin-bottom: 6px; display: flex; justify-content: space-between; align-items: baseline; }
.comment-header strong { font: 600 12px/1 var(--font-heading); color: var(--color-text); text-transform: uppercase; letter-spacing: 0.04em; }
.comment-time { color: var(--color-text-tertiary); font: 500 10px/1 var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: 0.04em; }
.comment-content { font: 400 14px/1.6 var(--font-body); color: var(--color-text); }
.comment-replies { margin: 10px 0 0 16px; padding: 8px 12px; background: transparent; font-size: 13px; border-left: 2px solid var(--color-border); }
.reply-item { padding: 4px 0; color: var(--color-text-secondary); }
.reply-item strong { color: var(--color-text); margin-right: 6px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.comment-input { display: flex; gap: 8px; margin-top: 16px; align-items: flex-start; padding-top: 16px; border-top: 1px solid var(--color-border); }
.comment-input :deep(.el-textarea) { flex: 1; }
.comment-input :deep(.el-textarea__wrapper) { border-radius: 0; box-shadow: 0 1px 0 0 var(--color-border); background: transparent; }
.comment-input :deep(.el-textarea__wrapper.is-focus) { box-shadow: 0 1px 0 0 var(--color-text); }
.comment-input :deep(.el-button) { height: auto; padding: 8px 16px; border-radius: 0; background: var(--color-text); border-color: var(--color-text); color: var(--color-text-inverse); font: 500 11px/1 var(--font-heading); letter-spacing: 0.08em; text-transform: uppercase; }
.comment-input :deep(.el-button:hover) { background: var(--color-primary); border-color: var(--color-primary); }
</style>
