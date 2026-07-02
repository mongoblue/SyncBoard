<template>
  <el-dialog
    :model-value="visible"
    title="新建缺陷"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item label="标题" required>
        <el-input v-model="form.title" placeholder="简短描述问题" />
      </el-form-item>
      <el-form-item label="指派给">
        <el-select
          v-model="form.assignee_id"
          placeholder="（可选）"
          clearable
          filterable
          style="width: 100%"
        >
          <el-option
            v-for="m in projectMembers"
            :key="m.user_id"
            :label="m.username"
            :value="m.user_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="关联任务">
        <el-input v-model="form.linked_task" placeholder="（可选）任务 UUID" />
      </el-form-item>
      <el-form-item label="严重程度">
        <el-select v-model="form.severity" style="width: 100%">
          <el-option
            v-for="s in SEVERITY_OPTIONS"
            :key="s.value"
            :label="s.label"
            :value="s.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="优先级">
        <el-select v-model="form.priority" style="width: 100%">
          <el-option
            v-for="p in PRIORITY_OPTIONS"
            :key="p.value"
            :label="p.label"
            :value="p.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="环境">
        <el-input v-model="form.environment" placeholder="如：dev / staging / prod" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
        />
      </el-form-item>
      <el-form-item label="复现步骤">
        <el-input
          v-model="form.steps_to_reproduce"
          type="textarea"
          :rows="4"
          placeholder="1. ...&#10;2. ...&#10;3. ..."
        />
      </el-form-item>
      <el-form-item label="预期结果">
        <el-input v-model="form.expected" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="实际结果">
        <el-input v-model="form.actual" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        创建
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createBug } from '@/api/bug'
import type { BugSeverity, BugPriority, ProjectMemberBrief, BugDetail } from '@/api/bug'
import { extractErrorMessage } from '@/utils/error'

const props = defineProps<{
  visible: boolean
  projectMembers: ProjectMemberBrief[]
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'created', bug: BugDetail): void
}>()

const submitting = ref(false)

const createFormDefaults = () => ({
  title: '',
  description: '',
  steps_to_reproduce: '',
  expected: '',
  actual: '',
  environment: '',
  severity: 'major' as BugSeverity,
  priority: 'p2' as BugPriority,
  assignee_id: null as number | null,
  linked_task: '',
})

const form = reactive(createFormDefaults())

const SEVERITY_OPTIONS = [
  { value: 'blocker', label: '阻塞' },
  { value: 'critical', label: '严重' },
  { value: 'major', label: '一般' },
  { value: 'minor', label: '次要' },
  { value: 'trivial', label: '轻微' },
] as const

const PRIORITY_OPTIONS = [
  { value: 'p0', label: 'P0' },
  { value: 'p1', label: 'P1' },
  { value: 'p2', label: 'P2' },
  { value: 'p3', label: 'P3' },
] as const

const handleSubmit = async () => {
  if (!form.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  submitting.value = true
  try {
    const payload: Record<string, any> = {
      project: props.projectId,
      title: form.title,
      description: form.description,
      steps_to_reproduce: form.steps_to_reproduce,
      expected: form.expected,
      actual: form.actual,
      environment: form.environment,
      severity: form.severity,
      priority: form.priority,
    }
    if (form.assignee_id) payload.assignee_id = form.assignee_id
    if (form.linked_task.trim()) payload.linked_task = form.linked_task.trim()

    const bug = await createBug(payload as any)
    ElMessage.success('缺陷已创建')
    emit('created', bug)
    // Reset form for next use
    Object.assign(form, createFormDefaults())
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '创建失败'))
  } finally {
    submitting.value = false
  }
}
</script>
