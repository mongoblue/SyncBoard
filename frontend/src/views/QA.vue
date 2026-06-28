<template>
  <div class="qa-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">质量中心</h1>
        <p class="page-subtitle">测试用例、自动化执行与质量指标的统一入口</p>
      </div>
      <div class="header-actions">
        <el-button type="warning" @click="showDataFactoryDialog = true">
          <el-icon><MagicStick /></el-icon>
          生成测试数据
        </el-button>
        <el-button @click="clearLogs" :disabled="logs.length === 0">
          <el-icon><Delete /></el-icon>
          清空日志
        </el-button>
        <el-dropdown split-button type="primary" @click="startTest('regression')" @command="startTest" :disabled="testing">
          <span v-if="testing"><el-icon class="is-loading"><Loading /></el-icon> 测试中...</span>
          <span v-else><el-icon><VideoPlay /></el-icon> 启动回归测试</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="regression">完整回归测试</el-dropdown-item>
              <el-dropdown-item command="api">接口测试</el-dropdown-item>
              <el-dropdown-item command="e2e">全链路测试</el-dropdown-item>
              <el-dropdown-item command="performance">性能压测</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 状态卡片 -->
    <div class="status-cards">
      <el-card class="status-card" shadow="never">
        <div class="status-label">当前状态</div>
        <div class="status-value" :class="statusColor">{{ currentStatus }}</div>
      </el-card>
      <el-card class="status-card progress-card" shadow="never">
        <div class="status-label">执行进度 ({{ finishedCount }} / {{ totalCount }})</div>
        <el-progress
          :percentage="progressPercentage"
          :status="progressStatus"
          :stroke-width="12"
          class="custom-progress"
        />
      </el-card>
    </div>

    <!-- 功能入口卡片 -->
    <div class="feature-cards">
      <el-card class="feature-card" shadow="hover" @click="goToApiCases">
        <div class="feature-icon" style="background: var(--color-info-bg); color: var(--color-info);"><el-icon :size="28"><Connection /></el-icon></div>
        <div class="feature-title">API 测试用例</div>
        <div class="feature-desc">创建和管理 API 接口测试用例</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="goToUiCases">
        <div class="feature-icon" style="background: var(--color-success-bg); color: var(--color-success);"><el-icon :size="28"><Monitor /></el-icon></div>
        <div class="feature-title">UI 测试用例</div>
        <div class="feature-desc">基于 Playwright 的 E2E 自动化测试</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="goToPerformanceCases">
        <div class="feature-icon" style="background: var(--color-warning-bg); color: var(--color-warning);"><el-icon :size="28"><Odometer /></el-icon></div>
        <div class="feature-title">性能测试</div>
        <div class="feature-desc">并发压测和性能指标分析</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="goToTestResults">
        <div class="feature-icon" style="background: var(--color-primary-bg); color: var(--color-primary);"><el-icon :size="28"><DataAnalysis /></el-icon></div>
        <div class="feature-title">测试结果</div>
        <div class="feature-desc">查看和管理测试执行历史</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="showDataFactoryDialog = true">
        <div class="feature-icon" style="background: var(--color-danger-bg); color: var(--color-danger);"><el-icon :size="28"><MagicStick /></el-icon></div>
        <div class="feature-title">数据工厂</div>
        <div class="feature-desc">快速生成测试数据</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="startTest('regression')">
        <div class="feature-icon" style="background: var(--color-primary-bg); color: var(--color-primary);"><el-icon :size="28"><VideoPlay /></el-icon></div>
        <div class="feature-title">回归测试</div>
        <div class="feature-desc">运行完整的测试套件</div>
      </el-card>
    </div>

    <!-- 提示信息 -->
    <el-alert
      v-if="showE2EWarning"
      type="warning"
      :closable="false"
      style="margin-bottom: 15px"
    >
      <template #title>
        <span>全链路测试 (E2E) 需要浏览器环境支持</span>
      </template>
      <div>
        <p>如果在 Windows 上运行遇到权限错误，请尝试：</p>
        <ul style="margin: 5px 0; padding-left: 20px">
          <li>以管理员身份运行后端服务</li>
          <li>检查杀毒软件是否阻止了浏览器启动</li>
          <li>使用接口测试代替全链路测试</li>
        </ul>
      </div>
    </el-alert>

    <!-- 终端窗口 -->
    <el-card class="terminal-card" shadow="never">
      <template #header>
        <div class="terminal-header">
          <span><el-icon><Monitor /></el-icon> 测试日志</span>
          <el-tag v-if="testing" type="warning" effect="dark">运行中</el-tag>
          <el-tag v-else-if="logs.length > 0" type="success" effect="dark">已完成</el-tag>
          <el-tag v-else type="info">就绪</el-tag>
        </div>
      </template>
      <div class="terminal-window" ref="terminalRef">
        <div v-if="logs.length === 0" class="terminal-placeholder">
          <el-icon :size="64"><VideoPlay /></el-icon>
          <p>准备就绪，点击上方按钮启动测试</p>
        </div>
        <div v-for="(line, index) in logs" :key="index" class="log-line">
          <span class="line-num">{{ index + 1 }}</span>
          <span class="line-content" v-html="formatLog(line)"></span>
        </div>
      </div>
    </el-card>

    <!-- 数据工厂弹窗 -->
    <el-dialog v-model="showDataFactoryDialog" title="生成测试数据" width="400px">
      <el-form :model="dataFactoryForm" label-position="top">
        <el-form-item label="目标列">
          <el-select v-model="dataFactoryForm.columnId" placeholder="选择要生成数据的列" style="width: 100%">
            <el-option
              v-for="col in columns"
              :key="col.id"
              :label="col.title"
              :value="col.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="生成数量">
          <el-input-number v-model="dataFactoryForm.count" :min="1" :max="100" style="width: 100%" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="dataFactoryForm.clearOld">生成前清空该列现有数据</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDataFactoryDialog = false">取消</el-button>
        <el-button type="primary" :loading="generatingData" @click="generateTestData">
          <el-icon><MagicStick /></el-icon>
          开始生成
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Loading, VideoPlay, Delete, MagicStick, Connection, Monitor, Odometer, DataAnalysis } from '@element-plus/icons-vue';
import service from '@/utils/request';
import { useBoardStore } from '@/stores/board';
import { buildWsUrl } from '@/composables/wsHost';

