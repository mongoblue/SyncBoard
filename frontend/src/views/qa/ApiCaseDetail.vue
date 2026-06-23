<!--
API 用例编辑/创建 + 单次运行。

注意：此页面走旧版后端路径（/api/qa/api-cases/），
后端是 views_api_test.py + test_executor.py，使用 django.test.Client 发送请求。

与新版 ApiAutoTestCase 的区别：
  旧版：单用例编辑 + 单次运行，不走套件，请求仅支持内部 Django URL
  新版：套件/计划批量执行，requests 发送，支持外部接口

路由：/projects/:projectId/qa/api-cases[/create|/:id]
-->
<template>
  <div class="api-case-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button class="back-btn" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <h2>{{ isEdit ? '编辑测试用例' : '新建测试用例' }}</h2>
      </div>
      <div class="header-actions">
        <el-button type="success" class="run-btn" @click="handleRun" :loading="running">
          <el-icon><VideoPlay /></el-icon>
          运行测试
        </el-button>
        <el-button type="primary" class="save-btn" @click="handleSave" :loading="saving">
          <el-icon><Check /></el-icon>
          保存
        </el-button>
      </div>
    </div>

    <div class="form-container">
      <el-form :model="form" label-position="top" :rules="rules" ref="formRef">
        <div class="form-section">
          <div class="section-title">
            <span class="section-icon">📋</span>
            基本信息
          </div>
          <el-row :gutter="20">
            <el-col :span="16">
              <el-form-item label="用例名称" prop="name">
                <el-input v-model="form.name" placeholder="请输入测试用例名称" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
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
            </el-col>
          </el-row>
        </div>

        <div class="form-section">
          <div class="section-title">
            <span class="section-icon">🔗</span>
            请求配置
          </div>
          <el-row :gutter="20">
            <el-col :span="4">
              <el-form-item label="请求方法" prop="method">
                <el-select v-model="form.method" placeholder="方法" class="method-select">
                  <el-option label="GET" value="GET" class="method-get" />
                  <el-option label="POST" value="POST" class="method-post" />
                  <el-option label="PUT" value="PUT" class="method-put" />
                  <el-option label="DELETE" value="DELETE" class="method-delete" />
                  <el-option label="PATCH" value="PATCH" class="method-patch" />
                  <el-option label="HEAD" value="HEAD" />
                  <el-option label="OPTIONS" value="OPTIONS" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="16">
              <el-form-item label="请求地址" prop="url">
                <el-input v-model="form.url" placeholder="请输入请求地址，如: http://localhost:8000/api/tasks/" />
              </el-form-item>
            </el-col>
            <el-col :span="4">
              <el-form-item label="期望状态码" prop="expected_status">
                <el-input-number v-model="form.expected_status" :min="100" :max="599" placeholder="200" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="请求头 (JSON)">
                <el-input
                  v-model="headersText"
                  type="textarea"
                  :rows="8"
                  placeholder='{"Content-Type": "application/json", "Authorization": "Bearer token"}'
                  class="code-input"
                />
                <div class="form-tip">请输入 JSON 格式的请求头</div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="请求体 (JSON)">
                <el-input
                  v-model="bodyText"
                  type="textarea"
                  :rows="8"
                  placeholder='{"key": "value"}'
                  class="code-input"
                />
                <div class="form-tip">请输入 JSON 格式的请求体 (仅 POST/PUT/PATCH 有效)</div>
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <div class="form-section assertions-section">
          <div class="section-title">
            <span class="section-icon">✅</span>
            断言配置
            <el-button type="primary" size="small" class="add-assertion-btn" @click="addAssertion">
              <el-icon><Plus /></el-icon>
              添加断言
            </el-button>
          </div>
          <p class="section-desc">配置断言规则来验证响应结果，支持状态码、JSONPath 表达式和响应头验证</p>
          
          <div v-if="form.assertions && form.assertions.length > 0" class="assertions-list">
            <div v-for="(assertion, index) in form.assertions" :key="index" class="assertion-card">
              <div class="assertion-header">
                <el-tag :type="getAssertionTypeTag(assertion.type)" size="small" effect="dark">
                  {{ getAssertionTypeLabel(assertion.type) }}
                </el-tag>
                <el-button type="danger" size="small" circle @click="removeAssertion(index)" class="delete-btn">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
              <el-row :gutter="12" class="assertion-body">
                <el-col :span="5">
                  <el-select v-model="assertion.type" placeholder="断言类型" size="small">
                    <el-option label="状态码" value="status_code" />
                    <el-option label="JSONPath" value="jsonpath" />
                    <el-option label="响应头" value="header" />
                  </el-select>
                </el-col>
                <el-col :span="5" v-if="assertion.type === 'jsonpath'">
                  <el-input v-model="assertion.expression" placeholder="$.data.id" size="small" />
                </el-col>
                <el-col :span="5" v-if="assertion.type === 'header'">
                  <el-input v-model="assertion.header_name" placeholder="Content-Type" size="small" />
                </el-col>
                <el-col :span="4">
                  <el-select v-model="assertion.operator" placeholder="运算符" size="small">
                    <el-option label="等于" value="==" />
                    <el-option label="不等于" value="!=" />
                    <el-option label="大于" value=">" />
                    <el-option label="小于" value="<" />
                    <el-option label="大于等于" value=">=" />
                    <el-option label="小于等于" value="<=" />
                    <el-option label="包含" value="contains" />
                    <el-option label="存在" value="exists" />
                  </el-select>
                </el-col>
                <el-col :span="5" v-if="assertion.operator !== 'exists'">
                  <el-input v-model="assertion.value" placeholder="期望值" size="small" />
                </el-col>
              </el-row>
            </div>
          </div>
          <el-empty v-else description="暂无断言配置，点击上方按钮添加" :image-size="80" />
        </div>
      </el-form>

      <!-- 关联任务 -->
      <div class="form-section" v-if="isEdit">
        <div class="section-title">
          <span class="section-icon">🔗</span>
          关联任务
          <el-button type="primary" size="small" class="add-assertion-btn" @click="openLinkTaskDialog">
            <el-icon><Plus /></el-icon>
            关联任务
          </el-button>
        </div>
        <div v-if="linkedTasks.length" class="linked-tasks-list">
          <div v-for="task in linkedTasks" :key="task.id" class="linked-task-item">
            <span class="task-title">{{ task.title }}</span>
            <el-tag v-if="task.column_title" size="small">{{ task.column_title }}</el-tag>
            <el-button link type="danger" size="small" @click="unlinkTask(task)" :loading="unlinkTaskId === task.id">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        <el-empty v-else description="暂无关联任务，点击上方按钮添加" :image-size="40" />
      </div>
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

    <div v-if="testResult" class="test-result-container">
      <div class="result-header" :class="testResult.passed ? 'passed' : 'failed'">
        <div class="result-icon">
          {{ testResult.passed ? '✅' : '❌' }}
        </div>
        <div class="result-title">
          {{ testResult.passed ? '测试通过' : '测试失败' }}
        </div>
        <div class="result-summary">
          <span class="summary-item">
            <span class="label">状态码</span>
            <span class="value" :class="getStatusCodeClass(testResult.status_code)">{{ testResult.status_code }}</span>
          </span>
          <span class="summary-item">
            <span class="label">响应时间</span>
            <span class="value">{{ testResult.response_time_ms }} ms</span>
          </span>
          <span class="summary-item" v-if="testResult.expected_status">
            <span class="label">期望状态码</span>
            <span class="value">{{ testResult.expected_status }}</span>
          </span>
        </div>
      </div>

      <div class="result-body">
        <div class="response-section">
          <h4>响应体</h4>
          <pre class="json-code">{{ formatJson(testResult.response_body) }}</pre>
        </div>

        <div v-if="testResult.error_message" class="error-section">
          <h4>错误信息</h4>
          <el-alert type="error" :title="testResult.error_message" :closable="false" show-icon />
        </div>

        <div v-if="testResult.assertion_results && testResult.assertion_results.length > 0" class="assertion-results-section">
          <h4>断言结果</h4>
          <div class="assertion-results-grid">
            <div 
              v-for="(result, index) in testResult.assertion_results" 
              :key="index" 
              class="assertion-result-card"
              :class="result.passed ? 'passed' : 'failed'"
            >
              <div class="result-card-header">
                <el-tag :type="getAssertionTypeTag(result.assertion?.type)" size="small" effect="dark">
                  {{ getAssertionTypeLabel(result.assertion?.type) }}
                </el-tag>
                <el-tag :type="result.passed ? 'success' : 'danger'" size="small" effect="plain">
                  {{ result.passed ? '通过' : '失败' }}
                </el-tag>
              </div>
              <div class="result-card-body">
                <div class="result-row" v-if="result.assertion?.type === 'jsonpath'">
                  <span class="result-label">表达式</span>
                  <code class="result-value">{{ result.assertion?.expression }}</code>
                </div>
                <div class="result-row" v-if="result.assertion?.type === 'header'">
                  <span class="result-label">响应头</span>
                  <code class="result-value">{{ result.assertion?.header_name }}</code>
                </div>
                <div class="result-row">
                  <span class="result-label">运算符</span>
                  <span class="result-value">{{ result.assertion?.operator }}</span>
                </div>
                <div class="result-row" v-if="result.assertion?.value !== undefined">
                  <span class="result-label">期望值</span>
                  <span class="result-value expected">{{ result.assertion?.value }}</span>
                </div>
                <div class="result-row">
                  <span class="result-label">实际值</span>
                  <span class="result-value actual">{{ formatActualValue(result.actual_value) }}</span>
                </div>
              </div>
              <div class="result-card-footer">
                {{ result.message }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { ArrowLeft, VideoPlay, Check, Plus, Delete, Search } from '@element-plus/icons-vue';
import service from '@/utils/request';

const router = useRouter();
const route = useRoute();

const formRef = ref();
const isEdit = computed(() => !!route.params.id);
const caseId = computed(() => route.params.id as string);

const form = ref({
  name: '',
  project: route.query.project as string || '',
  url: '',
  method: 'GET',
  headers: {},
  body: {},
  expected_status: null as number | null,
  assertions: [] as any[]
});

const headersText = ref('{}');
const bodyText = ref('{}');
const projects = ref<any[]>([]);
const saving = ref(false);
const running = ref(false);
const testResult = ref<any>(null);

const rules = {
  name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
  project: [{ required: true, message: '请选择项目', trigger: 'change' }],
  url: [{ required: true, message: '请输入请求地址', trigger: 'blur' }],
  method: [{ required: true, message: '请选择请求方法', trigger: 'change' }]
};

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
    const res = await service.get(`/qa/api-cases/${caseId.value}/linked-tasks/`);
    linkedTasks.value = Array.isArray(res) ? res : [];
  } catch { /* silent */ }
};

