<template>
  <el-dialog
    v-model="visible"
    title="批量执行 API 自动化用例"
    width="900px"
    :close-on-click-modal="false"
    :destroy-on-close="true"
    @closed="onClosed"
  >
    <!-- Stage 1: 选择用例 + 配置 -->
    <div v-if="stage === 'configure'" class="bre-body">
      <!-- 计划基本信息 -->
      <el-form :model="form" label-width="100px" size="default">
        <el-form-item label="计划名称" required>
          <el-input v-model="form.name" placeholder="例如：登录回归 / 下单核心链路" maxlength="80" />
        </el-form-item>
        <el-form-item label="并发执行">
          <el-switch v-model="form.parallel" />
          <span class="hint" v-if="form.parallel">
            同时最多 {{ form.max_workers }} 个用例
          </span>
          <span class="hint" v-else>串行执行，按勾选顺序逐个跑</span>
        </el-form-item>
        <el-form-item label="并发数" v-if="form.parallel">
          <el-input-number v-model="form.max_workers" :min="1" :max="32" />
        </el-form-item>
        <el-form-item label="遇错即停">
          <el-switch v-model="form.stop_on_failure" />
          <span class="hint">任一用例失败立即中止后续</span>
        </el-form-item>
        <el-form-item label="单条超时">
          <el-input-number
            v-model="form.case_timeout_seconds"
            :min="1"
            :max="300"
          />
          <span class="hint">秒；用例自身的 timeout_seconds 仍优先</span>
        </el-form-item>
      </el-form>

      <el-divider>选择用例</el-divider>

      <!-- 用例选择器 -->
      <div class="cases-toolbar">
        <el-input
          v-model="caseSearch"
          placeholder="按名称 / URL 搜索"
          clearable
          style="width: 240px"
          @input="onCaseSearch"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select
          v-model="suiteFilter"
          placeholder="按测试套筛选"
          clearable
          style="width: 200px"
        >
          <el-option
            v-for="s in suiteOptions"
            :key="s.id"
            :label="s.name"
            :value="s.id"
          />
        </el-select>
        <div class="selection-status">
          已选 <strong>{{ selectedIds.size }}</strong> / {{ filteredCases.length }} 条
          <el-button text size="small" @click="selectAllVisible">全选当前</el-button>
          <el-button text size="small" @click="clearSelection">清空</el-button>
        </div>
      </div>

      <el-table
        ref="caseTableRef"
        v-loading="casesLoading"
        :data="filteredCases"
        height="340"
        @selection-change="onTableSelectionChange"
        @row-click="(row: any) => toggleRow(row)"
        row-key="id"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column label="方法" width="80">
          <template #default="{ row }">
            <span class="method-tag" :class="row.method?.toLowerCase()">{{ row.method }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="用例名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="url" label="URL" min-width="240" show-overflow-tooltip />
        <el-table-column prop="suite_name" label="测试套" width="160" show-overflow-tooltip />
      </el-table>
    </div>

    <!-- Stage 2: 实时进度 -->
    <div v-else-if="stage === 'running' || stage === 'done'" class="bre-progress">
      <div class="progress-header">
        <div class="progress-title">
          <el-icon v-if="stage === 'running'" class="rotating"><Loading /></el-icon>
          <el-icon v-else-if="finalStatus === 'passed'" color="var(--color-success)"><CircleCheck /></el-icon>
          <el-icon v-else color="var(--color-danger)"><CircleClose /></el-icon>
          <span>{{ stageTitle }}</span>
        </div>
        <div class="progress-meta">
          {{ progress.completed }} / {{ progress.total }} 已执行
        </div>
      </div>

      <el-progress
        :percentage="progressPercent"
        :status="progressBarStatus"
        :stroke-width="12"
      />

      <div class="counter-row">
        <div class="counter">
          <div class="counter-label">通过</div>
          <div class="counter-value text-success">{{ progress.passed }}</div>
        </div>
        <div class="counter">
          <div class="counter-label">失败</div>
          <div class="counter-value text-danger">{{ progress.failed }}</div>
        </div>
        <div class="counter">
          <div class="counter-label">错误</div>
          <div class="counter-value text-warning">{{ progress.error }}</div>
        </div>
        <div class="counter">
          <div class="counter-label">剩余</div>
          <div class="counter-value">{{ Math.max(0, progress.total - progress.completed) }}</div>
        </div>
      </div>

      <div class="log-section">
        <div class="log-header">执行日志</div>
        <div ref="logScrollRef" class="log-list">
          <div
            v-for="(line, i) in progressLog"
            :key="i"
            class="log-line"
            :class="line.level"
          >
            <span class="log-time">{{ line.time }}</span>
            <span class="log-icon">
              <el-icon v-if="line.level === 'success'" color="var(--color-success)"><CircleCheck /></el-icon>
              <el-icon v-else-if="line.level === 'fail'" color="var(--color-danger)"><CircleClose /></el-icon>
              <el-icon v-else-if="line.level === 'info'" color="var(--color-text-tertiary)"><InfoFilled /></el-icon>
              <el-icon v-else color="var(--color-warning)"><Warning /></el-icon>
            </span>
            <span class="log-text">{{ line.text }}</span>
          </div>
          <el-empty v-if="!progressLog.length" description="等待执行..." :image-size="60" />
        </div>
      </div>
    </div>

    <template #footer>
      <div v-if="stage === 'configure'" class="footer-actions">
        <el-button @click="visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="startExecution"
        >
          开始执行 ({{ selectedIds.size }})
        </el-button>
      </div>
      <div v-else-if="stage === 'running'" class="footer-actions">
        <span class="hint">执行中，可关闭对话框继续在后台运行</span>
        <el-button @click="visible = false">最小化</el-button>
      </div>
      <div v-else class="footer-actions">
        <el-button @click="visible = false">关闭</el-button>
        <el-button
          v-if="resultId"
          type="primary"
          @click="goToDetail"
        >
          查看完整结果
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import {
  Search, Loading, CircleCheck, CircleClose, InfoFilled, Warning,
} from '@element-plus/icons-vue';
import {
  listSelectableCases,
  createRunPlan,
  executeRunPlan,
  type RunPlanCaseBrief,
  type RunPlanProgressEvent,
} from '@/api/runplan';

const props = defineProps<{
  modelValue: boolean;
  projectId: string | number;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void;
  (e: 'finished', resultId: number): void;
}>();

const router = useRouter();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
});

