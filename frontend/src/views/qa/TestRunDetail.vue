<template>
  <div class="test-run-detail" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
      <h2 v-if="run">{{ run.name }}
        <el-tag :type="tagType(run.status)" effect="dark">{{ run.status }}</el-tag>
      </h2>
      <el-button v-if="run && (run.status === 'running' || run.status === 'pending')" @click="cancelRun" type="danger">取消</el-button>
    </div>

    <RunProgressBar
      v-if="run"
      :total="run.total_count"
      :passedCount="run.passed_count"
      :failedCount="run.failed_count"
      :errorCount="run.error_count"
      :durationMs="run.duration_ms"
    />

    <div class="filters">
      <el-select v-model="filterStatus" placeholder="状态" clearable>
        <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
      </el-select>
    </div>

    <el-table :data="cases" stripe>
      <el-table-column prop="sequence" label="#" width="50" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="结果语义" min-width="220">
        <template #default="{ row }">
          <div class="semantic-result-cell">
            <el-tag :type="semanticTagType(row)" size="small">{{ semanticLabel(row) }}</el-tag>
            <span v-if="row.expectation_type === 'error_response' && row.expected_status" class="semantic-hint">
              期望 {{ row.expected_status }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="status_code" label="状态码" width="100" />
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">{{ row.duration_ms ? row.duration_ms + 'ms' : '--' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="goCaseDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer
      v-model="drawerOpen"
      title="用例详情"
      size="620px"
      destroy-on-close
    >
      <div v-loading="caseLoading">
        <template v-if="caseDetail">
          <div class="case-detail-header">
            <h3>{{ caseDetail.name }}</h3>
            <el-tag :type="tagType(caseDetail.status)" effect="dark">{{ caseDetail.status }}</el-tag>
          </div>

          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="状态码">{{ caseDetail.status_code ?? '--' }}</el-descriptions-item>
            <el-descriptions-item label="耗时">{{ caseDetail.duration_ms ? caseDetail.duration_ms + 'ms' : '--' }}</el-descriptions-item>
            <el-descriptions-item label="类型">{{ caseDetail.case_type }}</el-descriptions-item>
            <el-descriptions-item label="序列">#{{ caseDetail.sequence }}</el-descriptions-item>
          </el-descriptions>

          <div v-if="caseDetail.error_message" class="case-detail-error">
            <el-alert type="error" :title="caseDetail.error_message" :closable="false" show-icon />
          </div>

          <template v-if="caseDetail.assertion_results?.length">
            <h4>断言结果</h4>
            <el-table :data="caseDetail.assertion_results" size="small" stripe max-height="240">
              <el-table-column prop="assertion_type" label="类型" />
              <el-table-column prop="operator" label="操作符" width="100" />
              <el-table-column label="通过" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.passed ? 'success' : 'danger'" size="small">{{ row.passed ? '通过' : '失败' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="expected_value" label="期望" show-overflow-tooltip />
              <el-table-column prop="actual_value" label="实际" show-overflow-tooltip />
            </el-table>
          </template>

          <div class="case-detail-raw">
            <CollapsibleRawJson
              v-if="caseDetail.request_snapshot"
              :data="caseDetail.request_snapshot"
              label="请求快照"
              name="req"
            />
            <CollapsibleRawJson
              v-if="caseDetail.response_body"
              :data="caseDetail.response_body"
              label="响应体"
              name="resp"
              :default-open="caseDetail.status !== 'passed'"
            />
            <CollapsibleRawJson
              v-if="caseDetail.response_headers"
              :data="caseDetail.response_headers"
              label="响应头"
              name="headers"
            />
            <CollapsibleRawJson
              v-if="caseDetail.curl"
              :data="caseDetail.curl"
              label="cURL"
              name="curl"
            />
          </div>
        </template>
        <el-empty v-else-if="!caseLoading" description="无详情数据" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { testRunApi, type TestRun, type TestRunCaseResult } from '@/api/testrun'
import RunProgressBar from './components/RunProgressBar.vue'
import CollapsibleRawJson from './components/result/CollapsibleRawJson.vue'

const route = useRoute()
const router = useRouter()

const run = ref<TestRun | null>(null)
const cases = ref<TestRunCaseResult[]>([])
const loading = ref(false)
const filterStatus = ref('')
const statuses = ['pending', 'running', 'passed', 'failed', 'error', 'skipped']
const drawerOpen = ref(false)
const caseLoading = ref(false)
const caseDetail = ref<TestRunCaseResult | null>(null)
let ws: WebSocket | null = null

const runId = computed(() => Number(route.params.id))

async function loadRun() {
  run.value = await testRunApi.detail(runId.value)
}

async function loadCases() {
  const data = await testRunApi.cases(runId.value, { status: filterStatus.value || undefined })
  cases.value = data.results
}

async function loadData() {
  loading.value = true
  try {
    await loadRun()
    await loadCases()
  } finally {
    loading.value = false
  }
}

async function cancelRun() {
  try {
    await ElMessageBox.confirm('确定取消此批量执行?', '确认', { type: 'warning' })
    await testRunApi.cancel(runId.value)
    ElMessage.success('已取消')
    await loadData()
  } catch { /* user cancel */ }
}

async function goCaseDetail(row: TestRunCaseResult) {
  // 原实现跳转 /qa/test-runs/:id/cases/:caseResultId 未注册路由 → 空白页
  // 改为抽屉内直接加载用例详情（GET /qa/runs/:id/cases/:caseResultId）
  drawerOpen.value = true
  caseLoading.value = true
  caseDetail.value = null
  try {
    caseDetail.value = await testRunApi.caseDetail(runId.value, row.id)
  } catch {
    ElMessage.error('加载用例详情失败')
  } finally {
    caseLoading.value = false
  }
}

function goBack() { router.back() }

function tagType(s: string): 'success' | 'danger' | 'warning' | 'info' {
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'error' || s === 'cancelled') return 'warning'
  return 'info'
}

