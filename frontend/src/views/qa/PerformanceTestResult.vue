<template>
  <div class="performance-test-page">
    <!-- 左侧：用例列表和配置 -->
    <div class="left-panel">
      <div class="panel-header">
        <h3>性能测试用例</h3>
        <el-button type="primary" size="small" @click="showCreateDialog">
          <el-icon><Plus /></el-icon>
          新建
        </el-button>
      </div>
      
      <!-- 筛选 -->
      <div class="filter-bar">
        <el-select v-model="filterProject" placeholder="项目" clearable size="small">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-input v-model="searchKeyword" placeholder="搜索" size="small" clearable />
      </div>

      <!-- 用例列表 -->
      <div class="case-list">
        <div
          v-for="caseItem in filteredCases"
          :key="caseItem.id"
          class="case-item"
          :class="{ active: selectedCase?.id === caseItem.id }"
          @click="selectCase(caseItem)"
        >
          <div class="case-header">
            <el-tag :type="getMethodType(caseItem.method)" size="small">{{ caseItem.method }}</el-tag>
            <span class="case-name">{{ caseItem.name }}</span>
            <div class="case-actions" @click.stop>
              <el-button type="primary" link size="small" @click="editCase(caseItem)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button type="danger" link size="small" @click="deleteCase(caseItem)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <div class="case-url">{{ caseItem.url }}</div>
          <div class="case-meta">
            <span><el-icon><User /></el-icon> {{ caseItem.concurrent_users }}用户</span>
            <span><el-icon><Timer /></el-icon> {{ caseItem.duration_seconds }}秒</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：Locust 风格结果展示 -->
    <div class="right-panel">
      <div v-if="!selectedCase" class="empty-state">
        <el-icon><TrendCharts /></el-icon>
        <p>选择左侧用例开始测试</p>
      </div>

      <template v-else>
        <!-- 顶部工具栏 -->
        <div class="toolbar">
          <div class="toolbar-left">
            <h4>{{ selectedCase.name }}</h4>
            <el-tag size="small">{{ selectedCase.url }}</el-tag>
          </div>
          <div class="toolbar-right">
            <el-button 
              v-if="!isRunning" 
              type="primary" 
              @click="startTest"
              :loading="starting"
            >
              <el-icon><VideoPlay /></el-icon>
              开始测试
            </el-button>
            <el-button 
              v-else 
              type="danger" 
              @click="stopTest"
              :loading="stopping"
            >
              <el-icon><CircleClose /></el-icon>
              停止测试
            </el-button>
          </div>
        </div>

        <!-- Locust 风格统计 -->
        <div v-if="isRunning || hasData" class="locust-dashboard">
          <!-- 状态栏 -->
          <div class="status-bar">
            <span class="status" :class="testStatus">
              <el-icon v-if="testStatus === 'running'"><Loading /></el-icon>
              {{ statusText }}
            </span>
            <span class="duration">运行时间: {{ formatDuration(duration) }}</span>
          </div>

          <!-- 统计卡片 -->
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-label">RPS</div>
              <div class="stat-value">{{ currentStats.throughput?.toFixed(1) || '0.0' }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">失败率</div>
              <div class="stat-value" :class="{ 'text-danger': (currentStats.error_rate || 0) > 5 }">
                {{ currentStats.error_rate?.toFixed(2) || '0.00' }}%
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-label">平均响应时间</div>
              <div class="stat-value">{{ formatTime(currentStats.avg_response_time) }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">总请求数</div>
              <div class="stat-value">{{ currentStats.total_requests || 0 }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">并发用户</div>
              <div class="stat-value">{{ currentStats.current_users || selectedCase.concurrent_users }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">失败请求</div>
              <div class="stat-value" :class="{ 'text-danger': (currentStats.failed_requests || 0) > 0 }">
                {{ currentStats.failed_requests || 0 }}
              </div>
            </div>
          </div>

          <!-- Locust 风格统计表格 -->
          <div class="stats-table-container">
            <h5>请求统计</h5>
            <el-table :data="requestStats" size="small" border stripe>
              <el-table-column prop="method" label="Method" width="80" />
              <el-table-column prop="name" label="Name" min-width="150" show-overflow-tooltip />
              <el-table-column prop="num_requests" label="# Requests" width="100" align="right" />
              <el-table-column prop="num_failures" label="# Fails" width="80" align="right">
                <template #default="{ row }">
                  <span :class="{ 'text-danger': row.num_failures > 0 }">{{ row.num_failures }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="median_response_time" label="Median (ms)" width="110" align="right">
                <template #default="{ row }">{{ formatTime(row.median_response_time) }}</template>
              </el-table-column>
              <el-table-column prop="avg_response_time" label="Average (ms)" width="110" align="right">
                <template #default="{ row }">{{ formatTime(row.avg_response_time) }}</template>
              </el-table-column>
              <el-table-column prop="min_response_time" label="Min (ms)" width="90" align="right">
                <template #default="{ row }">{{ formatTime(row.min_response_time) }}</template>
              </el-table-column>
              <el-table-column prop="max_response_time" label="Max (ms)" width="90" align="right">
                <template #default="{ row }">{{ formatTime(row.max_response_time) }}</template>
              </el-table-column>
              <el-table-column prop="rps" label="RPS" width="80" align="right">
                <template #default="{ row }">{{ row.rps?.toFixed(1) || '0.0' }}</template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 实时图表 -->
          <div class="charts-container">
            <div ref="chartRef" class="chart"></div>
          </div>

          <!-- 失败请求 -->
          <div v-if="failures.length > 0" class="failures-container">
            <h5>失败请求</h5>
            <el-table :data="failures" size="small" border>
              <el-table-column prop="method" label="Method" width="80" />
              <el-table-column prop="name" label="Name" min-width="150" />
              <el-table-column prop="error" label="Error" />
              <el-table-column prop="occurrences" label="Occurrences" width="100" />
            </el-table>
          </div>
        </div>

        <!-- 未开始状态 -->
        <div v-else class="ready-state">
          <el-icon><VideoPlay /></el-icon>
          <p>点击"开始测试"按钮启动 Locust 压力测试</p>
          <div class="test-config">
            <div class="config-item">
              <label>并发用户:</label>
              <span>{{ selectedCase.concurrent_users }}</span>
            </div>
            <div class="config-item">
              <label>持续时间:</label>
              <span>{{ selectedCase.duration_seconds }} 秒</span>
            </div>
            <div class="config-item">
              <label>请求方法:</label>
              <span>{{ selectedCase.method }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑用例' : '新建用例'" width="600px">
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="项目" prop="project">
          <el-select v-model="form.project" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="URL" prop="url">
          <el-input v-model="form.url" />
        </el-form-item>
        <el-form-item label="方法" prop="method">
          <el-select v-model="form.method">
            <el-option label="GET" value="GET" />
            <el-option label="POST" value="POST" />
            <el-option label="PUT" value="PUT" />
            <el-option label="DELETE" value="DELETE" />
          </el-select>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="并发用户" prop="concurrent_users">
              <el-input-number v-model="form.concurrent_users" :min="1" :max="10000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="持续时间" prop="duration_seconds">
              <el-input-number v-model="form.duration_seconds" :min="1" :max="3600" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="请求头">
          <el-input v-model="form.headers" type="textarea" :rows="3" placeholder='{"Content-Type": "application/json"}' />
        </el-form-item>
        <el-form-item label="请求体">
          <el-input v-model="form.body" type="textarea" :rows="5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  Plus, VideoPlay, CircleClose, Loading, Timer, User, TrendCharts
} from '@element-plus/icons-vue';
import * as echarts from 'echarts';
import service from '@/utils/request';
import { buildWsUrl } from '@/composables/wsHost';

// 数据
const cases = ref<any[]>([]);
const projects = ref<any[]>([]);
const selectedCase = ref<any>(null);
const searchKeyword = ref('');
const filterProject = ref('');

// 状态
const isRunning = ref(false);
const starting = ref(false);
const stopping = ref(false);
const testStatus = ref('ready'); // ready, running, stopped
const duration = ref(0);
const currentStats = ref<any>({});
const requestStats = ref<any[]>([]);
const failures = ref<any[]>([]);
const hasData = ref(false);
const executionId = ref<number | null>(null);

// 图表
const chartRef = ref<HTMLElement>();
let chartInstance: echarts.ECharts | null = null;
const chartData = ref<any[]>([]);

// WebSocket
let ws: WebSocket | null = null;
let durationTimer: any = null;

// 表单
const dialogVisible = ref(false);
const isEdit = ref(false);
const submitting = ref(false);
const formRef = ref();
const form = reactive({
  id: null,
  name: '',
  project: null,
  url: '',
  method: 'GET',
  headers: '{}',
  body: '',
  concurrent_users: 10,
  duration_seconds: 60
});

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  project: [{ required: true, message: '请选择项目', trigger: 'change' }],
  url: [{ required: true, message: '请输入URL', trigger: 'blur' }],
  method: [{ required: true, message: '请选择方法', trigger: 'change' }],
  concurrent_users: [{ required: true, message: '请输入并发数', trigger: 'blur' }],
  duration_seconds: [{ required: true, message: '请输入持续时间', trigger: 'blur' }]
};

// 计算属性
const filteredCases = computed(() => {
  let result = cases.value;
  if (filterProject.value) {
    result = result.filter((c: any) => c.project_id === filterProject.value);
  }
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase();
    result = result.filter((c: any) => c.name.toLowerCase().includes(keyword));
  }
  return result;
});

const statusText = computed(() => {
  const texts: Record<string, string> = {
    ready: '准备就绪',
    running: '运行中',
    stopped: '已停止'
  };
  return texts[testStatus.value] || '未知';
});

// 方法
const loadCases = async () => {
  try {
    const res = await service.get('/qa/performance-cases/');
    cases.value = res.results || res;
  } catch (error) {
    ElMessage.error('加载用例失败');
  }
};

const loadProjects = async () => {
  try {
    const res = await service.get('/projects/');
    projects.value = res.results || res;
  } catch (error) {
    console.error('加载项目失败:', error);
  }
};

const selectCase = (caseItem: any) => {
  selectedCase.value = caseItem;
  // 重置状态
  testStatus.value = 'ready';
  isRunning.value = false;
  hasData.value = false;
  currentStats.value = {};
  requestStats.value = [];
  failures.value = [];
  chartData.value = [];
  duration.value = 0;
};

const startTest = async () => {
  if (!selectedCase.value) return;
  
  starting.value = true;
  try {
    const res = await service.post(`/qa/performance-cases/${selectedCase.value.id}/execute/`);
    
    testStatus.value = 'running';
    isRunning.value = true;
    hasData.value = true;
    executionId.value = res.execution_id;
    
    // 开始计时
    duration.value = 0;
    durationTimer = setInterval(() => {
      duration.value++;
    }, 1000);
    
    // 连接 WebSocket
    connectWebSocket(res.execution_id);
    
    // 初始化图表
    nextTick(() => {
      setTimeout(() => initChart(), 300);
    });
    
    ElMessage.success('测试已启动');
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '启动失败');
  } finally {
    starting.value = false;
  }
};

const stopTest = async () => {
  if (!selectedCase.value || !executionId.value) return;
  
  stopping.value = true;
  try {
    await service.post(`/qa/performance-cases/${selectedCase.value.id}/stop/`, {
      execution_id: executionId.value
    });
    testStatus.value = 'stopped';
    isRunning.value = false;
    executionId.value = null;
    
    if (durationTimer) {
      clearInterval(durationTimer);
      durationTimer = null;
    }
    
    disconnectWebSocket();
    ElMessage.success('测试已停止');
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '停止失败');
  } finally {
    stopping.value = false;
  }
};

const connectWebSocket = (executionId: number) => {
  if (ws) ws.close();

  ws = new WebSocket(buildWsUrl(`/ws/qa/performance/${executionId}/`));
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      currentStats.value = data;
      
      // 更新请求统计
      requestStats.value = [{
        method: selectedCase.value?.method,
        name: selectedCase.value?.url,
        num_requests: data.total_requests || 0,
        num_failures: data.failed_requests || 0,
        median_response_time: data.p50_response_time || 0,
        avg_response_time: data.avg_response_time || 0,
        min_response_time: data.min_response_time || 0,
        max_response_time: data.max_response_time || 0,
        rps: data.throughput || 0
      }];
      
      // 更新图表数据
      chartData.value.push({
        time: new Date().toLocaleTimeString(),
        rps: data.throughput || 0,
        avgResponseTime: data.avg_response_time || 0,
        errorRate: data.error_rate || 0
      });
      
      if (chartData.value.length > 100) {
        chartData.value.shift();
      }
      
      updateChart();
    } catch (e) {
      console.error('解析数据失败:', e);
    }
  };
  
  ws.onclose = () => {
    console.log('WebSocket 关闭');
  };
};

