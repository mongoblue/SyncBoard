<template>
  <div class="api-case-list">
    <header class="page-header">
      <div>
        <h1 class="page-title">API 测试用例</h1>
        <p class="page-subtitle">维护接口测试用例与断言规则</p>
      </div>
      <el-button type="primary" @click="handleCreate">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        新建测试用例
      </el-button>
    </header>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select v-model="selectedProject" placeholder="选择项目" clearable @change="loadCases">
        <el-option
          v-for="project in projects"
          :key="project.id"
          :label="project.name"
          :value="project.id"
        />
      </el-select>
      <el-input
        v-model="searchKeyword"
        placeholder="搜索测试用例"
        clearable
        style="width: 300px"
        @keyup.enter="loadCases"
      >
        <template #append>
          <el-button @click="loadCases">
            <el-icon><Search /></el-icon>
          </el-button>
        </template>
      </el-input>
    </div>

    <!-- 测试用例列表 -->
    <el-table :data="caseList" v-loading="loading" stripe>
      <el-table-column prop="name" label="用例名称" min-width="200">
        <template #default="{ row }">
          <el-link type="primary" @click="handleEdit(row)">{{ row.name }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="method" label="方法" width="100">
        <template #default="{ row }">
          <el-tag :type="getMethodType(row.method)" size="small">{{ row.method }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="url" label="请求地址" min-width="300" show-overflow-tooltip />
      <el-table-column prop="expected_status" label="期望状态码" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.expected_status" type="info" size="small">{{ row.expected_status }}</el-tag>
          <span v-else class="text-gray">-</span>
        </template>
      </el-table-column>
      <el-table-column label="最近执行结果" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.last_result" :type="row.last_result.passed ? 'success' : 'danger'" size="small">
            {{ row.last_result.passed ? '通过' : '失败' }}
          </el-tag>
          <span v-else class="text-gray">未执行</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_by_name" label="创建者" width="120" />
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="handleRun(row)">
            <el-icon><VideoPlay /></el-icon>
            运行
          </el-button>
          <el-button type="primary" link size="small" @click="handleEdit(row)">
            <el-icon><Edit /></el-icon>
            编辑
          </el-button>
          <el-button type="danger" link size="small" @click="handleDelete(row)">
            <el-icon><Delete /></el-icon>
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        layout="total, prev, pager, next"
        @current-change="loadCases"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Search, VideoPlay, Edit, Delete } from '@element-plus/icons-vue';
import service from '@/utils/request';

const router = useRouter();
const route = useRoute();

const loading = ref(false);
const caseList = ref<any[]>([]);
const projects = ref<any[]>([]);
const selectedProject = ref(route.query.project as string || '');
const searchKeyword = ref('');

const pagination = ref({
  page: 1,
  pageSize: 10,
  total: 0
});

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
    const params: any = {
      page: pagination.value.page,
      page_size: pagination.value.pageSize
    };
    if (selectedProject.value) {
      params.project = selectedProject.value;
    }
    
    const res = await service.get('/qa/api-cases/', { params });
    caseList.value = res.results || res;
    pagination.value.total = res.count || caseList.value.length;
  } catch (error) {
    ElMessage.error('加载测试用例失败');
  } finally {
    loading.value = false;
  }
};

// 获取请求方法标签类型
const getMethodType = (method: string) => {
  const types: Record<string, string> = {
    'GET': 'success',
    'POST': 'primary',
    'PUT': 'warning',
    'DELETE': 'danger',
    'PATCH': 'info'
  };
  return types[method] || 'info';
};

// 格式化日期
const formatDate = (date: string) => {
  if (!date) return '-';
  return new Date(date).toLocaleString('zh-CN');
};

// 新建测试用例
const handleCreate = () => {
  router.push({
    name: 'ApiCaseCreate',
    query: { project: selectedProject.value }
  });
};

// 编辑测试用例
const handleEdit = (row: any) => {
  router.push({
    name: 'ApiCaseDetail',
    params: { id: row.id }
  });
};

// 运行测试用例
const handleRun = async (row: any) => {
  try {
    const res = await service.post(`/qa/api-cases/${row.id}/run/`);
    if (res.passed) {
      ElMessage.success(`测试通过！状态码: ${res.status_code}, 响应时间: ${res.response_time_ms}ms`);
    } else {
      ElMessage.warning(`测试未通过！期望状态码: ${res.expected_status}, 实际: ${res.status_code}`);
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '运行测试失败');
  }
};

// 删除测试用例
const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要删除该测试用例吗？', '提示', {
      type: 'warning'
    });
    await service.delete(`/qa/api-cases/${row.id}/`);
    ElMessage.success('删除成功');
    loadCases();
  } catch (error) {
    // 取消删除
  }
};

onMounted(() => {
  loadProjects();
  loadCases();
});
</script>

<style scoped>
.api-case-list { padding: 0; }

.filter-bar {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.text-gray {
  color: var(--color-text-tertiary);
}
</style>
