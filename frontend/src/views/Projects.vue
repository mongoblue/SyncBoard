<template>
  <div class="projects-page">
    <!-- 页面头部 -->
    <div class="page-header projects-header">
      <div class="title-section">
        <div class="title-text">
          <h1 class="page-title">我的项目</h1>
          <p class="page-subtitle">{{ projects.length }} 个项目</p>
        </div>
      </div>
      <el-button
        type="primary"
        size="default"
        @click="createProject"
      >
        <el-icon :size="16" style="margin-right: 6px"><Plus /></el-icon>
        创建新项目
      </el-button>
    </div>

    <!-- 项目网格 -->
    <div class="projects-container">
      <div v-if="projects.length === 0" class="empty-state">
        <div class="empty-icon">
          <el-icon :size="48" color="var(--color-text-tertiary)"><Folder /></el-icon>
        </div>
        <h3>还没有项目</h3>
        <p>创建您的第一个项目开始协作</p>
        <el-button type="primary" @click="createProject">
          <el-icon><Plus /></el-icon>
          创建项目
        </el-button>
      </div>

      <div v-else class="project-grid">
        <div
          v-for="p in projects"
          :key="p.id"
          class="project-card"
          @click="goToBoard(p.id)"
        >
          <div class="card-actions">
            <el-button
              type="danger"
              link
              size="small"
              class="delete-btn"
              @click.stop="handleDeleteProject(p.id)"
            >
              <el-icon :size="16"><Delete /></el-icon>
            </el-button>
          </div>

          <div class="card-content">
            <div class="project-icon">
              <el-icon :size="20"><Folder /></el-icon>
            </div>
            <h3 class="project-name">{{ p.name }}</h3>
            <div class="project-meta">
              <span class="meta-item">
                <el-icon :size="14"><User /></el-icon>
                {{ p.owner_details?.username || '未知' }}
              </span>
              <span class="meta-item">
                <el-icon :size="14"><Calendar /></el-icon>
                {{ formatDate(p.created_at) }}
              </span>
            </div>
          </div>

          <div class="card-footer">
            <span class="footer-text">点击进入看板</span>
            <el-icon class="enter-icon" :size="16"><ArrowRight /></el-icon>
          </div>
        </div>

        <!-- 添加项目卡片 -->
        <div class="add-project-card" @click="createProject">
          <el-icon :size="24"><Plus /></el-icon>
          <span class="add-text">创建新项目</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import service from '@/utils/request';
import { ElMessageBox, ElMessage } from 'element-plus';
import { Folder, Plus, Delete, User, Calendar, ArrowRight } from '@element-plus/icons-vue';

const router = useRouter();
const projects = ref<any[]>([]);

const fetchProjects = async () => {
  try {
    const data = await service.get<any,any[]>('/projects/');
    projects.value = data;
  } catch (e) {
    console.error(e);
  }
};

const formatDate = (dateString: string) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
};

const goToBoard = (id: string) => {
  router.push(`/projects/${id}/board`);
};

const createProject = async () => {
  try {
    const { value } = await ElMessageBox.prompt('请输入项目名称', '创建项目', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：产品开发项目',
      inputValidator: (value) => {
        if (!value || value.trim() === '') {
          return '项目名称不能为空';
        }
        return true;
      }
    });

    if (value) {
      await service.post('/projects/', { name: value.trim() });
      ElMessage.success('项目创建成功');
      fetchProjects();
    }
  } catch(e) {}
};

const handleDeleteProject = async (projectId: string) => {
  try {
    await ElMessageBox.confirm(
      '删除项目将连带删除该项目下的所有看板和任务，且无法恢复。是否确认？',
      '删除项目',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );

    await service.delete(`/projects/${projectId}/`);
    ElMessage.success('项目已删除');
    fetchProjects();
  } catch (e) {}
};

onMounted(() => {
  fetchProjects();
});
</script>

<style scoped>
.projects-page {
  min-height: calc(100vh - 56px);
  background: var(--color-bg);
  padding: 24px 32px;
}

.projects-header {
  margin-bottom: 24px;
}

.title-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.title-text .page-title {
  font-size: 24px;
}

.title-text .page-subtitle {
  margin-top: 4px;
}

.projects-container {
  width: 100%;
}

.empty-state {
  text-align: center;
  padding: 64px 20px;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
}

.empty-icon { margin-bottom: 16px; }

.empty-state h3 {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 8px;
}

.empty-state p {
  color: var(--color-text-secondary);
  margin-bottom: 20px;
  font-size: 14px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

/* ── Project card ── */
.project-card {
  cursor: pointer;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  position: relative;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  display: flex;
  flex-direction: column;
}

.project-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.card-actions {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.project-card:hover .card-actions {
  opacity: 1;
}

.delete-btn {
  color: var(--color-text-tertiary);
  padding: 4px;
}

.delete-btn:hover {
  color: var(--color-danger);
}

.card-content {
  padding: 20px 20px 16px;
  flex: 1;
}

.project-icon {
  width: 36px;
  height: 36px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.project-name {
  margin: 0 0 12px 0;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  border-top: 1px solid var(--color-border-light);
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.enter-icon {
  transition: transform var(--transition-fast), color var(--transition-fast);
}

.project-card:hover .enter-icon {
  color: var(--color-primary);
  transform: translateX(2px);
}

/* ── Add project card ── */
.add-project-card {
  background: transparent;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
  gap: 10px;
  min-height: 180px;
  color: var(--color-text-tertiary);
}

.add-project-card:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-bg);
}

.add-text {
  font-size: 14px;
  font-weight: 500;
}
</style>
