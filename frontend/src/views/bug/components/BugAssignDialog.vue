<template>
  <el-dialog
    :model-value="visible"
    title="指派缺陷"
    width="420px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-width="80px">
      <el-form-item label="指派给" required>
        <el-select
          v-model="selectedUserId"
          filterable
          style="width: 100%"
          placeholder="选择成员"
        >
          <el-option
            v-for="m in projectMembers"
            :key="m.user_id"
            :label="m.username"
            :value="m.user_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="说明">
        <el-input
          v-model="comment"
          type="textarea"
          :rows="2"
          placeholder="（可选）填写指派说明"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!selectedUserId"
        @click="handleConfirm"
      >
        确认指派
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ProjectMemberBrief } from '@/api/bug'

const props = defineProps<{
  visible: boolean
  projectMembers: ProjectMemberBrief[]
  preSelectedUserId?: number | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'confirmed', userId: number, comment: string): void
}>()

const selectedUserId = ref<number | null>(null)
const comment = ref('')
const submitting = ref(false)

// Reset when dialog opens; apply pre-selected user if provided
watch(() => props.visible, (v) => {
  if (v) {
    selectedUserId.value = props.preSelectedUserId || null
    comment.value = ''
    submitting.value = false
  }
})

const handleConfirm = () => {
  if (!selectedUserId.value) return
  emit('confirmed', selectedUserId.value, comment.value)
}

defineExpose({ submitting })
</script>
