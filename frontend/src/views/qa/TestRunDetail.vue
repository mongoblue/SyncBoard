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
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="tagType(row.status)">{{ row.status }}</el-tag>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { testRunApi, type TestRun, type TestRunCaseResult } from '@/api/testrun'
import RunProgressBar from './components/RunProgressBar.vue'

const route = useRoute()
const router = useRouter()

const run = ref<TestRun | null>(null)
const cases = ref<TestRunCaseResult[]>([])
const loading = ref(false)
const filterStatus = ref('')
const statuses = ['pending', 'running', 'passed', 'failed', 'error', 'skipped']

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

function goCaseDetail(row: TestRunCaseResult) {
  router.push(`/projects/${run.value!.project_id}/qa/test-runs/${runId.value}/cases/${row.id}`)
}

function goBack() { router.back() }

function tagType(s: string): 'success' | 'danger' | 'warning' | 'info' {
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'error' || s === 'cancelled') return 'warning'
  return 'info'
}

watch(filterStatus, () => loadCases())
onMounted(loadData)
</script>

<style scoped>
.test-run-detail { padding: 16px 24px; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.header h2 { margin: 0; flex: 1; }
.filters { margin: 16px 0; }
</style>
