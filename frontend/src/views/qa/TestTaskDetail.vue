<template>
  <div class="test-task-detail">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
        <h2>{{ task?.name || '测试任务详情' }}</h2>
        <el-tag :type="getStatusType(task?.status || '')" size="small">
          {{ getStatusText(task?.status || '') }}
        </el-tag>
      </div>
      <div class="header-actions">
        <el-button
          type="primary"
          :icon="VideoPlay"
          :loading="executing"
          :disabled="task?.status === 'running'"
          @click="executeTask"
        >
          执行任务
        </el-button>
        <el-button :icon="Edit" @click="editTask">编辑</el-button>
        <el-button :icon="Delete" type="danger" @click="deleteTask">删除</el-button>
      </div>
    </div>

    <!-- 任务基本信息 -->
    <el-row :gutter="20" class="info-section">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>基本信息</span>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="任务名称">{{ task?.name }}</el-descriptions-item>
            <el-descriptions-item label="测试类型">
              <el-tag :type="getTestTypeType(task?.test_type as any)" size="small">
                {{ getTestTypeText(task?.test_type as any) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="触发方式">{{ getTriggerTypeText(task?.trigger_type) }}</el-descriptions-item>
            <el-descriptions-item label="所属项目">{{ task?.project_name }}</el-descriptions-item>
            <el-descriptions-item label="创建者">{{ task?.created_by_name }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDateTime(task?.created_at || null) }}</el-descriptions-item>
            <el-descriptions-item label="执行次数">{{ task?.execution_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="最后执行">{{ formatDateTime(task?.last_executed || null) }}</el-descriptions-item>
            <el-descriptions-item label="任务描述" :span="2">{{ task?.description || '暂无描述' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>执行统计</span>
            </div>
          </template>
          <div class="stats-content">
            <div class="stat-item">
              <div class="stat-value">{{ task?.execution_count || 0 }}</div>
              <div class="stat-label">总执行次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" :class="getLastResultClass()">
                {{ getLastResultText() }}
              </div>
              <div class="stat-label">最后执行结果</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 测试配置 -->
    <el-card class="config-section">
      <template #header>
        <div class="card-header">
          <span>测试配置</span>
        </div>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="API 测试用例">
          <div v-if="apiCases.length > 0">
            <el-tag v-for="caseId in apiCases" :key="caseId" size="small" class="case-tag">
              {{ getApiCaseName(caseId) }}
            </el-tag>
          </div>
          <span v-else class="text-gray">未配置</span>
        </el-descriptions-item>
        <el-descriptions-item label="UI 测试用例">
          <div v-if="uiCases.length > 0">
            <el-tag v-for="caseId in uiCases" :key="caseId" size="small" class="case-tag" type="success">
              {{ getUiCaseName(caseId) }}
            </el-tag>
          </div>
          <span v-else class="text-gray">未配置</span>
        </el-descriptions-item>
        <el-descriptions-item label="测试环境">{{ task?.test_config?.environment || '默认环境' }}</el-descriptions-item>
        <el-descriptions-item label="Cron 表达式" v-if="task?.cron_expression">{{ task.cron_expression }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 执行历史 -->
    <el-card class="history-section">
      <template #header>
        <div class="card-header">
          <span>执行历史</span>
          <el-button :icon="Refresh" circle size="small" @click="refreshStatus" :loading="refreshing" />
        </div>
      </template>

      <!-- 当前执行状态 -->
      <div v-if="currentExecution" class="current-execution">
        <h4>当前执行</h4>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="执行ID">#{{ currentExecution.id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusType(currentExecution.status)" size="small">
              {{ getStatusText(currentExecution.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(currentExecution.started_at) }}</el-descriptions-item>
        </el-descriptions>

        <!-- 执行日志 -->
        <div v-if="executionLogs.length > 0" class="execution-logs">
          <h5>执行日志 ({{ executionLogs.length }} 个用例)</h5>
          <el-collapse v-model="activeLogIndex">
            <el-collapse-item
              v-for="(log, index) in executionLogs"
              :key="index"
              :name="index"
            >
              <template #title>
                <div class="log-header">
                  <el-tag :type="log.status === 'passed' ? 'success' : 'danger'" size="small" class="log-status">
                    {{ log.status === 'passed' ? '通过' : '失败' }}
                  </el-tag>
                  <span class="log-case-name">{{ log.case_name || log.case || `用例 #${log.case_id}` }}</span>
                  <span v-if="log.type" class="log-type">[{{ log.type.toUpperCase() }}]</span>
                  <span v-if="log.response_time_ms" class="log-time-ms">{{ log.response_time_ms }}ms</span>
                </div>
              </template>
              
              <div class="log-detail">
                <!-- API 测试详情 -->
                <template v-if="log.request">
                  <div class="detail-section">
                    <div class="section-title">请求信息</div>
                    <div class="code-block">
                      <div class="request-line">
                        <span class="method" :class="log.request.method?.toLowerCase()">{{ log.request.method }}</span>
                        <span class="url">{{ log.request.url }}</span>
                      </div>
                      <div v-if="log.request.headers && Object.keys(log.request.headers).length > 0" class="headers">
                        <div class="sub-title">Headers:</div>
                        <pre>{{ JSON.stringify(log.request.headers, null, 2) }}</pre>
                      </div>
                      <div v-if="log.request.body" class="body">
                        <div class="sub-title">Body:</div>
                        <pre>{{ JSON.stringify(log.request.body, null, 2) }}</pre>
                      </div>
                    </div>
                  </div>
                  
                  <div class="detail-section" v-if="log.response">
                    <div class="section-title">响应信息</div>
                    <div class="code-block">
                      <div class="response-line">
                        <span class="status-code" :class="log.response.status_code >= 200 && log.response.status_code < 300 ? 'success' : 'error'">
                          {{ log.response.status_code }}
                        </span>
                      </div>
                      <div v-if="log.response.body" class="body">
                        <div class="sub-title">Body:</div>
                        <pre>{{ log.response.body }}</pre>
                      </div>
                    </div>
                  </div>
                </template>
                
                <!-- 简单消息 -->
                <div v-if="log.message" class="log-message-text">
                  {{ log.message }}
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- 实时日志输出 -->
        <div v-if="task?.status === 'running'" class="live-logs">
          <h5>实时输出</h5>
          <div class="log-console" ref="logConsole">
            <div v-for="(log, index) in liveLogs" :key="index" class="log-line">
              <span class="log-time">[{{ log.time }}]</span>
              <span :class="['log-level', `level-${log.level}`]">{{ log.level.toUpperCase() }}</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 历史执行记录 -->
      <el-table :data="executionHistory" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="执行ID" width="100" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="completed_at" label="完成时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.completed_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时" width="100">
          <template #default="{ row }">
            {{ formatDuration(row.duration_ms) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewExecutionDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编辑任务对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑测试任务" width="600px">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="任务描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="触发方式">
          <el-select v-model="editForm.trigger_type" style="width: 100%">
            <el-option label="手动触发" value="manual" />
            <el-option label="定时触发" value="scheduled" />
            <el-option label="Webhook触发" value="webhook" />
          </el-select>
        </el-form-item>
        <el-form-item label="Cron表达式" v-if="editForm.trigger_type === 'scheduled'">
          <el-input v-model="editForm.cron_expression" placeholder="0 0 * * *" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTask" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  ArrowLeft,
  VideoPlay,
  Edit,
  Delete,
  Refresh,
  CircleCheck,
  CircleClose,
} from '@element-plus/icons-vue';
import {
  getTestTask,
  executeTestTask,
  getTestTaskStatus,
  getTestTaskHistory,
  updateTestTask,
  deleteTestTask,
  getStatusType,
  getStatusText,
  getTestTypeType,
  getTestTypeText,
  formatDateTime,
  formatDuration,
} from '@/api/devops';
import type { TestTask } from '@/types/devops';
import service from '@/utils/request';

const route = useRoute();
const router = useRouter();
const taskId = computed(() => Number(route.params.id));

// 状态
const task = ref<TestTask | null>(null);
const loading = ref(false);
const executing = ref(false);
const refreshing = ref(false);
const editDialogVisible = ref(false);
const saving = ref(false);
const currentExecution = ref<any>(null);
const executionHistory = ref<any[]>([]);
const liveLogs = ref<any[]>([]);
const apiTestCases = ref<any[]>([]);
const uiTestCases = ref<any[]>([]);
const activeLogIndex = ref<number[]>([]);
let statusTimer: ReturnType<typeof setInterval> | null = null;

// 编辑表单
const editForm = ref({
  name: '',
  description: '',
  trigger_type: 'manual',
  cron_expression: '',
});

// 计算属性
const apiCases = computed(() => task.value?.test_config?.api_cases || []);
const uiCases = computed(() => task.value?.test_config?.ui_cases || []);

// 获取用例名称
const getApiCaseName = (caseId: number) => {
  const caseItem = apiTestCases.value.find(c => c.id === caseId);
  return caseItem?.name || `用例 #${caseId}`;
};

const getUiCaseName = (caseId: number) => {
  const caseItem = uiTestCases.value.find(c => c.id === caseId);
  return caseItem?.name || `用例 #${caseId}`;
};

const executionLogs = computed(() => {
  if (!currentExecution.value?.test_log) return [];
  try {
    const logs = JSON.parse(currentExecution.value.test_log);
    // 新格式: { summary: {}, results: [] }
    if (logs.results && Array.isArray(logs.results)) {
      return logs.results.map((r: any) => ({
        ...r,
        status: r.passed ? 'passed' : 'failed'
      }));
    }
    // 旧格式: 直接是数组
    return Array.isArray(logs) ? logs : [];
  } catch {
    return [];
  }
});

// 方法
const fetchTaskDetail = async () => {
  loading.value = true;
  try {
    const data = await getTestTask(taskId.value);
    task.value = data;
    // 加载测试用例详情
    await loadTestCases();
  } catch (error) {
    console.error('获取任务详情失败:', error);
    ElMessage.error('获取任务详情失败');
  } finally {
    loading.value = false;
  }
};

// 加载测试用例
const loadTestCases = async () => {
  try {
    const [apiRes, uiRes] = await Promise.all([
      service.get('/qa/api-cases/'),
      service.get('/qa/ui-cases/'),
    ]);
    apiTestCases.value = apiRes.results || apiRes || [];
    uiTestCases.value = uiRes.results || uiRes || [];
  } catch (error) {
    console.error('加载测试用例失败:', error);
  }
};

const fetchTaskStatus = async () => {
  try {
    const data = await getTestTaskStatus(taskId.value);
    currentExecution.value = data.current_execution;
  } catch (error) {
    console.error('获取任务状态失败:', error);
  }
};

const fetchTaskHistory = async () => {
  try {
    const history = await getTestTaskHistory(taskId.value);
    executionHistory.value = history;
  } catch (error) {
    console.error('获取执行历史失败:', error);
  }
};

const refreshStatus = async () => {
  refreshing.value = true;
  await Promise.all([fetchTaskStatus(), fetchTaskHistory()]);
  refreshing.value = false;
};

const executeTask = async () => {
  executing.value = true;
  try {
    const data = await executeTestTask(taskId.value);
    ElMessage.success('测试任务已启动');
    currentExecution.value = {
      id: data.execution_id,
      status: 'running',
      started_at: new Date().toISOString(),
    };
    task.value = data.task;
    startStatusPolling();
  } catch (error) {
    console.error('执行任务失败:', error);
    ElMessage.error('执行任务失败');
  } finally {
    executing.value = false;
  }
};

const editTask = () => {
  if (!task.value) return;
  editForm.value = {
    name: task.value.name,
    description: task.value.description || '',
    trigger_type: task.value.trigger_type,
    cron_expression: task.value.cron_expression || '',
  };
  editDialogVisible.value = true;
};

const saveTask = async () => {
  saving.value = true;
  try {
    await updateTestTask(taskId.value, editForm.value as any);
    ElMessage.success('任务更新成功');
    editDialogVisible.value = false;
    await fetchTaskDetail();
  } catch (error) {
    console.error('更新任务失败:', error);
    ElMessage.error('更新任务失败');
  } finally {
    saving.value = false;
  }
};

const deleteTask = async () => {
  try {
    await ElMessageBox.confirm('确定要删除此测试任务吗？', '确认删除', {
      type: 'warning',
    });
    await deleteTestTask(taskId.value);
    ElMessage.success('任务已删除');
    router.push('/qa/devops');
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('删除任务失败:', error);
      ElMessage.error('删除任务失败');
    }
  }
};

const goBack = () => {
  router.back();
};

const viewExecutionDetail = (row: any) => {
  const projectId = route.params.projectId || task.value?.project;
  router.push(`/projects/${projectId}/qa/test-results/${row.id}`);
};

const getTriggerTypeText = (type?: string) => {
  const map: Record<string, string> = {
    manual: '手动触发',
    scheduled: '定时触发',
    webhook: 'Webhook触发',
  };
  return map[type || ''] || type || '-';
};

const getLastResultText = () => {
  const lastResult = task.value?.last_result_summary;
  if (!lastResult) return '暂无';
  return lastResult.passed ? '通过' : '失败';
};

const getLastResultClass = () => {
  const lastResult = task.value?.last_result_summary;
  if (!lastResult) return '';
  return lastResult.passed ? 'text-success' : 'text-danger';
};

// 状态轮询
const startStatusPolling = () => {
  if (statusTimer) return;
  statusTimer = setInterval(() => {
    fetchTaskStatus();
    // 如果任务已完成，停止轮询
    if (task.value?.status !== 'running') {
      stopStatusPolling();
    }
  }, 3000);
};

const stopStatusPolling = () => {
  if (statusTimer) {
    clearInterval(statusTimer);
    statusTimer = null;
  }
};

// 生命周期
onMounted(() => {
  fetchTaskDetail();
  fetchTaskStatus();
  fetchTaskHistory();
  // 如果任务正在运行，开始轮询
  if (task.value?.status === 'running') {
    startStatusPolling();
  }
});

onUnmounted(() => {
  stopStatusPolling();
});
</script>

<style scoped>
.test-task-detail {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-left h2 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.info-section {
  margin-bottom: 20px;
}

.config-section,
.history-section {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  font-size: 32px;
  font-weight: bold;
  color: var(--el-color-primary);
}

.stat-value.text-success {
  color: var(--el-color-success);
}

.stat-value.text-danger {
  color: var(--el-color-danger);
}

.stat-label {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
}

.case-tag {
  margin-right: 8px;
  margin-bottom: 4px;
}

.text-gray {
  color: var(--el-text-color-secondary);
}

.current-execution {
  margin-bottom: 20px;
  padding: 16px;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
}

.current-execution h4 {
  margin-top: 0;
  margin-bottom: 16px;
}

.current-execution h5 {
  margin-top: 16px;
  margin-bottom: 12px;
}

.execution-logs {
  margin-top: 16px;
}

.log-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.log-status {
  flex-shrink: 0;
}

.log-case-name {
  font-weight: 500;
  flex: 1;
}

.log-type {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.log-time-ms {
  color: var(--color-primary);
  font-size: 12px;
  font-family: var(--font-mono);
}

.log-detail {
  padding: 12px;
  background-color: var(--color-surface-sunken);
  border-radius: var(--radius-md);
}

.detail-section {
  margin-bottom: 16px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font: 600 13px/1.3 var(--font-heading);
  margin-bottom: 8px;
  color: var(--color-text);
}

.code-block {
  background-color: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  color: var(--color-text);
  padding: 12px;
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 12px;
  overflow-x: auto;
}

.code-block pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.request-line {
  margin-bottom: 8px;
}

.method {
  font-weight: 600;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  margin-right: 8px;
  font-size: 11px;
}

.method.get { background-color: var(--color-info-bg); color: var(--color-info); }
.method.post { background-color: var(--color-success-bg); color: var(--color-success); }
.method.put { background-color: var(--color-warning-bg); color: var(--color-warning); }
.method.delete { background-color: var(--color-danger-bg); color: var(--color-danger); }

.url {
  color: var(--color-text);
}

.sub-title {
  color: var(--color-text-secondary);
  margin-top: 8px;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-code {
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.status-code.success { background-color: var(--color-success-bg); color: var(--color-success); }
.status-code.error { background-color: var(--color-danger-bg); color: var(--color-danger); }

.log-message-text {
  padding: 8px;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-primary);
}

.live-logs {
  margin-top: 16px;
}

.log-console {
  background-color: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  color: var(--color-text);
  padding: 12px;
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.log-line {
  margin-bottom: 4px;
  line-height: 1.5;
}

.log-time {
  color: var(--color-text-tertiary);
  margin-right: 8px;
}

.log-level {
  margin-right: 8px;
  font-weight: 600;
}

.log-level.level-info { color: var(--color-info); }
.log-level.level-success { color: var(--color-success); }
.log-level.level-error { color: var(--color-danger); }
.log-level.level-warning { color: var(--color-warning); }

.log-message {
  color: var(--color-text);
}
</style>