const unlinkTask = async (task: any) => {
  unlinkTaskId.value = task.id;
  try {
    await service.post('/qa/unlink-task/', { test_type: 'api', case_id: caseId.value, task_id: task.id });
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
    const payload = { test_type: 'api', case_id: caseId.value, task_id: task.id };
    await service.post(`/qa/${action}-task/`, payload);
    ElMessage.success(action === 'link' ? '关联成功' : '取消关联成功');
    await loadLinkedTasks();
  } catch (e: any) {
    ElMessage.error(e?.detail || '操作失败');
  } finally {
    linkTaskPending.value = null;
  }
};

const loadCaseDetail = async () => {
  if (!isEdit.value) return;
  try {
    const res = await service.get(`/qa/api-cases/${caseId.value}/`);
    form.value = {
      name: res.name,
      project: res.project,
      url: res.url,
      method: res.method,
      headers: res.headers || {},
      body: res.body || {},
      expected_status: res.expected_status,
      assertions: res.assertions || []
    };
    headersText.value = JSON.stringify(res.headers || {}, null, 2);
    bodyText.value = JSON.stringify(res.body || {}, null, 2);
    loadLinkedTasks();
  } catch (error) {
    ElMessage.error('加载测试用例失败');
  }
};

const parseJson = (text: string, fieldName: string): object | null => {
  const trimmed = text.trim();
  if (!trimmed || trimmed === '{}') return {};
  try {
    return JSON.parse(trimmed);
  } catch (e) {
    ElMessage.error(`${fieldName} JSON 格式错误`);
    return null;
  }
};

