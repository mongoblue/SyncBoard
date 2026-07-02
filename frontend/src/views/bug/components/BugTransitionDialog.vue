<template>
  <el-dialog
    :model-value="visible"
    :title="`状态流转${bug ? ' — #' + bug.id + ' ' + bug.title : ''}`"
    width="480px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-width="100px">
      <el-form-item label="当前状态">
        <BugStatusTag v-if="bug" :status="bug.status" />
      </el-form-item>
      <el-form-item label="目标状态" required>
        <el-select
          v-model="selectedStatus"
          placeholder="请选择目标状态"
          style="width: 100%"
        >
          <el-option
            v-for="s in bug?.allowed_transitions"
            :key="s"
            :label="STATUS_LABEL[s as BugStatus]"
            :value="s"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input
          v-model="comment"
          type="textarea"
          :rows="3"
          placeholder="（可选）填写流转说明"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!selectedStatus"
        @click="handleConfirm"
      >
        确认流转
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { STATUS_LABEL, type BugStatus, type BugListItem } from '@/api/bug'
import BugStatusTag from './BugStatusTag.vue'

const props = defineProps<{
  visible: boolean
  bug: BugListItem | null
  preSelectedStatus?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'confirmed', toStatus: string, comment: string): void
}>()

const selectedStatus = ref<string | null>(null)
const comment = ref('')
const submitting = ref(false)

// Reset when dialog opens
watch(() => props.visible, (v) => {
  if (v) {
    selectedStatus.value = props.preSelectedStatus || null
    comment.value = ''
    submitting.value = false
  }
})

const handleConfirm = () => {
  if (!selectedStatus.value) return
  emit('confirmed', selectedStatus.value, comment.value)
}

// Expose submitting so parent can control
defineExpose({ submitting })
</script>