const disconnectWebSocket = () => {
  if (ws) {
    ws.close();
    ws = null;
  }
};

const initChart = () => {
  if (!chartRef.value) {
    console.log('Chart ref not ready');
    return;
  }
  
  // 检查容器尺寸
  const rect = chartRef.value.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) {
    console.log('Chart container has zero size, retrying...');
    setTimeout(initChart, 500);
    return;
  }
  
  if (chartInstance) {
    chartInstance.dispose();
  }
  
  chartInstance = echarts.init(chartRef.value);
  
  const option = {
    title: { text: '实时性能指标', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { data: ['RPS', '响应时间(ms)', '错误率(%)'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '15%', containLabel: true },
    xAxis: { 
      type: 'category', 
      boundaryGap: false, 
      data: chartData.value.map(d => d.time),
      axisLabel: { rotate: 30, fontSize: 10 }
    },
    yAxis: [
      { type: 'value', name: 'RPS', position: 'left', min: 0 },
      { type: 'value', name: '响应时间(ms)', position: 'right', min: 0 }
    ],
    series: [
      { 
        name: 'RPS', 
        type: 'line', 
        smooth: true, 
        data: chartData.value.map(d => d.rps),
        itemStyle: { color: '#0F766E' },
        areaStyle: { opacity: 0.1 }
      },
      {
        name: '响应时间(ms)',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: chartData.value.map(d => d.avgResponseTime),
        itemStyle: { color: '#0969DA' }
      },
      {
        name: '错误率(%)',
        type: 'line',
        smooth: true,
        data: chartData.value.map(d => d.errorRate),
        itemStyle: { color: '#CF222E' }
      }
    ],
    animation: true
  };
  
  chartInstance.setOption(option);
  console.log('Chart initialized successfully');
};

const updateChart = () => {
  if (!chartInstance) {
    console.log('Chart instance not ready');
    return;
  }
  
  if (chartData.value.length === 0) return;
  
  chartInstance.setOption({
    xAxis: { data: chartData.value.map(d => d.time) },
    series: [
      { data: chartData.value.map(d => d.rps) },
      { data: chartData.value.map(d => d.avgResponseTime) },
      { data: chartData.value.map(d => d.errorRate) }
    ]
  });
};

// 窗口大小改变时重新调整图表
const handleResize = () => {
  if (chartInstance) {
    chartInstance.resize();
  }
};

// 表单方法
const showCreateDialog = () => {
  isEdit.value = false;
  Object.assign(form, {
    id: null, name: '', project: null, url: '', method: 'GET',
    headers: '{}', body: '', concurrent_users: 10, duration_seconds: 60
  });
  dialogVisible.value = true;
};

const editCase = (caseItem: any) => {
  isEdit.value = true;
  Object.assign(form, {
    id: caseItem.id,
    name: caseItem.name,
    project: caseItem.project,
    url: caseItem.url,
    method: caseItem.method,
    headers: JSON.stringify(caseItem.headers || {}, null, 2),
    body: caseItem.body || '',
    concurrent_users: caseItem.concurrent_users,
    duration_seconds: caseItem.duration_seconds
  });
  dialogVisible.value = true;
};

const deleteCase = async (caseItem: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用例 "${caseItem.name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    await service.delete(`/qa/performance-cases/${caseItem.id}/`);
    ElMessage.success('删除成功');
    
    // 如果删除的是当前选中的用例，清空选中状态
    if (selectedCase.value?.id === caseItem.id) {
      selectedCase.value = null;
    }
    
    loadCases();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '删除失败');
    }
  }
};

