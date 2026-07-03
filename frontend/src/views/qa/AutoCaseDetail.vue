<template>
  <div class="auto-case-detail">
    <header class="page-header">
      <div class="header-left">
        <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
        <div>
          <h1 class="page-title">{{ isEdit ? '编辑用例' : '新建用例' }}</h1>
          <p class="page-subtitle">配置 API 请求与断言，支持单条运行</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button
          v-if="isEdit"
          type="success"
          @click="handleRun"
          :loading="running"
        >
          <el-icon><VideoPlay /></el-icon>
          运行
        </el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          保存
        </el-button>
      </div>
    </header>

    <div class="content-wrapper">
      <!-- 左栏：配置 -->
      <div class="config-section">
        <el-form
          ref="formRef"
          :model="formData"
          :rules="formRules"
          label-position="top"
        >
          <!-- 基础配置 -->
          <el-card class="config-card" shadow="never">
            <template #header><span class="card-title">基础配置</span></template>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="用例名称" prop="name">
                  <el-input v-model="formData.name" placeholder="例如：登录接口测试" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="所属项目" prop="project">
                  <el-select v-model="formData.project" placeholder="选择项目" style="width: 100%" filterable>
                    <el-option
                      v-for="p in projects"
                      :key="p.id"
                      :label="p.name"
                      :value="p.id"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="绑定环境">
              <el-select v-model="formData.environment" placeholder="不绑定（用项目默认环境）" clearable style="width: 100%">
                <el-option
                  v-for="env in environments"
                  :key="env.id"
                  :label="env.name"
                  :value="env.id"
                />
              </el-select>
              <div class="form-tip">用例级环境覆盖；为空时回退到项目默认环境</div>
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="可选" />
            </el-form-item>
          </el-card>

          <!-- 请求定义 -->
          <el-card class="config-card" shadow="never">
            <template #header><span class="card-title">请求定义</span></template>
            <el-row :gutter="12">
              <el-col :span="6">
                <el-form-item label="方法" prop="method">
                  <el-select v-model="formData.method" style="width: 100%">
                    <el-option v-for="m in methods" :key="m" :label="m" :value="m" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="18">
                <el-form-item label="URL" prop="url">
                  <el-input v-model="formData.url" placeholder="例如：/api/projects/ 或 https://example.com/api" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="Content-Type">
              <el-select v-model="formData.content_type" style="width: 100%">
                <el-option label="JSON" value="application/json" />
                <el-option label="Form" value="application/x-www-form-urlencoded" />
                <el-option label="Multipart" value="multipart/form-data" />
                <el-option label="Text" value="text/plain" />
              </el-select>
            </el-form-item>
            <el-form-item label="请求头">
              <div class="kv-list">
                <div
                  v-for="(item, idx) in headerList"
                  :key="idx"
                  class="kv-item"
                >
                  <el-input v-model="item.key" placeholder="Header 名称" style="width: 200px" />
                  <el-input v-model="item.value" placeholder="Header 值" style="flex: 1" />
                  <el-button type="danger" link @click="headerList.splice(idx, 1)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <el-button type="primary" link @click="headerList.push({ key: '', value: '' })">
                  <el-icon><Plus /></el-icon>
                  添加 Header
                </el-button>
              </div>
            </el-form-item>
            <el-form-item label="请求体">
              <el-input
                v-model="formData.body"
                type="textarea"
                :rows="6"
                placeholder='JSON 内容，例如：{"username": "admin", "password": "***"}'
                style="font-family: monospace"
              />
            </el-form-item>
            <el-form-item label="预期状态码">
              <el-input-number v-model="formData.expected_status" :min="100" :max="599" style="width: 150px" />
              <span class="form-tip-inline">留空则不校验</span>
            </el-form-item>
          </el-card>

          <!-- 断言 -->
          <el-card class="config-card" shadow="never">
            <template #header><span class="card-title">断言</span></template>
            <el-table :data="assertionList" border style="width: 100%">
              <el-table-column label="类型" width="180">
                <template #default="{ row }">
                  <el-select v-model="row.assertion_type" style="width: 100%">
                    <el-option label="状态码" value="status_code" />
                    <el-option label="JSON 字段等于" value="json_equals" />
                    <el-option label="JSON 字段存在" value="json_exists" />
                    <el-option label="JSON 字段包含" value="json_contains" />
                    <el-option label="响应时间" value="response_time" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="JSON 路径" min-width="200">
                <template #default="{ row }">
                  <el-input v-model="row.json_path" placeholder="例如：data.user.name" />
                </template>
              </el-table-column>
              <el-table-column label="操作符" width="120">
                <template #default="{ row }">
                  <el-select v-model="row.comparison_operator" style="width: 100%">
                    <el-option label="等于" value="eq" />
                    <el-option label="不等于" value="ne" />
                    <el-option label="大于" value="gt" />
                    <el-option label="大于等于" value="gte" />
                    <el-option label="小于" value="lt" />
                    <el-option label="小于等于" value="lte" />
                    <el-option label="包含" value="contains" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="预期值" min-width="180">
                <template #default="{ row }">
                  <el-input v-model="row.expected_value" placeholder="预期值" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" fixed="right">
                <template #default="{ $index }">
                  <el-button type="danger" link @click="assertionList.splice($index, 1)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-button type="primary" link style="margin-top: 8px" @click="addAssertion">
              <el-icon><Plus /></el-icon>
              添加断言
            </el-button>
          </el-card>
        </el-form>
      </div>

      <!-- 右栏：执行结果 -->
      <div class="result-section">
        <el-card class="result-card" shadow="never">
          <template #header><span class="card-title">执行结果</span></template>
          <div v-if="!lastResult" class="empty-result">
            <el-empty description="点击「运行」后，结果会显示在这里" :image-size="100" />
          </div>
          <div v-else class="result-content">
            <el-alert
              :type="lastResult.passed ? 'success' : 'error'"
              :title="lastResult.passed ? '通过' : (lastResult.failure_type || '失败')"
              :description="lastResult.error_message || lastResult.summary || ''"
              :closable="false"
              show-icon
              style="margin-bottom: 12px"
            />
            <el-tabs v-model="resultTab">
              <el-tab-pane label="响应" name="response">
                <ResponseSnapshotPanel v-if="lastResult.response_snapshot" :snapshot="lastResult.response_snapshot" />
                <el-empty v-else description="无响应快照" :image-size="80" />
              </el-tab-pane>
              <el-tab-pane label="断言" name="assertions">
                <AssertionTable v-if="lastResult.assertion_results?.length" :assertions="lastResult.assertion_results" />
                <el-empty v-else description="无断言结果" :image-size="80" />
              </el-tab-pane>
              <el-tab-pane label="诊断" name="diagnosis">
                <DiagnosisCard v-if="lastResult.diagnosis" :diagnosis="lastResult.diagnosis" />
                <el-empty v-else description="无框架诊断信息" :image-size="80" />
              </el-tab-pane>
              <el-tab-pane label="请求" name="request">
                <RequestSnapshotPanel v-if="lastResult.request_snapshot" :snapshot="lastResult.request_snapshot" />
                <el-empty v-else description="无请求快照" :image-size="80" />
              </el-tab-pane>
            </el-tabs>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import {
  ArrowLeft, VideoPlay, Plus, Delete,
} from '@element-plus/icons-vue';
import service from '@/utils/request';
import { useBoardStore } from '@/stores/board';
import ResponseSnapshotPanel from './components/result/ResponseSnapshotPanel.vue';
import AssertionTable from './components/result/AssertionTable.vue';
import DiagnosisCard from './components/result/DiagnosisCard.vue';
import RequestSnapshotPanel from './components/result/RequestSnapshotPanel.vue';

