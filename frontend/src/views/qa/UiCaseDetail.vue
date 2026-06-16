<template>
  <div class="ui-case-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <h2>{{ isEdit ? '编辑 UI 测试用例' : '新建 UI 测试用例' }}</h2>
      </div>
      <div class="header-actions">
        <el-button
          :type="isRecording ? 'danger' : 'warning'"
          @click="toggleRecording"
          :disabled="!form.url"
        >
          <el-icon><CirclePlus v-if="!isRecording" /><CircleClose v-else /></el-icon>
          {{ isRecording ? '⏹️ 停止录制' : '🔴 开始录制' }}
        </el-button>
        <el-button type="success" @click="handleRunTemp" :loading="running" v-if="!isEdit">
          <el-icon><VideoPlay /></el-icon>
          试运行
        </el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          <el-icon><Check /></el-icon>
          保存
        </el-button>
      </div>
    </div>

    <RecorderPanel
      v-if="isRecording"
      :default-url="form.url"
      @panel-stopped="isRecording = false"
      @append-step="onAppendStep"
      @replace-step="onReplaceStep"
      @replace-all="onReplaceAllSteps"
      @append-all="onAppendAllSteps"
    />

    <div class="content-wrapper">
      <!-- 左侧：配置区 -->
      <div class="config-section">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <el-icon><Setting /></el-icon>
              <span>基础配置</span>
            </div>
          </template>
          
          <el-form :model="form" label-position="top" :rules="rules" ref="formRef">
            <el-form-item label="用例名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入测试用例名称" />
            </el-form-item>

            <el-form-item label="起始 URL" prop="url">
              <el-input v-model="form.url" placeholder="https://example.com 或 http://localhost:5173" />
            </el-form-item>

            <el-form-item label="所属项目" prop="project">
              <el-select v-model="form.project" placeholder="选择项目" style="width: 100%">
                <el-option
                  v-for="project in projects"
                  :key="project.id"
                  :label="project.name"
                  :value="project.id"
                />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="steps-card">
          <template #header>
            <div class="card-header">
              <el-icon><List /></el-icon>
              <span>测试步骤</span>
              <el-button type="primary" size="small" @click="addStep" class="add-btn">
                <el-icon><Plus /></el-icon>
                添加步骤
              </el-button>
            </div>
          </template>

          <div v-if="form.steps.length > 0" class="steps-list">
            <div
              v-for="(step, index) in form.steps"
              :key="index"
              class="step-item"
            >
              <div class="step-number">{{ index + 1 }}</div>
              <div class="step-content">
                <el-row :gutter="10">
                  <el-col :span="6">
                    <el-select v-model="step.action" placeholder="动作" size="small" @change="onActionChange(step)">
                      <el-option-group label="基础操作">
                        <el-option label="点击 (Click)" value="click" />
                        <el-option label="双击 (Double Click)" value="double_click" />
                        <el-option label="右键 (Right Click)" value="right_click" />
                        <el-option label="悬停 (Hover)" value="hover" />
                      </el-option-group>
                      <el-option-group label="输入操作">
                        <el-option label="输入 (Fill)" value="fill" />
                        <el-option label="选择 (Select)" value="select" />
                        <el-option label="上传 (Upload)" value="upload" />
                      </el-option-group>
                      <el-option-group label="键盘操作">
                        <el-option label="按键 (Keydown)" value="keydown" />
                      </el-option-group>
                      <el-option-group label="页面操作">
                        <el-option label="等待 (Wait)" value="wait" />
                        <el-option label="滚动 (Scroll)" value="scroll" />
                        <el-option label="拖拽 (Drag & Drop)" value="drag_and_drop" />
                      </el-option-group>
                      <el-option-group label="高级操作">
                        <el-option label="切换Iframe" value="iframe_switch" />
                        <el-option label="处理弹窗" value="alert_handle" />
                        <el-option label="截图 (Screenshot)" value="screenshot" />
                      </el-option-group>
                      <el-option-group label="断言操作">
                        <el-option label="断言文本 (Assert Text)" value="assert_text" />
                        <el-option label="断言元素可见 (Assert Visible)" value="assert_visible" />
                        <el-option label="断言元素存在 (Assert Exists)" value="assert_exists" />
                      </el-option-group>
                    </el-select>
                  </el-col>
                  <el-col :span="10" v-if="showSelectorField(step.action)">
                    <el-input
                      v-model="step.selector"
                      placeholder="CSS 选择器，如: #login-btn"
                      size="small"
                    />
                  </el-col>
                  <el-col :span="step.action === 'wait' || step.action === 'scroll' ? 14 : 8" v-if="showValueField(step.action)">
                    <el-input
                      v-model="step.value"
                      :placeholder="getValuePlaceholder(step.action)"
                      size="small"
                    />
                  </el-col>
                  <el-col :span="2">
                    <el-button
                      type="danger"
                      size="small"
                      circle
                      @click="removeStep(index)"
                    >
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </el-col>
                </el-row>
              </div>
            </div>
          </div>
          
          <el-empty v-else description="暂无测试步骤，点击上方按钮添加" :image-size="80">
            <el-button type="primary" size="small" @click="addStep">
              <el-icon><Plus /></el-icon>
              添加第一个步骤
            </el-button>
          </el-empty>

          <!-- 运行按钮（编辑模式） -->
          <div v-if="isEdit" class="run-section">
            <el-divider />
            <el-button
              type="success"
              size="large"
              @click="handleRun"
              :loading="running"
              style="width: 100%"
            >
              <el-icon><VideoPlay /></el-icon>
              运行测试
            </el-button>
          </div>
        </el-card>

        <!-- 关联任务 -->
        <el-card class="linked-tasks-card" v-if="isEdit">
          <template #header>
            <div class="card-header">
              <el-icon><Connection /></el-icon>
              <span>关联任务</span>
              <el-button type="primary" size="small" class="add-btn" @click="openLinkTaskDialog">
                <el-icon><Plus /></el-icon>
                关联
              </el-button>
            </div>
          </template>
          <div v-if="linkedTasks.length" class="linked-tasks-list">
            <div v-for="task in linkedTasks" :key="task.id" class="linked-task-item">
              <span class="task-title">{{ task.title }}</span>
              <el-tag v-if="task.column_title" size="small">{{ task.column_title }}</el-tag>
              <el-button link type="danger" size="small" @click="unlinkTask(task)" :loading="unlinkTaskId === task.id">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <el-empty v-else description="暂无关联任务" :image-size="40" />
        </el-card>
      </div>

      <!-- 关联任务对话框 -->
      <el-dialog v-model="linkTaskDialogVisible" title="关联任务" width="700px" destroy-on-close>
        <el-input v-model="taskSearch" placeholder="搜索任务标题..." clearable size="small" style="margin-bottom:12px">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-table :data="filteredTasks" v-loading="taskLoading" max-height="400px" size="small">
          <el-table-column label="标题" prop="title" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">{{ row.column_title || '-' }}</template>
          </el-table-column>
          <el-table-column label="负责人" width="100">
            <template #default="{ row }">{{ row.assignee_details?.username || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" align="center">
            <template #default="{ row }">
              <template v-if="isTaskLinked(row.id)">
                <el-button size="small" type="danger" plain @click="toggleTaskLink(row, 'unlink')" :loading="linkTaskPending === row.id">
                  取消关联
                </el-button>
              </template>
              <template v-else>
                <el-button size="small" type="primary" @click="toggleTaskLink(row, 'link')" :loading="linkTaskPending === row.id">
                  关联
                </el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!taskLoading && filteredTasks.length === 0" description="暂无匹配的任务" :image-size="60" />
      </el-dialog>

      <!-- 右侧：结果区 -->
      <div class="result-section">
        <el-card class="result-card" v-if="testResult">
          <template #header>
            <div class="result-header">
              <div class="result-title">
                <el-icon><Monitor /></el-icon>
                <span>执行结果</span>
              </div>
              <el-tag :type="testResult.success ? 'success' : 'danger'" size="large">
                {{ testResult.success ? '✅ 成功' : '❌ 失败' }}
              </el-tag>
            </div>
          </template>

          <!-- 步骤截图展示 -->
          <div v-if="testResult.step_screenshots && testResult.step_screenshots.length > 0" class="step-screenshots-section">
            <h4>
              <el-icon><Picture /></el-icon>
              步骤截图
            </h4>
            <el-carousel :interval="5000" arrow="always" height="400px" class="step-screenshots-carousel">
              <el-carousel-item v-for="(step, index) in testResult.step_screenshots" :key="index">
                <div class="step-screenshot-item">
                  <div class="step-screenshot-label">步骤 {{ step.step }}</div>
                  <img v-if="step.screenshot" :src="step.screenshot" :alt="`步骤 ${step.step} 截图`" class="step-screenshot-img" />
                  <div v-else class="step-screenshot-missing">步骤 {{ step.step }} 无截图</div>
                </div>
              </el-carousel-item>
            </el-carousel>
          </div>

          <!-- 最终截图展示 -->
          <div v-if="testResult.screenshot" class="screenshot-container">
            <h4>
              <el-icon><Picture /></el-icon>
              最终截图
            </h4>
            <img :src="testResult.screenshot" alt="测试截图" class="screenshot-img" />
          </div>

          <!-- 错误信息 -->
          <el-alert
            v-if="testResult.error"
            :title="testResult.error"
            type="error"
            :closable="false"
            show-icon
            class="error-alert"
          />

          <!-- 执行日志 -->
          <div class="logs-section">
            <h4>
              <el-icon><Document /></el-icon>
              执行日志
            </h4>
            <div class="logs-content">
              <div
                v-for="(log, index) in testResult.logs"
                :key="index"
                class="log-line"
                :class="getLogClass(log)"
              >
                {{ log }}
              </div>
            </div>
          </div>
        </el-card>

        <el-card v-else class="empty-result-card">
          <el-empty description="点击运行按钮查看测试结果" :image-size="120">
            <template #image>
              <el-icon :size="60" color="var(--color-text-tertiary)"><Monitor /></el-icon>
            </template>
          </el-empty>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import {
  ArrowLeft,
  VideoPlay,
  Check,
  Plus,
  Delete,
  Setting,
  List,
  Monitor,
  Document,
  CirclePlus,
  CircleClose,
  Picture,
  Search,
  Connection
} from '@element-plus/icons-vue';
import service from '@/utils/request';
import RecorderPanel from './components/RecorderPanel.vue';