const handleSave = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  const headers = parseJson(headersText.value, '请求头');
  if (headers === null) return;
  
  const body = parseJson(bodyText.value, '请求体');
  if (body === null) return;

  saving.value = true;
  try {
    const data = {
      ...form.value,
      headers,
      body
    };

    if (isEdit.value) {
      await service.put(`/qa/api-cases/${caseId.value}/`, data);
      ElMessage.success('更新成功');
    } else {
      await service.post('/qa/api-cases/', data);
      ElMessage.success('创建成功');
    }
    goBack();
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存失败');
  } finally {
    saving.value = false;
  }
};

const handleRun = async () => {
  const headers = parseJson(headersText.value, '请求头');
  if (headers === null) return;
  
  const body = parseJson(bodyText.value, '请求体');
  if (body === null) return;

  running.value = true;
  testResult.value = null;
  
  try {
    const url = isEdit.value 
      ? `/qa/api-cases/${caseId.value}/run/`
      : '/qa/api-cases/run/';
    
    const data = isEdit.value ? {} : {
      url: form.value.url,
      method: form.value.method,
      headers,
      body
    };

    const res = await service.post(url, data);
    testResult.value = res;
    
    if (res.passed) {
      ElMessage.success(`测试通过！状态码: ${res.status_code}, 响应时间: ${res.response_time_ms}ms`);
    } else {
      ElMessage.warning(`测试未通过！期望: ${res.expected_status}, 实际: ${res.status_code}`);
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '运行测试失败');
  } finally {
    running.value = false;
  }
};

