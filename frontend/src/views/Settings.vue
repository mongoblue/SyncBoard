<template>
  <div class="settings-page">
    <header class="page-header">
      <div class="header-left">
        <span class="header-folio">N° 01</span>
        <div class="header-titles">
          <h1 class="page-title">项目设置</h1>
          <p class="page-subtitle">管理项目基本信息和生命周期</p>
        </div>
      </div>
    </header>

    <div class="settings-grid">
      <!-- 基本信息 -->
      <section class="settings-card">
        <div class="card-header">
          <span class="card-folio">N° 02</span>
          <h2 class="card-title">基本信息</h2>
        </div>
        <div class="card-body">
          <el-form :model="projectForm" class="settings-form">
            <div class="form-row">
              <span class="form-label">项目名称</span>
              <el-input v-model="projectForm.name" placeholder="请输入项目名称" />
            </div>
            <div class="form-row">
              <span class="form-label">项目 ID</span>
              <span class="form-value mono">{{ projectId }}</span>
            </div>
            <div class="form-actions">
              <button class="primary-btn" @click="handleUpdateName">
                <el-icon :size="12"><Check /></el-icon>
                保存修改
              </button>
            </div>
          </el-form>
        </div>
      </section>

      <!-- 危险操作 -->
      <section class="settings-card settings-card-danger">
        <div class="card-header">
          <span class="card-folio">N° 03</span>
          <h2 class="card-title">危险操作</h2>
        </div>
        <div class="card-body">
          <div class="danger-item">
            <div class="danger-info">
              <h3 class="danger-title">删除项目</h3>
              <p class="danger-desc">
                删除项目将连带删除该项目下的所有看板、任务和标签，且无法恢复。
              </p>
            </div>
            <button class="danger-btn" @click="handleDeleteProject">
              <el-icon :size="12"><Delete /></el-icon>
              删除项目
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useBoardStore } from '@/stores/board';
import service from '@/utils/request';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Check, Delete } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const boardStore = useBoardStore();

const projectId = computed(() => route.params.projectId as string);

const projectForm = ref({
  name: '',
});

const handleUpdateName = async () => {
  if (!projectForm.value.name.trim()) {
    ElMessage.warning('项目名称不能为空');
    return;
  }
  try {
    await service.patch(`/projects/${projectId.value}/`, {
      name: projectForm.value.name,
    });
    ElMessage.success('项目名称已更新');
    await boardStore.fetchProjectInfo(projectId.value);
  } catch (error) {
    ElMessage.error('更新失败');
  }
};

const handleDeleteProject = async () => {
  try {
    await ElMessageBox.confirm(
      '删除项目将连带删除该项目下的所有看板、任务和标签，且无法恢复。是否确认？',
      '危险操作',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );
    await service.delete(`/projects/${projectId.value}/`);
    ElMessage.success('项目已删除');
    router.push('/projects');
  } catch (e) {
    // Cancelled
  }
};

onMounted(() => {
  projectForm.value.name = boardStore.currentProject?.name || '';
});
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ── Page header ── */
.page-header {
  padding-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
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

/* ── Two-column settings grid ── */
.settings-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  align-items: start;
}

@media (max-width: 1024px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}

/* ── Settings card ── */
.settings-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
}

.settings-card-danger {
  border-left: 2px solid var(--color-danger);
}

.card-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}

.card-folio {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.settings-card-danger .card-folio {
  color: var(--color-danger);
}

.card-title {
  margin: 0;
  font: 600 14px/1 var(--font-heading);
  color: var(--color-text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.card-body {
  padding: 24px 20px;
}

/* ── Form ── */
.settings-form {
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

.form-value {
  font: 500 14px/1.4 var(--font-heading);
  color: var(--color-text);
  padding: 6px 0;
}

.form-value.mono {
  font: 500 13px/1 var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
}

.settings-form :deep(.el-input__wrapper) {
  border-radius: 0;
  box-shadow: 0 1px 0 0 var(--color-border);
  background: transparent;
  padding-left: 0;
  padding-right: 0;
  transition: box-shadow var(--transition-fast);
}

.settings-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 1px 0 0 var(--color-text-tertiary);
}

.settings-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 1px 0 0 var(--color-text);
}

.settings-form :deep(.el-input__inner) {
  font-variant-numeric: tabular-nums;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
  margin-top: 4px;
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
}

.primary-btn:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

/* ── Danger item ── */
.danger-item {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.danger-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.danger-title {
  margin: 0;
  font: 600 15px/1.3 var(--font-heading);
  color: var(--color-danger);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.danger-desc {
  margin: 0;
  font: 400 13px/1.6 var(--font-body);
  color: var(--color-text-secondary);
}

.danger-btn {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
  background: transparent;
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
  cursor: pointer;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.danger-btn:hover {
  background: var(--color-danger);
  color: var(--color-text-inverse);
}
</style>
