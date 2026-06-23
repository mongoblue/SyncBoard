<template>
  <div class="quality-report">
    <header class="page-header">
      <div>
        <h1 class="page-title">项目质量报告</h1>
        <p class="page-subtitle">基于任务、Bug、部署与性能数据的综合评分</p>
      </div>
      <el-button @click="fetchReport" :loading="loading" size="small"><el-icon><Refresh /></el-icon>刷新</el-button>
    </header>

    <el-row :gutter="20" v-loading="loading">
      <!-- 总分 -->
      <el-col :span="6">
        <el-card class="score-card" shadow="hover">
          <div class="total-score">{{ report?.total_score || 0 }}</div>
          <div class="score-label">质量总分</div>
          <el-progress :percentage="report?.total_score || 0" :color="scoreColor" :stroke-width="8" />
        </el-card>
      </el-col>

      <!-- 摘要 -->
      <el-col :span="18">
        <el-card shadow="hover">
          <el-row :gutter="12">
            <el-col :span="6" v-for="s in summaryCards" :key="s.label">
              <div class="summary-item">
                <div class="summary-value">{{ s.value }}</div>
                <div class="summary-label">{{ s.label }}</div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top:20px">
      <!-- 雷达图 -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>五维评分</span></template>
          <div ref="radarChart" class="chart-container"></div>
        </el-card>
      </el-col>

      <!-- 维度详情 -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>维度详情</span></template>
          <div v-for="d in report?.dimensions || []" :key="d.name" class="dimension-item">
            <div class="dim-header">
              <span class="dim-name">{{ d.name }}</span>
              <span class="dim-score">{{ d.score }}/{{ d.max }}</span>
            </div>
            <el-progress :percentage="(d.score / d.max) * 100" :color="dimColor(d.score, d.max)" :stroke-width="6" />
            <div class="dim-detail">{{ d.detail }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 -->
    <el-card shadow="hover" style="margin-top:20px" v-if="report?.trend?.length">
      <template #header><span>30天趋势</span></template>
      <div ref="trendChart" class="chart-container"></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { useRoute } from 'vue-router';
import * as echarts from 'echarts';
import service from '@/utils/request';
import { Refresh } from '@element-plus/icons-vue';

const route = useRoute();
const projectId = computed(() => route.params.projectId as string);
const loading = ref(false);
const report = ref<any>(null);
const radarChart = ref<HTMLElement>();
const trendChart = ref<HTMLElement>();

const scoreColor = computed(() => {
  const s = report.value?.total_score || 0;
  return s >= 80 ? 'var(--color-success)' : s >= 60 ? 'var(--color-warning)' : 'var(--color-danger)';
});

const dimColor = (score: number, max: number) => {
  const r = score / max;
  return r >= 0.8 ? 'var(--color-success)' : r >= 0.5 ? 'var(--color-warning)' : 'var(--color-danger)';
};

const summaryCards = computed(() => {
  const s = report.value?.summary || {};
  return [
    { label: '总任务', value: s.total_tasks || 0 },
    { label: 'Bug数', value: s.bug_count || 0 },
    { label: '最近部署', value: s.recent_pipelines || 0 },
    { label: '性能数据', value: s.has_perf_data ? '有' : '无' },
  ];
});

const fetchReport = async () => {
  loading.value = true;
  try {
    const data = await service.get(`/qa/devops/quality-report/?project_id=${projectId.value}`);
    report.value = data;
    await nextTick();
    renderCharts();
  } catch { /* silent */ }
  finally { loading.value = false; }
};

const renderCharts = () => {
  if (!report.value) return;

  // 雷达图
  if (radarChart.value) {
    const dims = report.value.dimensions || [];
    const chart = echarts.init(radarChart.value);
    chart.setOption({
      radar: {
        indicator: dims.map((d: any) => ({ name: d.name, max: d.max })),
        center: ['50%', '55%'],
        radius: '70%',
      },
      series: [{
        type: 'radar',
        data: [{ value: dims.map((d: any) => d.score), name: '当前' }],
        areaStyle: { color: 'rgba(15,118,110,0.15)' },
        lineStyle: { color: '#0F766E', width: 2 },
        itemStyle: { color: '#0F766E' },
      }],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  // 趋势图
  if (trendChart.value && report.value.trend?.length) {
    const trend = report.value.trend;
    const chart = echarts.init(trendChart.value);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: trend.map((t: any) => t.date), axisLabel: { rotate: 30, fontSize: 10 } },
      yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
      series: [{
        name: '通过率', type: 'line', data: trend.map((t: any) => t.rate),
        smooth: true, lineStyle: { color: '#1A7F37' }, itemStyle: { color: '#1A7F37' },
        areaStyle: { color: 'rgba(26,127,55,0.10)' },
      }],
      grid: { left: 30, right: 20, top: 10, bottom: 40 },
    });
    window.addEventListener('resize', () => chart.resize());
  }
};

onMounted(fetchReport);
</script>

<style scoped>
.quality-report { padding: 0; }
.score-card { text-align: center; }
.total-score { font-family: var(--font-heading); font-size: 40px; font-weight: 600; color: var(--color-text); line-height: 1.1; }
.score-label { color: var(--color-text-secondary); font-size: 13px; margin: 6px 0 12px; }
.summary-item { text-align: center; padding: 8px; }
.summary-value { font-family: var(--font-heading); font-size: 20px; font-weight: 600; color: var(--color-text); }
.summary-label { font-size: 12px; color: var(--color-text-secondary); margin-top: 4px; }
.chart-container { height: 320px; }
.dimension-item { margin-bottom: 16px; }
.dim-header { display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 13px; }
.dim-name { color: var(--color-text); }
.dim-score { color: var(--color-text-secondary); font-weight: 600; }
.dim-detail { font-size: 12px; color: var(--color-text-tertiary); margin-top: 2px; }
</style>