const router = useRouter();
const route = useRoute();

const formRef = ref();
const isEdit = computed(() => !!route.params.id);
const caseId = computed(() => route.params.id as string);

const form = ref({
  name: '',
  project: route.query.project as string || '',
  url: '',
  steps: [] as any[]
});

const projects = ref<any[]>([]);
const saving = ref(false);
const running = ref(false);
const testResult = ref<any>(null);

// 录制相关状态
const isRecording = ref(false);

const rules = {
  name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
  url: [{ required: true, message: '请输入起始 URL', trigger: 'blur' }],
  project: [{ required: true, message: '请选择项目', trigger: 'change' }]
};

// 不需要选择器的操作
const noSelectorActions = ['wait', 'scroll', 'screenshot', 'alert_handle'];

// 不需要值的操作（断言操作需要值来存储期望文本）
const noValueActions = ['click', 'double_click', 'right_click', 'hover', 'screenshot', 'assert_visible', 'assert_exists'];

// 判断是否显示选择器字段
const showSelectorField = (action: string) => {
  return !noSelectorActions.includes(action);
};

// 判断是否显示值字段
const showValueField = (action: string) => {
  return !noValueActions.includes(action);
};

// 动作改变时重置相关字段
const onActionChange = (step: any) => {
  // 根据动作类型设置默认值
  if (step.action === 'wait') {
    step.value = '1000';
  } else if (step.action === 'alert_handle') {
    step.value = 'accept';
  } else if (step.action === 'scroll') {
    step.value = '500';
  } else if (step.action === 'keydown') {
    step.value = 'Enter';
  }
};

