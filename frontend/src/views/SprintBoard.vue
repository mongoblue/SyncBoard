<template>
  <div class="sprint-board" v-loading="loading">
    <header class="page-header">
      <div>
        <el-button link @click="$router.push(`/projects/${projectId}/sprints`)" style="padding-left: 0">
          <el-icon><ArrowLeft /></el-icon> 返回迭代列表
        </el-button>
        <h1 class="page-title">{{ sprint?.name }}</h1>
        <p v-if="sprint?.goal" class="page-subtitle">{{ sprint.goal }}</p>
      </div>
      <el-tag :type="sprint?.is_active ? 'success' : 'info'">{{ sprint?.is_active ? '进行中' : '已结束' }}</el-tag>
    </header>

    <el-row :gutter="20">
      <!-- 任务列表 -->
      <el-col :span="14">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>迭代任务 ({{ tasks.length }})</span>
              <el-button size="small" @click="showAddTask = true">
                <el-icon><Plus /></el-icon> 添加任务
              </el-button>
            </div>
          </template>
          <div v-if="tasks.length" class="task-list">
            <div v-for="st in tasks" :key="st.id" class="task-item"
              :class="{ done: st.task_detail?.column_title?.toLowerCase() === 'done' }">
              <div class="task-left">
                <el-checkbox
                  :model-value="st.task_detail?.column_title?.toLowerCase() === 'done'"
                  @change="() => {}"
                  disabled
                />
                <span class="task-title">{{ st.task_detail?.title }}</span>
              </div>
              <div class="task-right">
                <el-tag size="small">{{ st.task_detail?.column_title || st.task_detail?.column?.title }}</el-tag>
                <span v-if="st.task_detail?.assignee_details?.username" class="assignee">
                  {{ st.task_detail.assignee_details.username }}
                </span>
                <el-button link type="danger" size="small" @click="removeTask(st)">移除</el-button>
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无任务" :image-size="48" />
        </el-card>
      </el-col>

      <!-- 燃尽图 -->
      <el-col :span="10">
        <el-card shadow="hover">
          <template #header><span>燃尽图</span></template>
          <div ref="burndownChart" class="chart-container"></div>
          <div class="burndown-legend">
            <span class="ideal">理想线</span>
            <span class="actual">实际剩余</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 添加任务弹窗 -->
    <el-dialog v-model="showAddTask" title="添加任务到迭代" width="500px">
      <div class="add-task-search">
        <el-input v-model="searchText" placeholder="搜索任务..." clearable />
      </div>
      <div class="available-tasks">
        <el-checkbox-group v-model="selectedTaskIds">
          <div v-for="t in availableTasks" :key="t.id" class="available-task-item">
            <el-checkbox :label="t.id" :value="t.id">
              <span>{{ t.title }}</span>
              <el-tag size="small" style="margin-left:8px">{{ t.column_title || t.column?.title }}</el-tag>
            </el-checkbox>
          </div>
        </el-checkbox-group>
        <el-empty v-if="!availableTasks.length" description="没有可添加的任务" :image-size="48" />
      </div>
      <template #footer>
        <el-button @click="showAddTask = false">取消</el-button>
        <el-button type="primary" @click="addTasks" :loading="adding">添加选中</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { useRoute } from 'vue-router';
import * as echarts from 'echarts';
import service from '@/utils/request';
import { ElMessage } from 'element-plus';
import { Plus, ArrowLeft } from '@element-plus/icons-vue';

const route = useRoute();
const projectId = computed(() => route.params.projectId as string);
const sprintId = computed(() => (route.params as any).sprintId as string);
const sprint = ref<any>(null);
const tasks = ref<any[]>([]);
const loading = ref(false);
const showAddTask = ref(false);
const adding = ref(false);
const searchText = ref('');
const selectedTaskIds = ref<string[]>([]);
const availableTasks = ref<any[]>([]);
const burndownChart = ref<HTMLElement>();

const fetchSprint = async () => {
  loading.value = true;
  try {
    const [sRes, bRes] = await Promise.all([
      service.get(`/projects/${projectId.value}/sprints/${sprintId.value}/`),
      service.get(`/projects/${projectId.value}/sprints/${sprintId.value}/burndown/`),
    ]);
    sprint.value = sRes;
    tasks.value = (sRes as any).tasks || [];
    await nextTick();
    renderBurndown(bRes);
  } finally { loading.value = false; }
};

