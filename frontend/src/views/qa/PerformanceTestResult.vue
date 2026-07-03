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
            <div class="status-left">
              <span class="status" :class="lifecycleStatusClass">
                <el-icon v-if="lifecycleIsActive" class="is-loading"><Loading /></el-icon>
                {{ lifecycleLabel }}
              </span>
              <el-tag v-if="probeResult && !probeResult.ok" type="danger" size="small" class="status-tag">
                预检失败
              </el-tag>
              <el-tag v-if="probeResult?.is_localhost && probeResult?.localhost_allowed" type="warning" size="small" class="status-tag">
                localhost
              </el-tag>
            </div>
            <div class="status-right">
              <span class="duration" v-if="lifecycleIsActive || testStatus === 'stopped'">
                {{ formatDuration(duration) }}
              </span>
              <span class="last-update" v-if="lastMetricsAt">
                更新: {{ lastMetricsAtText }}
              </span>
              <span class="ws-indicator" :class="{ connected: wsConnected, disconnected: !wsConnected }">
                {{ wsConnected ? '●' : '○' }} WS
              </span>
            </div>
          </div>

          <!-- 生命周期原因（error/stopped/timeout） -->
          <el-alert
            v-if="lifecycleReason && lifecycleIsTerminal"
            :title="lifecycleReasonText"
            :type="lifecycleAlertType"
            show-icon
            :closable="false"
            class="diagnostic-alert"
          />

          <!-- localhost 警告 -->
          <el-alert
            v-if="probeResult && probeResult.is_localhost && probeResult.localhost_allowed"
            title="当前目标地址为 localhost。请注意：压力测试执行器访问的 localhost 是执行器所在机器/容器，不一定是你的浏览器本机。"
            type="warning"
            show-icon
            :closable="false"
            class="diagnostic-alert"
          />

          <!-- Warning 横幅（5s 无请求等） -->
          <el-alert
            v-if="diagnosticMessage && !lifecycleIsTerminal"
            :title="diagnosticMessage"
            :type="diagnosticType"
            show-icon
            :closable="false"
            class="diagnostic-alert"
          />

          <!-- 诊断面板（可折叠） -->
          <el-collapse v-if="hasDiagnostic || lifecycleHistory.length > 0" class="diagnostic-panel">
            <el-collapse-item title="诊断信息" name="diagnostic">
              <!-- 生命周期历史 -->
              <div v-if="lifecycleHistory.length > 0" class="lifecycle-timeline">
                <h6>生命周期</h6>
                <div class="timeline">
                  <div
                    v-for="(entry, idx) in lifecycleHistory"
                    :key="idx"
                    class="timeline-entry"
                    :class="{ active: idx === lifecycleHistory.length - 1 }"
                  >
                    <span class="timeline-dot"></span>
                    <span class="timeline-state">{{ entry.label }}</span>
                    <span v-if="entry.reason" class="timeline-reason">({{ entry.reason }})</span>
                  </div>
                </div>
              </div>

              <!-- Probe 结果 -->
              <div v-if="probeResult" class="probe-result">
                <h6>连通性预检</h6>
                <div class="probe-status-row">
                  <el-tag v-if="probeResult.ok" type="success" size="small">通过</el-tag>
                  <el-tag v-else-if="probeResult.blocked_by_policy" type="danger" size="small">
                    策略拦截: {{ probeResult.policy_block_reason }}
                  </el-tag>
                  <el-tag v-else type="danger" size="small">
                    失败: {{ probeResult.failure_reason }}
                  </el-tag>
                </div>
                <div class="probe-details">
                  <div v-if="probeResult.resolved_ips?.length" class="probe-line">
                    <span class="probe-label">DNS:</span>
                    <span>{{ probeResult.resolved_ips.join(', ') }}</span>
                    <el-tag v-if="probeResult.is_localhost" type="warning" size="small">localhost</el-tag>
                    <el-tag v-if="probeResult.is_private" type="info" size="small">内网</el-tag>
                    <el-tag v-if="probeResult.is_cloud_metadata" type="danger" size="small">metadata</el-tag>
                  </div>
                  <div v-if="probeResult.tcp_connect_ms" class="probe-line">
                    <span class="probe-label">TCP:</span>
                    <span>{{ probeResult.tcp_connect_ms }}ms</span>
                  </div>
                  <div v-if="probeResult.http_status_code" class="probe-line">
                    <span class="probe-label">HTTP:</span>
                    <span>{{ probeResult.http_status_code }} ({{ probeResult.http_duration_ms }}ms)</span>
                  </div>
                  <div v-if="probeResult.tls_ok" class="probe-line">
                    <span class="probe-label">TLS:</span>
                    <span>{{ probeResult.tls_version }} — {{ probeResult.tls_cert_subject }}</span>
                  </div>
                  <div v-if="probeResult.tls_error" class="probe-line text-danger">
                    <span class="probe-label">TLS 错误:</span>
                    <span>{{ probeResult.tls_error }}</span>
                  </div>
                  <div v-if="probeResult.ip_classification_notes?.length" class="probe-line">
                    <span class="probe-label">IP 分类:</span>
                    <span>{{ probeResult.ip_classification_notes.join('; ') }}</span>
                  </div>
                  <div v-if="probeResult.error_summary" class="probe-line text-danger">
                    <span>{{ probeResult.error_summary }}</span>
                  </div>
                </div>
              </div>

              <div class="diagnostic-grid">
                <div v-for="(value, key) in diagnosticInfo" :key="key" class="diagnostic-item">
                  <span class="diag-key">{{ key }}:</span>
                  <span class="diag-value">{{ formatDiagValue(value) }}</span>
                </div>
              </div>
              <div class="log-actions">
                <el-button size="small" @click="fetchLogs('stdout')" :loading="loadingStdout">
                  查看 stdout
                </el-button>
                <el-button size="small" @click="fetchLogs('stderr')" :loading="loadingStderr">
                  查看 stderr
                </el-button>
              </div>
              <!-- 日志内容显示 -->
              <div v-if="stdoutLog" class="log-viewer">
                <h6>stdout 日志</h6>
                <pre>{{ stdoutLog }}</pre>
              </div>
              <div v-if="stderrLog" class="log-viewer">
                <h6>stderr 日志</h6>
                <pre>{{ stderrLog }}</pre>
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 启动信息摘要 -->
          <div v-if="runInfo.host" class="run-info-bar">
            <span><strong>Host:</strong> {{ runInfo.host }}</span>
            <span><strong>Users:</strong> {{ runInfo.users }}</span>
            <span><strong>Spawn Rate:</strong> {{ runInfo.spawn_rate }}</span>
            <span><strong>Run Time:</strong> {{ runInfo.run_time }}</span>
            <span class="info-pid" v-if="runInfo.pid"><strong>PID:</strong> {{ runInfo.pid }}</span>
          </div>

          <!-- 指标产生前阶段提示 -->
          <div v-if="lifecycleIsPreMetrics" class="pre-metrics-notice">
            <el-icon class="is-loading"><Loading /></el-icon>
            <p>{{ lifecycleLabel }} — 性能指标尚未产生，请稍候...</p>
          </div>

          <!-- 统计卡片（仅在产生指标后显示） -->
          <div class="stats-grid" v-if="!lifecycleIsPreMetrics">
            <div class="stat-card">
              <div class="stat-label">RPS</div>
              <div class="stat-value">{{ (currentStats.rps || currentStats.throughput || 0).toFixed(1) }}</div>
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
            <div class="stat-card stat-card-meta">
              <div class="stat-label">最后指标更新</div>
              <div class="stat-value stat-value-small">
                {{ lastMetricsAtText }}
              </div>
            </div>
          </div>

          <!-- Locust 风格统计表格（仅在产生指标后显示） -->
          <div class="stats-table-container" v-if="!lifecycleIsPreMetrics">
            <h5>请求统计</h5>
            <el-table :data="requestStats" size="small" border stripe>
              <el-table-column prop="method" label="Method" width="70" />
              <el-table-column prop="name" label="Endpoint" min-width="150" show-overflow-tooltip />
              <el-table-column prop="num_requests" label="# 请求" width="80" align="right" />
              <el-table-column prop="num_failures" label="# 失败" width="70" align="right">
                <template #default="{ row }">
                  <span :class="{ 'text-danger': row.num_failures > 0 }">{{ row.num_failures }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="avg_response_time" label="Avg (ms)" width="80" align="right" />
              <el-table-column prop="p95" label="P95 (ms)" width="80" align="right" />
              <el-table-column prop="min_response_time" label="Min (ms)" width="70" align="right" />
              <el-table-column prop="max_response_time" label="Max (ms)" width="70" align="right" />
              <el-table-column prop="rps" label="RPS" width="60" align="right" />
            </el-table>
          </div>

          <!-- 实时图表 -->
          <div class="charts-container" v-if="!lifecycleIsPreMetrics">
            <div class="chart-header">
              <h5>实时性能指标</h5>
              <el-radio-group v-model="chartWindow" size="small" @change="updateChart">
                <el-radio-button value="30s">30秒</el-radio-button>
                <el-radio-button value="60s">1分钟</el-radio-button>
                <el-radio-button value="all">全部</el-radio-button>
              </el-radio-group>
            </div>
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

          <!-- 历史结果 -->
          <div class="history-section" v-if="historyResults.length > 0">
            <h5>历史结果</h5>
            <el-table :data="historyResults" size="small" border stripe @row-click="loadHistoryResult" style="cursor:pointer">
              <el-table-column prop="executed_at" label="时间" width="160">
                <template #default="{ row }">{{ new Date(row.executed_at).toLocaleString() }}</template>
              </el-table-column>
              <el-table-column prop="error_rate" label="错误率" width="80" align="right">
                <template #default="{ row }">{{ row.error_rate?.toFixed(1) }}%</template>
              </el-table-column>
              <el-table-column prop="avg_response_time_ms" label="Avg(ms)" width="80" align="right" />
              <el-table-column prop="p95_response_time_ms" label="P95(ms)" width="80" align="right" />
              <el-table-column prop="throughput" label="RPS" width="70" align="right">
                <template #default="{ row }">{{ row.throughput?.toFixed(1) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="70" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.throughput > 0 ? 'success' : 'danger'" size="small">
                    {{ row.throughput > 0 ? '完成' : '异常' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </template>
    </div>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑用例' : '新建用例'" width="780px" top="3vh">
      <el-form :model="form" label-width="110px" :rules="rules" ref="formRef">
        <el-tabs v-model="formTab" type="border-card">
          <!-- 基础信息 -->
          <el-tab-pane label="基础信息" name="basic">
            <el-form-item label="名称" prop="name">
              <el-input v-model="form.name" placeholder="如: 登录接口压测" />
            </el-form-item>
            <el-form-item label="项目" prop="project">
              <el-select v-model="form.project" style="width: 100%">
                <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选描述" />
            </el-form-item>
          </el-tab-pane>

          <!-- 请求配置 -->
          <el-tab-pane label="请求配置" name="request">
            <el-form-item label="URL" prop="url">
              <el-input v-model="form.url" placeholder="https://api.example.com/endpoint" />
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="方法" prop="method">
                  <el-select v-model="form.method">
                    <el-option label="GET" value="GET" />
                    <el-option label="POST" value="POST" />
                    <el-option label="PUT" value="PUT" />
                    <el-option label="PATCH" value="PATCH" />
                    <el-option label="DELETE" value="DELETE" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="请求体类型">
                  <el-select v-model="form.body_type">
                    <el-option label="无" value="none" />
                    <el-option label="JSON" value="json" />
                    <el-option label="表单" value="form" />
                    <el-option label="原始文本" value="raw" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="超时(秒)">
                  <el-input-number v-model="form.request_timeout" :min="1" :max="120" style="width:100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="请求头">
              <el-input v-model="form.headers" type="textarea" :rows="2" placeholder='{"Content-Type":"application/json"}' />
            </el-form-item>
            <el-form-item label="Query参数">
              <el-input v-model="form.query_params" type="textarea" :rows="2" placeholder='{"page":1,"size":20}' />
            </el-form-item>
            <el-form-item label="请求体" v-if="form.body_type !== 'none'">
              <el-input v-model="form.body" type="textarea" :rows="4" placeholder='{"key":"value"}' />
            </el-form-item>
          </el-tab-pane>

          <!-- 认证 -->
          <el-tab-pane label="认证" name="auth">
            <el-form-item label="认证类型">
              <el-select v-model="form.auth_type" @change="onAuthTypeChange">
                <el-option label="无" value="" />
                <el-option label="Bearer Token" value="bearer" />
                <el-option label="Basic Auth" value="basic" />
              </el-select>
            </el-form-item>
            <template v-if="form.auth_type === 'bearer'">
              <el-form-item label="Token">
                <el-input v-model="form.auth_token" placeholder="或 {{ENV_MY_TOKEN}} 引用环境变量" show-password />
              </el-form-item>
            </template>
            <template v-if="form.auth_type === 'basic'">
              <el-form-item label="用户名">
                <el-input v-model="form.auth_username" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input v-model="form.auth_password" type="password" show-password />
              </el-form-item>
            </template>
          </el-tab-pane>

          <!-- 压力参数 -->
          <el-tab-pane label="压力参数" name="load">
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="并发用户">
                  <el-input-number v-model="form.concurrent_users" :min="1" :max="10000" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="持续时间(秒)">
                  <el-input-number v-model="form.duration_seconds" :min="1" :max="3600" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="预热时间(秒)">
                  <el-input-number v-model="form.ramp_up_seconds" :min="0" :max="600" style="width:100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="RPS限制">
                  <el-input-number v-model="form.requests_per_second" :min="0" :max="100000" style="width:100%" placeholder="不限" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="思考时间最小(秒)">
                  <el-input-number v-model="form.think_time_min" :min="0" :max="10" :step="0.1" :precision="1" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="思考时间最大(秒)">
                  <el-input-number v-model="form.think_time_max" :min="0" :max="10" :step="0.1" :precision="1" style="width:100%" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-tab-pane>

          <!-- 断言 -->
          <el-tab-pane label="断言" name="assertions">
            <el-form-item label="期望错误率(%)">
              <el-input-number v-model="form.expected_error_rate" :min="0" :max="100" :step="0.1" :precision="1" />
            </el-form-item>
            <el-form-item label="期望响应时间(ms)">
              <el-input-number v-model="form.expected_response_time_ms" :min="1" :max="60000" />
            </el-form-item>
            <el-form-item label="期望吞吐量(req/s)">
              <el-input-number v-model="form.expected_throughput" :min="0" :precision="0" placeholder="可选" />
            </el-form-item>
          </el-tab-pane>

          <!-- 高级 -->
          <el-tab-pane label="高级" name="advanced">
            <el-form-item label="跟随重定向">
              <el-switch v-model="form.follow_redirects" />
            </el-form-item>
            <el-form-item label="验证SSL">
              <el-switch v-model="form.verify_ssl" />
            </el-form-item>
            <el-form-item label="权重">
              <el-input-number v-model="form.weight" :min="1" :max="100" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="form.is_active" />
            </el-form-item>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="success" @click="submitForm(true)" :loading="submitting">
          保存并运行
        </el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
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
const testStatus = ref('ready'); // ready, running, stopped, error
const duration = ref(0);
const currentStats = ref<any>({});
const requestStats = ref<any[]>([]);
const failures = ref<any[]>([]);
const hasData = ref(false);
const executionId = ref<number | null>(null);

// ── 新增：诊断相关状态 ──────────────────────────────────────────
const wsConnected = ref(false);
const diagnosticMessage = ref('');
const diagnosticType = ref<'warning' | 'error' | 'info'>('info');
const hasDiagnostic = ref(false);
const diagnosticInfo = ref<Record<string, any>>({});
const runInfo = ref<Record<string, any>>({});
const lastMetricsAt = ref<number | null>(null);
const stdoutLog = ref('');
const stderrLog = ref('');
const loadingStdout = ref(false);
const loadingStderr = ref(false);
const stderrTail = ref('');

// ── 生命周期状态 ──────────────────────────────────────────────
const lifecycleState = ref('pending');
const lifecycleLabel = ref('准备中');
const lifecycleIsActive = ref(true);
const lifecycleIsTerminal = ref(false);
const lifecycleIsPreMetrics = ref(true);
const lifecycleReason = ref('');
const lifecycleHistory = ref<any[]>([]);
const probeResult = ref<any>(null);

// ── 历史结果 ──────────────────────────────────────────────────
const historyResults = ref<any[]>([]);

// 图表
const chartRef = ref<HTMLElement>();
let chartInstance: echarts.ECharts | null = null;
const chartData = ref<any[]>([]);
const chartWindow = ref('60s');

// WebSocket (auto-reconnect with exponential backoff)
let ws: WebSocket | null = null;
let wsReconnectTimer: any = null;
let wsReconnectAttempts = 0;
const WS_MAX_RECONNECT_ATTEMPTS = 10;
const WS_BASE_DELAY_MS = 1000;
let durationTimer: any = null;

// 表单
const dialogVisible = ref(false);
const isEdit = ref(false);
const submitting = ref(false);
const formRef = ref();
const formTab = ref('basic');
const form = reactive({
  id: null as any,
  name: '',
  description: '',
  project: null as any,
  url: '',
  method: 'GET',
  headers: '{}',
  query_params: '{}',
  body: '',
  body_type: 'json',
  request_timeout: 30,
  follow_redirects: true,
  verify_ssl: true,
  auth_type: '',
  auth_token: '',
  auth_username: '',
  auth_password: '',
  concurrent_users: 10,
  duration_seconds: 60,
  ramp_up_seconds: 10,
  requests_per_second: null as any,
  think_time_min: 0.1,
  think_time_max: 0.5,
  weight: 1,
  expected_error_rate: 5.0,
  expected_response_time_ms: 1000,
  expected_throughput: null as any,
  is_active: true
});

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  project: [{ required: true, message: '请选择项目', trigger: 'change' }],
  url: [{ required: true, message: '请输入URL', trigger: 'blur' }],
  method: [{ required: true, message: '请选择方法', trigger: 'change' }],
};

const onAuthTypeChange = () => {
  // reset auth fields when switching type
  form.auth_token = '';
  form.auth_username = '';
  form.auth_password = '';
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
    stopped: '已停止',
    error: '错误'
  };
  return texts[testStatus.value] || '未知';
});

