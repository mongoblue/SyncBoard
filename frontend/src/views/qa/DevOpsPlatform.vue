<template>
  <div class="devops-platform">
    <header class="page-header">
      <div>
        <h1 class="page-title">DevOps 测试平台</h1>
        <p class="page-subtitle">内置测试平台，支持持续集成和自动化测试</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="showBatchRunDialog = true">
          <el-icon><VideoPlay /></el-icon>
          批量执行
        </el-button>
        <el-button type="success" @click="router.push(`/projects/${projectId}/quality`)">
          <el-icon><DataLine /></el-icon>
          质量报告
        </el-button>
        <el-button @click="refreshData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </header>

    <div class="platform-content">
      <!-- 功能卡片区域 -->
      <el-row :gutter="20">
        <el-col :span="8">
          <el-card class="feature-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon><Monitor /></el-icon>
                <span>CI/CD 集成</span>
              </div>
            </template>
            <div class="card-body">
              <p>支持与 Jenkins、GitLab CI、GitHub Actions 等主流 CI/CD 工具集成</p>
              <div class="integration-status" v-if="ciCdConfigs.length > 0">
                <el-tag type="success" size="small">已配置 {{ ciCdConfigs.length }} 个集成</el-tag>
              </div>
              <el-button type="primary" class="action-btn" @click="showCiCdDialog = true">
                配置集成
              </el-button>
            </div>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card class="feature-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon><VideoPlay /></el-icon>
                <span>自动化测试</span>
              </div>
            </template>
            <div class="card-body">
              <p>支持 API 测试、UI 测试、性能测试等多种测试类型</p>
              <div class="test-stats" v-if="stats">
                <el-tag type="info" size="small">{{ stats.overview.total_cases }} 个测试用例</el-tag>
              </div>
              <el-button type="primary" class="action-btn" @click="showTestTaskDialog = true">
                创建测试
              </el-button>
            </div>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card class="feature-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-icon><DataLine /></el-icon>
                <span>测试报告</span>
              </div>
            </template>
            <div class="card-body">
              <p>自动生成测试报告，支持历史趋势分析和质量度量</p>
              <div class="report-status" v-if="stats">
                <el-tag :type="getPassRateType(stats.overview.pass_rate)" size="small">
                  通过率 {{ stats.overview.pass_rate }}%
                </el-tag>
              </div>
              <el-button type="primary" class="action-btn" @click="goToReports">
                查看报告
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 统计和执行记录区域 -->
      <el-row :gutter="20" class="mt-20">
        <el-col :span="12">
          <el-card v-loading="loading">
            <template #header>
              <div class="card-header">
                <span>最近执行</span>
                <el-button text @click="goToTestResults">查看全部</el-button>
              </div>
            </template>
            <el-table :data="recentExecutions" style="width: 100%" v-if="recentExecutions.length > 0">
              <el-table-column prop="name" label="任务名称" min-width="150" show-overflow-tooltip />
              <el-table-column label="类型" width="100">
                <template #default="{ row }">
                  <el-tag :type="getTestTypeType(row.test_type)" size="small">
                    {{ getTestTypeText(row.test_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)" size="small">
                    {{ getStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="执行时间" width="160">
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" fixed="right">
                <template #default="{ row }">
                  <el-button type="primary" link size="small" @click="viewExecutionDetail(row)">
                    查看
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无执行记录" :image-size="100" />
          </el-card>
        </el-col>

        <el-col :span="12">
          <el-card v-loading="loading">
            <template #header>
              <div class="card-header">
                <span>测试统计</span>
                <el-tooltip content="最近7天统计数据">
                  <el-icon><InfoFilled /></el-icon>
                </el-tooltip>
              </div>
            </template>
            <div class="stats-content" v-if="stats">
              <div class="stat-item">
                <div class="stat-value">{{ stats.overview.total_cases }}</div>
                <div class="stat-label">总测试用例</div>
              </div>
              <div class="stat-item">
                <div class="stat-value" :class="getPassRateClass(stats.overview.pass_rate)">
                  {{ stats.overview.pass_rate }}%
                </div>
                <div class="stat-label">通过率</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{{ stats.overview.today_executions }}</div>
                <div class="stat-label">今日执行</div>
              </div>
            </div>
            <div class="stats-detail" v-if="stats">
              <el-divider />
              <div class="detail-row">
                <span class="detail-label">接口测试用例</span>
                <span class="detail-value">{{ stats.overview.api_cases }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">UI 测试用例</span>
                <span class="detail-value">{{ stats.overview.ui_cases }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">总执行次数（7天）</span>
                <span class="detail-value">{{ stats.overview.total_executions }}</span>
              </div>
            </div>
            <el-empty v-else description="加载中..." :image-size="100" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 测试任务列表 -->
      <el-row class="mt-20">
        <el-col :span="24">
          <el-card v-loading="loading">
            <template #header>
              <div class="card-header">
                <span>测试任务</span>
                <el-button type="primary" size="small" @click="showTestTaskDialog = true">
                  <el-icon><Plus /></el-icon>
                  新建任务
                </el-button>
              </div>
            </template>
            <el-table :data="testTasks" style="width: 100%" v-if="testTasks.length > 0">
              <el-table-column prop="name" label="任务名称" min-width="150" show-overflow-tooltip />
              <el-table-column label="类型" width="100">
                <template #default="{ row }">
                  <el-tag :type="getTestTypeType(row.test_type)" size="small">
                    {{ getTestTypeText(row.test_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="触发方式" width="100">
                <template #default="{ row }">
                  <el-tag type="info" size="small" effect="plain">
                    {{ getTriggerTypeText(row.trigger_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)" size="small">
                    {{ getStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="最后执行" width="160">
                <template #default="{ row }">
                  {{ formatDateTime(row.last_executed) }}
                </template>
              </el-table-column>
              <el-table-column label="执行次数" width="90" align="center">
                <template #default="{ row }">
                  {{ row.execution_count }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="240" fixed="right">
                <template #default="{ row }">
                  <el-button
                    type="primary"
                    link
                    size="small"
                    @click="viewTaskDetail(row)"
                  >
                    <el-icon><View /></el-icon>
                    查看
                  </el-button>
                  <el-button
                    type="primary"
                    link
                    size="small"
                    @click="executeTask(row)"
                    :loading="executingTaskId === row.id"
                    :disabled="row.status === 'running'"
                  >
                    <el-icon><VideoPlay /></el-icon>
                    执行
                  </el-button>
                  <el-button type="primary" link size="small" @click="editTask(row)">
                    <el-icon><Edit /></el-icon>
                    编辑
                  </el-button>
                  <el-button type="danger" link size="small" @click="deleteTask(row)">
                    <el-icon><Delete /></el-icon>
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无测试任务，点击上方按钮创建" :image-size="100" />
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- Pipeline 执行历史 -->
    <el-card class="section-card" style="margin-top:20px">
      <PipelineTimeline :project-id="projectId" />
    </el-card>

    <!-- CI/CD 配置对话框 -->
    <CiCdConfigDialog
      v-model="showCiCdDialog"
      :configs="ciCdConfigs"
      @refresh="loadCiCdConfigs"
    />

    <!-- 测试任务对话框 -->
    <TestTaskDialog
      v-model="showTestTaskDialog"
      :task="editingTask"
      @refresh="loadTestTasks"
      @close="editingTask = null"
    />

    <!-- 批量执行 API 自动化用例 -->
    <BatchRunExecuteDialog
      v-model="showBatchRunDialog"
      :project-id="projectId"
      @finished="onBatchRunFinished"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import PipelineTimeline from '@/components/PipelineTimeline.vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  Monitor,
  VideoPlay,
  DataLine,
  Refresh,
  Plus,
  Edit,
  Delete,
  InfoFilled,
  View,
} from '@element-plus/icons-vue';
import type {
  DashboardStats,
  RecentExecution,
  CiCdConfig,
  TestTask,
  TestType,
} from '@/types/devops';
import {
  getDashboardStats,
  getRecentExecutions,
  getCiCdConfigs,
  getTestTasks,
  executeTestTask,
  deleteTestTask,
  getStatusType,
  getStatusText,
  getTestTypeType,
  getTestTypeText,
  formatDateTime,
} from '@/api/devops';
import CiCdConfigDialog from './components/CiCdConfigDialog.vue';
import TestTaskDialog from './components/TestTaskDialog.vue';
import BatchRunExecuteDialog from './components/BatchRunExecuteDialog.vue';

const router = useRouter();
const route = useRoute();
const projectId = computed(() => route.params.projectId as string);

// 加载状态
const loading = ref(false);
const executingTaskId = ref<number | null>(null);

// 数据
const stats = ref<DashboardStats | null>(null);
const recentExecutions = ref<RecentExecution[]>([]);
const ciCdConfigs = ref<CiCdConfig[]>([]);
const testTasks = ref<TestTask[]>([]);

// 对话框显示状态
const showCiCdDialog = ref(false);
const showTestTaskDialog = ref(false);
const showBatchRunDialog = ref(false);
const editingTask = ref<TestTask | null>(null);

// 获取通过率样式
const getPassRateType = (rate: number): 'success' | 'warning' | 'danger' => {
  if (rate >= 90) return 'success';
  if (rate >= 70) return 'warning';
  return 'danger';
};

const getPassRateClass = (rate: number): string => {
  if (rate >= 90) return 'text-success';
  if (rate >= 70) return 'text-warning';
  return 'text-danger';
};

// 获取触发方式文本
const getTriggerTypeText = (type: string): string => {
  const map: Record<string, string> = {
    manual: '手动',
    scheduled: '定时',
    webhook: 'Webhook',
  };
  return map[type] || type;
};

// 加载仪表板统计数据
const loadStats = async () => {
  try {
    const data = await getDashboardStats(7);
    stats.value = data;
  } catch (error) {
    console.error('加载统计数据失败', error);
  }
};

// 加载最近执行记录
const loadRecentExecutions = async () => {
  try {
    const data = await getRecentExecutions(5);
    recentExecutions.value = data;
  } catch (error) {
    console.error('加载最近执行记录失败', error);
  }
};

// 加载 CI/CD 配置
const loadCiCdConfigs = async () => {
  try {
    const data = await getCiCdConfigs();
    ciCdConfigs.value = data;
  } catch (error) {
    console.error('加载 CI/CD 配置失败', error);
  }
};

// 加载测试任务
const loadTestTasks = async () => {
  try {
    const data = await getTestTasks();
    testTasks.value = data;
  } catch (error) {
    console.error('加载测试任务失败', error);
  }
};

// 刷新所有数据
const refreshData = async () => {
  loading.value = true;
  await Promise.all([
    loadStats(),
    loadRecentExecutions(),
    loadCiCdConfigs(),
    loadTestTasks(),
  ]);
  loading.value = false;
  ElMessage.success('数据已刷新');
};

// 查看执行详情
const viewExecutionDetail = (row: RecentExecution) => {
  router.push({
    name: 'TestResultDetail',
    params: { id: row.id },
  });
};

// 跳转到测试报告
const goToReports = () => {
  router.push({ name: 'TestResultList' });
};

// 跳转到测试结果列表
const goToTestResults = () => {
  router.push({ name: 'TestResultList' });
};

// 执行测试任务
const executeTask = async (task: TestTask) => {
  try {
    await ElMessageBox.confirm(
      `确定要执行测试任务 "${task.name}" 吗？`,
      '确认执行',
      {
        confirmButtonText: '执行',
        cancelButtonText: '取消',
        type: 'info',
      }
    );

    executingTaskId.value = task.id;
    const result = await executeTestTask(task.id);
    ElMessage.success(result.message);

    // 刷新任务列表
    await loadTestTasks();

    // 开始轮询任务状态
    pollTaskStatus(task.id);
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '执行任务失败');
    }
  } finally {
    executingTaskId.value = null;
  }
};

// 轮询任务状态
const pollTaskStatus = async (taskId: number) => {
  const maxAttempts = 30; // 最多轮询30次
  let attempts = 0;

  const checkStatus = async () => {
    if (attempts >= maxAttempts) {
      return;
    }

    try {
      const response = await import('@/api/devops').then(m => m.getTestTaskStatus(taskId));
      const task = response.task;

      // 更新任务列表中的状态
      const index = testTasks.value.findIndex(t => t.id === taskId);
      if (index !== -1) {
        testTasks.value[index] = task;
      }

      // 如果任务还在运行，继续轮询
      if (task.status === 'running') {
        attempts++;
        setTimeout(checkStatus, 2000);
      } else {
        // 任务完成，显示结果
        if ((task as any).last_result) {
          const { passed, failed, pass_rate } = (task as any).last_result;
          if (failed === 0) {
            ElMessage.success(`任务执行完成！通过率 ${pass_rate}%`);
          } else {
            ElMessage.warning(`任务执行完成，${failed} 个用例失败`);
          }
        }
        // 刷新统计数据
        loadStats();
        loadRecentExecutions();
      }
    } catch (error) {
      console.error('获取任务状态失败', error);
    }
  };

  checkStatus();
};

// 查看任务详情
const viewTaskDetail = (task: TestTask) => {
  router.push({
    name: 'TestTaskDetail',
    params: { id: task.id }
  });
};

// 编辑任务
const editTask = (task: TestTask) => {
  editingTask.value = task;
  showTestTaskDialog.value = true;
};

// 删除任务
const deleteTask = async (task: TestTask) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除测试任务 "${task.name}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );

    await deleteTestTask(task.id);
    ElMessage.success('删除成功');
    await loadTestTasks();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '删除失败');
    }
  }
};

// 批量执行完成回调：刷新统计与最近执行
const onBatchRunFinished = (_resultId: number) => {
  loadStats();
  loadRecentExecutions();
};

onMounted(() => {
  refreshData();
});
</script>

<style scoped>
.devops-platform { padding: 0; }

.header-actions {
  display: flex;
  gap: 8px;
}

.feature-card {
  height: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.feature-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-family: var(--font-heading);
  font-size: 14px;
  color: var(--color-text);
}

.card-header .el-icon {
  font-size: 18px;
  color: var(--color-primary);
}

.card-body p {
  color: var(--color-text-secondary);
  margin: 0 0 12px 0;
  line-height: 1.6;
  min-height: 44px;
  font-size: 13px;
}

.integration-status,
.test-stats,
.report-status {
  margin-bottom: 12px;
}

.action-btn {
  width: 100%;
}

.mt-20 {
  margin-top: 20px;
}

.stats-content {
  display: flex;
  justify-content: space-around;
  padding: 20px 0;
}

.stat-item {
  text-align: center;
}

.stat-value {
  font-family: var(--font-heading);
  font-size: 28px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 4px;
}

.stat-value.text-success { color: var(--color-success); }
.stat-value.text-warning { color: var(--color-warning); }
.stat-value.text-danger { color: var(--color-danger); }

.stat-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.stats-detail {
  padding: 0 10px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-border-light);
  font-size: 13px;
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-label {
  color: var(--color-text-secondary);
}

.detail-value {
  font-weight: 600;
  color: var(--color-text);
}

:deep(.el-card__header) {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-light);
}

:deep(.el-card__body) {
  padding: 16px;
}
</style>