const route = useRoute();
const router = useRouter();
const boardStore = useBoardStore();

const visible = ref(true);
const testing = ref(false);
const logs = ref<string[]>([]);
const totalCount = ref(0);
const finishedCount = ref(0);
const currentStatus = ref('Ready');
const terminalRef = ref<HTMLElement | null>(null);
const showE2EWarning = ref(false);
let qaSocket: WebSocket | null = null;

const currentProjectId = computed(() => {
  const routeProjectId = route.params.projectId;
  return String(Array.isArray(routeProjectId) ? routeProjectId[0] : routeProjectId || boardStore.currentProject?.id || '');
});

// 数据工厂相关
const showDataFactoryDialog = ref(false);
const generatingData = ref(false);
const columns = computed(() => boardStore.Columns);
const dataFactoryForm = ref({
  columnId: '',
  count: 10,
  clearOld: false,
});

// 生成测试数据
const generateTestData = async () => {
  if (!dataFactoryForm.value.columnId) {
    ElMessage.warning('请选择目标列');
    return;
  }

  generatingData.value = true;
  try {
    const response = await service.post('/qa/data-factory/', {
      column_id: dataFactoryForm.value.columnId,
      count: dataFactoryForm.value.count,
      clear_old: dataFactoryForm.value.clearOld,
    });
    ElMessage.success(response.msg || '测试数据生成成功');
    showDataFactoryDialog.value = false;
    // 刷新看板数据
    const projectId = currentProjectId.value;
    if (projectId) {
      await boardStore.fetchColumns(projectId);
    }
  } catch (error: any) {
    const msg = error.response?.data?.error || '生成失败';
    ElMessage.error(msg);
  } finally {
    generatingData.value = false;
  }
};

// 计算进度条百分比
const progressPercentage = computed(() => {
  if (totalCount.value === 0) return 0;
  return Math.min(100, Math.floor((finishedCount.value / totalCount.value) * 100));
});

// 计算状态颜色
const statusColor = computed(() => {
  if (testing.value) return 'text-blue';
  if (currentStatus.value.includes('失败') || currentStatus.value.includes('异常')) return 'text-red';
  if (currentStatus.value.includes('完成')) return 'text-green';
  return 'text-gray';
});

const progressStatus = computed(() => {
  if (currentStatus.value.includes('失败')) return 'exception';
  if (progressPercentage.value === 100) return 'success';
  return '';
});

// WebSocket 连接
const connectSocket = () => {
  if (qaSocket && qaSocket.readyState === WebSocket.OPEN) return;
  const path = currentProjectId.value
    ? `/ws/qa/dashboard/${currentProjectId.value}/`
    : '/ws/qa/dashboard/';

  qaSocket = new WebSocket(buildWsUrl(path));

  qaSocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleServerEvent(data);
  };
};