const router = useRouter();
const route = useRoute();
const boardStore = useBoardStore();

const caseId = computed(() => (route.params.id ? Number(route.params.id) : null));
const isEdit = computed(() => !!caseId.value);

const formRef = ref<FormInstance>();
const saving = ref(false);
const running = ref(false);

const projects = ref<any[]>([]);
const environments = ref<any[]>([]);

const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];

const formData = ref({
  name: '',
  description: '',
  url: '',
  method: 'GET',
  headers: {} as Record<string, string>,
  content_type: 'application/json',
  body: '',
  expected_status: null as number | null,
  project: (route.query.project ? Number(route.query.project) : null) as number | null,
  environment: null as number | null,
});

const headerList = ref<{ key: string; value: string }[]>([]);
const assertionList = ref<any[]>([]);

const lastResult = ref<any>(null);
const resultTab = ref('response');

const formRules: FormRules = {
  name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
  url: [{ required: true, message: '请输入 URL', trigger: 'blur' }],
  method: [{ required: true, message: '请选择方法', trigger: 'change' }],
  project: [{ required: true, message: '请选择项目', trigger: 'change' }],
};

const addAssertion = () => {
  assertionList.value.push({
    assertion_type: 'status_code',
    json_path: '',
    expected_value: '',
    comparison_operator: 'eq',
    is_active: true,
  });
};

const loadProjects = async () => {
  try {
    const res = await service.get('/projects/');
    projects.value = res.results || res || [];
  } catch (e) {
    console.error('加载项目失败', e);
  }
};

