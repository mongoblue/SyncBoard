<template>
  <div class="tags-page">
    <header class="page-header">
      <div class="header-left">
        <span class="header-folio">N° 01</span>
        <div class="header-titles">
          <h1 class="page-title">标签管理</h1>
          <p class="page-subtitle">{{ tags.length }} 个标签 · 用于任务分类与筛选</p>
        </div>
      </div>
      <button class="primary-btn" @click="openCreateDialog">
        <el-icon :size="12"><Plus /></el-icon>
        创建标签
      </button>
    </header>

    <section v-if="tags.length === 0" class="empty-state">
      <span class="empty-folio">EMPTY</span>
      <p class="empty-text">暂无标签，点击右上角创建</p>
      <button class="primary-btn" @click="openCreateDialog">
        <el-icon :size="12"><Plus /></el-icon>
        创建标签
      </button>
    </section>

    <div v-else class="tags-grid">
      <article
        v-for="tag in tags"
        :key="tag.id"
        class="tag-card"
      >
        <div class="tag-rail" :style="{ background: tag.color }"></div>
        <div class="tag-body">
          <div class="tag-row tag-row-main">
            <span class="tag-folio">TAG</span>
            <div class="tag-preview">
              <span
                class="tag-chip-live"
                :style="{ background: tag.color + '14', color: tag.color, borderColor: tag.color + '40' }"
              >
                <span class="chip-dot" :style="{ background: tag.color }"></span>
                {{ tag.name }}
              </span>
            </div>
          </div>
          <div class="tag-row tag-row-meta">
            <span class="meta-cell">
              <span class="meta-folio">USE</span>
              <span class="meta-value mono">{{ String(getTagTaskCount(tag.id)).padStart(3, '0') }}</span>
            </span>
            <span class="meta-cell">
              <span class="meta-folio">HEX</span>
              <span class="meta-value mono" :style="{ color: tag.color }">{{ tag.color.toUpperCase() }}</span>
            </span>
            <span class="meta-cell">
              <span class="meta-folio">ID</span>
              <span class="meta-value mono">T-{{ String(tag.id).padStart(3, '0') }}</span>
            </span>
          </div>
        </div>
        <div class="tag-actions">
          <button class="card-icon-btn" @click="openEditDialog(tag)" title="编辑标签">
            <el-icon :size="14"><Edit /></el-icon>
          </button>
          <button class="card-icon-btn card-icon-btn-danger" @click="handleDeleteTag(tag)" title="删除标签">
            <el-icon :size="14"><Delete /></el-icon>
          </button>
        </div>
      </article>
    </div>

    <!-- 创建/编辑 弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :width="dialogMode === 'create' ? '460px' : '460px'"
      class="app-dialog"
      :show-close="false"
    >
      <template #header>
        <div class="dialog-header">
          <span class="dialog-folio">{{ dialogMode === 'create' ? 'NEW' : 'EDIT' }}</span>
          <span class="dialog-title">{{ dialogMode === 'create' ? '创建新标签' : '编辑标签' }}</span>
        </div>
      </template>
      <el-form :model="formData" label-position="top" class="tag-form">
        <div class="form-row">
          <span class="form-label">标签名称</span>
          <el-input
            v-model="formData.name"
            placeholder="输入标签名称"
            maxlength="20"
            show-word-limit
          />
        </div>
        <div class="form-row">
          <span class="form-label">预览效果</span>
          <span
            class="live-preview"
            :style="{ background: formData.color + '14', color: formData.color, borderColor: formData.color + '40' }"
          >
            <span class="chip-dot" :style="{ background: formData.color }"></span>
            {{ formData.name || '标签名称' }}
          </span>
        </div>
        <div class="form-row">
          <span class="form-label">标签颜色</span>
          <div class="color-pick-area">
            <div class="color-presets">
              <button
                v-for="c in predefineColors"
                :key="c"
                class="color-preset"
                :class="{ active: formData.color === c }"
                :style="{ background: c }"
                @click.prevent="formData.color = c"
                :aria-label="c"
                tabindex="0"
                @keydown.enter.prevent="formData.color = c"
                @keydown.space.prevent="formData.color = c"
              ></button>
            </div>
            <div class="color-custom">
              <el-color-picker v-model="formData.color" :predefine="predefineColors" />
              <code class="color-hex">{{ formData.color.toUpperCase() }}</code>
            </div>
          </div>
        </div>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <button class="text-btn" @click="dialogVisible = false">取消</button>
          <button class="primary-btn" @click="handleSubmit">
            {{ dialogMode === 'create' ? '创建' : '保存' }}
          </button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useBoardStore } from '@/stores/board';
