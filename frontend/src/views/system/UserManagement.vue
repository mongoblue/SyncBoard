<template>
  <div class="user-management">
    <header class="page-header">
      <div>
        <h1 class="page-title">用户管理</h1>
        <p class="page-subtitle">管理系统账号、状态、角色分配与凭据</p>
      </div>
      <el-button type="primary" @click="handleAdd" v-permission="'sys:user:add'">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        新增用户
      </el-button>
    </header>

    <el-card class="user-card">
      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索用户名或邮箱"
          clearable
          style="width: 300px;"
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button @click="handleSearch">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>
      </div>

      <el-table :data="userList" v-loading="loading" border>
        <el-table-column label="头像" width="80">
          <template #default="{ row }">
            <el-avatar :size="40" :src="row.avatar || defaultAvatar" />
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column prop="roles" label="角色" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="role in row.roles"
              :key="role.id"
              type="primary"
              size="small"
              style="margin-right: 4px; margin-bottom: 4px;"
            >
              {{ role.name }}
            </el-tag>
            <span v-if="!row.roles?.length" class="no-role">未分配角色</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="date_joined" label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ formatDate(row.date_joined) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              @click="handleEdit(row)"
              v-permission="'sys:user:edit'"
            >
              编辑
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              @click="handleRole(row)"
              v-permission="'sys:user:role'"
            >
              分配角色
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              @click="handleResetPassword(row)"
              v-permission="'sys:user:reset-password'"
            >
              重置密码
            </el-button>
            <el-button
              type="danger"
              link
              size="small"
              @click="handleDelete(row)"
              v-permission="'sys:user:delete'"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑用户' : '新增用户'"
      width="500px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" :disabled="isEdit" />
        </el-form-item>

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>

        <el-form-item label="密码" prop="password" v-if="!isEdit">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>

        <el-form-item label="姓" prop="first_name">
          <el-input v-model="form.first_name" placeholder="请输入姓" />
        </el-form-item>

        <el-form-item label="名" prop="last_name">
          <el-input v-model="form.last_name" placeholder="请输入名" />
        </el-form-item>

        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitLoading">确定</el-button>
      </template>
    </el-dialog>

    <!-- 分配角色对话框 -->
    <el-dialog
      v-model="roleDialogVisible"
      title="分配角色"
      width="500px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="用户">
          <span style="font-weight: 600;">{{ currentUser?.username }}</span>
        </el-form-item>
        <el-form-item label="角色">
          <el-select
            v-model="selectedRoles"
            multiple
            placeholder="请选择角色"
            style="width: 100%;"
          >
            <el-option
              v-for="role in roleOptions"
              :key="role.id"
              :label="role.name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveRoles" :loading="roleLoading">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog
      v-model="passwordDialogVisible"
      title="重置密码"
      width="400px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item label="用户">
          <span style="font-weight: 600;">{{ currentUser?.username }}</span>
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="newPassword"
            type="password"
            placeholder="请输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSavePassword" :loading="passwordLoading">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import service from '@/utils/request';
import { Plus, Search } from '@element-plus/icons-vue';

// 默认头像
const defaultAvatar = 'https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png';

// 用户数据
const userList = ref<any[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const roleDialogVisible = ref(false);
const passwordDialogVisible = ref(false);
const isEdit = ref(false);
const submitLoading = ref(false);
const roleLoading = ref(false);
const passwordLoading = ref(false);
const formRef = ref<FormInstance>();

// 搜索
const searchKeyword = ref('');

// 当前编辑的用户
const currentUser = ref<any>(null);

// 角色选项
const roleOptions = ref<any[]>([]);
const selectedRoles = ref<number[]>([]);

// 新密码
const newPassword = ref('');

// 表单数据
const form = ref({
  id: undefined as number | undefined,
  username: '',
  email: '',
  password: '',
  first_name: '',
  last_name: '',
  is_active: true,
});

// 表单验证规则
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
};

