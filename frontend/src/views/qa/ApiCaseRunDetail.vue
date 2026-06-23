<template>
  <div class="api-case-run-detail" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
      <h2 v-if="caseResult">
        {{ caseResult.name }}  {{ caseResult.request_snapshot?.method || '' }}
        <code v-if="caseResult.request_snapshot">{{ caseResult.request_snapshot.url }}</code>
        <el-tag :type="statusTagType" effect="dark">{{ caseResult.status }}</el-tag>
      </h2>
    </div>

    <el-tabs v-if="caseResult" v-model="activeTab">
      <el-tab-pane label="Request" name="request">
        <RequestPanel
          :method="caseResult.request_snapshot?.method || 'GET'"
          :url="caseResult.request_snapshot?.url || ''"
          :headers="caseResult.request_snapshot?.headers"
          :body="caseResult.request_snapshot?.body"
        />
      </el-tab-pane>
      <el-tab-pane label="Response" name="response">
        <ResponsePanel
          :statusCode="caseResult.status_code || 0"
          :duration="caseResult.duration_ms || 0"
          :body="caseResult.response_body || ''"
          :headers="caseResult.response_headers || {}"
        />
      </el-tab-pane>
      <el-tab-pane :label="`Tests(${assertionCount})`" name="tests">
        <TestsPanel
          :results="caseResult.assertion_results || []"
        />
      </el-tab-pane>
      <el-tab-pane label="cURL" name="curl">
        <CurlPanel :curl="caseResult.curl || ''" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { testRunApi } from '@/api/testrun'
import RequestPanel from './components/RequestPanel.vue'
import ResponsePanel from './components/ResponsePanel.vue'
import TestsPanel from './components/TestsPanel.vue'
import CurlPanel from './components/CurlPanel.vue'

const route = useRoute()
const router = useRouter()

const caseResult = ref<any>(null)
const loading = ref(true)
const activeTab = ref('request')

const runId = computed(() => Number(route.params.runId))
const caseResultId = computed(() => Number(route.params.caseResultId))

const statusTagType = computed(() => {
  const s = caseResult.value?.status
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'error') return 'warning'
  if (s === 'skipped') return 'info'
  return 'info'
})

const assertionCount = computed(() => {
  const list = caseResult.value?.assertion_results || []
  return list.filter((r: any) => r && !('extractions' in r) && 'passed' in r).length
})

async function loadData() {
  loading.value = true
  try {
    caseResult.value = await testRunApi.caseDetail(runId.value, caseResultId.value)
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.back()
}

onMounted(loadData)
</script>

<style scoped>
.api-case-run-detail { padding: 0; }
.header {
  display: flex; align-items: center; gap: 12px;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-border-light);
}
.header h2 {
  margin: 0;
  font: 600 18px/1.3 var(--font-heading);
  color: var(--color-text);
  display: flex; align-items: center; gap: 8px;
}
.header code {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
