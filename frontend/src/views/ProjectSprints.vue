<template>
  <div class="sprints-page">
    <div class="page-header">
      <h2>迭代管理</h2>
      <el-button type="primary" @click="showCreate = true"><el-icon><Plus /></el-icon>新建迭代</el-button>
    </div>

    <el-row :gutter="20" v-loading="loading">
      <el-col :span="8" v-for="s in sprints" :key="s.id">
        <el-card class="sprint-card" shadow="hover" @click="$router.push(`/projects/${projectId}/sprints/${s.id}`)">
          <div class="sprint-header">
            <el-tag :type="s.is_active ? 'success' : 'info'" size="small">{{ s.is_active ? '进行中' : '已结束' }}</el-tag>
            <span class="sprint-dates">{{ s.start_date }} ~ {{ s.end_date }}</span>
          </div>
          <h3>{{ s.name }}</h3>
          <p v-if="s.goal" class="sprint-goal">{{ s.goal }}</p>
          <el-progress
            :percentage="s.task_count ? Math.round(s.completed_count / s.task_count * 100) : 0"
            :stroke-width="8"
          />
          <div class="sprint-meta">{{ s.completed_count }}/{{ s.task_count }} 任务完成</div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && !sprints.length" description="暂无迭代，点击上方按钮创建" />

    <!-- 创建弹窗 -->
    <el-dialog v-model="showCreate" title="新建迭代" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="目标"><el-input v-model="form.goal" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="开始日期"><el-date-picker v-model="form.start_date" type="date" style="width:100%" /></el-form-item>
        <el-form-item label="结束日期"><el-date-picker v-model="form.end_date" type="date" style="width:100%" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createSprint" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import service from '@/utils/request';
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';

const route = useRoute();
const projectId = computed(() => route.params.projectId as string);
const sprints = ref<any[]>([]);
const loading = ref(false);
const showCreate = ref(false);
const creating = ref(false);
const form = ref({ name: '', goal: '', start_date: '', end_date: '' });

const fetchSprints = async () => {
  loading.value = true;
  try {
    sprints.value = await service.get(`/projects/${projectId.value}/sprints/`);
  } finally { loading.value = false; }
};

const createSprint = async () => {
  if (!form.value.name || !form.value.start_date || !form.value.end_date) {
    ElMessage.warning('请填写完整信息'); return;
  }
  creating.value = true;
  try {
    await service.post(`/projects/${projectId.value}/sprints/`, {
      name: form.value.name, goal: form.value.goal,
      start_date: form.value.start_date, end_date: form.value.end_date,
    });
    ElMessage.success('迭代已创建');
    showCreate.value = false;
    form.value = { name: '', goal: '', start_date: '', end_date: '' };
    fetchSprints();
  } catch (e: any) { ElMessage.error(e?.detail || '创建失败'); }
  finally { creating.value = false; }
};

onMounted(fetchSprints);
</script>

<style scoped>
.sprints-page { max-width: 1000px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; }
.sprint-card { cursor: pointer; margin-bottom: 16px; }
.sprint-card:hover { border-color: var(--color-primary-light); }
.sprint-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sprint-dates { font-size: 12px; color: var(--color-text-tertiary); }
.sprint-card h3 { margin: 0 0 8px; font-size: 16px; }
.sprint-goal { color: var(--color-text-secondary); font-size: 13px; margin: 0 0 12px; }
.sprint-meta { font-size: 12px; color: var(--color-text-tertiary); margin-top: 8px; text-align: right; }
</style>