// 加载项目列表
const loadProjects = async () => {
  try {
    const res = await service.get('/projects/');
    projects.value = res.results || res;
  } catch (error) {
    console.error('加载项目失败', error);
  }
};

// ---------- 关联任务 ----------
const linkedTasks = ref<any[]>([]);
const unlinkTaskId = ref<string | null>(null);
const linkTaskDialogVisible = ref(false);
const taskSearch = ref('');
const taskLoading = ref(false);
const linkTaskPending = ref<string | null>(null);
const allTasks = ref<any[]>([]);
const linkedTaskIds = computed(() => new Set(linkedTasks.value.map((t: any) => t.id)));

const loadLinkedTasks = async () => {
  if (!isEdit.value) return;
  try {
    const res = await service.get(`/qa/ui-cases/${caseId.value}/linked-tasks/`);
    linkedTasks.value = Array.isArray(res) ? res : [];
  } catch { /* silent */ }
};

const unlinkTask = async (task: any) => {
  unlinkTaskId.value = task.id;
  try {
    await service.post('/qa/unlink-task/', { test_type: 'ui', case_id: caseId.value, task_id: task.id });
    ElMessage.success('取消关联成功');
    await loadLinkedTasks();
  } catch (e: any) {
    ElMessage.error(e?.detail || '取消关联失败');
  } finally {
    unlinkTaskId.value = null;
  }
};