// 处理后端事件
const handleServerEvent = (data: any) => {
  // 1. 开始信号
  if (data.message_type === 'test_start') {
    testing.value = true;
    logs.value = [];
    totalCount.value = 0;
    finishedCount.value = 0;
    currentStatus.value = '运行中...';
    logs.value.push(`>>> ${data.msg}`);
  }

  // 2. 元数据（收到总数）
  else if (data.message_type === 'test_meta') {
    totalCount.value = data.total;
    logs.value.push(`>>> 识别到 ${data.total} 个测试用例`);
  }

  // 3. 日志流
  else if (data.message_type === 'test_log') {
    const line = data.log;
    logs.value.push(line);

    // 简单的进度推断：每当看到 PASSED 或 FAILED，计数+1
    if (line.includes('PASSED') || line.includes('FAILED')) {
      finishedCount.value++;
    }
    scrollToBottom();
  }

  // 4. 结束信号
  else if (data.message_type === 'test_end') {
    testing.value = false;
    currentStatus.value = data.status;
    logs.value.push(`>>> ${data.status} (Exit Code: ${data.code})`);

    if (data.code === 0) {
      ElMessage.success('测试执行成功');
      finishedCount.value = totalCount.value || finishedCount.value;
    } else {
      ElMessage.error('测试执行存在失败项');
    }
    scrollToBottom();
  }
};

const startTest = async (type: string = 'default') => {
  // 显示 E2E 警告
  showE2EWarning.value = type === 'e2e' || type === 'regression';
  try {
    logs.value = [];
    testing.value = true;
    currentStatus.value = '启动中...';
    await service.post('/qa/run-test/', {
      test_type: type,
      ...(currentProjectId.value ? { project_id: currentProjectId.value } : {}),
    });
  } catch (e) {
    testing.value = false;
    currentStatus.value = '启动失败';
    ElMessage.error('无法连接到后端服务');
  }
};

// 跳转到 API 测试用例页面
const goToApiCases = () => {
  router.push({
    name: 'ApiCaseList',
    query: { project: boardStore.currentProject?.id }
  });
};

// 跳转到 UI 测试用例页面
const goToUiCases = () => {
  router.push({
    name: 'UiCaseList',
    query: { project: boardStore.currentProject?.id }
  });
};

const goToPerformanceCases = () => {
  router.push({
    name: 'PerformanceTestResults',
    query: { project: boardStore.currentProject?.id }
  });
};

const goToTestResults = () => {
  router.push({
    name: 'TestResultList',
    query: { project: boardStore.currentProject?.id }
  });
};

const clearLogs = () => {
  logs.value = [];
  totalCount.value = 0;
  finishedCount.value = 0;
  currentStatus.value = 'Ready';
};

const scrollToBottom = () => {
  nextTick(() => {
    if (terminalRef.value) {
      terminalRef.value.scrollTop = terminalRef.value.scrollHeight;
    }
  });
};

// 简单的日志着色
const formatLog = (line: string) => {
  if (!line) return '';
  let colored = line
    .replace(/PASSED/g, '<span style="color:var(--color-success); font-weight:600">PASSED</span>')
    .replace(/FAILED/g, '<span style="color:var(--color-danger); font-weight:600">FAILED</span>')
    .replace(/ERROR/g, '<span style="color:var(--color-danger); font-weight:600">ERROR</span>')
    .replace(/SKIPPED/g, '<span style="color:var(--color-warning)">SKIPPED</span>')
    .replace(/collecting .../g, '<span style="color:var(--color-primary)">collecting ...</span>');
  return colored;
};

onMounted(() => {
  connectSocket();
  // 加载项目列数据
  const projectId = route.params.projectId as string;
  if (projectId) {
    boardStore.fetchColumns(projectId);
  }
});

onUnmounted(() => {
  if (qaSocket) qaSocket.close();
});
</script>

<style scoped>
.qa-page { padding: 0; }

.header-actions {
  display: flex;
  gap: 8px;
}

.status-cards {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.status-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.status-card :deep(.el-card__body) { padding: 16px 20px; }

.status-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}

.status-value {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 600;
}

.text-blue { color: var(--color-primary); }
.text-green { color: var(--color-success); }
.text-red { color: var(--color-danger); }
.text-gray { color: var(--color-text-tertiary); }

.progress-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

/* 功能入口卡片 */
.feature-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.feature-card {
  cursor: pointer;
  text-align: center;
  padding: 20px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.feature-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.feature-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  margin: 0 auto 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.feature-title {
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 4px;
}

.feature-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.terminal-card {
  margin-bottom: 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.terminal-window {
  background-color: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  height: 480px;
  overflow-y: auto;
  padding: 12px 16px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text);
}

.terminal-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  gap: 12px;
}

.log-line {
  display: flex;
  word-break: break-all;
  margin-bottom: 2px;
}

.line-num {
  color: var(--color-text-tertiary);
  width: 36px;
  flex-shrink: 0;
  text-align: right;
  margin-right: 12px;
  user-select: none;
}

.line-content {
  white-space: pre-wrap;
}
</style>
