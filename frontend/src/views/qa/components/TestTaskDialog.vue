<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEditing ? '编辑测试任务' : '创建测试任务'"
    width="700px"
    destroy-on-close
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-position="top"
    >
      <el-row :gutter="20">
        <el-col :span="16">
          <el-form-item label="任务名称" prop="name">
            <el-input
              v-model="formData.name"
              placeholder="例如：每日回归测试"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="测试类型" prop="test_type">
            <el-select v-model="formData.test_type" placeholder="选择类型" style="width: 100%">
              <el-option label="接口测试" value="api">
                <span style="display: flex; align-items: center; gap: 8px">
                  <el-icon><Connection /></el-icon> 接口测试
                </span>
              </el-option>
              <el-option label="UI测试" value="ui">
                <span style="display: flex; align-items: center; gap: 8px">
                  <el-icon><Monitor /></el-icon> UI测试
                </span>
              </el-option>
              <el-option label="性能测试" value="performance">
                <span style="display: flex; align-items: center; gap: 8px">
                  <el-icon><Lightning /></el-icon> 性能测试
                </span>
              </el-option>
              <el-option label="回归测试" value="regression">
                <span style="display: flex; align-items: center; gap: 8px">
                  <el-icon><Refresh /></el-icon> 回归测试
                </span>
              </el-option>
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="任务描述">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="2"
          placeholder="描述这个测试任务的用途..."
        />
      </el-form-item>

      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="触发方式" prop="trigger_type">
            <el-select v-model="formData.trigger_type" placeholder="选择触发方式" style="width: 100%">
              <el-option label="手动触发" value="manual">
                <span style="display: flex; align-items: center; gap: 8px">
                  <el-icon><Pointer /></el-icon> 手动触发
                </span>
              </el-option>
              <el-option label="定时触发" value="scheduled">
                <span style="display: flex; align-items: center; gap: 8px">
                  <el-icon><Timer /></el-icon> 定时触发
                </span>
              </el-option>
              <el-option label="Webhook触发" value="webhook">
                <span style="display: flex; align-items: center; gap: 8px">
                  <el-icon><Link /></el-icon> Webhook触发
                </span>
              </el-option>
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="执行环境">
            <el-select v-model="formData.test_config.environment" placeholder="选择环境" style="width: 100%">
              <el-option label="开发环境" value="development" />
              <el-option label="测试环境" value="testing" />
              <el-option label="预发布环境" value="staging" />
              <el-option label="生产环境" value="production" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 定时配置 -->
      <el-form-item v-if="formData.trigger_type === 'scheduled'" label="定时规则 (Cron)">
        <el-input
          v-model="formData.cron_expression"
          placeholder="0 0 * * * (每天零点执行)"
        />
        <div class="form-tip">
          使用 Cron 表达式定义执行时间，例如：0 9 * * 1-5 (工作日早上9点)
        </div>
      </el-form-item>

      <!-- 测试用例选择 -->
      <el-form-item label="选择测试用例">
        <div class="test-cases-selector">
          <div class="selector-header">
            <el-checkbox
              v-model="selectAll"
              :indeterminate="isIndeterminate"
              @change="handleSelectAll"
            >
              全选
            </el-checkbox>
            <span class="selected-count">
              已选择 {{ selectedCaseCount }} 个用例
            </span>
          </div>

          <el-tabs v-model="activeTab" type="border-card">
            <el-tab-pane label="API 测试用例" name="api">
              <div class="case-list" v-if="apiTestCases.length > 0">
                <el-checkbox-group v-model="formData.test_config.api_cases">
                  <div
                    v-for="item in apiTestCases"
                    :key="item.id"
                    class="case-item"
                  >
                    <el-checkbox :value="item.id">
                      <div class="case-info">
                        <span class="case-name">{{ item.name }}</span>
                        <el-tag size="small" :type="getMethodType(item.method)">
                          {{ item.method }}
                        </el-tag>
                      </div>
                    </el-checkbox>
                  </div>
                </el-checkbox-group>
              </div>
              <el-empty v-else description="暂无 API 测试用例" :image-size="80" />
            </el-tab-pane>

            <el-tab-pane label="UI 测试用例" name="ui">
              <div class="case-list" v-if="uiTestCases.length > 0">
                <el-checkbox-group v-model="formData.test_config.ui_cases">
                  <div
                    v-for="item in uiTestCases"
                    :key="item.id"
                    class="case-item"
                  >
                    <el-checkbox :value="item.id">
                      <div class="case-info">
                        <span class="case-name">{{ item.name }}</span>
                        <el-tag size="small" type="info">
                          {{ item.steps?.length || 0 }} 个步骤
                        </el-tag>
                      </div>
                    </el-checkbox>
                  </div>
                </el-checkbox-group>
              </div>
              <el-empty v-else description="暂无 UI 测试用例" :image-size="80" />
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-form-item>

      <!-- 高级配置 -->
      <el-form-item>
        <el-collapse>
          <el-collapse-item title="高级配置" name="advanced">
            <el-form-item label="失败重试次数">
              <el-input-number
                v-model="formData.config.retry_count"
                :min="0"
                :max="5"
                style="width: 150px"
              />
              <span class="form-tip-inline">测试失败时的自动重试次数</span>
            </el-form-item>

            <el-form-item label="超时时间 (秒)">
              <el-input-number
                v-model="formData.config.timeout"
                :min="30"
                :max="3600"
                :step="30"
                style="width: 150px"
              />
            </el-form-item>

            <el-form-item label="并发执行">
              <el-switch
                v-model="formData.config.parallel"
                active-text="开启"
                inactive-text="关闭"
              />
              <span class="form-tip-inline">同时执行多个测试用例（仅适用于API测试）</span>
            </el-form-item>

            <el-form-item label="失败时停止">
              <el-switch
                v-model="formData.config.fail_fast"
                active-text="是"
                inactive-text="否"
              />
              <span class="form-tip-inline">遇到失败的用例时立即停止后续测试</span>
            </el-form-item>

            <el-form-item label="通知邮箱">
              <el-select
                v-model="formData.config.notifications"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="输入邮箱地址"
                style="width: 100%"
              >
                <el-option
                  v-for="email in notificationEmails"
                  :key="email"
                  :label="email"
                  :value="email"
                />
              </el-select>
              <div class="form-tip">测试完成后发送结果通知到指定邮箱</div>
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleSave" :loading="saving">
        {{ isEditing ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import {
  Connection,
  Monitor,
  Lightning,
  Refresh,
  Pointer,
  Timer,
  Link,
} from '@element-plus/icons-vue';
import type { TestTask, CreateTestTaskRequest, TestType } from '@/types/devops';
import {
  createTestTask,
  updateTestTask,
  getTestTypeText,
} from '@/api/devops';
import service from '@/utils/request';
import { useBoardStore } from '@/stores/board';

interface Props {
  modelValue: boolean;
  task?: TestTask | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  'refresh': [];
  'close': [];
}>();

const boardStore = useBoardStore();

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

// 表单数据接口
interface FormData {
  name: string;
  description: string;
  test_type: TestType;
  project: number;
  trigger_type: 'manual' | 'scheduled' | 'webhook';
  cron_expression: string;
  webhook_url: string;
  test_config: {
    api_cases: number[];
    ui_cases: number[];
    environment: string;
    parallel: boolean;
  };
  config: {
    retry_count: number;
    timeout: number;
    parallel: boolean;
    fail_fast: boolean;
    notifications: string[];
  };
}

// 表单相关
const formRef = ref<FormInstance>();
const saving = ref(false);
const isEditing = computed(() => !!props.task);

const formData = ref<FormData>({
  name: '',
  description: '',
  test_type: 'api',
  project: 0,
  trigger_type: 'manual',
  cron_expression: '',
  webhook_url: '',
  test_config: {
    api_cases: [],
    ui_cases: [],
    environment: 'testing',
    parallel: false,
  },
  config: {
    retry_count: 0,
    timeout: 300,
    parallel: false,
    fail_fast: false,
    notifications: [],
  },
});

const formRules: FormRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  test_type: [{ required: true, message: '请选择测试类型', trigger: 'change' }],
  trigger_type: [{ required: true, message: '请选择触发方式', trigger: 'change' }],
};

// 测试用例列表
const apiTestCases = ref<any[]>([]);
const uiTestCases = ref<any[]>([]);
const activeTab = ref('api');

// 全选相关
const selectAll = ref(false);
const isIndeterminate = ref(false);

// 通知邮箱列表（示例）
const notificationEmails = ref<string[]>([
  'test@example.com',
  'qa@example.com',
]);

// 计算选中的用例总数
const selectedCaseCount = computed(() => {
  return (formData.value.test_config.api_cases?.length || 0) +
         (formData.value.test_config.ui_cases?.length || 0);
});

// 获取请求方法标签类型
const getMethodType = (method: string): 'success' | 'primary' | 'warning' | 'danger' | 'info' => {
  const types: Record<string, 'success' | 'primary' | 'warning' | 'danger' | 'info'> = {
    'GET': 'success',
    'POST': 'primary',
    'PUT': 'warning',
    'DELETE': 'danger',
    'PATCH': 'info',
  };
  return types[method] || 'info';
};

// 加载测试用例
const loadTestCases = async () => {
  try {
    const [apiRes, uiRes] = await Promise.all([
      service.get('/qa/api-cases/'),
      service.get('/qa/ui-cases/'),
    ]);
    apiTestCases.value = apiRes.results || apiRes || [];
    uiTestCases.value = uiRes.results || uiRes || [];
  } catch (error) {
    console.error('加载测试用例失败', error);
  }
};

// 全选处理
const handleSelectAll = (val: boolean) => {
  if (val) {
    // 全选当前标签页的用例
    if (activeTab.value === 'api') {
      formData.value.test_config.api_cases = apiTestCases.value.map(c => c.id);
    } else {
      formData.value.test_config.ui_cases = uiTestCases.value.map(c => c.id);
    }
  } else {
    // 取消全选当前标签页的用例
    if (activeTab.value === 'api') {
      formData.value.test_config.api_cases = [];
    } else {
      formData.value.test_config.ui_cases = [];
    }
  }
  isIndeterminate.value = false;
};

// 监听选中状态变化
watch(() => [formData.value.test_config.api_cases, formData.value.test_config.ui_cases], () => {
  updateSelectAllState();
}, { deep: true });

// 监听标签页切换
watch(activeTab, () => {
  updateSelectAllState();
});

// 更新全选状态
const updateSelectAllState = () => {
  let currentCases: any[] = [];
  let selectedCases: number[] = [];

  if (activeTab.value === 'api') {
    currentCases = apiTestCases.value;
    selectedCases = formData.value.test_config.api_cases || [];
  } else {
    currentCases = uiTestCases.value;
    selectedCases = formData.value.test_config.ui_cases || [];
  }

  const currentIds = currentCases.map(c => c.id);
  const selectedCount = selectedCases.filter(id => currentIds.includes(id)).length;

  if (selectedCount === 0) {
    selectAll.value = false;
    isIndeterminate.value = false;
  } else if (selectedCount === currentCases.length) {
    selectAll.value = true;
    isIndeterminate.value = false;
  } else {
    selectAll.value = false;
    isIndeterminate.value = true;
  }
};

// 初始化表单数据
const initFormData = () => {
  // 获取当前项目ID
  const projectId = boardStore.currentProject?.id || 0;

  if (props.task) {
    formData.value = {
      name: props.task.name,
      description: props.task.description || '',
      test_type: props.task.test_type,
      project: props.task.project,
      trigger_type: props.task.trigger_type,
      cron_expression: props.task.cron_expression || '',
      webhook_url: props.task.webhook_url || '',
      test_config: {
        api_cases: props.task.test_config?.api_cases || [],
        ui_cases: props.task.test_config?.ui_cases || [],
        environment: props.task.test_config?.environment || 'testing',
        parallel: props.task.test_config?.parallel || false,
      },
      config: {
        retry_count: 0,
        timeout: 300,
        parallel: false,
        fail_fast: false,
        notifications: [],
      },
    };
  } else {
    formData.value = {
      name: '',
      description: '',
      test_type: 'api',
      project: projectId,
      trigger_type: 'manual',
      cron_expression: '',
      webhook_url: '',
      test_config: {
        api_cases: [],
        ui_cases: [],
        environment: 'testing',
        parallel: false,
      },
      config: {
        retry_count: 0,
        timeout: 300,
        parallel: false,
        fail_fast: false,
        notifications: [],
      },
    };
  }
};

// 准备提交的数据
const prepareSubmitData = (): CreateTestTaskRequest => {
  return {
    name: formData.value.name,
    description: formData.value.description,
    test_type: formData.value.test_type,
    project: formData.value.project,
    trigger_type: formData.value.trigger_type,
    cron_expression: formData.value.cron_expression || undefined,
    webhook_url: formData.value.webhook_url || undefined,
    test_config: {
      api_cases: formData.value.test_config.api_cases,
      ui_cases: formData.value.test_config.ui_cases,
      environment: formData.value.test_config.environment,
      parallel: formData.value.config.parallel,
    },
    notify_on_success: false,
    notify_on_failure: true,
    notification_channels: formData.value.config.notifications,
  };
};

// 保存任务
const handleSave = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (!valid) return;

    saving.value = true;

    try {
      const submitData = prepareSubmitData();

      if (isEditing.value && props.task) {
        await updateTestTask(props.task.id, submitData);
        ElMessage.success('任务更新成功');
      } else {
        await createTestTask(submitData);
        ElMessage.success('任务创建成功');
      }

      dialogVisible.value = false;
      emit('refresh');
      handleClose();
    } catch (error: any) {
      console.error('保存失败:', error);
      const errorMsg = error.response?.data?.test_type?.[0] ||
                       error.response?.data?.project?.[0] ||
                       error.response?.data?.error ||
                       '保存失败';
      ElMessage.error(errorMsg);
    } finally {
      saving.value = false;
    }
  });
};

// 关闭处理
const handleClose = () => {
  formRef.value?.resetFields();
  selectAll.value = false;
  isIndeterminate.value = false;
  emit('close');
};

// 监听对话框打开
watch(() => props.modelValue, (val) => {
  if (val) {
    initFormData();
    loadTestCases();
  }
});

onMounted(() => {
  loadTestCases();
});
</script>

<style scoped>
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

.test-cases-selector {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 16px;
}

.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border-light);
}

.selected-count {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.case-list {
  max-height: 250px;
  overflow-y: auto;
}

.case-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--color-border-light);
}

.case-item:last-child {
  border-bottom: none;
}

.case-info {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-left: 8px;
}

.case-name {
  font-size: 14px;
  color: var(--color-text);
}

:deep(.el-checkbox__label) {
  display: flex;
  align-items: center;
}

:deep(.el-collapse-item__header) {
  font-weight: 500;
}
</style>
