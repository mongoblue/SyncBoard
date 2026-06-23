<template>
  <div class="settings-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">项目设置</h1>
        <p class="page-subtitle">管理项目基本信息和生命周期</p>
      </div>
    </header>

    <div class="settings-grid">
      <!-- 基本信息 -->
      <section class="card">
        <div class="card-section">
          <h2 class="card-section-title">基本信息</h2>
          <p class="card-section-subtitle">用于识别项目的基本属性</p>

          <div class="form-field">
            <label class="form-label">项目名称</label>
            <el-input v-model="projectForm.name" placeholder="请输入项目名称" />
            <p class="form-help">项目名称会显示在所有看板视图中。</p>
          </div>

          <div class="form-field">
            <label class="form-label">项目 ID</label>
            <div class="readonly-value">{{ projectId }}</div>
            <p class="form-help">系统自动生成，不可修改。</p>
          </div>

          <div class="form-actions">
            <el-button type="primary" @click="handleUpdateName">
              <el-icon style="margin-right: 4px"><Check /></el-icon>
              保存修改
            </el-button>
          </div>
        </div>
      </section>

      <!-- 危险操作 -->
      <section class="card danger-card">
        <div class="card-section">
          <h2 class="card-section-title danger-title">危险操作</h2>
          <p class="card-section-subtitle">这些操作不可恢复，请谨慎执行。</p>

          <div class="danger-item">
            <div class="danger-info">
              <h3>删除项目</h3>
              <p>删除项目将连带删除该项目下的所有看板、任务和标签，且无法恢复。</p>
            </div>
            <el-button type="danger" plain @click="handleDeleteProject">
              <el-icon style="margin-right: 4px"><Delete /></el-icon>
              删除项目
            </el-button>
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
}

/* Page header (uses global .page-title / .page-subtitle but local layout) */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-border-light);
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

@media (max-width: 1024px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}

.danger-card {
  border-left: 3px solid var(--color-danger);
}

.danger-title {
  color: var(--color-danger);
}

.readonly-value {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--color-text-secondary);
  padding: 8px 12px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  word-break: break-all;
}

.danger-item {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--color-danger-bg);
  border-radius: var(--radius-md);
}

.danger-info h3 {
  margin: 0 0 6px 0;
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.danger-info p {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}
</style>
