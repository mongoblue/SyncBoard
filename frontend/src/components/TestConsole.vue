<template>
  <el-dialog 
    v-model="visible" 
    title="🛡️ 质量控制中心" 
    width="800px"
    :close-on-click-modal="false"
    :before-close="handleClose"
    class="qa-dialog"
  >
    <div class="dashboard-header">
      <div class="status-card">
        <span class="label">状态</span>
        <span class="value" :class="statusColor">{{ currentStatus }}</span>
      </div>
      <div class="status-card flex-grow">
        <span class="label">执行进度 ({{ finishedCount }} / {{ totalCount }})</span>
        <el-progress 
          :percentage="progressPercentage" 
          :status="progressStatus"
          :stroke-width="10"
          :show-text="false"
          class="custom-progress"
        />
      </div>
    </div>

    <div class="terminal-window" ref="terminalRef">
      <div v-if="logs.length === 0" class="terminal-placeholder">
        <el-icon :size="48"><VideoPlay /></el-icon>
        <p>准备就绪，等待指令...</p>
      </div>
      
      <div v-for="(line, index) in logs" :key="index" class="log-line">
        <span class="line-num">{{ index + 1 }}</span>
        <span class="line-content" v-html="formatLog(line)"></span>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose" :disabled="testing">关闭窗口</el-button>
        
        <el-dropdown split-button type="primary" @click="startTest('default')" @command="startTest" :disabled="testing">
          <span v-if="testing"><el-icon class="is-loading"><Loading /></el-icon> 测试运行中...</span>
          <span v-else>🚀 启动回归测试</span>
          
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="api">🔌 接口测试 (API)</el-dropdown-item>
              <el-dropdown-item command="e2e">🎭 全链路测试 (E2E)</el-dropdown-item>
              <el-dropdown-item command="performance">⚡ 性能压测 (Locust)</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Loading, VideoPlay } from '@element-plus/icons-vue';
import service from '@/utils/request';

const visible = ref(false);
const testing = ref(false);
const logs = ref<string[]>([]);
const totalCount = ref(0);
const finishedCount = ref(0);
const currentStatus = ref('Ready');
const terminalRef = ref<HTMLElement | null>(null);
let qaSocket: WebSocket | null = null;

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

const open = () => {
  visible.value = true;
  connectSocket();
};

const handleClose = () => {
  if (testing.value) {
    ElMessage.warning('请等待测试结束后再关闭');
    return;
  }
  visible.value = false;
};

// WebSocket 连接
const connectSocket = () => {
  if (qaSocket && qaSocket.readyState === WebSocket.OPEN) return;
  const host = window.location.hostname;
  // 简单判断环境，如果不是 localhost 可能需要调整端口逻辑
  const port = (host === 'localhost' || host === '127.0.0.1') ? ':8000' : '';
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  
  qaSocket = new WebSocket(`${protocol}://${host}${port}/ws/qa/dashboard/`);

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
  
  // 4. 结束信号 (最重要：解锁按钮)
  else if (data.message_type === 'test_end') {
    testing.value = false;
    currentStatus.value = data.status;
    logs.value.push(`>>> ${data.status} (Exit Code: ${data.code})`);
    
    if (data.code === 0) {
      ElMessage.success('测试执行成功');
      // 强行拉满进度条
      finishedCount.value = totalCount.value || finishedCount.value; 
    } else {
      ElMessage.error('测试执行存在失败项');
    }
    scrollToBottom();
  }
};

const startTest = async (type: string = 'default') => {
  try {
    logs.value = [];
    testing.value = true;
    currentStatus.value = "启动中...";
    await service.post('/api/qa/run-test/', { test_type: type });
  } catch (e) {
    testing.value = false;
    currentStatus.value = "启动失败";
    ElMessage.error('无法连接到后端服务');
  }
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
    .replace(/PASSED/g, '<span style="color:#67C23A; font-weight:bold">PASSED</span>')
    .replace(/FAILED/g, '<span style="color:#F56C6C; font-weight:bold">FAILED</span>')
    .replace(/ERROR/g, '<span style="color:#F56C6C; font-weight:bold">ERROR</span>')
    .replace(/SKIPPED/g, '<span style="color:#E6A23C">SKIPPED</span>')
    .replace(/collecting .../g, '<span style="color:#409EFF">collecting ...</span>');
  return colored;
};

onUnmounted(() => {
  if (qaSocket) qaSocket.close();
});

defineExpose({ open });
</script>

<style scoped>
.qa-dialog :deep(.el-dialog__body) {
  padding: 10px 20px;
  background-color: #f5f7fa;
}

.dashboard-header {
  display: flex;
  gap: 15px;
  margin-bottom: 15px;
}

.status-card {
  background: white;
  padding: 10px 15px;
  border-radius: 6px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.status-card.flex-grow {
  flex: 1;
}

.label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.value {
  font-size: 16px;
  font-weight: 600;
}

.text-blue { color: #409EFF; }
.text-green { color: #67C23A; }
.text-red { color: #F56C6C; }
.text-gray { color: #909399; }

/* 终端样式 */
.terminal-window {
  background-color: #1e1e1e; /* VS Code 默认背景色 */
  border-radius: 6px;
  height: 450px;
  overflow-y: auto;
  padding: 12px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #d4d4d4;
  border: 1px solid #333;
  box-shadow: inset 0 0 8px rgba(0,0,0,0.2);
}

.terminal-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #5c6370;
  opacity: 0.8;
}

.log-line {
  display: flex;
  word-break: break-all;
}

.line-num {
  color: #4b5563;
  width: 30px;
  flex-shrink: 0;
  text-align: right;
  margin-right: 12px;
  user-select: none;
}

.line-content {
  white-space: pre-wrap; /* 保留空格 */
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  padding-top: 10px;
}
</style>