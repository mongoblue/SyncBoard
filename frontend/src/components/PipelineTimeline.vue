<template>
  <div class="pipeline-timeline">
    <div class="timeline-header">
      <h4>Pipeline 执行历史</h4>
      <el-button size="small" @click="fetchRuns" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <el-empty v-if="!loading && runs.length === 0" description="暂无执行记录" :image-size="48" />

    <div v-else class="timeline-list">
      <div
        v-for="run in runs"
        :key="run.id"
        class="timeline-item"
        :class="'status-' + run.status"
        @click="selectedRun = run"
      >
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <div class="run-header">
            <el-tag :type="statusTag(run.status)" size="small">{{ statusLabel(run.status) }}</el-tag>
            <span class="run-name">{{ run.cicd_config_name }}</span>
            <span class="run-branch" v-if="run.branch">{{ run.branch }}</span>
          </div>
          <div class="run-meta">
            <span v-if="run.commit_sha">#{{ run.commit_sha.substring(0, 7) }}</span>
            <span>{{ formatTime(run.created_at) }}</span>
            <span v-if="run.test_results_summary?.total">
              测试 {{ run.test_results_summary.passed }}/{{ run.test_results_summary.total }} 通过
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="Pipeline 执行详情" width="600px">
      <template v-if="selectedRun">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="配置">{{ selectedRun.cicd_config_name }}</el-descriptions-item>
          <el-descriptions-item label="CI类型">{{ selectedRun.ci_type }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(selectedRun.status)">{{ statusLabel(selectedRun.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="分支">{{ selectedRun.branch || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Commit">{{ selectedRun.commit_sha?.substring(0, 7) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatTime(selectedRun.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatTime(selectedRun.completed_at) }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="selectedRun.test_results_summary?.total" class="test-summary">
          <h4>测试结果</h4>
          <el-progress
            :percentage="Math.round((selectedRun.test_results_summary.passed / selectedRun.test_results_summary.total) * 100)"
            :status="selectedRun.status === 'passed' ? 'success' : 'exception'"
          />
          <div class="test-detail">
            <el-tag type="success">通过 {{ selectedRun.test_results_summary.passed }}</el-tag>
            <el-tag type="danger">失败 {{ selectedRun.test_results_summary.failed }}</el-tag>
            <el-tag>总计 {{ selectedRun.test_results_summary.total }}</el-tag>
          </div>
        </div>

        <div v-if="selectedRun.log_output" class="log-section">
          <h4>构建日志</h4>
          <pre class="log-output">{{ selectedRun.log_output }}</pre>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import service from '@/utils/request';
import { Refresh } from '@element-plus/icons-vue';

const props = defineProps<{ projectId: string }>();
const runs = ref<any[]>([]);
const loading = ref(false);
const selectedRun = ref<any>(null);
const detailVisible = ref(false);

const statusTag = (s: string) => s === 'passed' ? 'success' : s === 'failed' ? 'danger' : s === 'running' ? 'warning' : 'info';
const statusLabel = (s: string) => ({ passed:'通过', failed:'失败', running:'运行中', pending:'等待中' } as any)[s] || s;
const formatTime = (ts: string | null) => ts ? new Date(ts).toLocaleString('zh-CN', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '-';

const fetchRuns = async () => {
  loading.value = true;
  try {
    const data = await service.get(`/qa/devops/pipeline-runs/?project_id=${props.projectId}`);
    runs.value = (data as any).results || [];
  } catch { /* silent */ }
  finally { loading.value = false; }
};

watch(() => selectedRun.value, (v) => {
  detailVisible.value = !!v;
});
watch(detailVisible, (v) => { if (!v) selectedRun.value = null; });

onMounted(fetchRuns);
</script>

<style scoped>
.pipeline-timeline { }
.timeline-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.timeline-header h4 { margin: 0; font-size: 14px; color: var(--color-text); }
.timeline-list { max-height: 400px; overflow-y: auto; padding-left: 8px; }
.timeline-item { display: flex; gap: 12px; padding: 8px 0; padding-left: 16px; border-left: 2px solid var(--color-border); cursor: pointer; position: relative; }
.timeline-item:hover { background: var(--color-bg); }
.timeline-item.status-passed { border-left-color: var(--color-success); }
.timeline-item.status-failed { border-left-color: var(--color-danger); }
.timeline-item.status-running { border-left-color: var(--color-warning); }
.timeline-dot { position: absolute; left: -5px; top: 14px; width: 8px; height: 8px; border-radius: 50%; background: var(--color-text-tertiary); }
.status-passed .timeline-dot { background: var(--color-success); }
.status-failed .timeline-dot { background: var(--color-danger); }
.status-running .timeline-dot { background: var(--color-warning); }
.timeline-content { flex: 1; min-width: 0; }
.run-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.run-name { font-weight: 500; font-size: 13px; }
.run-branch { font-size: 12px; color: var(--color-text-tertiary); background: var(--color-border-light); padding: 0 6px; border-radius: 3px; }
.run-meta { font-size: 12px; color: var(--color-text-tertiary); display: flex; gap: 12px; }
.test-summary { margin-top: 16px; }
.test-summary h4, .log-section h4 { font-size: 13px; color: var(--color-text-secondary); margin: 12px 0 8px; }
.test-detail { display: flex; gap: 8px; margin-top: 8px; }
.log-output { background: #1E293B; color: var(--color-border); padding: 12px; border-radius: 6px; font-size: 12px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; }
</style>
