<template>
  <div class="auto-case-list">
    <header class="page-header">
      <div>
        <h1 class="page-title">API 测试用例</h1>
        <p class="page-subtitle">管理 API 自动化测试用例，支持单条运行与断言校验</p>
      </div>
      <el-button type="primary" @click="handleCreate">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        新建用例
      </el-button>
    </header>

    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索用例名称或 URL"
        clearable
        style="width: 280px"
        @keyup.enter="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select
        v-model="filterActive"
        placeholder="启用状态"
        clearable
        style="width: 140px"
        @change="loadCases"
      >
        <el-option label="启用" value="true" />
        <el-option label="禁用" value="false" />
      </el-select>
      <el-button @click="handleSearch">
        <el-icon><Search /></el-icon>
        搜索
      </el-button>
      <el-button @click="loadCases">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <el-table :data="cases" v-loading="loading" stripe border style="width: 100%">
      <el-table-column type="index" width="50" />
      <el-table-column label="用例名称" min-width="220">
        <template #default="{ row }">
          <div class="case-name">
            <el-icon><Connection /></el-icon>
            <span>{{ row.name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="方法" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="getMethodType(row.method)">{{ row.method }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="URL" min-width="280">
        <template #default="{ row }">
          <el-tooltip :content="row.url" placement="top">
            <span class="url-text">{{ row.url }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="断言数" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.assertion_count ?? 0 }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建者" width="120">
        <template #default="{ row }">{{ row.created_by_name || '-' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button type="success" size="small" @click="handleRun(row)" :loading="row._running">
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

    <el-empty
      v-if="!loading && cases.length === 0"
      description="暂无 API 测试用例"
      :image-size="120"
    >
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        创建第一个用例
      </el-button>
    </el-empty>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      style="margin-top: 16px; justify-content: flex-end"
      @current-change="loadCases"
      @size-change="loadCases"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  Plus, Search, Refresh, Connection, VideoPlay, Edit, Delete,
} from '@element-plus/icons-vue';
import service from '@/utils/request';
import { useBoardStore } from '@/stores/board';

const router = useRouter();
const boardStore = useBoardStore();

const cases = ref<any[]>([]);
const loading = ref(false);
const searchKeyword = ref('');
const filterActive = ref('');
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const getMethodType = (method: string): 'success' | 'primary' | 'warning' | 'danger' | 'info' => {
  const types: Record<string, 'success' | 'primary' | 'warning' | 'danger' | 'info'> = {
    GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info',
  };
  return types[method] || 'info';
};

const formatDate = (s: string) => {
  if (!s) return '-';
  return new Date(s).toLocaleString('zh-CN');
};

const loadCases = async () => {
  loading.value = true;
  try {
    const params: any = {
      page: page.value,
      page_size: pageSize.value,
    };
    const projectId = boardStore.currentProject?.id;
    if (projectId) params.project = projectId;
    if (searchKeyword.value) params.search = searchKeyword.value;
    if (filterActive.value) params.is_active = filterActive.value;
    const res = await service.get('/qa/auto-cases/', { params });
    cases.value = res.results || res || [];
    total.value = res.count ?? cases.value.length;
  } catch (e) {
    ElMessage.error('加载测试用例失败');
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => {
  page.value = 1;
  loadCases();
};

const handleCreate = () => {
  router.push({
    name: 'AutoCaseCreate',
    query: { project: boardStore.currentProject?.id },
  });
};

const handleEdit = (row: any) => {
  router.push({ name: 'AutoCaseDetail', params: { id: row.id } });
};

const handleRun = async (row: any) => {
  row._running = true;
  try {
    const res: any = await service.post(`/qa/auto-cases/${row.id}/execute/`);
    if (res.result_id) {
      router.push({ name: 'AutoResultDetail', params: { id: res.result_id } });
    } else {
      ElMessage.warning('执行完成但未返回结果 ID');
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '执行失败');
  } finally {
    row._running = false;
  }
};

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定要删除用例 "${row.name}" 吗？`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
    await service.delete(`/qa/auto-cases/${row.id}/`);
    ElMessage.success('删除成功');
    loadCases();
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('删除失败');
  }
};

onMounted(loadCases);
</script>

<style scoped>
.auto-case-list { padding: 0; }

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
  max-width: 320px;
}
</style>
