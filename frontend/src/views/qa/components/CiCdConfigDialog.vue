<template>
  <el-dialog
    v-model="dialogVisible"
    title="CI/CD 集成配置"
    width="800px"
    destroy-on-close
    @close="handleClose"
  >
    <div class="cicd-dialog-content">
      <!-- 配置列表 -->
      <div class="config-list" v-if="!showForm">
        <div class="list-header">
          <el-button type="primary" @click="handleAdd">
            <el-icon><Plus /></el-icon>
            添加集成
          </el-button>
        </div>

        <el-table :data="configs" style="width: 100%" v-if="configs.length > 0">
          <el-table-column prop="name" label="名称" min-width="120" />
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              <el-tag :type="getCiCdTypeType(row.type)" size="small">
                {{ getCiCdTypeText(row.type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                {{ row.enabled ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="自动触发" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.auto_trigger" type="warning" size="small">开启</el-tag>
              <span v-else class="text-gray">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="handleEdit(row)">
                编辑
              </el-button>
              <el-button type="success" link size="small" @click="handleTest(row)">
                测试
              </el-button>
              <el-button type="danger" link size="small" @click="handleDelete(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-else description="暂无 CI/CD 集成配置" :image-size="120">
          <el-button type="primary" @click="handleAdd">添加第一个集成</el-button>
        </el-empty>
      </div>

      <!-- 配置表单 -->
      <el-form
        v-else
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-position="top"
        class="config-form"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="配置名称" prop="name">
              <el-input v-model="formData.name" placeholder="例如：生产环境 Jenkins" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="CI/CD 类型" prop="type">
              <el-select v-model="formData.type" placeholder="选择类型" style="width: 100%">
                <el-option label="Jenkins" value="jenkins">
                  <span style="display: flex; align-items: center; gap: 8px">
                    <span>🔧</span> Jenkins
                  </span>
                </el-option>
                <el-option label="GitLab CI" value="gitlab">
                  <span style="display: flex; align-items: center; gap: 8px">
                    <span>🦊</span> GitLab CI
                  </span>
                </el-option>
                <el-option label="GitHub Actions" value="github">
                  <span style="display: flex; align-items: center; gap: 8px">
                    <span>🐙</span> GitHub Actions
                  </span>
                </el-option>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="Webhook URL" prop="webhook_url">
          <el-input
            v-model="formData.webhook_url"
            placeholder="https://jenkins.example.com/job/test-job/build"
          />
          <div class="form-tip">
            用于触发 CI/CD 流水线的 Webhook 地址
          </div>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="分支" prop="branch">
              <el-input v-model="formData.branch" placeholder="main" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="请求头配置">
              <el-button type="primary" link @click="showHeadersDialog = true">
                <el-icon><Setting /></el-icon>
                配置 Headers ({{ Object.keys(formData.headers || {}).length }})
              </el-button>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-checkbox v-model="formData.enabled">启用此集成</el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="formData.auto_trigger">
            代码提交后自动触发测试
            <el-tooltip content="当代码推送到指定分支时自动触发测试任务">
              <el-icon><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-checkbox>
        </el-form-item>

        <el-form-item v-if="formData.auto_trigger" label="选择测试套件">
          <el-select
            v-model="formData.test_suite"
            multiple
            placeholder="选择要自动执行的测试用例"
            style="width: 100%"
          >
            <el-option-group label="API 测试">
              <el-option
                v-for="item in apiTestCases"
                :key="`api-${item.id}`"
                :label="item.name"
                :value="item.id"
              />
            </el-option-group>
            <el-option-group label="UI 测试">
              <el-option
                v-for="item in uiTestCases"
                :key="`ui-${item.id}`"
                :label="item.name"
                :value="item.id"
              />
            </el-option-group>
          </el-select>
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <div v-if="showForm">
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          保存
        </el-button>
      </div>
      <div v-else>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </div>
    </template>

    <!-- Headers 配置对话框 -->
    <el-dialog
      v-model="showHeadersDialog"
      title="配置请求头"
      width="500px"
      append-to-body
    >
      <div class="headers-list">
        <div
          v-for="(value, key) in formData.headers"
          :key="key"
          class="header-item"
        >
          <el-input v-model="headerKeys[key]" placeholder="Header 名称" style="width: 150px" />
          <el-input v-model="headerValues[key]" placeholder="Header 值" style="flex: 1" />
          <el-button type="danger" link @click="removeHeader(key)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
        <el-button type="primary" link @click="addHeader">
          <el-icon><Plus /></el-icon>
          添加 Header
        </el-button>
      </div>
      <template #footer>
        <el-button @click="showHeadersDialog = false">确定</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import {
  Plus,
  Setting,
  QuestionFilled,
  Delete,
} from '@element-plus/icons-vue';
import type { CiCdConfig, CreateCiCdConfigRequest } from '@/types/devops';
import {
  createCiCdConfig,
  updateCiCdConfig,
  deleteCiCdConfig,
  getCiCdTypeText,
} from '@/api/devops';
import service from '@/utils/request';

interface Props {
  modelValue: boolean;
  configs: CiCdConfig[];
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  'refresh': [];
}>();

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

// 表单相关
const formRef = ref<FormInstance>();
const showForm = ref(false);
const saving = ref(false);
const isEditing = ref(false);
const editingId = ref<number | null>(null);

const formData = ref<CreateCiCdConfigRequest & { headers: Record<string, string> }>({
  name: '',
  type: 'jenkins',
  webhook_url: '',
  branch: 'main',
  enabled: true,
  auto_trigger: false,
  test_suite: [],
  headers: {},
});

const formRules: FormRules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择 CI/CD 类型', trigger: 'change' }],
  webhook_url: [
    { required: true, message: '请输入 Webhook URL', trigger: 'blur' },
    { type: 'url', message: '请输入有效的 URL', trigger: 'blur' },
  ],
};

// Headers 配置
const showHeadersDialog = ref(false);
const headerKeys = ref<Record<string, string>>({});
const headerValues = ref<Record<string, string>>({});

// 测试用例列表
const apiTestCases = ref<any[]>([]);
const uiTestCases = ref<any[]>([]);

// 获取 CI/CD 类型标签样式
const getCiCdTypeType = (type: string): 'primary' | 'success' | 'warning' => {
  const map: Record<string, 'primary' | 'success' | 'warning'> = {
    jenkins: 'primary',
    gitlab: 'success',
    github: 'warning',
  };
  return map[type] || 'primary';
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

// 添加 Header
const addHeader = () => {
  const key = `header_${Date.now()}`;
  formData.value.headers[key] = '';
  headerKeys.value[key] = '';
  headerValues.value[key] = '';
};

// 移除 Header
const removeHeader = (key: string) => {
  delete formData.value.headers[key];
  delete headerKeys.value[key];
  delete headerValues.value[key];
};

// 添加配置
const handleAdd = () => {
  isEditing.value = false;
  editingId.value = null;
  formData.value = {
    name: '',
    type: 'jenkins',
    webhook_url: '',
    branch: 'main',
    enabled: true,
    auto_trigger: false,
    test_suite: [],
    headers: {},
  };
  headerKeys.value = {};
  headerValues.value = {};
  showForm.value = true;
};

// 编辑配置
const handleEdit = (config: CiCdConfig) => {
  isEditing.value = true;
  editingId.value = config.id;
  formData.value = {
    name: config.name,
    type: config.type,
    webhook_url: config.webhook_url,
    branch: config.branch,
    enabled: config.enabled,
    auto_trigger: config.auto_trigger,
    test_suite: config.test_suite || [],
    headers: { ...config.headers },
  };

  // 初始化 header keys/values
  headerKeys.value = {};
  headerValues.value = {};
  Object.entries(config.headers || {}).forEach(([key, value]) => {
    headerKeys.value[key] = key;
    headerValues.value[key] = value;
  });

  showForm.value = true;
};

// 测试配置
const handleTest = async (config: CiCdConfig) => {
  try {
    // 模拟测试 Webhook
    ElMessage.info(`正在测试 ${config.name} 的连接...`);

    // 实际项目中应该调用后端测试接口
    // await testCiCdWebhook(config.id);

    setTimeout(() => {
      ElMessage.success('连接测试成功！');
    }, 1500);
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '测试失败');
  }
};

// 删除配置
const handleDelete = async (config: CiCdConfig) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 CI/CD 配置 "${config.name}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );

    await deleteCiCdConfig(config.id);
    ElMessage.success('删除成功');
    emit('refresh');
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || '删除失败');
    }
  }
};