const renderBurndown = (data: any) => {
  if (!burndownChart.value || !data?.burndown?.length) return;
  const bd = data.burndown;
  const chart = echarts.init(burndownChart.value);
  chart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: bd.map((d: any) => d.date), axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', name: '剩余任务' },
    series: [
      { name: '理想线', type: 'line', data: bd.map((d: any) => d.ideal), lineStyle: { type: 'dashed', color: '#8C959F' }, itemStyle: { color: '#8C959F' } },
      { name: '实际剩余', type: 'line', data: bd.map((d: any) => d.remaining), lineStyle: { color: '#0F766E' }, itemStyle: { color: '#0F766E' }, areaStyle: { color: 'rgba(15,118,110,0.08)' } },
    ],
    grid: { left: 40, right: 20, top: 10, bottom: 40 },
  });
  window.addEventListener('resize', () => chart.resize());
};

// 加载可添加的任务（项目中不在迭代里的任务）
const loadAvailableTasks = async () => {
  const existingIds = tasks.value.map(t => t.task_detail?.id || t.task).filter(Boolean);
  try {
    // 获取项目所有列的任务
    const cols = await service.get(`/columns/?project=${projectId.value}`);
    const all: any[] = [];
    for (const c of (Array.isArray(cols) ? cols : (cols as any).results || [])) {
      for (const t of c.tasks || []) {
        if (!existingIds.includes(t.id)) {
          all.push({ ...t, column_title: c.title });
        }
      }
    }
    const q = searchText.value.toLowerCase();
    availableTasks.value = q ? all.filter(t => t.title?.toLowerCase().includes(q)) : all;
  } catch { availableTasks.value = []; }
};

watch(showAddTask, (v) => { if (v) loadAvailableTasks(); });
watch(searchText, () => loadAvailableTasks());

const addTasks = async () => {
  if (!selectedTaskIds.value.length) return;
  adding.value = true;
  try {
    for (const tid of selectedTaskIds.value) {
      await service.post(`/projects/${projectId.value}/sprints/${sprintId.value}/tasks/`, { task_id: tid });
    }
    ElMessage.success(`已添加 ${selectedTaskIds.value.length} 个任务`);
    showAddTask.value = false;
    selectedTaskIds.value = [];
    fetchSprint();
  } catch (e: any) { ElMessage.error(e?.detail || '添加失败'); }
  finally { adding.value = false; }
};

const removeTask = async (st: any) => {
  const tid = st.task_detail?.id || st.task;
  try {
    await service.delete(`/projects/${projectId.value}/sprints/${sprintId.value}/tasks/?task_id=${tid}`);
    ElMessage.success('已移除');
    fetchSprint();
  } catch { ElMessage.error('移除失败'); }
};

onMounted(fetchSprint);
</script>

<style scoped>
.sprint-board { padding: 0; }

.card-header { display: flex; justify-content: space-between; align-items: center; }

.task-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border-light);
}
.task-item:last-child { border-bottom: none; }
.task-item.done { opacity: 0.5; }
.task-item.done .task-title { text-decoration: line-through; }

.task-left { display: flex; align-items: center; gap: 8px; }
.task-right { display: flex; align-items: center; gap: 8px; }
.assignee { font-size: 12px; color: var(--color-text-tertiary); }

.chart-container { height: 280px; }

.burndown-legend {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 8px;
}

.burndown-legend .ideal::before {
  content: '';
  display: inline-block;
  width: 16px;
  height: 0;
  border-top: 2px dashed var(--color-text-tertiary);
  margin-right: 4px;
  vertical-align: middle;
}

.burndown-legend .actual::before {
  content: '';
  display: inline-block;
  width: 16px;
  height: 0;
  border-top: 2px solid var(--color-primary);
  margin-right: 4px;
  vertical-align: middle;
}

.available-tasks { max-height: 300px; overflow-y: auto; }
.available-task-item { padding: 6px 0; border-bottom: 1px solid var(--color-border-light); }
.available-task-item:last-child { border-bottom: none; }
.add-task-search { margin-bottom: 12px; }
</style>