const formatJson = (text: string) => {
  if (!text) return '';
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
};

const getStatusCodeClass = (code: number) => {
  if (code >= 200 && code < 300) return 'success';
  if (code >= 300 && code < 400) return 'warning';
  if (code >= 400) return 'danger';
  return 'info';
};

const goBack = () => {
  router.push({ name: 'ApiCaseList' });
};

const addAssertion = () => {
  if (!form.value.assertions) {
    form.value.assertions = [];
  }
  form.value.assertions.push({
    type: 'status_code',
    operator: '==',
    value: '200'
  });
};

const removeAssertion = (index: number) => {
  form.value.assertions.splice(index, 1);
};

const getAssertionTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    'status_code': '状态码',
    'jsonpath': 'JSONPath',
    'header': '响应头'
  };
  return labels[type] || type;
};

const getAssertionTypeTag = (type: string) => {
  const types: Record<string, string> = {
    'status_code': 'primary',
    'jsonpath': 'success',
    'header': 'warning'
  };
  return types[type] || 'info';
};

const formatActualValue = (value: any) => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

onMounted(() => {
  loadProjects();
  loadCaseDetail();
});
</script>

<style scoped>
.api-case-detail { padding: 0; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.back-btn { /* default el-button styling via global overrides */ }

.header-actions { display: flex; gap: 8px; }

.run-btn,
.save-btn { /* use Element Plus type colors + global overrides */ }

.form-container {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.form-section {
  padding: 20px 24px;
  border-bottom: 1px solid var(--color-border-light);
}

.form-section:last-child { border-bottom: none; }

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font: 600 14px/1.3 var(--font-heading);
  color: var(--color-text);
  margin-bottom: 16px;
}

.section-icon { font-size: 16px; }

.section-desc {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-top: -8px;
  margin-bottom: 12px;
}

.add-assertion-btn { margin-left: auto; }

.form-tip {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.code-input :deep(textarea) {
  font-family: var(--font-mono);
  font-size: 12px;
}

.assertions-section {
  background: var(--color-surface-sunken);
}

.assertions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.assertion-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  transition: border-color var(--transition-fast);
}

.assertion-card:hover {
  border-color: var(--color-primary);
}

.assertion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.assertion-body { align-items: center; }

.delete-btn { color: var(--color-text-tertiary); }
.delete-btn:hover { color: var(--color-danger); }

.test-result-container {
  margin-top: 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.result-header {
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-light);
}

.result-header.passed {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.result-header.failed {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.result-icon { font-size: 20px; }

.result-title {
  font: 600 16px/1.3 var(--font-heading);
}

.result-summary {
  margin-left: auto;
  display: flex;
  gap: 20px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.summary-item .label {
  font-size: 12px;
  color: inherit;
  opacity: 0.75;
}

.summary-item .value {
  font: 600 14px/1.3 var(--font-heading);
  color: inherit;
}

.summary-item .value.success { color: var(--color-success); }
.summary-item .value.warning { color: var(--color-warning); }
.summary-item .value.danger { color: var(--color-danger); }

.result-body { padding: 20px 24px; }

.response-section,
.error-section,
.assertion-results-section { margin-bottom: 20px; }

.response-section h4,
.error-section h4,
.assertion-results-section h4 {
  margin: 0 0 8px 0;
  font: 600 13px/1.3 var(--font-heading);
  color: var(--color-text);
}

.json-code {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  color: var(--color-text);
  padding: 12px 14px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}

.assertion-results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.assertion-result-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.assertion-result-card.passed { border-left: 3px solid var(--color-success); }
.assertion-result-card.failed { border-left: 3px solid var(--color-danger); }

.result-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--color-surface-sunken);
  border-bottom: 1px solid var(--color-border-light);
}

.result-card-body { padding: 12px 14px; }

.result-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
}

.result-row:not(:last-child) {
  border-bottom: 1px solid var(--color-border-light);
}

.result-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.result-value {
  font-size: 13px;
  color: var(--color-text);
  font-weight: 500;
}

.result-value.expected { color: var(--color-success); }
.result-value.actual { color: var(--color-info); }

.result-value code {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 12px;
}

.result-card-footer {
  padding: 8px 14px;
  background: var(--color-surface-sunken);
  border-top: 1px solid var(--color-border-light);
  font-size: 12px;
  color: var(--color-text-secondary);
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
  background: var(--color-surface-sunken);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}

.task-title {
  flex: 1;
  font-size: 13px;
  color: var(--color-text);
}

:deep(.el-empty) { padding: 32px 0; }
:deep(.el-empty__description) { color: var(--color-text-tertiary); }
</style>
