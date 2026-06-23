<template>
  <div class="ui-case-list">
    <header class="page-header">
      <div>
        <h1 class="page-title">UI 测试用例</h1>
        <p class="page-subtitle">基于 Playwright 的 E2E 自动化测试</p>
      </div>
      <el-button type="primary" @click="handleCreate">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        新建用例
      </el-button>
    </header>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select
        v-model="selectedProject"
        placeholder="选择项目"
        clearable
        style="width: 200px"
        @change="loadCases"
      >
        <el-option
          v-for="project in projects"
          :key="project.id"
          :label="project.name"
          :value="project.id"
        />
      </el-select>
      <el-input
        v-model="searchKeyword"
        placeholder="搜索用例名称"
        clearable
        style="width: 250px"
        @keyup.enter="loadCases"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button @click="loadCases">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 用例列表 -->
    <el-table
      :data="cases"
      v-loading="loading"
      stripe
      border
      style="width: 100%"
    >
      <el-table-column type="index" width="50" />
      <el-table-column label="用例名称" min-width="200">
        <template #default="{ row }">
          <div class="case-name">
            <el-icon><Monitor /></el-icon>
            <span>{{ row.name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="起始 URL" min-width="250">
        <template #default="{ row }">
          <el-tooltip :content="row.url" placement="top">
            <span class="url-text">{{ row.url }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="步骤数" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.steps?.length || 0 }} 步</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建者" width="120">
        <template #default="{ row }">
          {{ row.created_by_name || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" size="small" @click="handleRun(row)">
            <el-icon><VideoPlay /></el-icon>
            运行
          </el-button>
          <el-button type="default" size="small" @click="handleEdit(row)">
            <el-icon><Edit /></el-icon>
            编辑
          </el-button>
          <el-button type="danger" size="small" @click="handleDelete(row)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <el-empty
      v-if="!loading && cases.length === 0"
      description="暂无 UI 测试用例"
      :image-size="120"
    >
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        创建第一个用例
      </el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  Plus,
  Search,
  Refresh,
  Monitor,
  VideoPlay,
  Edit,
  Delete
} from '@element-plus/icons-vue';
import service from '@/utils/request';

const router = useRouter();
const route = useRoute();

const cases = ref<any[]>([]);
const projects = ref<any[]>([]);
const loading = ref(false);
const selectedProject = ref(route.query.project as string || '');
const searchKeyword = ref('');

// 加载项目列表
const loadProjects = async () => {
  try {
    const res = await service.get('/projects/');
    projects.value = res;
  } catch (error) {
    console.error('加载项目失败', error);
  }
};

// 加载测试用例列表
const loadCases = async () => {
  loading.value = true;
  try {
    const params: any = {};
    if (selectedProject.value) {
      params.project = selectedProject.value;
    }
    const res = await service.get('/qa/ui-cases/', { params });
    // 处理分页响应
    let list = res.results || res;
    // 过滤搜索关键词
    if (searchKeyword.value) {
      const keyword = searchKeyword.value.toLowerCase();
      list = list.filter((item: any) =>
        item.name.toLowerCase().includes(keyword)
      );
    }
    cases.value = list;
  } catch (error) {
    ElMessage.error('加载测试用例失败');
  } finally {
    loading.value = false;
  }
};

// 格式化日期
const formatDate = (dateString: string) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleString('zh-CN');
};

// 创建用例
const handleCreate = () => {
  router.push({
    name: 'UiCaseCreate',
    query: { project: selectedProject.value }
  });
};

// 编辑用例
const handleEdit = (row: any) => {
  router.push({
    name: 'UiCaseDetail',
    params: { id: row.id }
  });
};

// 运行测试 -> 跳转到详情页并自动开跑
const handleRun = (row: any) => {
  router.push({
    name: 'UiCaseDetail',
    params: { id: row.id },
    query: { autorun: '1' }
  });
};

// 删除用例
const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除测试用例 "${row.name}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    await service.delete(`/qa/ui-cases/${row.id}/`);
    ElMessage.success('删除成功');
    loadCases();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

onMounted(() => {
  loadProjects();
  loadCases();
});
</script>

<style scoped>
.ui-case-list { padding: 0; }

.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: center;
}

.case-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.url-text {
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  max-width: 300px;
}
</style>
