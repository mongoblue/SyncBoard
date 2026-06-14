<template>
  <div class="projects-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <div class="title-section">
          <div class="icon-wrapper">
            <el-icon :size="28" color="#14B8A6"><FolderOpened /></el-icon>
          </div>
          <div class="title-text">
            <h1>我的项目</h1>
            <p class="subtitle">{{ projects.length }} 个项目</p>
          </div>
        </div>
        <el-button
          type="primary"
          size="large"
          class="create-btn"
          @click="createProject"
        >
          <el-icon :size="18"><Plus /></el-icon>
          创建新项目
        </el-button>
      </div>
    </div>

    <!-- 项目网格 -->
    <div class="projects-container">
      <div v-if="projects.length === 0" class="empty-state">
        <div class="empty-icon">
          <el-icon :size="64" color="var(--color-text-tertiary)"><Folder /></el-icon>
        </div>
        <h3>还没有项目</h3>
        <p>创建您的第一个项目开始协作</p>
        <el-button type="primary" @click="createProject">
          <el-icon><Plus /></el-icon>
          创建项目
        </el-button>
      </div>

      <div v-else class="project-grid">
        <el-card
          v-for="(p, index) in projects"
          :key="p.id"
          class="project-card"
          :class="'card-accent-' + (index % 4)"
          shadow="hover"
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
              <el-icon :size="28"><Folder /></el-icon>
            </div>
            <h3 class="project-name">{{ p.name }}</h3>
            <div class="project-meta">
              <div class="owner-badge">
                <el-icon :size="14"><User /></el-icon>
                <span>{{ p.owner_details?.username || '未知' }}</span>
              </div>
              <div class="project-stats">
                <span class="stat-item">
                  <el-icon :size="14"><Calendar /></el-icon>
                  {{ formatDate(p.created_at) }}
                </span>
              </div>
            </div>
          </div>
          
          <div class="card-footer">
            <div class="member-avatars">
              <div class="avatar-placeholder">
                <el-icon :size="14"><User /></el-icon>
              </div>
              <span class="member-text">项目负责人</span>
            </div>
            <el-icon class="enter-icon" :size="20"><ArrowRight /></el-icon>
          </div>
        </el-card>

        <!-- 添加项目卡片 -->
        <div class="add-project-card" @click="createProject">
          <div class="add-icon-wrapper">
            <el-icon :size="28"><Plus /></el-icon>
          </div>
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
import { Folder, FolderOpened, Plus, Delete, User, Calendar, ArrowRight } from '@element-plus/icons-vue';

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

// 格式化日期
const formatDate = (dateString: string) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
};

// 跳转到看板
const goToBoard = (id: string) => {
  router.push(`/projects/${id}/board`);
};

// 创建项目
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
}

/* ── Header ── */
.page-header {
  background: var(--color-text);
  padding: 36px 0;
  margin-bottom: 32px;
  border-bottom: 1px solid var(--color-border);
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 40px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title-section {
  display: flex;
  align-items: center;
  gap: 20px;
}

.icon-wrapper {
  width: 56px;
  height: 56px;
  background: transparent;
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border-strong);
  color: var(--color-text-inverse);
}

.title-text h1 {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 26px;
  font-weight: 700;
  color: var(--color-text-inverse);
}

.subtitle {
  margin: 4px 0 0 0;
  font-size: 14px;
  color: var(--color-text-tertiary);
}

.create-btn {
  background: var(--color-text-inverse);
  color: var(--color-text);
  border: 1px solid var(--color-text-inverse);
  font-weight: 600;
  padding: 11px 22px;
  border-radius: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.2s, color 0.2s;
}

.create-btn:hover {
  background: var(--color-accent);
  color: var(--color-text-inverse);
  border-color: var(--color-accent);
}

/* ── 项目网格 ── */
.projects-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 40px 48px;
}

.empty-state {
  text-align: center;
  padding: 80px 20px;
  background: var(--color-surface);
  border-radius: 0;
  border: 1px dashed var(--color-border);
}

.empty-icon {
  margin-bottom: 20px;
}

.empty-state h3 {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 8px;
}

.empty-state p {
  color: var(--color-text-secondary);
  margin-bottom: 24px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

/* ── Project card ── */
.project-card {
  cursor: pointer;
  border: 1px solid var(--color-border) !important;
  border-radius: 0;
  overflow: hidden;
  position: relative;
  background: var(--color-surface);
  transition: border-color 0.2s, transform 0.2s;
}

.project-card:hover {
  border-color: var(--color-primary-border) !important;
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

/* 顶部强调色条 */
.project-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 4px;
  z-index: 1;
}

.card-accent-0::before { background: var(--color-accent-bar-0); }
.card-accent-1::before { background: var(--color-accent-bar-1); }
.card-accent-2::before { background: var(--color-accent-bar-2); }
.card-accent-3::before { background: var(--color-accent-bar-3); }

.card-actions {
  position: absolute;
  top: 16px;
  right: 12px;
  z-index: 10;
  opacity: 0;
  transition: opacity 0.2s;
}

.project-card:hover .card-actions {
  opacity: 1;
}

.delete-btn {
  color: var(--color-text-tertiary);
  padding: 6px;
  border-radius: 6px;
}

.delete-btn:hover {
  color: var(--color-danger);
  background: rgba(239, 68, 68, 0.08);
}

.card-content {
  padding: 28px 22px 18px;
}

.project-icon {
  width: 46px;
  height: 46px;
  background: transparent;
  color: var(--color-text);
  border-radius: 0;
  border: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 14px;
}

.project-name {
  margin: 0 0 14px 0;
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 14px;
}

.owner-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.project-stats {
  display: flex;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 22px;
  background: var(--color-bg);
  border-top: 1px solid var(--color-border-light);
}

.member-avatars {
  display: flex;
  align-items: center;
  gap: 8px;
}

.avatar-placeholder {
  width: 26px;
  height: 26px;
  background: var(--color-border);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
}

.member-text {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.enter-icon {
  color: var(--color-text-tertiary);
  transition: color 0.2s, transform 0.2s;
}

.project-card:hover .enter-icon {
  color: var(--color-primary);
  transform: translateX(3px);
}

/* ── Add project card ── */
.add-project-card {
  min-height: 100%;
  background: transparent;
  border: 1px dashed var(--color-border);
  border-radius: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
  gap: 14px;
  padding: 48px 20px;
  color: var(--color-text-tertiary);
}

.add-project-card:hover {
  border-color: var(--color-text);
  color: var(--color-text);
}

.add-icon-wrapper {
  width: 52px;
  height: 52px;
  background: transparent;
  color: var(--color-text);
  border-radius: 0;
  border: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
}

.add-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-secondary);
}
</style>