type Stage = 'configure' | 'running' | 'done';
const stage = ref<Stage>('configure');

// ---------- 表单 ----------
const form = ref({
  name: '',
  parallel: true,
  max_workers: 4,
  stop_on_failure: false,
  case_timeout_seconds: 30,
});

// ---------- 用例列表 ----------
const casesLoading = ref(false);
const allCases = ref<RunPlanCaseBrief[]>([]);
const caseSearch = ref('');
const suiteFilter = ref<number | ''>('');
const selectedIds = ref<Set<number>>(new Set());
const caseTableRef = ref<any>(null);

const suiteOptions = computed(() => {
  const seen = new Map<number, string>();
  for (const c of allCases.value) {
    if (!seen.has(c.suite_id)) seen.set(c.suite_id, c.suite_name);
  }
  return Array.from(seen, ([id, name]) => ({ id, name }));
});

const filteredCases = computed(() => {
  const s = caseSearch.value.trim().toLowerCase();
  return allCases.value.filter((c) => {
    if (suiteFilter.value !== '' && c.suite_id !== suiteFilter.value) return false;
    if (s && !c.name.toLowerCase().includes(s) && !c.url.toLowerCase().includes(s)) return false;
    return true;
  });
});

const canSubmit = computed(
  () => !!form.value.name.trim() && selectedIds.value.size > 0 && !submitting.value,
);

let searchTimer: number | null = null;
const onCaseSearch = () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(loadCases, 300);
};

const loadCases = async () => {
  casesLoading.value = true;
  try {
    const res = await listSelectableCases(props.projectId, caseSearch.value || undefined);
    allCases.value = res.results;
    // 同步表格的勾选态（el-table 在数据变化后会丢勾选）
    nextTick(() => syncTableSelection());
  } catch {
    ElMessage.error('加载用例失败');
  } finally {
    casesLoading.value = false;
  }
};

const onTableSelectionChange = (rows: RunPlanCaseBrief[]) => {
  // 在当前可见集中：被勾选的加入，未勾选的剔除（其他视图保留）
  const visibleIds = new Set(filteredCases.value.map((c) => c.id));
  const next = new Set(selectedIds.value);
  for (const id of visibleIds) next.delete(id);
  for (const r of rows) next.add(r.id);
  selectedIds.value = next;
};

const toggleRow = (row: RunPlanCaseBrief) => {
  if (caseTableRef.value) caseTableRef.value.toggleRowSelection(row);
};

const selectAllVisible = () => {
  const next = new Set(selectedIds.value);
  for (const c of filteredCases.value) next.add(c.id);
  selectedIds.value = next;
  nextTick(() => syncTableSelection());
};

const clearSelection = () => {
  selectedIds.value = new Set();
  if (caseTableRef.value) caseTableRef.value.clearSelection();
};

const syncTableSelection = () => {
  if (!caseTableRef.value) return;
  for (const row of filteredCases.value) {
    caseTableRef.value.toggleRowSelection(row, selectedIds.value.has(row.id));
  }
};

