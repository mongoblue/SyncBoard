<template>
  <div class="menu-management">
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><Menu /></el-icon>
        菜单管理
      </h2>
      <el-button type="primary" @click="handleAdd" v-permission="'sys:menu:add'">
        <el-icon><Plus /></el-icon>
        新增菜单
      </el-button>
    </div>

    <el-card class="menu-card">
      <el-table
        :data="menuTree"
        row-key="id"
        border
        default-expand-all
        :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
        v-loading="loading"
      >
        <el-table-column prop="name" label="菜单名称" min-width="180">
          <template #default="{ row }">
            <el-icon v-if="row.icon" :size="16" style="margin-right: 8px;">
              <component :is="getIconComponent(row.icon)" />
            </el-icon>
            <span>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTypeType(row.type)">
              {{ getTypeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="权限标识" min-width="150" />
        <el-table-column prop="path" label="路由路径" min-width="150" />
        <el-table-column prop="order" label="排序" width="80" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              @click="handleAddChild(row)"
              v-permission="'sys:menu:add'"
            >
              添加子项
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              @click="handleEdit(row)"
              v-permission="'sys:menu:edit'"
            >
              编辑
            </el-button>
            <el-button
              type="danger"
              link
              size="small"
              @click="handleDelete(row)"
              v-permission="'sys:menu:delete'"
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
      :title="isEdit ? '编辑菜单' : '新增菜单'"
      width="600px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item label="菜单类型" prop="type">
          <el-radio-group v-model="form.type">
            <el-radio label="directory">目录</el-radio>
            <el-radio label="menu">菜单</el-radio>
            <el-radio label="button">按钮</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="菜单名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入菜单名称" />
        </el-form-item>

        <el-form-item label="上级菜单" prop="parent">
          <el-tree-select
            v-model="form.parent"
            :data="menuOptions"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            placeholder="请选择上级菜单（不选则为顶级菜单）"
            clearable
            check-strictly
            :render-after-expand="false"
          />
        </el-form-item>

        <el-form-item label="权限标识" prop="code">
          <el-input v-model="form.code" placeholder="如：sys:user:add" />
          <div class="form-tip">按钮类型必须填写，用于权限控制</div>
        </el-form-item>

        <el-form-item label="路由路径" prop="path" v-if="form.type !== 'button'">
          <el-input v-model="form.path" placeholder="如：/system/user" />
        </el-form-item>

        <el-form-item label="图标" prop="icon" v-if="form.type !== 'button'">
          <el-select v-model="form.icon" placeholder="请选择图标" clearable style="width: 100%;">
            <el-option
              v-for="icon in iconOptions"
              :key="icon.value"
              :label="icon.label"
              :value="icon.value"
            >
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-icon><component :is="icon.component" /></el-icon>
                <span>{{ icon.label }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="排序" prop="order">
          <el-input-number v-model="form.order" :min="0" :max="999" style="width: 100%;" />
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import service from '@/utils/request';
import {
  Plus,
  Menu,
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
  UserFilled,
  OfficeBuilding
} from '@element-plus/icons-vue';
import type { Component } from 'vue';

// 菜单数据
const menuTree = ref<any[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const isEdit = ref(false);
const submitLoading = ref(false);
const formRef = ref<FormInstance>();

// 表单数据
const form = ref({
  id: undefined as number | undefined,
  name: '',
  code: '',
  path: '',
  type: 'menu' as 'directory' | 'menu' | 'button',
  icon: '',
  parent: undefined as number | undefined,
  order: 0,
  is_active: true,
});

// 表单验证规则
const rules: FormRules = {
  name: [{ required: true, message: '请输入菜单名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择菜单类型', trigger: 'change' }],
  code: [{ required: true, message: '请输入权限标识', trigger: 'blur' }],
};

// 图标选项
const iconOptions = [
  { value: 'Grid', label: '网格', component: Grid },
  { value: 'User', label: '用户', component: User },
  { value: 'Collection', label: '集合', component: Collection },
  { value: 'DataLine', label: '数据', component: DataLine },
  { value: 'Setting', label: '设置', component: Setting },
  { value: 'ChatDotRound', label: '聊天', component: ChatDotRound },
  { value: 'Bell', label: '通知', component: Bell },
  { value: 'ChatLineRound', label: '对话', component: ChatLineRound },
  { value: 'Monitor', label: '监控', component: Monitor },
  { value: 'FolderOpened', label: '文件夹', component: FolderOpened },
  { value: 'Folder', label: '目录', component: Folder },
  { value: 'Document', label: '文档', component: Document },
  { value: 'Tools', label: '工具', component: Tools },
  { value: 'Management', label: '管理', component: Management },
  { value: 'List', label: '列表', component: List },
  { value: 'Operation', label: '操作', component: Operation },
  { value: 'Lock', label: '锁', component: Lock },
  { value: 'Key', label: '钥匙', component: Key },
  { value: 'UserFilled', label: '用户填充', component: UserFilled },
  { value: 'OfficeBuilding', label: '办公楼', component: OfficeBuilding },
];

// 图标映射
const iconMap: Record<string, Component> = {
  Grid, User, Collection, DataLine, Setting, ChatDotRound, Bell,
  ChatLineRound, Monitor, FolderOpened, Folder, Document, Tools,
  Management, List, Operation, Lock, Key, UserFilled, OfficeBuilding,
};

// 获取图标组件
const getIconComponent = (iconName?: string): Component => {
  if (iconName && iconMap[iconName]) {
    return iconMap[iconName];
  }
  return Document;
};

// 菜单选项（用于上级菜单选择）
const menuOptions = computed(() => {
  const filterDirectory = (menus: any[]): any[] => {
    return menus
      .filter(m => m.type === 'directory' || m.type === 'menu')
      .map(m => ({
        ...m,
        children: m.children ? filterDirectory(m.children) : undefined,
      }));
  };
  return filterDirectory(menuTree.value);
});

// 获取类型标签
const getTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    directory: '目录',
    menu: '菜单',
    button: '按钮',
  };
  return map[type] || type;
};

// 获取类型样式
const getTypeType = (type: string) => {
  const map: Record<string, string> = {
    directory: 'primary',
    menu: 'success',
    button: 'warning',
  };
  return map[type] || 'info';
};

// 获取菜单列表
const fetchMenus = async () => {
  loading.value = true;
  try {
    const res = await service.get('/system/menus/');
    menuTree.value = res || [];
  } catch (error) {
    ElMessage.error('获取菜单列表失败');
  } finally {
    loading.value = false;
  }
};

// 新增菜单
const handleAdd = () => {
  isEdit.value = false;
  form.value = {
    id: undefined,
    name: '',
    code: '',
    path: '',
    type: 'menu',
    icon: '',
    parent: undefined,
    order: 0,
    is_active: true,
  };
  dialogVisible.value = true;
};

// 添加子菜单
const handleAddChild = (row: any) => {
  isEdit.value = false;
  form.value = {
    id: undefined,
    name: '',
    code: '',
    path: '',
    type: 'menu',
    icon: '',
    parent: row.id,
    order: 0,
    is_active: true,
  };
  dialogVisible.value = true;
};

// 编辑菜单
const handleEdit = (row: any) => {
  isEdit.value = true;
  form.value = {
    id: row.id,
    name: row.name,
    code: row.code || '',
    path: row.path || '',
    type: row.type,
    icon: row.icon || '',
    parent: row.parent?.id,
    order: row.order,
    is_active: row.is_active,
  };
  dialogVisible.value = true;
};

// 删除菜单
const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除菜单 "${row.name}" 吗？如果包含子菜单，子菜单也会被删除。`,
      '确认删除',
      { type: 'warning' }
    );
    await service.delete(`/system/menus/${row.id}/`);
    ElMessage.success('删除成功');
    fetchMenus();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
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
      if (!data.parent) {
        delete (data as any).parent;
      }

      if (isEdit.value && data.id) {
        await service.put(`/system/menus/${data.id}/`, data);
        ElMessage.success('更新成功');
      } else {
        await service.post('/system/menus/', data);
        ElMessage.success('创建成功');
      }
      dialogVisible.value = false;
      fetchMenus();
    } catch (error) {
      ElMessage.error(isEdit.value ? '更新失败' : '创建失败');
    } finally {
      submitLoading.value = false;
    }
  });
};

onMounted(() => {
  fetchMenus();
});
</script>

<style scoped>
.menu-management {
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

.menu-card {
  min-height: 500px;
}

.form-tip {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}
</style>