const openLinkTaskDialog = async () => {
  linkTaskDialogVisible.value = true;
  taskSearch.value = '';
  linkTaskPending.value = null;
  await loadAvailableTasks();
};

const loadAvailableTasks = async () => {
  taskLoading.value = true;
  try {
    const res = await service.get('/tasks/', { params: { project: form.value.project } });
    allTasks.value = Array.isArray(res) ? res : (res as any).results || [];
  } catch {
    ElMessage.error('加载任务列表失败');
  } finally {
    taskLoading.value = false;
  }
};

const filteredTasks = computed(() => {
  if (!taskSearch.value) return allTasks.value;
  const kw = taskSearch.value.toLowerCase();
  return allTasks.value.filter((t: any) => (t.title || '').toLowerCase().includes(kw));
});

const isTaskLinked = (taskId: string) => linkedTaskIds.value.has(taskId);

const toggleTaskLink = async (task: any, action: 'link' | 'unlink') => {
  linkTaskPending.value = task.id;
  try {
    const payload = { test_type: 'ui', case_id: caseId.value, task_id: task.id };
    await service.post(`/qa/${action}-task/`, payload);
    ElMessage.success(action === 'link' ? '关联成功' : '取消关联成功');
    await loadLinkedTasks();
  } catch (e: any) {
    ElMessage.error(e?.detail || '操作失败');
  } finally {
    linkTaskPending.value = null;
  }
};

// 加载测试用例详情
const loadCaseDetail = async () => {
  if (!isEdit.value) return;
  try {
    const res = await service.get(`/qa/ui-cases/${caseId.value}/`);
    form.value = {
      name: res.name,
      project: res.project,
      url: res.url,
      steps: res.steps || []
    };
    loadLinkedTasks();
  } catch (error) {
    ElMessage.error('加载测试用例失败');
  }
};