// 格式化日期
const formatDate = (date: string) => {
  if (!date) return '-';
  return new Date(date).toLocaleString('zh-CN');
};

// 获取用户列表
const fetchUsers = async () => {
  loading.value = true;
  try {
    const params: any = {};
    if (searchKeyword.value) {
      params.keyword = searchKeyword.value;
    }
    const res = await service.get('/system/users/', { params });
    userList.value = res || [];
  } catch (error) {
    ElMessage.error('获取用户列表失败');
  } finally {
    loading.value = false;
  }
};

// 获取角色列表
const fetchRoles = async () => {
  try {
    const res = await service.get('/system/roles/');
    roleOptions.value = res || [];
  } catch (error) {
    ElMessage.error('获取角色列表失败');
  }
};

// 搜索
const handleSearch = () => {
  fetchUsers();
};

// 新增用户
const handleAdd = () => {
  isEdit.value = false;
  form.value = {
    id: undefined,
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    is_active: true,
  };
  dialogVisible.value = true;
};

// 编辑用户
const handleEdit = (row: any) => {
  isEdit.value = true;
  form.value = {
    id: row.id,
    username: row.username,
    email: row.email,
    password: '',
    first_name: row.first_name || '',
    last_name: row.last_name || '',
    is_active: row.is_active,
  };
  dialogVisible.value = true;
};

// 删除用户
const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${row.username}" 吗？`,
      '确认删除',
      { type: 'warning' }
    );
    await service.delete(`/system/users/${row.id}/`);
    ElMessage.success('删除成功');
    fetchUsers();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

// 分配角色
const handleRole = async (row: any) => {
  currentUser.value = row;
  await fetchRoles();
  selectedRoles.value = row.roles?.map((r: any) => r.id) || [];
  roleDialogVisible.value = true;
};

// 保存角色分配
const handleSaveRoles = async () => {
  if (!currentUser.value) return;

  roleLoading.value = true;
  try {
    await service.put(`/system/users/${currentUser.value.id}/`, {
      role_ids: selectedRoles.value,
    });
    ElMessage.success('角色分配成功');
    roleDialogVisible.value = false;
    fetchUsers();
  } catch (error) {
    ElMessage.error('角色分配失败');
  } finally {
    roleLoading.value = false;
  }
};

// 重置密码
const handleResetPassword = (row: any) => {
  currentUser.value = row;
  newPassword.value = '';
  passwordDialogVisible.value = true;
};

// 保存新密码
const handleSavePassword = async () => {
  if (!currentUser.value || !newPassword.value) {
    ElMessage.warning('请输入新密码');
    return;
  }

  passwordLoading.value = true;
  try {
    await service.post(`/system/users/${currentUser.value.id}/reset-password/`, {
      password: newPassword.value,
    });
    ElMessage.success('密码重置成功');
    passwordDialogVisible.value = false;
  } catch (error) {
    ElMessage.error('密码重置失败');
  } finally {
    passwordLoading.value = false;
  }
};

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return;

  await formRef.value.validate(async (valid) => {
    if (!valid) return;

    submitLoading.value = true;
    try {
      const data = { ...form.value };

      if (isEdit.value && data.id) {
        delete (data as any).password;
        await service.put(`/system/users/${data.id}/`, data);
        ElMessage.success('更新成功');
      } else {
        await service.post('/system/users/', data);
        ElMessage.success('创建成功');
      }
      dialogVisible.value = false;
      fetchUsers();
    } catch (error) {
      ElMessage.error(isEdit.value ? '更新失败' : '创建失败');
    } finally {
      submitLoading.value = false;
    }
  });
};

onMounted(() => {
  fetchUsers();
});
</script>

<style scoped>
.user-management { padding: 0; }

.user-card { min-height: 500px; }

.search-bar { margin-bottom: 16px; }

.no-role {
  color: var(--color-text-tertiary);
  font-size: 12px;
}
</style>