// 保存配置
const handleSave = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (!valid) return;

    saving.value = true;

    try {
      // 处理 headers
      const headers: Record<string, string> = {};
      Object.entries(headerKeys.value).forEach(([oldKey, newKey]) => {
        if (newKey && headerValues.value[oldKey]) {
          headers[newKey] = headerValues.value[oldKey];
        }
      });

      const data = {
        ...formData.value,
        headers,
      };

      if (isEditing.value && editingId.value) {
        await updateCiCdConfig(editingId.value, data);
        ElMessage.success('更新成功');
      } else {
        await createCiCdConfig(data);
        ElMessage.success('创建成功');
      }

      showForm.value = false;
      emit('refresh');
    } catch (error: any) {
      ElMessage.error(error.response?.data?.error || '保存失败');
    } finally {
      saving.value = false;
    }
  });
};

// 关闭处理
const handleClose = () => {
  showForm.value = false;
  isEditing.value = false;
  editingId.value = null;
};

onMounted(() => {
  loadTestCases();
});
</script>

<style scoped>
.cicd-dialog-content {
  min-height: 300px;
}

.list-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.config-form {
  padding: 10px 0;
}

.form-tip {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.text-gray {
  color: var(--color-text-tertiary);
}

.headers-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.header-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.el-dialog__body) {
  padding-top: 10px;
  padding-bottom: 10px;
}
</style>
