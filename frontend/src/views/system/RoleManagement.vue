<template>
  <div class="role-management">
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><UserFilled /></el-icon>
        角色管理
      </h2>
      <el-button type="primary" @click="handleAdd" v-permission="'sys:role:add'">
        <el-icon><Plus /></el-icon>
        新增角色
      </el-button>
    </div>

    <el-card class="role-card">
      <el-table :data="roleList" v-loading="loading" border>
        <el-table-column prop="name" label="角色名称" min-width="150" />
        <el-table-column prop="key" label="角色标识" min-width="150">
          <template #default="{ row }">
            <el-tag type="info">{{ row.key }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="menus" label="权限数量" width="120">
          <template #default="{ row }">
            <el-tag type="success">{{ row.menus?.length || 0 }} 个</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              @click="handleEdit(row)"
              v-permission="'sys:role:edit'"
            >
              编辑
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              @click="handlePermission(row)"
              v-permission="'sys:role:permission'"
            >
              分配权限
            </el-button>
            <el-button
              type="danger"
              link
              size="small"
              @click="handleDelete(row)"
              v-permission="'sys:role:delete'"
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
      :title="isEdit ? '编辑角色' : '新增角色'"
      width="500px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入角色名称" />
        </el-form-item>

        <el-form-item label="角色标识" prop="key">
          <el-input v-model="form.key" placeholder="如：admin、tester" />
          <div class="form-tip">唯一标识，创建后不可修改</div>
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

    <!-- 权限分配对话框 -->
    <el-dialog
      v-model="permissionDialogVisible"
      title="分配权限"
      width="600px"
      destroy-on-close
    >
      <el-tree
        ref="permissionTreeRef"
        :data="menuTree"
        show-checkbox
        node-key="id"
        :props="{ label: 'name', children: 'children' }"
        :default-checked-keys="selectedPermissions"
        :check-strictly="false"
        default-expand-all
      >
        <template #default="{ node, data }">
          <span class="tree-node">
            <el-icon v-if="data.icon" :size="14" style="margin-right: 4px;">
              <component :is="getIconComponent(data.icon)" />
            </el-icon>
            <span>{{ node.label }}</span>
            <el-tag
              v-if="data.type === 'button'"
              type="warning"
              size="small"
              style="margin-left: 8px;"
            >
              {{ data.code }}
            </el-tag>
          </span>
        </template>
      </el-tree>

      <template #footer>
        <el-button @click="permissionDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSavePermission" :loading="permissionLoading">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance, FormRules, ElTree } from 'element-plus';
import service from '@/utils/request';
import {
  Plus,
  UserFilled,
  Grid,
  User,
  Collection,
  DataLine,
  Setting,
  ChatDotRound,
  Bell,
  ChatLineRound,
  Monitor,
  FolderOpened,
  Folder,
  Document,
  Tools,
  Management,
  List,
  Operation,
  Lock,
  Key,
  OfficeBuilding
} from '@element-plus/icons-vue';
import type { Component } from 'vue';

// 角色数据
const roleList = ref<any[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const permissionDialogVisible = ref(false);
const isEdit = ref(false);
const submitLoading = ref(false);
const permissionLoading = ref(false);
const formRef = ref<FormInstance>();
const permissionTreeRef = ref<InstanceType<typeof ElTree>>();

// 当前编辑的角色
const currentRole = ref<any>(null);

// 菜单树和选中的权限
const menuTree = ref<any[]>([]);
const selectedPermissions = ref<number[]>([]);

// 表单数据
const form = ref({
  id: undefined as number | undefined,
  name: '',
  key: '',
  is_active: true,
});

// 表单验证规则
const rules: FormRules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  key: [{ required: true, message: '请输入角色标识', trigger: 'blur' }],
};

// 图标映射
const iconMap: Record<string, Component> = {
  Grid, User, Collection, DataLine, Setting, ChatDotRound, Bell,
  ChatLineRound, Monitor, FolderOpened, Folder, Document, Tools,
  Management, List, Operation, Lock, Key, OfficeBuilding,
};

// 获取图标组件
const getIconComponent = (iconName?: string): Component => {
  if (iconName && iconMap[iconName]) {
    return iconMap[iconName];
  }
  return Document;
};

// 格式化日期
const formatDate = (date: string) => {
  if (!date) return '-';
  return new Date(date).toLocaleString('zh-CN');
};

// 获取角色列表
const fetchRoles = async () => {
  loading.value = true;
  try {
    const res = await service.get('/system/roles/');
    roleList.value = res || [];
  } catch (error) {
    ElMessage.error('获取角色列表失败');
  } finally {
    loading.value = false;
  }
};

// 获取菜单树
const fetchMenuTree = async () => {
  try {
    const res = await service.get('/system/menus/tree/');
    menuTree.value = res || [];
  } catch (error) {
    ElMessage.error('获取菜单树失败');
  }
};

// 新增角色
const handleAdd = () => {
  isEdit.value = false;
  form.value = {
    id: undefined,
    name: '',
    key: '',
    is_active: true,
  };
  dialogVisible.value = true;
};

// 编辑角色
const handleEdit = (row: any) => {
  isEdit.value = true;
  form.value = {
    id: row.id,
    name: row.name,
    key: row.key,
    is_active: row.is_active,
  };
  dialogVisible.value = true;
};

// 删除角色
const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色 "${row.name}" 吗？`,
      '确认删除',
      { type: 'warning' }
    );
    await service.delete(`/system/roles/${row.id}/`);
    ElMessage.success('删除成功');
    fetchRoles();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

// 分配权限
const handlePermission = async (row: any) => {
  currentRole.value = row;
  await fetchMenuTree();
  // 设置已选中的权限
  selectedPermissions.value = row.menus?.map((m: any) => m.id) || [];
  permissionDialogVisible.value = true;
};

// 保存权限
const handleSavePermission = async () => {
  if (!currentRole.value || !permissionTreeRef.value) return;

  permissionLoading.value = true;
  try {
    const checkedKeys = permissionTreeRef.value.getCheckedKeys();
    const halfCheckedKeys = permissionTreeRef.value.getHalfCheckedKeys();
    const allKeys = [...checkedKeys, ...halfCheckedKeys];

    await service.put(`/system/roles/${currentRole.value.id}/`, {
      menu_ids: allKeys,
    });
    ElMessage.success('权限分配成功');
    permissionDialogVisible.value = false;
    fetchRoles();
  } catch (error) {
    ElMessage.error('权限分配失败');
  } finally {
    permissionLoading.value = false;
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

      // 删除前端-only 字段，避免后端报错
      delete (data as any).menus;
      delete (data as any).created_at;
      delete (data as any).updated_at;

      if (isEdit.value && data.id) {
        const id = data.id;
        delete (data as any).id;  // id 已经在 URL 中，不需要在 body 中发送
        await service.put(`/system/roles/${id}/`, data);
        ElMessage.success('更新成功');
      } else {
        delete (data as any).id;  // 创建时不需要 id
        await service.post('/system/roles/', data);
        ElMessage.success('创建成功');
      }
      dialogVisible.value = false;
      fetchRoles();
    } catch (error) {
      ElMessage.error(isEdit.value ? '更新失败' : '创建失败');
    } finally {
      submitLoading.value = false;
    }
  });
};

onMounted(() => {
  fetchRoles();
});
</script>

<style scoped>
.role-management {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.role-card {
  min-height: 500px;
}

.form-tip {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.tree-node {
  display: flex;
  align-items: center;
}
</style>
