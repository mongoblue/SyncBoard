<template>
  <div class="tags-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">标签管理</h1>
        <p class="page-subtitle">{{ tags.length }} 个标签 · 用于任务分类与筛选</p>
      </div>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        创建标签
      </el-button>
    </header>

    <section v-if="tags.length === 0" class="empty-state">
      <p class="empty-text">暂无标签，点击右上角创建</p>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        创建标签
      </el-button>
    </section>

    <div v-else class="tags-grid">
      <article
        v-for="tag in tags"
        :key="tag.id"
        class="tag-card card"
      >
        <div class="tag-main">
          <span class="color-dot" :style="{ background: tag.color }"></span>
          <span class="tag-name">{{ tag.name }}</span>
        </div>
        <div class="tag-meta">
          <span class="meta-row">
            <span class="meta-label">使用</span>
            <span class="meta-value">{{ getTagTaskCount(tag.id) }} 个任务</span>
          </span>
          <span class="meta-row">
            <span class="meta-label">颜色</span>
            <span class="meta-value mono">{{ tag.color.toUpperCase() }}</span>
          </span>
        </div>
        <div class="tag-actions">
          <el-button link size="small" @click="openEditDialog(tag)">
            <el-icon style="margin-right: 4px"><Edit /></el-icon>
            编辑
          </el-button>
          <el-button link size="small" type="danger" @click="handleDeleteTag(tag)">
            <el-icon style="margin-right: 4px"><Delete /></el-icon>
            删除
          </el-button>
        </div>
      </article>
    </div>

    <!-- 创建/编辑 弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '创建新标签' : '编辑标签'"
      width="460px"
    >
      <el-form :model="formData" label-position="top">
        <div class="form-field">
          <label class="form-label">标签名称</label>
          <el-input
            v-model="formData.name"
            placeholder="输入标签名称"
            maxlength="20"
            show-word-limit
          />
        </div>
        <div class="form-field">
          <label class="form-label">预览效果</label>
          <div>
            <span class="tag-chip-live" :style="{
              background: formData.color + '14',
              color: formData.color,
              borderColor: formData.color + '40'
            }">
              <span class="color-dot" :style="{ background: formData.color }"></span>
              {{ formData.name || '标签名称' }}
            </span>
          </div>
        </div>
        <div class="form-field">
          <label class="form-label">标签颜色</label>
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
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">
          {{ dialogMode === 'create' ? '创建' : '保存' }}
        </el-button>
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
  '#0F766E', '#0969DA', '#1A7F37', '#9A6700',
  '#CF222E', '#8250DF', '#BF3989', '#0550AE',
  '#116329', '#A40E26', '#3192AA', '#6E7781',
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
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-border-light);
  gap: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 64px 20px;
  background: var(--color-surface);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  text-align: center;
}

.empty-text {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

/* ── Tags grid ── */
.tags-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.tag-card {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.tag-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.tag-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.color-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  display: inline-block;
}

.tag-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.meta-row {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}

.meta-label {
  color: var(--color-text-secondary);
}

.meta-value {
  color: var(--color-text);
}

.meta-value.mono {
  font-family: var(--font-mono);
}

.tag-actions {
  display: flex;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
}

/* ── Form dialog ── */
.tag-chip-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid;
  border-radius: var(--radius-sm);
}

.color-pick-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
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
  border-radius: var(--radius-sm);
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
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.color-preset.active {
  border-color: var(--color-text);
  box-shadow: 0 0 0 2px var(--color-surface), 0 0 0 3px var(--color-primary);
}

.color-custom {
  display: flex;
  align-items: center;
  gap: 10px;
}

.color-hex {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-secondary);
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
  .tags-grid {
    grid-template-columns: 1fr;
  }
}
</style>