// 获取值输入框占位符
const getValuePlaceholder = (action: string) => {
  switch (action) {
    case 'click':
    case 'double_click':
    case 'right_click':
    case 'hover':
      return '无需填写';
    case 'fill':
      return '输入内容';
    case 'select':
      return '选项值';
    case 'drag_and_drop':
      return '目标元素选择器';
    case 'wait':
      return '等待时间 (ms)，如: 1000';
    case 'scroll':
      return '滚动距离 (px) 或 JSON';
    case 'upload':
      return '文件路径';
    case 'keydown':
      return '按键，如: Enter, Escape, Tab';
    case 'iframe_switch':
      return 'iframe name/id (空=主页面)';
    case 'alert_handle':
      return 'accept / dismiss / 输入值';
    case 'assert_text':
      return '期望的文本内容';
    case 'assert_visible':
      return '无需填写';
    case 'assert_exists':
      return '无需填写';
    default:
      return '';
  }
};

// 添加步骤
const addStep = () => {
  form.value.steps.push({
    action: 'click',
    selector: '',
    value: ''
  });
};

// 删除步骤
const removeStep = (index: number) => {
  form.value.steps.splice(index, 1);
};

// 保存测试用例
const handleSave = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  saving.value = true;
  try {
    const data = { ...form.value };

    if (isEdit.value) {
      await service.put(`/qa/ui-cases/${caseId.value}/`, data);
      ElMessage.success('更新成功');
    } else {
      await service.post('/qa/ui-cases/', data);
      ElMessage.success('创建成功');
    }
    goBack();
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存失败');
  } finally {
    saving.value = false;
  }
};

// 运行测试（已保存的用例）
const handleRun = async () => {
  if (!isEdit.value) {
    ElMessage.warning('请先保存用例');
    return;
  }

  running.value = true;
  testResult.value = null;

  try {
    const res = await service.post(`/qa/ui-cases/${caseId.value}/run/`, {}, {
      timeout: 300000
    });
    testResult.value = res;

    if (res.success) {
      ElMessage.success('测试执行成功');
    } else {
      ElMessage.error('测试执行失败');
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '运行测试失败');
  } finally {
    running.value = false;
  }
};

// 临时运行测试（未保存的用例）
const handleRunTemp = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  if (form.value.steps.length === 0) {
    ElMessage.warning('请至少添加一个测试步骤');
    return;
  }

  running.value = true;
  testResult.value = null;

  try {
    const res = await service.post('/qa/ui-cases/run_temp/', {
      url: form.value.url,
      steps: form.value.steps
    }, {
      timeout: 300000
    });
    testResult.value = res;

    if (res.success) {
      ElMessage.success('测试执行成功');
    } else {
      ElMessage.error('测试执行失败');
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '运行测试失败');
  } finally {
    running.value = false;
  }
};

// 获取日志样式类
const getLogClass = (log: string) => {
  if (log.includes('✅')) return 'log-success';
  if (log.includes('❌')) return 'log-error';
  if (log.includes('⚠️')) return 'log-warning';
  if (log.includes('🚀') || log.includes('📍')) return 'log-info';
  return '';
};

// 返回列表页
const goBack = () => {
  router.push({ name: 'UiCaseList' });
};

onMounted(() => {
  loadProjects();
  loadCaseDetail();
});

// 切换录制面板显示（实际的 WebSocket 由 RecorderPanel 内部管理）
const toggleRecording = async () => {
  if (!form.value.url) {
    ElMessage.warning('请先输入起始 URL');
    return;
  }
  isRecording.value = !isRecording.value;
};