import service from '@/utils/request';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Edit, Delete } from '@element-plus/icons-vue';

const route = useRoute();
const boardStore = useBoardStore();

const projectId = computed(() => route.params.projectId as string);
const tags = computed(() => boardStore.currentProject?.available_tags || []);

const predefineColors = [
  '#0F766E', '#FF4F00', '#5C5C5C', '#14B8A6',
  '#3B82F6', '#22C55E', '#F59E0B', '#EF4444',
  '#8B5CF6', '#EC4899', '#F97316', '#06B6D4',
];

const dialogVisible = ref(false);
const dialogMode = ref<'create' | 'edit'>('create');
const formData = ref({ id: 0, name: '', color: '#0F766E' });

const getTagTaskCount = (tagId: number) => {
  let count = 0;
  boardStore.Columns.forEach((col) => {
    col.tasks?.forEach((task: any) => {
      if (task.tags?.includes(tagId)) count++;
    });
  });
  return count;
};

const openCreateDialog = () => {
  dialogMode.value = 'create';
  formData.value = { id: 0, name: '', color: '#0F766E' };
  dialogVisible.value = true;
};

const openEditDialog = (tag: any) => {
  dialogMode.value = 'edit';
  formData.value = { ...tag };
  dialogVisible.value = true;
};

const handleSubmit = async () => {
  if (!formData.value.name.trim()) {
    ElMessage.warning('请输入标签名称');
    return;
  }
  try {
    if (dialogMode.value === 'create') {
      await boardStore.createTag(projectId.value, formData.value.name, formData.value.color);
      ElMessage.success('标签已创建');
    } else {
      await service.patch(`/tags/${formData.value.id}/`, {
        name: formData.value.name,
        color: formData.value.color,
      });
      ElMessage.success('标签已更新');
      await boardStore.fetchProjectInfo(projectId.value);
    }
    dialogVisible.value = false;
  } catch (error) {
    console.error('操作失败', error);
    ElMessage.error('操作失败');
  }
};