watch(() => visible.value, (v) => {
  if (v) {
    // 若上次执行已结束，回到配置态；运行中则保留进度视图
    if (stage.value === 'done') {
      stage.value = 'configure';
      resetProgress();
    }
    if (stage.value === 'configure') loadCases();
  }
});

watch(suiteFilter, () => nextTick(() => syncTableSelection()));
watch(filteredCases, () => nextTick(() => syncTableSelection()));

// ---------- 执行 ----------
const submitting = ref(false);
const planId = ref<number | null>(null);
const resultId = ref<number | null>(null);
const finalStatus = ref<'passed' | 'failed' | 'error' | null>(null);

const progress = ref({
  total: 0, completed: 0, passed: 0, failed: 0, error: 0,
});

interface LogLine { time: string; level: 'info' | 'success' | 'fail' | 'warn'; text: string }
const progressLog = ref<LogLine[]>([]);
const logScrollRef = ref<HTMLElement | null>(null);

let ws: WebSocket | null = null;

const startExecution = async () => {
  submitting.value = true;
  try {
    // 1. 创建 plan
    const plan = await createRunPlan({
      project: props.projectId,
      name: form.value.name.trim(),
      case_ids: Array.from(selectedIds.value),
      parallel: form.value.parallel,
      max_workers: form.value.max_workers,
      stop_on_failure: form.value.stop_on_failure,
      case_timeout_seconds: form.value.case_timeout_seconds,
    });
    planId.value = plan.id;

    // 2. 进入进度阶段并连 WS（先连，避免错过 started 事件）
    stage.value = 'running';
    progress.value = {
      total: selectedIds.value.size,
      completed: 0, passed: 0, failed: 0, error: 0,
    };
    pushLog('info', `已创建批量计划 #${plan.id}（${selectedIds.value.size} 条用例）`);
    connectWebSocket();

    // 3. 触发执行
    await executeRunPlan(plan.id, {
      parallel: form.value.parallel,
      max_workers: form.value.max_workers,
      stop_on_failure: form.value.stop_on_failure,
    });
    pushLog('info', '已下发执行请求，等待后端推送进度...');
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '创建/执行失败');
    stage.value = 'configure';
  } finally {
    submitting.value = false;
  }
};

const connectWebSocket = () => {
  if (ws) { try { ws.close(); } catch { /* noop */ } }
  const host = window.location.hostname;
  const port = host === 'localhost' || host === '127.0.0.1' ? ':8000' : '';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${host}${port}/ws/qa/dashboard/`);

  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as RunPlanProgressEvent;
      if (data?.type !== 'run_plan_progress') return;
      if (planId.value && data.plan_id !== planId.value) return;
      handleProgressEvent(data);
    } catch {
      // ignore
    }
  };
  ws.onerror = () => pushLog('warn', 'WebSocket 连接异常，进度可能延迟');
  ws.onclose = () => { ws = null; };
};

const handleProgressEvent = (ev: RunPlanProgressEvent) => {
  if (ev.result_id) resultId.value = ev.result_id;
  if (typeof ev.total === 'number' && ev.total > 0) progress.value.total = ev.total;

  if (ev.phase === 'started') {
    pushLog('info', `执行已启动，共 ${ev.total} 条用例`);
    return;
  }
  if (ev.phase === 'case_done') {
    progress.value.completed = ev.completed ?? progress.value.completed;
    progress.value.passed = ev.passed ?? progress.value.passed;
    progress.value.failed = ev.failed ?? progress.value.failed;
    progress.value.error = ev.error ?? progress.value.error;
    const name = ev.case_name || `#${ev.case_id}`;
    if (ev.case_passed) {
      pushLog('success', `[${progress.value.completed}/${progress.value.total}] PASS  ${name}`);
    } else {
      const errPart = ev.case_error ? ` — ${ev.case_error}` : '';
      pushLog('fail', `[${progress.value.completed}/${progress.value.total}] FAIL  ${name}${errPart}`);
    }
    return;
  }
  if (ev.phase === 'finished') {
    finalStatus.value = ev.status ?? 'failed';
    progress.value.completed = ev.completed ?? progress.value.completed;
    progress.value.passed = ev.passed ?? progress.value.passed;
    progress.value.failed = ev.failed ?? progress.value.failed;
    progress.value.error = ev.error ?? progress.value.error;
    pushLog(
      finalStatus.value === 'passed' ? 'success' : 'fail',
      `执行结束：${labelOfStatus(finalStatus.value)}  通过 ${progress.value.passed}，失败 ${progress.value.failed}，错误 ${progress.value.error}`,
    );
    stage.value = 'done';
    if (resultId.value) emit('finished', resultId.value);
    closeWebSocket();
  }
};