const submitForm = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  
  submitting.value = true;
  try {
    let headers = {};
    try {
      headers = form.headers ? JSON.parse(form.headers) : {};
    } catch (e) {
      ElMessage.error('请求头格式错误');
      return;
    }
    
    const data = { ...form, headers, body: form.body };
    
    if (isEdit.value) {
      await service.put(`/qa/performance-cases/${form.id}/`, data);
    } else {
      await service.post('/qa/performance-cases/', data);
    }
    
    ElMessage.success(isEdit.value ? '更新成功' : '创建成功');
    dialogVisible.value = false;
    loadCases();
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '操作失败');
  } finally {
    submitting.value = false;
  }
};

// 工具函数
const getMethodType = (method: string) => {
  const types: Record<string, string> = {
    GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info'
  };
  return types[method] || 'info';
};

const formatTime = (ms: number) => {
  if (!ms || ms === 0) return '0';
  if (ms < 1000) return Math.round(ms).toString();
  return (ms / 1000).toFixed(2) + 's';
};

const formatDuration = (seconds: number) => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

onMounted(() => {
  loadCases();
  loadProjects();
  window.addEventListener('resize', handleResize);
});

// 组件卸载时清理
const cleanup = () => {
  window.removeEventListener('resize', handleResize);
  disconnectWebSocket();
  if (durationTimer) {
    clearInterval(durationTimer);
    durationTimer = null;
  }
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
};