const loadEnvironments = async () => {
  try {
    const res = await service.get('/qa/environments/', { params: { page_size: 100 } });
    environments.value = res.results || res || [];
  } catch (e) {
    console.error('加载环境失败', e);
  }
};

const loadCase = async () => {
  if (!caseId.value) {
    // 新建：默认项目取当前 boardStore
    if (!formData.value.project && boardStore.currentProject?.id) {
      formData.value.project = boardStore.currentProject.id;
    }
    return;
  }
  try {
    const res: any = await service.get(`/qa/auto-cases/${caseId.value}/`);
    formData.value = {
      name: res.name || '',
      description: res.description || '',
      url: res.url || '',
      method: res.method || 'GET',
      headers: res.headers || {},
      content_type: res.content_type || 'application/json',
      body: res.body || '',
      expected_status: res.expected_status ?? null,
      project: res.project ?? null,
      environment: res.environment ?? null,
    };
    headerList.value = Object.entries(res.headers || {}).map(([key, value]) => ({
      key, value: String(value),
    }));
    assertionList.value = (res.assertions || []).map((a: any) => ({ ...a }));
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '加载用例失败');
  }
};

const buildHeaders = (): Record<string, string> => {
  const out: Record<string, string> = {};
  headerList.value.forEach(({ key, value }) => {
    if (key.trim()) out[key.trim()] = value;
  });
  return out;
};

const handleSave = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      const payload = {
        name: formData.value.name,
        description: formData.value.description,
        url: formData.value.url,
        method: formData.value.method,
        headers: buildHeaders(),
        content_type: formData.value.content_type,
        body: formData.value.body,
        expected_status: formData.value.expected_status,
        project: formData.value.project,
        environment: formData.value.environment,
      };
      if (isEdit.value && caseId.value) {
        await service.put(`/qa/auto-cases/${caseId.value}/`, payload);
        // 同步断言：简单做法 —— 全删后全建
        await service.post(`/qa/assertions/bulk_delete/`, {
          ids: assertionList.value.filter(a => a.id).map(a => a.id),
        });
        for (const a of assertionList.value) {
          await service.post(`/qa/assertions/`, {
            ...a,
            case: caseId.value,
          });
        }
        ElMessage.success('保存成功');
      } else {
        const res: any = await service.post(`/qa/auto-cases/`, payload);
        const newId = res.id;
        for (const a of assertionList.value) {
          await service.post(`/qa/assertions/`, { ...a, case: newId });
        }
        ElMessage.success('创建成功');
        router.replace({ name: 'AutoCaseDetail', params: { id: newId } });
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || '保存失败');
    } finally {
      saving.value = false;
    }
  });
};

const handleRun = async () => {
  if (!caseId.value) return;
  running.value = true;
  lastResult.value = null;
  try {
    const res: any = await service.post(`/qa/auto-cases/${caseId.value}/execute/`);
    const resultId = res.result_id;
    if (!resultId) {
      ElMessage.warning('执行完成但未返回结果 ID');
      return;
    }
    // 拉取执行结果详情
    const detail: any = await service.get(`/qa/auto-results/${resultId}/case_detail/`, {
      params: { case_result_id: res.case_result_id },
    });
    lastResult.value = {
      passed: detail.passed ?? detail.status === 'passed',
      failure_type: detail.failure_type || '',
      error_message: detail.error_message || '',
      summary: detail.result_metadata?.summary || '',
      diagnosis: detail.result_metadata?.diagnosis || null,
      request_snapshot: detail.request_snapshot || null,
      response_snapshot: detail.response_snapshot || null,
      assertion_results: detail.assertion_results || detail.assertion_details || [],
    };
    resultTab.value = detail.passed ? 'response' : (detail.failure_type === 'framework_error' ? 'diagnosis' : 'response');
    ElMessage[detail.passed ? 'success' : 'error'](detail.passed ? '执行通过' : '执行失败');
  } catch (e: any) {
    ElMessage.error(e.response?.data?.error || '执行失败');
  } finally {
    running.value = false;
  }
};

const goBack = () => {
  router.push({ name: 'AutoCaseList' });
};

onMounted(async () => {
  await Promise.all([loadProjects(), loadEnvironments()]);
  await loadCase();
});
</script>

<style scoped>
.auto-case-detail { padding: 0; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
}

.page-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 4px 0 0;
}

.content-wrapper {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 1280px) {
  .content-wrapper { grid-template-columns: 1fr; }
}

.config-card, .result-card {
  margin-bottom: 16px;
}

.card-title {
  font-weight: 600;
}

.form-tip {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.form-tip-inline {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-left: 10px;
}

.kv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.kv-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-result {
  padding: 24px 0;
}

.result-content {
  min-height: 200px;
}

:deep(.el-card__body) {
  padding: 16px;
}
</style>