const handleDeleteTag = async (tag: any) => {
  const taskCount = getTagTaskCount(tag.id);
  let warningMsg = '确定要删除此标签吗？';
  if (taskCount > 0) {
    warningMsg += ` 该标签已被 ${taskCount} 个任务使用，删除后将移除关联。`;
  }
  try {
    await ElMessageBox.confirm(warningMsg, '删除标签', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
    await boardStore.deleteTag(tag.id);
  } catch (e) { /* cancelled */ }
};

onMounted(() => {
  boardStore.fetchColumns(projectId.value);
});
</script>

<style scoped>
.tags-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ── Page header ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
  gap: 24px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.header-folio {
  font: 600 11px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
  padding-top: 6px;
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  margin: 0;
  font: 600 26px/1.2 var(--font-heading);
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.page-subtitle {
  margin: 0;
  font: 500 12px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

/* ── Primary button (Swiss) ── */
.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
  background: var(--color-text);
  border: 1px solid var(--color-text);
  color: var(--color-text-inverse);
  cursor: pointer;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: background var(--transition-fast), border-color var(--transition-fast);
  white-space: nowrap;
}

.primary-btn:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.text-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 0;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  transition: color var(--transition-fast);
}

.text-btn:hover {
  color: var(--color-text);
}

/* ── Empty state ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 20px;
  background: var(--color-surface);
  border: 1px dashed var(--color-border);
  text-align: center;
}

.empty-folio {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.empty-text {
  margin: 0;
  font: 400 14px/1.5 var(--font-body);
  color: var(--color-text-secondary);
}

/* ── Tags grid ── */
.tags-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.tag-card {
  display: grid;
  grid-template-columns: 4px 1fr 56px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  transition: border-color var(--transition-fast);
  min-height: 88px;
  overflow: hidden;
}

.tag-card:hover {
  border-color: var(--color-text);
}

.tag-rail {
  height: 100%;
}

.tag-body {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  min-width: 0;
  gap: 10px;
  border-right: 1px solid var(--color-border-light);
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.tag-folio {
  font: 600 9px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  flex-shrink: 0;
}

.tag-preview {
  flex: 1;
  min-width: 0;
}

.tag-chip-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  font: 500 12px/1.4 var(--font-heading);
  border: 1px solid;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
}

.tag-row-meta {
  gap: 16px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
}

.meta-cell {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.meta-folio {
  font: 600 9px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.meta-value {
  font: 500 11px/1 var(--font-mono);
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.tag-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 6px;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.tag-card:hover .tag-actions {
  opacity: 1;
}

.card-icon-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  color: var(--color-text-tertiary);
  transition: all var(--transition-fast);
  border-radius: 0;
  padding: 0;
}

.card-icon-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border);
}

.card-icon-btn.card-icon-btn-danger:hover {
  color: var(--color-danger);
  border-color: var(--color-danger);
}

/* ── Form dialog ── */
.app-dialog :deep(.el-dialog) {
  border-radius: 0;
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-md);
}

.app-dialog :deep(.el-dialog__header) {
  padding: 18px 24px;
  margin: 0;
  border-bottom: 1px solid var(--color-border);
}

.app-dialog :deep(.el-dialog__title) {
  display: none;
}

.app-dialog :deep(.el-dialog__headerbtn) {
  display: none;
}

.app-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.app-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--color-border);
  margin: 0;
}

.dialog-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.dialog-folio {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.dialog-title {
  font: 600 15px/1 var(--font-heading);
  color: var(--color-text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.tag-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-secondary);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.app-dialog :deep(.el-input__wrapper) {
  border-radius: 0;
  box-shadow: 0 1px 0 0 var(--color-border);
  background: transparent;
  padding-left: 0;
  padding-right: 0;
  transition: box-shadow var(--transition-fast);
}

.app-dialog :deep(.el-input__wrapper:hover) {
  box-shadow: 0 1px 0 0 var(--color-text-tertiary);
}

.app-dialog :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 1px 0 0 var(--color-text);
}

.live-preview {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font: 500 14px/1.4 var(--font-heading);
  border: 1px solid;
  align-self: flex-start;
}

/* ── Color picker ── */
.color-pick-area {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.color-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.color-preset {
  width: 28px;
  height: 28px;
  border: 1px solid var(--color-border);
  cursor: pointer;
  transition: transform var(--transition-fast), border-color var(--transition-fast);
  padding: 0;
  outline: none;
}

.color-preset:hover {
  transform: scale(1.1);
  border-color: var(--color-text);
}

.color-preset:focus-visible {
  outline: 2px solid var(--color-text);
  outline-offset: 2px;
}

.color-preset.active {
  border-color: var(--color-text);
  box-shadow: 0 0 0 2px var(--color-surface), 0 0 0 3px var(--color-text);
}

.color-custom {
  display: flex;
  align-items: center;
  gap: 12px;
}

.color-hex {
  font: 500 12px/1 var(--font-mono);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  align-items: center;
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .tags-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
  .primary-btn {
    align-self: flex-start;
  }
  .tags-grid {
    grid-template-columns: 1fr;
  }
  .tag-card {
    grid-template-columns: 4px 1fr 48px;
  }
}
</style>
