<template>
  <div class="projects-container">
    <div class="header">
        <div class="left">
      <h2>我的项目</h2>
      <el-button type="primary" icon="Plus" @click="createProject">创建新项目</el-button>
    </div>
    <div class="user-area">
        <span class="username">{{ authStore.user?.username }}</span>
        <el-button type="danger" link @click="handleLogout">退出</el-button>
    </div>
    </div>
    <div class="project-grid">
      <el-card 
        v-for="p in projects" 
        :key="p.id" 
        class="project-card" 
        shadow="hover"
        @click="goToBoard(p.id)"
      >
        <div class="card-actions">
      <el-button 
        type="danger" 
        icon="Delete" 
        circle 
        size="small" 
        class="delete-btn"
        @click.stop="handleDeleteProject(p.id)" 
      />
      </div>
        <div class="card-content">
          <el-icon class="folder-icon" :size="40" color="#409eff"><Folder /></el-icon>
          <h3>{{ p.name }}</h3>
          <p class="owner">负责人: {{ p.owner_name || 'Admin' }}</p>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import service from '@/utils/request';
import { ElMessageBox, ElMessage } from 'element-plus';
import { useAuthStore } from '@/stores/Auth';
const authStore = useAuthStore();

const router = useRouter();
const projects = ref<any[]>([]);

// 获取项目列表
const fetchProjects = async () => {
  try {
    const data = await service.get<any,any[]>('/api/projects/');
    projects.value = data;
  } catch (e) {
    console.error(e);
  }
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
    });
    
    if (value) {
      await service.post('/api/projects/', { name: value });
      ElMessage.success('创建成功');
      fetchProjects(); // 刷新列表
    }
  } catch(e) {}
};

const handleDeleteProject = async (projectId: string) => {
  try {
    // 1. 弹出确认框
    await ElMessageBox.confirm(
      '删除项目将连带删除该项目下的所有看板和任务，且无法恢复。是否确认？',
      '危险操作',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );

    // 2. 调用接口
    await service.delete(`/api/projects/${projectId}/`);
    ElMessage.success('项目已删除');
    
    // 3. 刷新列表
    fetchProjects();
  } catch (e) {
    // 用户点击取消，什么都不做
  }
};

const handleLogout = async () => {
  await authStore.logout();
  router.push('/login');
};

onMounted(() => {
  fetchProjects();
});
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  /* 加个底色区分一下 */
  padding-bottom: 20px;
  border-bottom: 1px solid #eee;
}
.left { display: flex; align-items: center; gap: 15px; }
.left h2 { margin: 0; }
.user-area { display: flex; align-items: center; gap: 15px; color: #666; font-size: 14px;}
.projects-container {
  padding: 40px;
  max-width: 1200px;
  margin: 0 auto;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 20px;
}
.project-card {
  cursor: pointer;
  transition: transform 0.2s;
  text-align: center;
  position: relative
}
.project-card:hover {
  transform: translateY(-5px);
}
.card-content {
  padding: 20px;
}
.folder-icon {
  margin-bottom: 15px;
}
h3 { margin: 10px 0; }
.owner { color: #999; font-size: 12px; }
.card-actions {
  position: absolute;
  top: 10px;
  right: 10px;
  opacity: 0; 
  transition: opacity 0.3s;
}

.project-card:hover .card-actions {
  opacity: 1;
}
</style>