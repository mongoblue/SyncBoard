<template>
  <div class="test-run-list" v-loading="loading">
    <header class="page-header">
      <div>
        <h1 class="page-title">批量执行历史</h1>
        <p class="page-subtitle">查看历次批量执行任务的状态、通过率与耗时</p>
      </div>
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
    </header>
    <div class="filters">
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 160px">
        <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
      </el-select>
    </div>
    <el-table :data="runs" @row-click="goDetail" stripe>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="tagType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="通过率" width="100">
        <template #default="{ row }">
          {{ row.passed_count }}/{{ row.total_count }} ({{ row.pass_rate }}%)
        </template>
      </el-table-column>
      <el-table-column prop="test_type" label="类型" width="80" />
      <el-table-column prop="trigger" label="触发" width="80" />
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">
          {{ row.duration_ms ? row.duration_ms + 'ms' : '--' }}
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      @current-change="loadData"
      @size-change="loadData"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { testRunApi, type TestRun } from '@/api/testrun'

const route = useRoute()
const router = useRouter()

const runs = ref<TestRun[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const statuses = ['pending', 'running', 'passed', 'failed', 'error', 'cancelled']

const filters = ref({
  status: '',
  project: route.params.projectId ? Number(route.params.projectId) : undefined,
})

async function loadData() {
  loading.value = true
  try {
    const data = await testRunApi.list({
      ...filters.value,
      page: page.value,
      page_size: pageSize.value,
    })
    runs.value = data.results
    total.value = data.count
  } finally {
    loading.value = false
  }
}

function tagType(s: string): 'success' | 'danger' | 'warning' | 'info' {
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'error' || s === 'cancelled') return 'warning'
  return 'info'
}

function formatTime(iso: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}

function goDetail(row: TestRun) {
  router.push(`/projects/${filters.value.project}/qa/test-runs/${row.id}`)
}

function goBack() { router.back() }

watch(filters, () => { page.value = 1; loadData() }, { deep: true })
onMounted(loadData)
</script>

<style scoped>
.test-run-list { padding: 0; }
.filters { margin-bottom: 16px; }
.el-pagination { margin-top: 16px; justify-content: flex-end; }
</style>
