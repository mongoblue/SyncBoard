<template>
  <div class="suite-list">
    <header class="page-header">
      <div>
        <h1 class="page-title">测试套件</h1>
        <p class="page-subtitle">将相关测试用例组织为套件，一键批量执行</p>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        新建套件
      </el-button>
    </header>

    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索套件名称或描述"
        clearable
        style="width: 280px"
        @keyup.enter="loadSuites"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button @click="loadSuites">
        <el-icon><Search /></el-icon>
        搜索
      </el-button>
      <el-button @click="loadSuites">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <el-table :data="suites" v-loading="loading" stripe border style="width: 100%">
      <el-table-column type="index" width="50" />
      <el-table-column label="套件名称" min-width="220">
        <template #default="{ row }">
          <div class="suite-name">
            <el-icon><FolderOpened /></el-icon>
            <span>{{ row.name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
      <el-table-column label="用例数" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.case_count ?? 0 }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近执行" width="160">
        <template #default="{ row }">
          <template v-if="row.last_run">
            <el-tag size="small" :type="row.last_run.status === 'passed' ? 'success' : (row.last_run.status === 'failed' ? 'danger' : 'warning')">
              {{ getStatusText(row.last_run.status) }}
            </el-tag>
            <div class="last-run-time">{{ formatTime(row.last_run.created_at) }}</div>
          </template>
          <span v-else class="no-run">未执行</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建者" width="110">
        <template #default="{ row }">{{ row.created_by_name }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" plain :loading="executingId === row.id" @click="handleExecute(row)">
            执行
          </el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      class="pagination"
      layout="prev, pager, next, total"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="handlePageChange"
    />

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑套件' : '新建套件'" width="520px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="套件名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：登录模块回归" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="套件用途说明（可选）" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh, FolderOpened } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import service from '@/utils/request'

const route = useRoute()
const router = useRouter()

const suites = ref<any[]>([])
const loading = ref(false)
const searchKeyword = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const executingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const projectId = computed(() => String(route.params.projectId || route.query.project || ''))

const form = ref({
  name: '',
  description: '',
  is_active: true,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入套件名称', trigger: 'blur' }],
}

async function loadSuites() {
  loading.value = true
  try {
    const params: Record<string, any> = { page: page.value, page_size: pageSize, search: searchKeyword.value || undefined }
    if (projectId.value) params.project = projectId.value
    const res: any = await service.get('/qa/auto-suites/', { params })
    if (Array.isArray(res)) {
      suites.value = res
      total.value = res.length
    } else {
      suites.value = res.results || []
      total.value = res.count || suites.value.length
    }
  } catch {
    ElMessage.error('加载套件列表失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.value = { name: '', description: '', is_active: true }
  dialogVisible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.value = { name: row.name, description: row.description || '', is_active: row.is_active }
  dialogVisible.value = true
}

async function handleSave() {
  if (!formRef.value) return
  await formRef.value.validate()
  saving.value = true
  try {
    if (editingId.value) {
      await service.patch(`/qa/auto-suites/${editingId.value}/`, {
        name: form.value.name,
        description: form.value.description,
        is_active: form.value.is_active,
      })
      ElMessage.success('套件已更新')
    } else {
      await service.post('/qa/auto-suites/', {
        name: form.value.name,
        description: form.value.description,
        is_active: form.value.is_active,
        project: Number(projectId.value || route.query.project),
      })
      ElMessage.success('套件已创建')
    }
    dialogVisible.value = false
    await loadSuites()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleExecute(row: any) {
  executingId.value = row.id
  try {
    const res: any = await service.post(`/qa/auto-suites/${row.id}/execute/`)
    const resultId = res?.result?.id
    ElMessage.success(res?.message || '执行完成')
    if (resultId) {
      router.push(`/projects/${projectId.value}/qa/auto-results/${resultId}`)
    } else {
      await loadSuites()
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error || '执行失败')
  } finally {
    executingId.value = null
  }
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除套件「${row.name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await service.delete(`/qa/auto-suites/${row.id}/`)
    ElMessage.success('已删除')
    await loadSuites()
  } catch {
    ElMessage.error('删除失败')
  }
}

function handlePageChange(p: number) {
  page.value = p
  loadSuites()
}

function formatTime(t?: string) {
  if (!t) return '--'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function getStatusText(status: string) {
  const map: Record<string, string> = {
    passed: '通过',
    failed: '失败',
    error: '错误',
    running: '运行中',
    pending: '待执行',
  }
  return map[status] || status
}

onMounted(loadSuites)
</script>

<style scoped>
.suite-list {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 20px;
}

.page-subtitle {
  margin: 4px 0 0;
  color: var(--color-text-secondary, #888);
  font-size: 13px;
}

.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.suite-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.last-run-time {
  font-size: 12px;
  color: var(--color-text-secondary, #888);
  margin-top: 2px;
}

.no-run {
  color: var(--color-text-secondary, #888);
  font-size: 12px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
