<template>
  <div class="bug-view-tabs">
    <el-tabs :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.value"
        :label="tab.label"
        :name="tab.value"
      />
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
}>()

defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const tabs = [
  { value: 'all', label: '全部缺陷' },
  { value: 'my_pending', label: '我的待处理' },
  { value: 'reported_by_me', label: '我提交的' },
  { value: 'verifying', label: '待验证' },
  { value: 'high_risk', label: '高风险' },
  { value: 'closed', label: '已关闭' },
]
</script>

<style scoped>
.bug-view-tabs {
  margin-bottom: 12px;
}
</style>