const pushLog = (level: LogLine['level'], text: string) => {
  const t = new Date();
  const time = `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
  progressLog.value.push({ time, level, text });
  if (progressLog.value.length > 500) progressLog.value.splice(0, 100);
  nextTick(() => {
    if (logScrollRef.value) logScrollRef.value.scrollTop = logScrollRef.value.scrollHeight;
  });
};

const pad = (n: number) => (n < 10 ? `0${n}` : String(n));

const labelOfStatus = (s: 'passed' | 'failed' | 'error') =>
  ({ passed: '全部通过', failed: '存在失败', error: '存在错误' }[s]);

const progressPercent = computed(() => {
  if (!progress.value.total) return 0;
  return Math.min(100, Math.round((progress.value.completed / progress.value.total) * 100));
});

const progressBarStatus = computed<'success' | 'exception' | 'warning' | ''>(() => {
  if (stage.value !== 'done') return '';
  if (finalStatus.value === 'passed') return 'success';
  if (finalStatus.value === 'error') return 'warning';
  return 'exception';
});

const stageTitle = computed(() => {
  if (stage.value === 'running') return '执行中...';
  if (finalStatus.value === 'passed') return '执行完成';
  return '执行完成（有失败/错误）';
});

const goToDetail = () => {
  if (!resultId.value) return;
  router.push(`/projects/${props.projectId}/qa/auto-results/${resultId.value}`);
  visible.value = false;
};

const closeWebSocket = () => {
  if (ws) { try { ws.close(); } catch { /* noop */ } ws = null; }
};

const resetProgress = () => {
  progress.value = { total: 0, completed: 0, passed: 0, failed: 0, error: 0 };
  progressLog.value = [];
  planId.value = null;
  resultId.value = null;
  finalStatus.value = null;
  caseSearch.value = '';
  suiteFilter.value = '';
  selectedIds.value = new Set();
  form.value.name = '';
};

const onClosed = () => {
  // 对话框关闭时：若任务跑完，重置；若还在跑，保留 WS 让其在后台收到 finished 事件
  if (stage.value === 'done') resetProgress();
};

onBeforeUnmount(closeWebSocket);
</script>

<style scoped>
.bre-body { max-height: 70vh; overflow-y: auto; padding-right: 4px; }
.hint { margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px; }

.cases-toolbar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap;
}
.selection-status { margin-left: auto; color: var(--el-text-color-secondary); font-size: 13px; }
.selection-status strong { color: var(--el-color-primary); margin: 0 2px; }

.method-tag {
  font-weight: 600; font-size: 11px; padding: 2px 6px; border-radius: 3px;
  background: var(--color-border-light);
}
.method-tag.get { background: #e0f2fe; color: #075985; }
.method-tag.post { background: #dcfce7; color: #166534; }
.method-tag.put { background: #fef3c7; color: #92400e; }
.method-tag.patch { background: #ede9fe; color: #5b21b6; }
.method-tag.delete { background: #fee2e2; color: #991b1b; }

.bre-progress { padding: 8px 0; }
.progress-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
}
.progress-title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 600; }
.progress-meta { color: var(--el-text-color-secondary); font-size: 13px; }
.rotating { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

.counter-row {
  display: flex; gap: 24px; margin: 16px 0;
  padding: 12px 16px; background: var(--el-fill-color-light); border-radius: 6px;
}
.counter { display: flex; flex-direction: column; gap: 4px; }
.counter-label { color: var(--el-text-color-secondary); font-size: 12px; }
.counter-value { font-size: 20px; font-weight: 600; }
.text-success { color: var(--el-color-success); }
.text-danger { color: var(--el-color-danger); }
.text-warning { color: var(--el-color-warning); }

.log-section { margin-top: 12px; }
.log-header {
  font-weight: 600; margin-bottom: 6px; color: var(--el-text-color-regular);
}
.log-list {
  height: 240px; overflow-y: auto;
  background: #1E293B; border-radius: 4px; padding: 8px 12px;
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px;
}
.log-line {
  display: flex; align-items: center; gap: 8px; padding: 2px 0;
  color: var(--color-text-tertiary);
}
.log-line.success { color: #86efac; }
.log-line.fail { color: #fca5a5; }
.log-line.warn { color: #fcd34d; }
.log-line.info { color: #93c5fd; }
.log-time { color: var(--color-text-secondary); flex-shrink: 0; }
.log-text { word-break: break-all; }

.footer-actions {
  display: flex; justify-content: flex-end; align-items: center; gap: 8px;
}
.footer-actions .hint { margin-right: auto; }
</style>