// 监听选中用例变化，确保图表正确初始化
watch(() => selectedCase.value, (newCase) => {
  if (newCase && isRunning.value) {
    nextTick(() => {
      setTimeout(() => initChart(), 300);
    });
  }
});
</script>

<style scoped>
.performance-test-page {
  display: flex;
  height: calc(100vh - 100px);
  gap: 16px;
}

/* 左侧面板 */
.left-panel {
  width: 320px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: 16px;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.panel-header h3 {
  margin: 0;
  font: 600 14px/1.3 var(--font-heading);
  color: var(--color-text);
}

.filter-bar { display: flex; gap: 8px; margin-bottom: 12px; }

.case-list { flex: 1; overflow-y: auto; }

.case-item {
  padding: 10px 12px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast);
}

.case-item:hover {
  border-color: var(--color-border);
  background: var(--color-surface-hover);
}

.case-item.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.case-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.case-name {
  font-weight: 500;
  font-size: 13px;
  color: var(--color-text);
  flex: 1;
}

.case-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.case-item:hover .case-actions { opacity: 1; }

.case-url {
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.case-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.case-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 右侧面板 */
.right-panel {
  flex: 1;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: 20px 24px;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-tertiary);
}

.empty-state .el-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

/* 工具栏 */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border-light);
}