function semanticLabel(row: TestRunCaseResult): string {
  return row.semantic_label || (row.status === 'passed' ? '成功响应断言通过' : '测试失败')
}

function semanticTagType(row: TestRunCaseResult): 'success' | 'danger' | 'warning' | 'info' {
  if (row.semantic_status === 'expected_error_matched' || row.semantic_status === 'success_response_passed') return 'success'
  if (row.semantic_status === 'expected_error_unmatched' || row.semantic_status === 'success_response_failed') return 'danger'
  if (row.semantic_status === 'expected_error_execution_error') return 'warning'
  return tagType(row.status)
}

function openWs() {
  if (ws) return
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${window.location.host}/ws/qa/test-run/${runId.value}/`)
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'case_done' || msg.type === 'run_finished') {
        // 后端推完一条 case 或整个 run 收尾,刷新计数 + 列表
        loadRun().catch(() => {})
        loadCases().catch(() => {})
      }
    } catch { /* ignore non-JSON */ }
  }
  ws.onerror = () => { /* 静默,降级到轮询 */ }
}
function closeWs() {
  if (ws) {
    ws.close()
    ws = null
  }
}

watch(filterStatus, () => loadCases())
onMounted(() => {
  loadData().then(() => {
    if (run.value && (run.value.status === 'pending' || run.value.status === 'running')) {
      openWs()
    }
  })
})
onBeforeUnmount(closeWs)
</script>

<style scoped>
.semantic-result-cell { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.semantic-hint { font-size: 12px; color: var(--color-text-secondary); }
.test-run-detail { padding: 16px 24px; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.header h2 { margin: 0; flex: 1; }
.filters { margin: 16px 0; }
.case-detail-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.case-detail-header h3 { margin: 0; flex: 1; }
.case-detail-error { margin-top: 12px; }
.case-detail-raw { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.case-detail-raw h4 { margin: 8px 0 4px; }
</style>
