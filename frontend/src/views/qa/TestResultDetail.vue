<template>
  <div class="test-result-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <h2>测试结果详情</h2>
      </div>
      <div class="header-actions">
        <el-button @click="loadData">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <div v-if="result" class="detail-content">
      <!-- 基本信息卡片 -->
      <el-card class="info-card">
        <template #header>
          <div class="card-header">
            <span>基本信息</span>
            <el-tag :type="getStatusType(result.status)" size="large">
              {{ result.status_display }}
            </el-tag>
          </div>
        </template>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="测试名称">{{ result.name }}</el-descriptions-item>
          <el-descriptions-item label="测试类型">
            <el-tag :type="getTestTypeType(result.test_type)">
              {{ result.test_type_display }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="所属项目">{{ result.project_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="执行人员">{{ result.executed_by_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDate(result.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatDate(result.completed_at) }}</el-descriptions-item>
          <el-descriptions-item label="执行时长">
            {{ result.duration_ms ? formatDuration(result.duration_ms) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(result.created_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 执行摘要 -->
      <el-card v-if="executionSummary" class="summary-card">
        <template #header>
          <span>执行摘要</span>
        </template>
        <el-row :gutter="20">
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-value">{{ executionSummary.total }}</div>
              <div class="metric-label">总用例数</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-value text-success">{{ executionSummary.passed }}</div>
              <div class="metric-label">通过</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-value text-danger">{{ executionSummary.failed }}</div>
              <div class="metric-label">失败</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-value">{{ executionSummary.pass_rate }}%</div>
              <div class="metric-label">通过率</div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- 性能测试专用指标 -->
      <el-card v-if="isPerformanceTest && performanceMetrics" class="performance-metrics-card">
        <template #header>
          <div class="card-header">
            <span>📊 性能指标</span>
            <el-tag type="warning" size="small">性能测试</el-tag>
          </div>
        </template>
        
        <!-- 核心指标卡片 -->
        <el-row :gutter="16" class="perf-metrics-row">
          <el-col :span="4">
            <div class="perf-metric-card rps">
              <div class="perf-metric-icon">⚡</div>
              <div class="perf-metric-value">{{ performanceMetrics.throughput?.toFixed(1) || '0.0' }}</div>
              <div class="perf-metric-label">RPS (每秒请求)</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="perf-metric-card avg-time">
              <div class="perf-metric-icon">⏱️</div>
              <div class="perf-metric-value">{{ formatTime(performanceMetrics.avg_response_time) }}</div>
              <div class="perf-metric-label">平均响应时间</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="perf-metric-card error-rate" :class="{ 'high-error': (performanceMetrics.error_rate || 0) > 5 }">
              <div class="perf-metric-icon">⚠️</div>
              <div class="perf-metric-value">{{ performanceMetrics.error_rate?.toFixed(2) || '0.00' }}%</div>
              <div class="perf-metric-label">错误率</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="perf-metric-card total-req">
              <div class="perf-metric-icon">📈</div>
              <div class="perf-metric-value">{{ performanceMetrics.total_requests || 0 }}</div>
              <div class="perf-metric-label">总请求数</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="perf-metric-card success-req">
              <div class="perf-metric-icon">✅</div>
              <div class="perf-metric-value">{{ performanceMetrics.successful_requests || 0 }}</div>
              <div class="perf-metric-label">成功请求</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="perf-metric-card failed-req">
              <div class="perf-metric-icon">❌</div>
              <div class="perf-metric-value">{{ performanceMetrics.failed_requests || 0 }}</div>
              <div class="perf-metric-label">失败请求</div>
            </div>
          </el-col>
        </el-row>

        <!-- 响应时间分布 -->
        <div class="response-time-section">
          <div class="section-title">
            <el-icon><Timer /></el-icon>
            响应时间分布
          </div>
          <el-row :gutter="16">
            <el-col :span="4">
              <div class="time-distribution-item">
                <div class="time-label">最小</div>
                <div class="time-value">{{ formatTime(performanceMetrics.min_response_time) }}</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="time-distribution-item">
                <div class="time-label">P50 (中位数)</div>
                <div class="time-value">{{ formatTime(performanceMetrics.p50_response_time) }}</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="time-distribution-item">
                <div class="time-label">P90</div>
                <div class="time-value">{{ formatTime(performanceMetrics.p90_response_time) }}</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="time-distribution-item">
                <div class="time-label">P95</div>
                <div class="time-value">{{ formatTime(performanceMetrics.p95_response_time) }}</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="time-distribution-item">
                <div class="time-label">P99</div>
                <div class="time-value">{{ formatTime(performanceMetrics.p99_response_time) }}</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="time-distribution-item">
                <div class="time-label">最大</div>
                <div class="time-value">{{ formatTime(performanceMetrics.max_response_time) }}</div>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 测试配置信息 -->
        <div class="test-config-section">
          <div class="section-title">
            <el-icon><Setting /></el-icon>
            测试配置
          </div>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="并发用户数">{{ result.concurrent_users || '-' }}</el-descriptions-item>
            <el-descriptions-item label="测试时长">{{ result.duration_ms ? formatDuration(result.duration_ms) : '-' }}</el-descriptions-item>
            <el-descriptions-item label="目标URL">{{ performanceMetrics.url || '-' }}</el-descriptions-item>
            <el-descriptions-item label="请求方法">{{ performanceMetrics.method || '-' }}</el-descriptions-item>
            <el-descriptions-item label="测试状态">{{ performanceMetrics.state || result.status }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatDate(performanceMetrics.start_time) }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 错误详情 -->
        <div v-if="performanceMetrics.errors && performanceMetrics.errors.length > 0" class="errors-section">
          <div class="section-title">
            <el-icon><Warning /></el-icon>
            错误详情 ({{ performanceMetrics.errors.length }} 种)
          </div>
          <el-table :data="performanceMetrics.errors" size="small" border>
            <el-table-column label="错误信息" prop="message" min-width="300" show-overflow-tooltip />
            <el-table-column label="出现次数" prop="count" width="100" align="center" />
          </el-table>
        </div>
      </el-card>

      <!-- 用例执行详情 -->
      <el-card v-if="caseResults.length > 0" class="cases-card">
        <template #header>
          <div class="card-header">
            <span>用例执行详情 ({{ caseResults.length }} 个)</span>
          </div>
        </template>
        
        <el-collapse v-model="activeCaseIndex">
          <el-collapse-item
            v-for="(caseResult, index) in caseResults"
            :key="index"
            :name="index"
          >
            <template #title>
              <div class="case-header">
                <el-tag :type="caseResult.passed ? 'success' : 'danger'" size="small" class="case-status">
                  {{ caseResult.passed ? '通过' : '失败' }}
                </el-tag>
                <span class="case-name">{{ caseResult.case_name || `用例 #${caseResult.case_id}` }}</span>
                <span class="case-type">[{{ caseResult.request?.method || 'API' }}]</span>
                <span class="case-time">{{ caseResult.response_time_ms }}ms</span>
              </div>
            </template>

            <div class="case-detail">
              <!-- UI 测试步骤 -->
              <div v-if="caseResult.type === 'ui' && caseResult.steps && caseResult.steps.length > 0" class="detail-section">
                <div class="section-title">
                  <el-icon><List /></el-icon>
                  执行步骤 ({{ caseResult.steps.length }} 个)
                </div>
                <el-timeline>
                  <el-timeline-item
                    v-for="step in caseResult.steps"
                    :key="step.step_number"
                    :type="step.status === 'passed' ? 'success' : 'danger'"
                    :icon="step.status === 'passed' ? CircleCheck : CircleClose"
                  >
                    <div class="step-item">
                      <div class="step-header">
                        <span class="step-number">步骤 {{ step.step_number }}</span>
                        <el-tag size="small" :type="getActionType(step.action)">{{ step.action }}</el-tag>
                        <span v-if="step.selector" class="step-selector">{{ step.selector }}</span>
                        <span v-if="step.value" class="step-value">{{ step.value }}</span>
                      </div>
                      <div v-if="step.logs && step.logs.length > 0" class="step-logs">
                        <div v-for="(log, idx) in step.logs" :key="idx" class="log-line">{{ log }}</div>
                      </div>
                    </div>
                  </el-timeline-item>
                </el-timeline>
              </div>

              <!-- 请求信息 (API 测试) -->
              <div v-if="caseResult.type !== 'ui'" class="detail-section">
                <div class="section-title">
                  <el-icon><Upload /></el-icon>
                  请求信息
                </div>
                <div class="code-block">
                  <div class="request-line">
                    <span class="method" :class="caseResult.request?.method?.toLowerCase()">{{ caseResult.request?.method }}</span>
                    <span class="url">{{ caseResult.request?.url }}</span>
                  </div>
                  <div v-if="caseResult.request?.headers && Object.keys(caseResult.request.headers).length > 0" class="headers">
                    <div class="sub-title">Headers:</div>
                    <pre>{{ JSON.stringify(caseResult.request.headers, null, 2) }}</pre>
                  </div>
                  <div v-if="caseResult.request?.body" class="body">
                    <div class="sub-title">Body:</div>
                    <pre>{{ JSON.stringify(caseResult.request.body, null, 2) }}</pre>
                  </div>
                </div>
              </div>

              <!-- 响应信息 (API 测试) -->
              <div v-if="caseResult.type !== 'ui'" class="detail-section">
                <div class="section-title">
                  <el-icon><Download /></el-icon>
                  响应信息
                </div>
                <div class="code-block">
                  <div class="response-line">
                    <span class="status-code" :class="getStatusCodeClass(caseResult.response?.status_code)">
                      {{ caseResult.response?.status_code || '-' }}
                    </span>
                    <span class="response-time">{{ caseResult.response_time_ms }}ms</span>
                  </div>
                  <div v-if="caseResult.response?.headers" class="headers">
                    <div class="sub-title">Headers:</div>
                    <pre>{{ JSON.stringify(caseResult.response.headers, null, 2) }}</pre>
                  </div>
                  <div v-if="caseResult.response?.body" class="body">
                    <div class="sub-title">Body:</div>
                    <pre>{{ formatJson(caseResult.response.body) }}</pre>
                  </div>
                </div>
              </div>

              <!-- UI 测试截图 -->
              <div v-if="caseResult.screenshot_url" class="detail-section">
                <div class="section-title">
                  <el-icon><Picture /></el-icon>
                  执行截图
                </div>
                <div class="screenshot-preview">
                  <img :src="caseResult.screenshot_url" alt="测试截图" @click="previewImage(caseResult.screenshot_url)" />
                </div>
              </div>

              <!-- 断言结果 -->
              <div v-if="caseResult.assertions && caseResult.assertions.length > 0" class="detail-section">
                <div class="section-title">
                  <el-icon><Check /></el-icon>
                  断言验证 ({{ caseResult.assertions.length }} 个)
                </div>
                <el-table :data="caseResult.assertions" size="small" border>
                  <el-table-column label="断言类型" width="120">
                    <template #default="{ row }">
                      <el-tag size="small" :type="row.passed ? 'success' : 'danger'">
                        {{ getAssertionTypeText(row.type) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="字段" prop="field" width="150" />
                  <el-table-column label="运算符" width="100">
                    <template #default="{ row }">
                      {{ getOperatorText(row.operator) }}
                    </template>
                  </el-table-column>
                  <el-table-column label="期望值" prop="expected_value" width="150" />
                  <el-table-column label="实际值" prop="actual_value" width="150" />
                  <el-table-column label="结果" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.passed ? 'success' : 'danger'" size="small">
                        {{ row.passed ? '通过' : '失败' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="说明" prop="message" min-width="200" />
                </el-table>
              </div>

              <!-- 执行消息 -->
              <div v-if="caseResult.message" class="detail-section">
                <div class="section-title">执行消息</div>
                <div class="message-block" :class="caseResult.passed ? 'success' : 'error'">
                  {{ caseResult.message }}
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>

      <!-- 旧数据格式提示 -->
      <el-alert
        v-if="isOldDataFormat"
        title="旧数据格式提示"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 20px;"
      >
        <div>此测试结果是旧格式数据，建议重新执行测试任务以查看详细的执行步骤和截图。</div>
      </el-alert>

      <!-- 原始测试日志 -->
      <el-card v-if="result.test_log && !isOldDataFormat" class="log-card">
        <template #header>
          <span>原始日志</span>
        </template>
        <div class="log-content">
          <pre>{{ formatJson(result.test_log) }}</pre>
        </div>
      </el-card>

      <!-- 测试截图 -->
      <el-card v-if="result.screenshots && result.screenshots.length > 0" class="screenshots-card">
        <template #header>
          <span>测试截图 ({{ result.screenshots.length }})</span>
        </template>
        <div class="screenshots-grid">
          <div
            v-for="screenshot in result.screenshots"
            :key="screenshot.id"
            class="screenshot-item"
            @click="previewScreenshot(screenshot)"
          >
            <img :src="screenshot.image_url || screenshot.image" :alt="screenshot.name" />
            <div class="screenshot-info">
              <div class="screenshot-name">{{ screenshot.name }}</div>
              <div class="screenshot-desc" v-if="screenshot.description">{{ screenshot.description }}</div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 截图预览弹窗 -->
    <el-dialog v-model="previewVisible" title="截图预览" width="80%">
      <img v-if="currentScreenshot" :src="currentScreenshot.image_url || currentScreenshot.image" style="width: 100%" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { ArrowLeft, Refresh, Upload, Download, Check, List, Picture, CircleCheck, CircleClose, Timer, Setting, Warning } from '@element-plus/icons-vue';
import service from '@/utils/request';

const route = useRoute();
const router = useRouter();

const result = ref<any>(null);
const activeCaseIndex = ref<number[]>([0]); // 默认展开第一个
const previewVisible = ref(false);
const currentScreenshot = ref<any>(null);

const resultId = computed(() => route.params.id as string);

// 解析执行摘要
const executionSummary = computed(() => {
  if (!result.value?.test_log) return null;
  try {
    const log = JSON.parse(result.value.test_log);
    return log.summary || null;
  } catch {
    return null;
  }
});

// 解析用例执行结果
const caseResults = computed(() => {
  if (!result.value?.test_log) return [];
  try {
    const log = JSON.parse(result.value.test_log);
    // 新格式: { summary: {}, results: [] }
    if (log.results && Array.isArray(log.results)) {
      return log.results;
    }
    // 旧格式兼容: 直接是数组
    if (Array.isArray(log)) {
      return log;
    }
    return [];
  } catch {
    return [];
  }
});

// 是否是旧数据格式
const isOldDataFormat = computed(() => {
  if (!result.value?.test_log) return false;
  try {
    const log = JSON.parse(result.value.test_log);
    // 如果存在 screenshot 字段且是长字符串（base64），说明是旧格式
    if (Array.isArray(log)) {
      return log.some((item: any) => item.screenshot && item.screenshot.length > 1000);
    }
    if (log.results && Array.isArray(log.results)) {
      return log.results.some((item: any) => item.screenshot && item.screenshot.length > 1000);
    }
    return false;
  } catch {
    return false;
  }
});

// 是否是性能测试
const isPerformanceTest = computed(() => {
  return result.value?.test_type === 'performance';
});

// 性能测试指标
const performanceMetrics = computed(() => {
  if (!result.value?.test_log) return null;
  try {
    const log = JSON.parse(result.value.test_log);
    // 从 results 中提取性能指标
    if (log.results && Array.isArray(log.results) && log.results.length > 0) {
      const perfResult = log.results[0];
      return {
        throughput: perfResult.throughput || 0,
        avg_response_time: perfResult.avg_response_time || 0,
        min_response_time: perfResult.min_response_time || 0,
        max_response_time: perfResult.max_response_time || 0,
        p50_response_time: perfResult.p50_response_time || 0,
        p90_response_time: perfResult.p90_response_time || 0,
        p95_response_time: perfResult.p95_response_time || 0,
        p99_response_time: perfResult.p99_response_time || 0,
        total_requests: perfResult.total_requests || 0,
        successful_requests: perfResult.successful_requests || 0,
        failed_requests: perfResult.failed_requests || 0,
        error_rate: perfResult.error_rate || 0,
        errors: perfResult.errors || [],
        state: perfResult.state || 'completed',
        url: perfResult.request?.url || result.value.test_params?.url,
        method: perfResult.request?.method || result.value.test_params?.method,
        start_time: perfResult.start_time
      };
    }
    // 直接返回 log 中的指标（如果存储格式不同）
    if (log.throughput !== undefined) {
      return {
        throughput: log.throughput || 0,
        avg_response_time: log.avg_response_time || 0,
        min_response_time: log.min_response_time || 0,
        max_response_time: log.max_response_time || 0,
        p50_response_time: log.p50_response_time || 0,
        p90_response_time: log.p90_response_time || 0,
        p95_response_time: log.p95_response_time || 0,
        p99_response_time: log.p99_response_time || 0,
        total_requests: log.total_requests || 0,
        successful_requests: log.successful_requests || 0,
        failed_requests: log.failed_requests || 0,
        error_rate: log.error_rate || 0,
        errors: log.errors || [],
        state: log.state || 'completed',
        url: log.url || result.value.test_params?.url,
        method: log.method || result.value.test_params?.method,
        start_time: log.start_time
      };
    }
    return null;
  } catch {
    return null;
  }
});

// 加载数据
const loadData = async () => {
  try {
    const res = await service.get(`/qa/test-results/${resultId.value}/`);
    result.value = res;
  } catch (error) {
    ElMessage.error('加载测试结果失败');
  }
};

// 获取状态类型
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

// 获取测试类型标签类型
const getTestTypeType = (type: string) => {
  const types: Record<string, string> = {
    'api': 'success',
    'ui': 'primary',
    'performance': 'warning',
    'regression': 'info'
  };
  return types[type] || 'info';
};

// 获取状态码样式
const getStatusCodeClass = (code: number) => {
  if (code >= 200 && code < 300) return 'success';
  if (code >= 300 && code < 400) return 'warning';
  if (code >= 400) return 'error';
  return '';
};

// 获取断言类型文本
const getAssertionTypeText = (type: string) => {
  const texts: Record<string, string> = {
    'status_code': '状态码',
    'json_path': 'JSON字段',
    'header': '响应头',
    'response_time': '响应时间'
  };
  return texts[type] || type;
};

// 获取运算符文本
const getOperatorText = (operator: string) => {
  const texts: Record<string, string> = {
    'equals': '等于',
    'not_equals': '不等于',
    'greater_than': '大于',
    'less_than': '小于',
    'contains': '包含',
    'exists': '存在'
  };
  return texts[operator] || operator;
};

// 格式化日期
const formatDate = (date: string) => {
  if (!date) return '-';
  return new Date(date).toLocaleString('zh-CN');
};

// 格式化时长
const formatDuration = (ms: number) => {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = ((ms % 60000) / 1000).toFixed(2);
  return `${minutes}m ${seconds}s`;
};

// 格式化 JSON
const formatJson = (data: any) => {
  if (typeof data === 'string') {
    try {
      return JSON.stringify(JSON.parse(data), null, 2);
    } catch {
      return data;
    }
  }
  return JSON.stringify(data, null, 2);
};

// 返回上一页
const goBack = () => {
  router.back();
};

// 预览截图
const previewScreenshot = (screenshot: any) => {
  currentScreenshot.value = screenshot;
  previewVisible.value = true;
};

// 预览图片
const previewImage = (url: string) => {
  currentScreenshot.value = { image_url: url };
  previewVisible.value = true;
};

// 获取操作类型标签
const getActionType = (action: string) => {
  const types: Record<string, string> = {
    'click': 'primary',
    'fill': 'success',
    'navigate': 'info',
    'wait': 'warning',
    'screenshot': 'danger',
    'assert': 'success'
  };
  return types[action] || '';
};

// 格式化时间（毫秒转易读格式）
const formatTime = (ms: number) => {
  if (!ms || ms === 0) return '0 ms';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
};

onMounted(() => {
  loadData();
});
</script>

<style scoped>
.test-result-detail {
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

.detail-content > .el-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.metric-item {
  text-align: center;
  padding: 20px;
  background-color: var(--color-bg);
  border-radius: 8px;
}

.metric-value {
  font-size: 32px;
  font-weight: bold;
  color: var(--el-color-primary);
}

.metric-value.text-success {
  color: var(--el-color-success);
}

.metric-value.text-danger {
  color: var(--el-color-danger);
}

.metric-label {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
}

.case-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.case-status {
  flex-shrink: 0;
}

.case-name {
  font-weight: 500;
  flex: 1;
}

.case-type {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.case-time {
  color: var(--el-color-primary);
  font-size: 12px;
  font-family: monospace;
}

.case-detail {
  padding: 16px;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-weight: bold;
  margin-bottom: 12px;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.code-block {
  background-color: #1E293B;
  color: var(--color-border);
  padding: 16px;
  border-radius: 8px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  overflow-x: auto;
}

.code-block pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.request-line {
  margin-bottom: 12px;
}

.method {
  font-weight: bold;
  padding: 4px 8px;
  border-radius: 4px;
  margin-right: 8px;
  font-size: 12px;
}

.method.get {
  background-color: #4ec9b0;
  color: #000;
}

.method.post {
  background-color: #4fc1ff;
  color: #000;
}

.method.put {
  background-color: #dcdcaa;
  color: #000;
}

.method.delete {
  background-color: #f48771;
  color: #000;
}

.url {
  color: var(--color-border);
}

.response-line {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-code {
  font-weight: bold;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 14px;
}

.status-code.success {
  background-color: #4ec9b0;
  color: #000;
}

.status-code.warning {
  background-color: #dcdcaa;
  color: #000;
}

.status-code.error {
  background-color: #f48771;
  color: #000;
}

.response-time {
  color: #858585;
  font-size: 12px;
}

.sub-title {
  color: #858585;
  margin-top: 12px;
  margin-bottom: 8px;
  font-size: 12px;
}

.message-block {
  padding: 12px 16px;
  border-radius: 4px;
  font-size: 14px;
}

.message-block.success {
  background-color: #f0f9eb;
  border-left: 4px solid var(--el-color-success);
  color: var(--el-color-success);
}

.message-block.error {
  background-color: #fef0f0;
  border-left: 4px solid var(--el-color-danger);
  color: var(--el-color-danger);
}

.log-content {
  background-color: #1E293B;
  color: var(--color-border);
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
}

.log-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.screenshots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.screenshot-item {
  cursor: pointer;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  overflow: hidden;
  transition: box-shadow 0.3s;
}

.screenshot-item:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.screenshot-item img {
  width: 100%;
  height: 150px;
  object-fit: cover;
}

.screenshot-info {
  padding: 8px;
}

.screenshot-name {
  font-weight: 500;
  font-size: 14px;
}

.screenshot-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

/* 步骤样式 */
.step-item {
  padding: 8px 0;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.step-number {
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.step-selector {
  color: var(--el-text-color-secondary);
  font-family: monospace;
  background-color: var(--color-bg);
  padding: 2px 8px;
  border-radius: 4px;
}

.step-value {
  color: var(--el-color-primary);
  font-style: italic;
}

.step-logs {
  margin-top: 8px;
  padding: 8px 12px;
  background-color: var(--color-bg);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.log-line {
  margin-bottom: 4px;
  line-height: 1.5;
}

.log-line:last-child {
  margin-bottom: 0;
}

/* 性能测试指标样式 */
.performance-metrics-card {
  margin-bottom: 20px;
}

.perf-metrics-row {
  margin-bottom: 24px;
}

.perf-metric-card {
  background: linear-gradient(135deg, var(--color-bg) 0%, var(--color-surface) 100%);
  border-radius: 12px;
  padding: 20px 12px;
  text-align: center;
  border: 1px solid var(--color-border);
  transition: all 0.3s ease;
}

.perf-metric-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.perf-metric-card.rps {
  border-top: 4px solid var(--color-primary-light);
}

.perf-metric-card.avg-time {
  border-top: 4px solid #3B82F6;
}

.perf-metric-card.error-rate {
  border-top: 4px solid var(--color-warning);
}

.perf-metric-card.error-rate.high-error {
  border-top: 4px solid var(--color-danger);
  background: linear-gradient(135deg, #fef2f2 0%, var(--color-surface) 100%);
}

.perf-metric-card.total-req {
  border-top: 4px solid #a78bfa;
}

.perf-metric-card.success-req {
  border-top: 4px solid var(--color-success);
}

.perf-metric-card.failed-req {
  border-top: 4px solid var(--color-danger);
}

.perf-metric-icon {
  font-size: 28px;
  margin-bottom: 8px;
}

.perf-metric-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 4px;
}

.perf-metric-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.response-time-section {
  margin-bottom: 24px;
  padding: 20px;
  background: var(--color-bg);
  border-radius: 12px;
}

.time-distribution-item {
  text-align: center;
  padding: 16px 8px;
  background: white;
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.time-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}

.time-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-primary-light);
  font-family: 'Courier New', monospace;
}

.test-config-section {
  margin-bottom: 24px;
}

.errors-section {
  margin-top: 20px;
}

/* 截图预览 */
.screenshot-preview {
  max-width: 100%;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.screenshot-preview img {
  width: 100%;
  max-height: 400px;
  object-fit: contain;
  cursor: pointer;
  transition: transform 0.3s;
}

.screenshot-preview img:hover {
  transform: scale(1.02);
}
</style>