.toolbar-left h4 {
  margin: 0 0 4px 0;
  font: 600 16px/1.3 var(--font-heading);
  color: var(--color-text);
}

/* Locust 仪表板 */
.locust-dashboard {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  font-size: 13px;
}

.status.running { color: var(--color-success); }
.status.stopped { color: var(--color-text-tertiary); }

.status .el-icon { animation: rotating 2s linear infinite; }

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.duration {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* 统计网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  text-align: center;
}

.stat-card .stat-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
  font-weight: 500;
}

.stat-card .stat-value {
  font: 600 24px/1.2 var(--font-heading);
  color: var(--color-text);
}

.stat-card .stat-value.text-danger { color: var(--color-danger); }

/* 统计表格 */
.stats-table-container,
.failures-container {
  margin-bottom: 20px;
}

.stats-table-container h5,
.failures-container h5 {
  margin: 0 0 8px 0;
  font: 600 13px/1.3 var(--font-heading);
  color: var(--color-text);
}

/* 图表容器 */
.charts-container {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: 16px;
  margin-bottom: 20px;
}

.chart {
  width: 100%;
  height: 280px;
}

/* 准备状态 */
.ready-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--color-text-tertiary);
}

.ready-state .el-icon {
  font-size: 40px;
  margin-bottom: 12px;
  color: var(--color-primary);
}

.test-config {
  margin-top: 20px;
  display: flex;
  gap: 24px;
}

.config-item { text-align: center; }

.config-item label {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.config-item span {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

/* 通用 */
.text-danger {
  color: var(--color-danger) !important;
}
</style>
