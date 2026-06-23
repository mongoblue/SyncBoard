<template>
  <div class="test-result-list">
    <header class="page-header">
      <div>
        <h1 class="page-title">测试结果管理</h1>
        <p class="page-subtitle">查看和管理所有测试执行结果</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadStatistics">
          <el-icon><TrendCharts /></el-icon>
          统计概览
        </el-button>
        <el-button type="primary" @click="refreshData">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </header>

    <!-- 统计卡片 -->
    <div class="statistics-cards" v-if="statistics">
      <el-card class="stat-card">
        <div class="stat-value">{{ statistics.total }}</div>
        <div class="stat-label">总测试数</div>
      </el-card>
      <el-card class="stat-card success">
        <div class="stat-value">{{ statistics.passed }}</div>
        <div class="stat-label">通过</div>
      </el-card>
      <el-card class="stat-card danger">
        <div class="stat-value">{{ statistics.failed }}</div>
        <div class="stat-label">失败</div>
      </el-card>
      <el-card class="stat-card warning">
        <div class="stat-value">{{ statistics.error }}</div>
        <div class="stat-label">错误</div>
      </el-card>
      <el-card class="stat-card info">
        <div class="stat-value">{{ statistics.pass_rate }}%</div>
        <div class="stat-label">通过率</div>
      </el-card>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select
        v-model="filters.source"
        placeholder="结果来源"
        clearable
        style="width: 150px"
        @change="loadResults"
      >
        <el-option label="DevOps执行" value="devops" />
        <el-option label="单个用例执行" value="single" />
      </el-select>

      <el-select
        v-model="filters.test_type"
        placeholder="测试类型"
        clearable
        style="width: 150px"
        @change="loadResults"
      >
        <el-option label="接口测试" value="api" />
        <el-option label="UI测试" value="ui" />
        <el-option label="性能测试" value="performance" />
        <el-option label="回归测试" value="regression" />
      </el-select>

      <el-select
        v-model="filters.status"
        placeholder="测试状态"
        clearable
        style="width: 150px"
        @change="loadResults"
      >
        <el-option label="通过" value="passed">
          <el-tag type="success" size="small">通过</el-tag>
        </el-option>
        <el-option label="失败" value="failed">
          <el-tag type="danger" size="small">失败</el-tag>
        </el-option>
        <el-option label="错误" value="error">
          <el-tag type="warning" size="small">错误</el-tag>
        </el-option>
        <el-option label="运行中" value="running">
          <el-tag type="info" size="small">运行中</el-tag>
        </el-option>
      </el-select>

      <el-select
        v-model="filters.project"
        placeholder="所属项目"
        clearable
        style="width: 200px"
        @change="loadResults"
      >
        <el-option
          v-for="project in projects"
          :key="project.id"
          :label="project.name"
          :value="project.id"
        />
      </el-select>

      <el-date-picker
        v-model="filters.date_range"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        @change="loadResults"
        style="width: 260px"
      />

      <el-input
        v-model="filters.keyword"
        placeholder="搜索测试名称"
        clearable
        style="width: 200px"
        @keyup.enter="loadResults"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 测试结果列表 -->
    <el-table
      :data="filteredResults"
      v-loading="loading"
      stripe
      border
      style="width: 100%"
    >
      <el-table-column type="index" width="50" />

      <el-table-column label="测试名称" min-width="200">
        <template #default="{ row }">
          <div class="test-name">
            <el-icon :size="18">
              <Monitor v-if="row.test_type === 'ui'" />
              <Connection v-else-if="row.test_type === 'api'" />
              <Lightning v-else-if="row.test_type === 'performance'" />
              <Collection v-else />
            </el-icon>
            <span>{{ row.name }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="测试类型" width="120">
        <template #default="{ row }">
          <el-tag :type="getTestTypeType(row.test_type)" size="small">
            {{ row.test_type_display }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ row.status_display }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="所属项目" min-width="150">
        <template #default="{ row }">
          {{ row.project_name || '-' }}
        </template>
      </el-table-column>

      <el-table-column label="执行人员" width="120">
        <template #default="{ row }">
          {{ row.executed_by_name || '-' }}
        </template>
      </el-table-column>

      <el-table-column label="执行时长" width="120">
        <template #default="{ row }">
          <span v-if="row.duration_ms">{{ formatDuration(row.duration_ms) }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="截图" width="80" align="center">
        <template #default="{ row }">
          <el-badge :value="row.screenshot_count" v-if="row.screenshot_count > 0">
            <el-icon><Picture /></el-icon>
          </el-badge>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column label="执行时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" size="small" @click="viewDetail(row)">
            <el-icon><View /></el-icon>
            查看
          </el-button>
          <el-button type="danger" size="small" @click="handleDelete(row)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <el-empty
      v-if="!loading && filteredResults.length === 0"
      description="暂无测试结果"
      :image-size="120"
    />

    <!-- 统计弹窗 -->
    <el-dialog
      v-model="statisticsDialogVisible"
      title="测试统计概览"
      width="600px"
    >
      <div v-if="statistics" class="statistics-detail">
        <el-row :gutter="20">
          <el-col :span="12">
            <h4>按类型统计</h4>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="接口测试">
                {{ statistics.by_type?.api || 0 }}
              </el-descriptions-item>
              <el-descriptions-item label="UI测试">
                {{ statistics.by_type?.ui || 0 }}
              </el-descriptions-item>
              <el-descriptions-item label="性能测试">
                {{ statistics.by_type?.performance || 0 }}
              </el-descriptions-item>
              <el-descriptions-item label="回归测试">
                {{ statistics.by_type?.regression || 0 }}
              </el-descriptions-item>
            </el-descriptions>
          </el-col>
          <el-col :span="12">
            <h4>按状态统计</h4>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="通过">
                <el-tag type="success">{{ statistics.by_status?.passed || 0 }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="失败">
                <el-tag type="danger">{{ statistics.by_status?.failed || 0 }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="错误">
                <el-tag type="warning">{{ statistics.by_status?.error || 0 }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="运行中">
                <el-tag type="info">{{ statistics.by_status?.running || 0 }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </el-col>
        </el-row>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  Refresh,
  Search,
  Monitor,
  Connection,
  Lightning,
  Collection,
  Picture,
  View,
  Delete,
  TrendCharts
} from '@element-plus/icons-vue';
import service from '@/utils/request';

const router = useRouter();

const results = ref<any[]>([]);
const projects = ref<any[]>([]);
const loading = ref(false);
const statistics = ref<any>(null);
const statisticsDialogVisible = ref(false);

const filters = ref({
  source: '',
  test_type: '',
  status: '',
  project: '',
  date_range: null as Date[] | null,
  keyword: ''
});

// 过滤后的结果
const filteredResults = computed(() => {
  let filtered = results.value;

  if (filters.value.keyword) {
    const keyword = filters.value.keyword.toLowerCase();
    filtered = filtered.filter(item =>
      item.name.toLowerCase().includes(keyword)
    );
  }

  return filtered;
});

// 加载测试结果
const loadResults = async () => {
  loading.value = true;
  try {
    const params: any = {};

    if (filters.value.source) {
      params.source = filters.value.source;
    }
    if (filters.value.test_type) {
      params.test_type = filters.value.test_type;
    }
    if (filters.value.status) {
      params.status = filters.value.status;
    }
    if (filters.value.project) {
      params.project = filters.value.project;
    }
    if (filters.value.date_range && filters.value.date_range.length === 2) {
      params.start_date = filters.value.date_range[0]!.toISOString().split('T')[0];
      params.end_date = filters.value.date_range[1]!.toISOString().split('T')[0];
    }

    const res = await service.get('/qa/test-results/', { params });
    results.value = res.results || res;
  } catch (error) {
    ElMessage.error('加载测试结果失败');
  } finally {
    loading.value = false;
  }
};

// 加载项目列表
const loadProjects = async () => {
  try {
    const res = await service.get('/projects/');
    projects.value = res;
  } catch (error) {
    console.error('加载项目失败', error);
  }
};

// 加载统计信息
const loadStatistics = async () => {
  try {
    const params: any = {};
    if (filters.value.project) {
      params.project = filters.value.project;
    }
    if (filters.value.date_range && filters.value.date_range.length === 2) {
      params.start_date = filters.value.date_range[0]!.toISOString().split('T')[0];
      params.end_date = filters.value.date_range[1]!.toISOString().split('T')[0];
    }

    const res = await service.get('/qa/test-results/statistics/', { params });
    statistics.value = res;
    statisticsDialogVisible.value = true;
  } catch (error) {
    ElMessage.error('加载统计信息失败');
  }
};

// 刷新数据
const refreshData = () => {
  loadResults();
  ElMessage.success('数据已刷新');
};

// 获取测试类型标签样式
const getTestTypeType = (type: string) => {
  const types: Record<string, string> = {
    'api': 'primary',
    'ui': 'success',
    'performance': 'warning',
    'regression': 'info'
  };
  return types[type] || 'info';
};

// 获取状态标签样式
const getStatusType = (status: string) => {
  const types: Record<string, string> = {
    'passed': 'success',
    'failed': 'danger',
    'error': 'warning',
    'running': 'info',
    'pending': 'info'
  };
  return types[status] || 'info';
};

// 格式化时长
const formatDuration = (ms: number) => {
  if (ms < 1000) {
    return `${ms}ms`;
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`;
  } else {
    return `${(ms / 60000).toFixed(1)}m`;
  }
};

// 格式化日期
const formatDate = (dateString: string) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleString('zh-CN');
};

// 查看详情
const viewDetail = (row: any) => {
  router.push({
    name: 'TestResultDetail',
    params: { id: row.id }
  });
};

// 删除结果
const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除测试结果 "${row.name}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    await service.delete(`/qa/test-results/${row.id}/`);
    ElMessage.success('删除成功');
    loadResults();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

onMounted(() => {
  loadProjects();
  loadResults();
});
</script>

<style scoped>
.test-result-list { padding: 0; }

.header-actions {
  display: flex;
  gap: 8px;
}

/* 统计卡片 */
.statistics-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.stat-card :deep(.el-card__body) { padding: 16px; }

.stat-value {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 600;
  color: var(--color-primary);
  margin-bottom: 4px;
}

.stat-card.success .stat-value { color: var(--color-success); }
.stat-card.danger .stat-value { color: var(--color-danger); }
.stat-card.warning .stat-value { color: var(--color-warning); }
.stat-card.info .stat-value { color: var(--color-info); }

.stat-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* 筛选栏 */
.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: center;
  flex-wrap: wrap;
}

/* 测试名称 */
.test-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 统计弹窗 */
.statistics-detail h4 {
  margin: 0 0 12px 0;
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

@media (max-width: 1200px) {
  .statistics-cards { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 768px) {
  .statistics-cards { grid-template-columns: repeat(2, 1fr); }
  .filter-bar { flex-direction: column; align-items: stretch; }
  .filter-bar > * { width: 100% !important; }
}
</style>
