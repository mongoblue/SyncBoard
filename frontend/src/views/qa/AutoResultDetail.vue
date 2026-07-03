<template>
  <div class="auto-result-detail" v-loading="loading">
    <div class="page-header">
      <div class="header-left">
        <el-button @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <h2 v-if="summary">{{ summary.name }}</h2>
      </div>
      <div class="header-actions">
        <el-button @click="reload">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button
          v-if="hasFailures && projectId"
          type="warning"
          :loading="bulkCreatingBugs"
          @click="bulkCreateBugs"
        >
          <el-icon><Warning /></el-icon>
          一键为失败用例建 Bug ({{ summary?.failed_cases || 0 }})
        </el-button>
      </div>
    </div>

    <!-- 顶部执行概览 -->
    <el-card v-if="summary" class="overview-card">
      <div class="overview-row">
        <div class="overview-item">
          <div class="overview-label">状态</div>
          <el-tag :type="statusType(summary.status)" size="large">{{ summary.status_display }}</el-tag>
        </div>
        <div class="overview-item">
          <div class="overview-label">总用例</div>
          <div class="overview-value">{{ summary.total_cases }}</div>
        </div>
        <div class="overview-item">
          <div class="overview-label">通过</div>
          <div class="overview-value text-success">{{ summary.passed_cases }}</div>
        </div>
        <div class="overview-item">
          <div class="overview-label">失败</div>
          <div class="overview-value text-danger">{{ summary.failed_cases }}</div>
        </div>
        <div class="overview-item">
          <div class="overview-label">错误</div>
          <div class="overview-value text-warning">{{ summary.error_cases }}</div>
        </div>
        <div class="overview-item">
          <div class="overview-label">通过率</div>
          <div class="overview-value">{{ passRate }}%</div>
        </div>
        <div class="overview-item">
          <div class="overview-label">总耗时</div>
          <div class="overview-value">{{ formatDuration(summary.duration_ms) }}</div>
        </div>
        <div class="overview-item">
          <div class="overview-label">执行人</div>
          <div class="overview-value">{{ summary.executed_by_name || '-' }}</div>
        </div>
      </div>
      <el-alert
        v-if="summary.error_message"
        :title="summary.error_message"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 12px"
      />
    </el-card>

    <!-- 筛选 + 表格 -->
    <el-card class="cases-card">
      <template #header>
        <div class="cases-toolbar">
          <strong>用例执行结果</strong>
          <div class="filters">
            <el-input
              v-model="search"
              placeholder="搜索名称/URL"
              clearable
              style="width: 200px"
              @change="reloadCases"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-select
              v-model="passedFilter"
              placeholder="全部"
              clearable
              style="width: 120px"
              @change="reloadCases"
            >
              <el-option label="通过" value="true" />
              <el-option label="失败/错误" value="false" />
            </el-select>
            <el-select v-model="ordering" style="width: 180px" @change="reloadCases">
              <el-option label="执行顺序" value="executed_at" />
              <el-option label="耗时 ↓" value="-response_time_ms" />
              <el-option label="耗时 ↑" value="response_time_ms" />
              <el-option label="状态码 ↓" value="-status_code" />
              <el-option label="失败优先" value="passed" />
            </el-select>
          </div>
        </div>
      </template>

      <el-table
        :data="cases"
        v-loading="casesLoading"
        stripe
        @row-click="openCaseDrawer"
        row-class-name="clickable-row"
      >
        <el-table-column label="结果语义" min-width="220">
          <template #default="{ row }">
            <div class="semantic-result-cell">
              <el-tag :type="semanticTagType(row)" size="small">
                {{ semanticLabel(row) }}
              </el-tag>
              <span v-if="row.expectation_type === 'error_response' && row.expected_status" class="semantic-hint">
                期望 {{ row.expected_status }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="方法" width="80">
          <template #default="{ row }">
            <span class="method-tag" :class="row.case_method?.toLowerCase()">{{ row.case_method }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="case_name" label="用例名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="case_url" label="URL" min-width="240" show-overflow-tooltip />
        <el-table-column label="状态码" width="90">
          <template #default="{ row }">
            <span :class="statusCodeClass(row.status_code)">{{ row.status_code || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ row.response_time_ms }}ms</template>
        </el-table-column>
        <el-table-column label="断言" width="100">
          <template #default="{ row }">
            <span>{{ row.assertion_passed }}/{{ row.assertion_total }}</span>
          </template>
        </el-table-column>
        <el-table-column label="错误摘要" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="error-summary">{{ row.error_summary || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        class="pagination"
        @current-change="loadCases"
      />
    </el-card>

    <!-- 单条详情抽屉 -->
    <el-drawer v-model="drawerVisible" size="60%" :title="drawerTitle" destroy-on-close>
      <div v-if="currentDetail" v-loading="detailLoading" class="drawer-body">
        <el-tabs v-model="activeTab">
          <!-- 概览 -->
          <el-tab-pane label="概览" name="overview">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="用例">{{ currentDetail.case_name }}</el-descriptions-item>
              <el-descriptions-item label="结果语义">
                <div class="semantic-result-cell">
                  <el-tag :type="semanticTagType(currentDetail)" size="small">
                    {{ semanticLabel(currentDetail) }}
                  </el-tag>
                  <span
                    v-if="currentDetail.expectation_type === 'error_response' && currentDetail.expected_status"
                    class="semantic-hint"
                  >
                    期望 {{ currentDetail.expected_status }}
                  </span>
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="失败类型">
                <el-tag v-if="currentDetail.failure_type" :type="failureTagType" size="small">
                  {{ failureLabel }}
                </el-tag>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="状态码">{{ currentDetail.status_code }}</el-descriptions-item>
              <el-descriptions-item label="方法">{{ currentDetail.case_method }}</el-descriptions-item>
              <el-descriptions-item label="耗时">{{ currentDetail.response_time_ms }}ms</el-descriptions-item>
              <el-descriptions-item label="执行时间">{{ formatDate(currentDetail.executed_at) }}</el-descriptions-item>
              <el-descriptions-item v-if="currentDetail.trace_id" label="Trace ID">
                <code class="trace-id">{{ currentDetail.trace_id }}</code>
              </el-descriptions-item>
              <el-descriptions-item label="URL" :span="2">{{ currentDetail.case_url }}</el-descriptions-item>
            </el-descriptions>

            <DiagnosisCard
              v-if="currentDetail.result_metadata?.diagnosis"
              :diagnosis="currentDetail.result_metadata.diagnosis"
            />

            <el-alert
              v-if="currentDetail.error_message"
              :title="currentDetail.error_message"
              type="error"
              :closable="false"
              show-icon
              style="margin-top: 12px"
            />
          </el-tab-pane>

          <!-- 断言 -->
          <el-tab-pane :label="`断言 (${currentDetail.assertion_details?.length || 0})`" name="assertions">
            <AssertionTable :assertions="currentDetail.assertion_details" />
          </el-tab-pane>

          <!-- 请求 -->
          <el-tab-pane label="请求" name="request">
            <RequestSnapshotPanel :snapshot="currentDetail.request_snapshot" />
          </el-tab-pane>

          <!-- 响应 -->
          <el-tab-pane label="响应" name="response">
            <ResponseSnapshotPanel :snapshot="currentDetail.response_snapshot" />
          </el-tab-pane>

          <!-- 提取变量 -->
          <el-tab-pane
            v-if="currentDetail.extracted_variables_preview && hasExtractedVars"
            label="提取变量"
            name="extracted"
          >
            <el-table :data="extractedVarRows" border size="small">
              <el-table-column prop="name" label="变量名" />
              <el-table-column label="预览">
                <template #default="{ row }">
                  <code class="extracted-preview">{{ row.preview }}</code>
                </template>
              </el-table-column>
              <el-table-column label="脱敏" width="80">
                <template #default="{ row }">
                  <el-tag v-if="row.redacted" type="info" size="small">是</el-tag>
                  <span v-else>否</span>
                </template>
              </el-table-column>
              <el-table-column label="截断" width="80">
                <template #default="{ row }">
                  <el-tag v-if="row.truncated" type="warning" size="small">是</el-tag>
                  <span v-else>否</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- cURL -->
          <el-tab-pane v-if="currentDetail.curl?.preview" label="cURL" name="curl">
            <div class="curl-hint">可直接复制到终端复现请求：</div>
            <pre class="code"><code>{{ currentDetail.curl.preview }}</code></pre>
          </el-tab-pane>
        </el-tabs>

        <div class="drawer-footer">
          <el-button
            v-if="!currentDetail.passed && projectId"
            type="warning"
            :loading="singleCreatingBug"
            @click="createBugForCurrent"
          >
            为此用例建 Bug
          </el-button>
          <el-button @click="drawerVisible = false">关闭</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { ArrowLeft, Refresh, Search, Warning } from '@element-plus/icons-vue';
import {
  getAutoResult,
  listAutoResultCases,
  getAutoCaseResultDetail,
  createBugFromCaseResult,
  FAILURE_TYPE_LABELS,
  FAILURE_TYPE_TAG,
  type AutoResultSummary,
  type AutoCaseResultBrief,
  type AutoCaseResultFull,
} from '@/api/autoresult';
import DiagnosisCard from './components/result/DiagnosisCard.vue';
import AssertionTable from './components/result/AssertionTable.vue';
import RequestSnapshotPanel from './components/result/RequestSnapshotPanel.vue';
import ResponseSnapshotPanel from './components/result/ResponseSnapshotPanel.vue';

const route = useRoute();
const router = useRouter();
const resultId = Number(route.params.id);
const projectId = (route.params.projectId as string) || '';

const loading = ref(false);
const summary = ref<AutoResultSummary | null>(null);

const casesLoading = ref(false);
const cases = ref<AutoCaseResultBrief[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;

const search = ref('');
const passedFilter = ref<string>('');
const ordering = ref('executed_at');

const drawerVisible = ref(false);
const detailLoading = ref(false);
const currentDetail = ref<AutoCaseResultFull | null>(null);
const activeTab = ref('overview');

const singleCreatingBug = ref(false);
const bulkCreatingBugs = ref(false);

const passRate = computed(() => {
  if (!summary.value || !summary.value.total_cases) return 0;
  return Math.round((summary.value.passed_cases / summary.value.total_cases) * 1000) / 10;
});

const hasFailures = computed(
  () => !!summary.value && summary.value.failed_cases + summary.value.error_cases > 0,
);

const drawerTitle = computed(() => currentDetail.value?.case_name || '用例详情');

const loadSummary = async () => {
  try {
    summary.value = await getAutoResult(resultId);
  } catch {
    ElMessage.error('加载执行结果失败');
  }
};

const loadCases = async () => {
  casesLoading.value = true;
  try {
    const params: any = { page: page.value, page_size: pageSize, ordering: ordering.value };
    if (search.value) params.search = search.value;
    if (passedFilter.value !== '') params.passed = passedFilter.value === 'true';
    const res = await listAutoResultCases(resultId, params);
    cases.value = res.results;
    total.value = res.count;
  } catch {
    ElMessage.error('加载用例结果失败');
  } finally {
    casesLoading.value = false;
  }
};

const reloadCases = () => {
  page.value = 1;
  loadCases();
};

const reload = async () => {
  loading.value = true;
  await Promise.all([loadSummary(), loadCases()]);
  loading.value = false;
};

const openCaseDrawer = async (row: AutoCaseResultBrief) => {
  drawerVisible.value = true;
  activeTab.value = 'overview';
  currentDetail.value = null;
  detailLoading.value = true;
  try {
    currentDetail.value = await getAutoCaseResultDetail(resultId, row.id);
  } catch {
    ElMessage.error('加载详情失败');
  } finally {
    detailLoading.value = false;
  }
};

const createBugForCurrent = async () => {
  if (!currentDetail.value || !projectId) return;
  singleCreatingBug.value = true;
  try {
    const { id } = await createBugFromCaseResult(projectId, currentDetail.value);
    ElMessage.success(`已创建 Bug #${id}`);
    router.push(`/projects/${projectId}/bugs/${id}`);
  } catch {
    ElMessage.error('创建 Bug 失败');
  } finally {
    singleCreatingBug.value = false;
  }
};

const bulkCreateBugs = async () => {
  if (!summary.value || !projectId) return;
  await ElMessageBox.confirm(
    `将为本次执行中所有失败/错误用例（${summary.value.failed_cases + summary.value.error_cases} 条）创建 Bug，是否继续？`,
    '确认',
    { type: 'warning' },
  );
  bulkCreatingBugs.value = true;
  try {
    // 拉所有失败的用例（按需分页，最多 200 条以保护后端）
    const failed = await listAutoResultCases(resultId, {
      passed: false, page: 1, page_size: 200,
    });
    let ok = 0;
    let fail = 0;
    for (const c of failed.results) {
      try {
        await createBugFromCaseResult(projectId, c);
        ok += 1;
      } catch {
        fail += 1;
      }
    }
    ElMessage.success(`完成：成功 ${ok} 条${fail ? `，失败 ${fail} 条` : ''}`);
  } catch {
    // 用户取消或网络
  } finally {
    bulkCreatingBugs.value = false;
  }
};

const goBack = () => router.back();

const semanticLabel = (row: Partial<AutoCaseResultBrief> | Partial<AutoCaseResultFull> | null | undefined) => {
  if (!row) return '未知结果';
  return row.semantic_label || (row.passed ? '成功响应断言通过' : '测试失败');
};

const semanticTagType = (row: Partial<AutoCaseResultBrief> | Partial<AutoCaseResultFull> | null | undefined) => {
  const semantic = row?.semantic_status || '';
  if (semantic === 'expected_error_matched' || semantic === 'success_response_passed') return 'success';
  if (semantic === 'expected_error_unmatched' || semantic === 'success_response_failed') return 'danger';
  if (semantic === 'expected_error_execution_error') return 'warning';
  return row?.passed ? 'success' : 'warning';
};

const statusType = (s: string) =>
  ({ passed: 'success', failed: 'danger', error: 'warning', running: 'info', pending: 'info' } as Record<
    string,
    string
  >)[s] || 'info';

const statusCodeClass = (code: number) => {
  if (!code) return '';
  if (code >= 200 && code < 300) return 'sc-2xx';
  if (code >= 300 && code < 400) return 'sc-3xx';
  if (code >= 400 && code < 500) return 'sc-4xx';
  return 'sc-5xx';
};

const formatDuration = (ms: number | null | undefined) => {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
  const m = Math.floor(ms / 60000);
  const s = ((ms % 60000) / 1000).toFixed(1);
  return `${m}m ${s}s`;
};

const formatDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleString() : '-');

const formatJson = (data: any) => {
  if (data == null) return '';
  if (typeof data === 'string') {
    try { return JSON.stringify(JSON.parse(data), null, 2); } catch { return data; }
  }
  return JSON.stringify(data, null, 2);
};

const formatValue = (v: any) => {
  if (v === null || v === undefined) return '(空)';
  if (typeof v === 'object') return JSON.stringify(v, null, 2);
  return String(v);
};

const failureLabel = computed(() => {
  const ft = currentDetail.value?.failure_type;
  if (!ft) return '';
  return FAILURE_TYPE_LABELS[ft] || ft;
});

const failureTagType = computed(() => {
  const ft = currentDetail.value?.failure_type;
  if (!ft) return 'info' as const;
  return FAILURE_TYPE_TAG[ft] || 'info';
});

const hasExtractedVars = computed(() => {
  const p = currentDetail.value?.extracted_variables_preview;
  return !!p && Object.keys(p).length > 0;
});

const extractedVarRows = computed(() => {
  const p = currentDetail.value?.extracted_variables_preview || {};
  return Object.entries(p).map(([name, env]) => ({
    name,
    preview: env?.preview ?? '',
    redacted: env?.redacted ?? false,
    truncated: env?.truncated ?? false,
  }));
});

onMounted(reload);
</script>

<style scoped>
.auto-result-detail { padding: 0; }
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-border-light);
}
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h2 {
  margin: 0;
  font: 600 20px/1.3 var(--font-heading);
  color: var(--color-text);
}
.header-actions { display: flex; gap: 8px; }

.overview-card { margin-bottom: 16px; }
.overview-row { display: flex; gap: 32px; flex-wrap: wrap; }
.overview-item { display: flex; flex-direction: column; gap: 4px; min-width: 80px; }
.overview-label { color: var(--color-text-secondary); font-size: 12px; font-weight: 500; }
.overview-value {
  font: 600 22px/1.2 var(--font-heading);
  color: var(--color-text);
}
.text-success { color: var(--color-success); }
.text-danger { color: var(--color-danger); }
.text-warning { color: var(--color-warning); }

.cases-card { margin-bottom: 16px; }
.cases-toolbar { display: flex; justify-content: space-between; align-items: center; }
.filters { display: flex; gap: 8px; }
.clickable-row { cursor: pointer; }
.pagination { margin-top: 12px; justify-content: flex-end; display: flex; }

.semantic-result-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.semantic-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.method-tag {
  font-weight: 600; font-size: 11px; padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-sunken);
  color: var(--color-text-secondary);
}
.method-tag.get { background: var(--color-info-bg); color: var(--color-info); }
.method-tag.post { background: var(--color-success-bg); color: var(--color-success); }
.method-tag.put { background: var(--color-warning-bg); color: var(--color-warning); }
.method-tag.patch { background: var(--color-primary-bg); color: var(--color-primary); }
.method-tag.delete { background: var(--color-danger-bg); color: var(--color-danger); }

.sc-2xx { color: var(--color-success); font-weight: 600; }
.sc-3xx { color: var(--color-warning); font-weight: 600; }
.sc-4xx { color: var(--color-danger); font-weight: 600; }
.sc-5xx { color: var(--color-danger); font-weight: 700; }
.error-summary { color: var(--color-danger); font-size: 12px; }

.drawer-body { display: flex; flex-direction: column; height: 100%; }
.drawer-footer {
  display: flex; gap: 8px; justify-content: flex-end;
  padding-top: 12px;
  border-top: 1px solid var(--color-border-light);
  margin-top: 12px;
}

.section-title {
  font: 600 14px/1.3 var(--font-heading);
  color: var(--color-text);
  margin: 16px 0 8px;
}
.code {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  padding: 12px;
  border-radius: var(--radius-md);
  white-space: pre-wrap; word-break: break-all;
  font-family: var(--font-mono); font-size: 12px;
  color: var(--color-text);
  max-height: 320px; overflow: auto;
}

.trace-id {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--color-text-secondary);
}
.curl-hint {
  font-size: 12px; color: var(--color-text-secondary);
  margin-bottom: 6px;
}
.extracted-preview {
  font-family: var(--font-mono); font-size: 12px;
  word-break: break-all;
}
</style>