// 共用：根据录制事件构造 step
const buildStepFromEvent = (eventData: any) => {
  if (!eventData) return null;
  let selectorValue = eventData.selector;
  if (eventData.selector && typeof eventData.selector === 'object') {
    selectorValue = eventData.selector.css || JSON.stringify(eventData.selector);
  }
  let valueData = eventData.value;
  if (eventData.action === 'drag_and_drop' && eventData.value && typeof eventData.value === 'object') {
    valueData = eventData.value.css || JSON.stringify(eventData.value);
  }
  const step: any = { action: eventData.action, selector: selectorValue, value: valueData };
  if (eventData.attribute) step.attribute = eventData.attribute;
  if (eventData.expected_value) step.expected_value = eventData.expected_value;
  return step;
};

// 替换/追加单个事件
const onAppendStep = (ev: any) => {
  const step = buildStepFromEvent(ev);
  if (step) form.value.steps.push(step);
};
const onReplaceStep = (ev: any, index: number) => {
  const step = buildStepFromEvent(ev);
  if (!step) return;
  if (index < 0 || index >= form.value.steps.length) {
    ElMessage.warning('替换位置越界，请使用「追加到当前用例」或「替换当前用例步骤」');
    return;
  }
  form.value.steps[index] = step;
};
const onAppendAllSteps = (evs: any[]) => {
  evs.forEach((ev) => {
    const step = buildStepFromEvent(ev);
    if (step) form.value.steps.push(step);
  });
};
const onReplaceAllSteps = (evs: any[]) => {
  form.value.steps = evs.map(buildStepFromEvent).filter((s: any) => s != null);
};
</script>

<style scoped>
.ui-case-detail {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 15px;
}

.header-left h2 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.content-wrapper {
  display: flex;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

/* 左侧配置区 */
.config-section {
  width: 45%;
  display: flex;
  flex-direction: column;
  gap: 15px;
  overflow-y: auto;
}

.config-card,
.steps-card {
  flex-shrink: 0;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.add-btn {
  margin-left: auto;
}

/* 步骤列表 */
.steps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  background: var(--color-bg);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.step-number {
  width: 28px;
  height: 28px;
  background: var(--color-primary);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-content {
  flex: 1;
}

.run-section {
  margin-top: 10px;
}

.linked-tasks-card {
  margin-top: 15px;
}

.linked-tasks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.linked-task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.task-title {
  flex: 1;
  font-size: 14px;
  color: var(--color-text);
}

/* 右侧结果区 */
.result-section {
  width: 55%;
  min-height: 0;
}

.result-card,
.empty-result-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.result-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

/* 截图 */
.screenshot-container {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-bg);
  margin-top: 15px;
}

.screenshot-container h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 12px 15px;
  background: var(--color-bg);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  font-size: 14px;
}

.screenshot-img {
  width: 100%;
  display: block;
}

/* 步骤截图区域 */
.step-screenshots-section {
  margin-bottom: 15px;
}

.step-screenshots-section h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.step-screenshots-carousel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-bg);
}

.step-screenshot-item {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.step-screenshot-label {
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
  padding: 5px 15px;
  background: var(--color-border);
  border-radius: 4px;
}

.step-screenshot-img {
  max-width: 100%;
  max-height: 320px;
  object-fit: contain;
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.step-screenshot-missing {
  color: var(--color-text-tertiary);
  font-style: italic;
  padding: 20px;
}

/* 错误提示 */
.error-alert {
  margin-bottom: 10px;
}

/* 日志区域 */
.logs-section {
  flex: 1;
  min-height: 200px;
}

.logs-section h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.logs-content {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  color: var(--color-text);
  border-radius: var(--radius-md);
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  max-height: 300px;
  overflow-y: auto;
}

.log-line {
  color: var(--color-text);
  padding: 2px 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-success {
  color: var(--color-success);
}

.log-error {
  color: var(--color-danger);
}

.log-warning {
  color: var(--color-warning);
}

.log-info {
  color: var(--color-info);
}

/* 空状态 */
.empty-result-card {
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-result-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

/* 响应式 */
@media (max-width: 1200px) {
  .content-wrapper {
    flex-direction: column;
  }
  
  .config-section,
  .result-section {
    width: 100%;
  }
}
</style>