const lastMetricsAtText = computed(() => {
  if (!lastMetricsAt.value) {
    const ts = currentStats.value?.timestamp;
    if (ts) return formatDateTime(ts);
    return '等待中...';
  }
  return formatDateTime(lastMetricsAt.value);
});

const lifecycleStatusClass = computed(() => {
  if (lifecycleIsTerminal.value && lifecycleState.value === 'error') return 'error';
  if (lifecycleIsTerminal.value && lifecycleState.value === 'failed') return 'error';
  if (lifecycleIsTerminal.value && lifecycleState.value === 'timeout') return 'error';
  if (lifecycleState.value === 'stopping') return 'error';
  if (lifecycleIsTerminal.value) return 'stopped';
  return 'running';
});

const lifecycleAlertType = computed(() => {
  if (lifecycleState.value === 'error' || lifecycleState.value === 'timeout') return 'error' as const;
  if (lifecycleState.value === 'stopped') return 'warning' as const;
  return 'info' as const;
});

const lifecycleReasonText = computed(() => {
  if (!lifecycleReason.value) return '';
  const reasonMap: Record<string, string> = {
    'probe_failed': '目标 URL 不可达，请检查网络和 URL 配置',
    'probe_timeout': '目标 URL 连接超时，请检查服务是否正常运行',
    'probe_error': '连通性检查异常',
    'locust_start_failed': 'Locust 子进程启动失败，请检查 stderr 日志',
    'locustfile_generation_failed': 'Locust 测试文件生成失败',
    'user_requested': '用户手动停止测试',
    'max_runtime_exceeded': '运行时间超过最大限制，已被强制终止',
    'worker_exception': 'Worker 执行异常',
  };
  return reasonMap[lifecycleReason.value] || lifecycleReason.value;
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
  resetState();
  loadHistory(caseItem.id);
};

const loadHistory = async (caseId: number) => {
  try {
    const res = await service.get(`/qa/performance-cases/${caseId}/results/`, { params: { limit: 10 } });
    historyResults.value = res.results || res || [];
  } catch (e) {
    historyResults.value = [];
  }
};

const loadHistoryResult = (row: any) => {
  // Load a specific history result into view
  ElMessage.info(`点击查看执行 #${row.id} 的详情`);
};

const resetState = () => {
  testStatus.value = 'ready';
  isRunning.value = false;
  hasData.value = false;
  currentStats.value = {};
  requestStats.value = [];
  failures.value = [];
  chartData.value = [];
  duration.value = 0;
  // 重置诊断
  wsConnected.value = false;
  diagnosticMessage.value = '';
  diagnosticType.value = 'info';
  hasDiagnostic.value = false;
  diagnosticInfo.value = {};
  runInfo.value = {};
  lastMetricsAt.value = null;
  stdoutLog.value = '';
  stderrLog.value = '';
  stderrTail.value = '';
  // 重置生命周期
  lifecycleState.value = 'pending';
  lifecycleLabel.value = '准备中';
  lifecycleIsActive.value = true;
  lifecycleIsTerminal.value = false;
  lifecycleIsPreMetrics.value = true;
  lifecycleReason.value = '';
  lifecycleHistory.value = [];
  probeResult.value = null;
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
    
    // 重置诊断
    diagnosticMessage.value = '';
    diagnosticType.value = 'info';
    hasDiagnostic.value = false;
    diagnosticInfo.value = {};
    runInfo.value = {};
    lastMetricsAt.value = null;
    stdoutLog.value = '';
    stderrLog.value = '';
    stderrTail.value = '';
    
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

const connectWebSocket = (execId: number) => {
  disconnectWebSocket();
  wsReconnectAttempts = 0;

  const doConnect = () => {
    if (wsReconnectAttempts >= WS_MAX_RECONNECT_ATTEMPTS) {
      console.warn('[PerfTest] Max reconnect attempts reached, falling back to status API');
      diagnosticMessage.value = 'WebSocket 重连失败，请刷新页面获取最新状态';
      diagnosticType.value = 'warning';
      return;
    }

    ws = new WebSocket(buildWsUrl(`/ws/qa/performance/${execId}/`));

    ws.onopen = () => {
      wsConnected.value = true;
      wsReconnectAttempts = 0;
      console.log('[PerfTest] WebSocket connected for execution', execId);
    };

    ws.onmessage = (event) => { handleWsMessage(event); };

    ws.onclose = () => {
      wsConnected.value = false;
      console.log('[PerfTest] WebSocket 关闭');
      // 只在测试运行中时尝试重连
      if (isRunning.value && wsReconnectAttempts < WS_MAX_RECONNECT_ATTEMPTS) {
        const delay = WS_BASE_DELAY_MS * Math.pow(2, wsReconnectAttempts);
        wsReconnectAttempts++;
        console.log(`[PerfTest] 将在 ${delay}ms 后重连 (attempt ${wsReconnectAttempts}/${WS_MAX_RECONNECT_ATTEMPTS})`);
        diagnosticMessage.value = `WebSocket 断开，${(delay/1000).toFixed(0)}s 后自动重连...`;
        diagnosticType.value = 'warning';
        wsReconnectTimer = setTimeout(doConnect, delay);
      } else if (!isRunning.value) {
        diagnosticMessage.value = '';
      }
    };

    ws.onerror = (err) => {
      wsConnected.value = false;
      console.error('[PerfTest] WebSocket 错误:', err);
    };
  };

  doConnect();
};

const handleWsMessage = (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    
    if (data.type === 'connected') {
      console.log('[PerfTest]', data.message);
      return;
    }
    
    currentStats.value = data;
    
    // lifecycle
    if (data.lifecycle_state) {
      lifecycleState.value = data.lifecycle_state;
      lifecycleLabel.value = data.lifecycle_label || data.lifecycle_state;
      lifecycleIsActive.value = data.lifecycle_is_active ?? !data.lifecycle_is_terminal;
      lifecycleIsTerminal.value = data.lifecycle_is_terminal ?? false;
      lifecycleIsPreMetrics.value = data.lifecycle_is_pre_metrics ?? false;
      lifecycleReason.value = data.lifecycle_reason || '';
      if (data.lifecycle_history) lifecycleHistory.value = data.lifecycle_history;
    }

    if (data.probe_result) probeResult.value = data.probe_result;
    
    if (data.last_metrics_at) lastMetricsAt.value = data.last_metrics_at;
    else if (data.timestamp) lastMetricsAt.value = data.timestamp;

    const phase = data.phase || '';
    const state = data.state || '';
    
    if (phase === 'error' || state === 'error' || data.lifecycle_is_terminal) {
      testStatus.value = 'error';
      isRunning.value = false;
      if (durationTimer) { clearInterval(durationTimer); durationTimer = null; }
    }

    const diagMsg = data.diagnostic_message || '';
    if (diagMsg && data.warning !== 'no_requests_after_5s') {
      diagnosticMessage.value = diagMsg;
      diagnosticType.value = phase === 'error' || state === 'error' ? 'error' : 'info';
    }

    if (data.diagnostic && typeof data.diagnostic === 'object') {
      diagnosticInfo.value = data.diagnostic;
      hasDiagnostic.value = Object.keys(data.diagnostic).length > 0;
      const diag = data.diagnostic;
      if (diag.host || diag.users) {
        runInfo.value = { host: diag.host || '', users: diag.users || '', spawn_rate: diag.spawn_rate || '', run_time: diag.run_time || '', pid: diag.pid || '', target_path: diag.target_path || '' };
      }
    }

    if (data.stderr_tail) stderrTail.value = data.stderr_tail;

    // per-endpoint stats table
    const eps = data.per_endpoint || {};
    if (Object.keys(eps).length > 0) {
      requestStats.value = Object.entries(eps).map(([name, ep]: [string, any]) => ({
        method: selectedCase.value?.method || 'GET',
        name,
        num_requests: ep.total_requests || 0,
        num_failures: ep.failed_requests || 0,
        median_response_time: 0,
        avg_response_time: ep.avg_response_time || 0,
        min_response_time: ep.min_response_time || 0,
        max_response_time: ep.max_response_time || 0,
        p95: ep.p95_response_time || 0,
        rps: 0
      }));
    } else {
      const rpsVal = data.rps || data.throughput || 0;
      requestStats.value = [{
        method: selectedCase.value?.method,
        name: selectedCase.value?.url,
        num_requests: data.total_requests || 0,
        num_failures: data.failed_requests || 0,
        median_response_time: data.p50_response_time || 0,
        avg_response_time: data.avg_response_time || 0,
        min_response_time: data.min_response_time || 0,
        max_response_time: data.max_response_time || 0,
        p95: data.p95_response_time || 0,
        rps: rpsVal
      }];
    }

    if (data.errors?.length) {
      failures.value = data.errors.map((e: any) => ({
        method: selectedCase.value?.method || 'GET', name: selectedCase.value?.url || '/',
        error: e.message || e.type || 'Unknown error', occurrences: e.count || 1
      }));
    }

    const rpsV = data.rps || data.throughput || 0;
    chartData.value.push({ time: new Date().toLocaleTimeString(), rps: rpsV, avgResponseTime: data.avg_response_time || 0, p95: data.p95_response_time || 0, errorRate: data.error_rate || 0 });
    if (chartData.value.length > 120) chartData.value.shift();
    updateChart();
  } catch (e) {
    console.error('[PerfTest] 解析数据失败:', e);
  }
};

const disconnectWebSocket = () => {
  if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  wsConnected.value = false;
  wsReconnectAttempts = 0;
};

const initChart = () => {
  if (!chartRef.value) return;
  const rect = chartRef.value.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) { setTimeout(initChart, 500); return; }
  if (chartInstance) chartInstance.dispose();
  
  chartInstance = echarts.init(chartRef.value);
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['RPS', '响应时间(ms)', 'P95(ms)', '错误率(%)'], bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: '3%', right: '5%', bottom: '12%', top: '5%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: [], axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: [
      { type: 'value', name: 'RPS', min: 0 },
      { type: 'value', name: 'ms / %', min: 0 }
    ],
    series: [
      { name: 'RPS', type: 'line', smooth: true, data: [], itemStyle: { color: '#0F766E' }, areaStyle: { opacity: 0.1 } },
      { name: '响应时间(ms)', type: 'line', smooth: true, data: [], itemStyle: { color: '#0969DA' } },
      { name: 'P95(ms)', type: 'line', smooth: true, yAxisIndex: 1, data: [], itemStyle: { color: '#D97706' }, lineStyle: { type: 'dashed' } },
      { name: '错误率(%)', type: 'line', smooth: true, yAxisIndex: 1, data: [], itemStyle: { color: '#CF222E' } }
    ],
    animation: true
  });
  console.log('Chart initialized');
};

const updateChart = () => {
  if (!chartInstance || chartData.value.length === 0) return;
  
  // Apply time window filter
  let filtered = chartData.value;
  if (chartWindow.value === '30s') {
    const cutoff = chartData.value.length - 30;
    filtered = chartData.value.slice(Math.max(0, cutoff));
  } else if (chartWindow.value === '60s') {
    const cutoff = chartData.value.length - 60;
    filtered = chartData.value.slice(Math.max(0, cutoff));
  }
  
  chartInstance.setOption({
    xAxis: { data: filtered.map(d => d.time) },
    series: [
      { data: filtered.map(d => d.rps) },
      { data: filtered.map(d => d.avgResponseTime) },
      { data: filtered.map(d => d.p95 || 0) },
      { data: filtered.map(d => d.errorRate) }
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
  formTab.value = 'basic';
  Object.assign(form, {
    id: null, name: '', description: '', project: null, url: '', method: 'GET',
    headers: '{}', query_params: '{}', body: '', body_type: 'json',
    request_timeout: 30, follow_redirects: true, verify_ssl: true,
    auth_type: '', auth_token: '', auth_username: '', auth_password: '',
    concurrent_users: 10, duration_seconds: 60, ramp_up_seconds: 10,
    requests_per_second: null, think_time_min: 0.1, think_time_max: 0.5,
    weight: 1, expected_error_rate: 5.0, expected_response_time_ms: 1000,
    expected_throughput: null, is_active: true
  });
  dialogVisible.value = true;
};

const editCase = (caseItem: any) => {
  isEdit.value = true;
  formTab.value = 'basic';
  const auth = caseItem.auth_config || {};
  Object.assign(form, {
    id: caseItem.id,
    name: caseItem.name,
    description: caseItem.description || '',
    project: caseItem.project || caseItem.project_id,
    url: caseItem.url,
    method: caseItem.method,
    headers: JSON.stringify(caseItem.headers || {}, null, 2),
    query_params: JSON.stringify(caseItem.query_params || {}, null, 2),
    body: caseItem.body || '',
    body_type: caseItem.body_type || 'json',
    request_timeout: caseItem.request_timeout || 30,
    follow_redirects: caseItem.follow_redirects !== false,
    verify_ssl: caseItem.verify_ssl !== false,
    auth_type: auth.type || '',
    auth_token: auth.token || '',
    auth_username: auth.username || '',
    auth_password: auth.password || '',
    concurrent_users: caseItem.concurrent_users,
    duration_seconds: caseItem.duration_seconds,
    ramp_up_seconds: caseItem.ramp_up_seconds || 10,
    requests_per_second: caseItem.requests_per_second || null,
    think_time_min: caseItem.think_time_min || 0.1,
    think_time_max: caseItem.think_time_max || 0.5,
    weight: caseItem.weight || 1,
    expected_error_rate: caseItem.expected_error_rate,
    expected_response_time_ms: caseItem.expected_response_time_ms,
    expected_throughput: caseItem.expected_throughput || null,
    is_active: caseItem.is_active !== false
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

const submitForm = async (runAfter: boolean = false) => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  
  submitting.value = true;
  try {
    let headers = {};
    let query_params = {};
    try {
      headers = form.headers ? JSON.parse(form.headers) : {};
    } catch (e) { ElMessage.error('请求头格式错误'); return; }
    try {
      query_params = form.query_params ? JSON.parse(form.query_params) : {};
    } catch (e) { ElMessage.error('Query参数格式错误'); return; }

    // 构建 auth_config
    const auth_config: any = {};
    if (form.auth_type === 'bearer') {
      auth_config.type = 'bearer';
      auth_config.token = form.auth_token;
    } else if (form.auth_type === 'basic') {
      auth_config.type = 'basic';
      auth_config.username = form.auth_username;
      auth_config.password = form.auth_password;
    }

    const data = {
      ...form,
      headers,
      query_params,
      auth_config,
      // 移除 UI 专用字段
      auth_type: undefined,
      auth_token: undefined,
      auth_username: undefined,
      auth_password: undefined,
    };
    // 清理 undefined
    Object.keys(data).forEach(k => { if (data[k] === undefined) delete data[k]; });

    let result;
    if (isEdit.value) {
      result = await service.put(`/qa/performance-cases/${form.id}/`, data);
    } else {
      result = await service.post('/qa/performance-cases/', data);
    }

    ElMessage.success(isEdit.value ? '更新成功' : '创建成功');
    dialogVisible.value = false;
    await loadCases();

    // 保存并运行
    if (runAfter) {
      const caseId = result?.data?.id || result?.id;
      if (caseId) {
        // 选中刚创建/编辑的用例
        const c = cases.value.find((x: any) => x.id === caseId);
        if (c) selectCase(c);
        // 延迟一下确保选中后再启动
        setTimeout(() => startTest(), 500);
      }
    }
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

const formatDateTime = (ts: number) => {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
};

const formatDiagValue = (value: any): string => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const fetchLogs = async (logType: 'stdout' | 'stderr') => {
  if (!selectedCase.value || !executionId.value) return;
  
  if (logType === 'stdout') loadingStdout.value = true;
  else loadingStderr.value = true;

  try {
    const res = await service.get(
      `/qa/performance-cases/${selectedCase.value.id}/execution-logs/`,
      { params: { execution_id: executionId.value, type: logType, lines: 100 } }
    );
    if (logType === 'stdout') {
      stdoutLog.value = res.stdout || '(日志文件不存在或为空)';
    } else {
      stderrLog.value = res.stderr || stderrTail.value || '(日志文件不存在或为空)';
    }
  } catch (error: any) {
    ElMessage.error('获取日志失败');
  } finally {
    if (logType === 'stdout') loadingStdout.value = false;
    else loadingStderr.value = false;
  }
};

onMounted(() => {
  loadCases();
  loadProjects();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  cleanup();
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
  padding: 10px 14px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  flex-wrap: wrap;
  gap: 8px;
}

.status-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status-right {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.status-tag { margin-left: 4px; }

.last-update {
  font-family: var(--font-mono);
  color: var(--color-text-tertiary);
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
.status.error { color: var(--color-danger); }

.status .el-icon { animation: rotating 2s linear infinite; }

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* WebSocket 指示器 */
.ws-indicator {
  font-size: 11px;
  margin-left: 8px;
  font-weight: 600;
}
.ws-indicator.connected { color: var(--color-success); }
.ws-indicator.disconnected { color: var(--color-danger); }

/* 诊断警告横幅 */
.diagnostic-alert {
  margin-bottom: 16px;
}

/* 诊断面板 */
.diagnostic-panel {
  margin-bottom: 16px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.diagnostic-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 16px;
  padding: 8px 0;
}

.diagnostic-item {
  font-size: 12px;
  line-height: 1.6;
}

.diag-key {
  color: var(--color-text-secondary);
  font-weight: 500;
}

.diag-value {
  color: var(--color-text);
  font-family: var(--font-mono);
  word-break: break-all;
}

.log-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
}

/* 日志查看器 */
.log-viewer {
  margin-top: 12px;
}

.log-viewer h6 {
  margin: 0 0 4px 0;
  font: 600 12px/1.3 var(--font-heading);
  color: var(--color-text-secondary);
}

.log-viewer pre {
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text);
  margin: 0;
}

/* 运行信息栏 */
.run-info-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-text-secondary);
}

.run-info-bar span {
  white-space: nowrap;
}

.run-info-bar strong {
  color: var(--color-text);
}

.info-pid {
  font-family: var(--font-mono);
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

.stat-card-meta {
  grid-column: span 1;
}

.stat-value-small {
  font-size: 14px !important;
  font-weight: 400 !important;
  font-family: var(--font-mono);
}

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

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.chart-header h5 {
  margin: 0;
  font: 600 13px/1.3 var(--font-heading);
  color: var(--color-text);
}

.chart {
  width: 100%;
  height: 300px;
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

/* 历史结果 */
.history-section {
  margin-top: 32px;
  width: 100%;
  max-width: 800px;
  text-align: left;
}

.history-section h5 {
  margin: 0 0 8px 0;
  font: 600 13px/1.3 var(--font-heading);
  color: var(--color-text);
}

/* 通用 */
.text-danger {
  color: var(--color-danger) !important;
}

/* 生命周期时间线 */
.lifecycle-timeline {
  margin-bottom: 12px;
}

.lifecycle-timeline h6 {
  margin: 0 0 8px 0;
  font: 600 12px/1.3 var(--font-heading);
  color: var(--color-text-secondary);
}

.timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.timeline-entry {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
}

.timeline-entry.active {
  color: var(--color-text);
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
  font-weight: 500;
}

.timeline-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-border);
}

.timeline-entry.active .timeline-dot {
  background: var(--color-primary);
}

.timeline-state {
  white-space: nowrap;
}

.timeline-reason {
  color: var(--color-text-tertiary);
  font-style: italic;
}

/* Probe 结果 */
.probe-result {
  margin-bottom: 12px;
}

.probe-result h6 {
  margin: 0 0 8px 0;
  font: 600 12px/1.3 var(--font-heading);
  color: var(--color-text-secondary);
}

.probe-status-row {
  margin-bottom: 6px;
}

.probe-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.probe-line {
  font-size: 12px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.probe-label {
  font-weight: 500;
  color: var(--color-text);
  min-width: 36px;
}

.probe-detail {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
}

/* 指标前阶段提示 */
.pre-metrics-notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--color-text-tertiary);
  gap: 8px;
}

.pre-metrics-notice .el-icon {
  font-size: 28px;
  color: var(--color-primary);
}

.pre-metrics-notice p {
  margin: 0;
  font-size: 13px;
}
</style>
