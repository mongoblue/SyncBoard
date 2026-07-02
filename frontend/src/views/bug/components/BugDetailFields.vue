<template>
  <div class="detail-fields">
    <!-- 问题描述 -->
    <el-card class="section-card">
      <template #header><strong>问题描述</strong></template>
      <EditableText
        :model-value="bug.description"
        placeholder="（无）"
        :rows="3"
        @save="(v: string) => $emit('save-field', 'description', v)"
      />
    </el-card>

    <!-- 复现步骤 -->
    <el-card class="section-card">
      <template #header><strong>复现步骤</strong></template>
      <EditableText
        :model-value="bug.steps_to_reproduce"
        placeholder="（无）"
        :rows="4"
        @save="(v: string) => $emit('save-field', 'steps_to_reproduce', v)"
      />
    </el-card>

    <!-- 预期 & 实际 -->
    <div class="two-col">
      <el-card class="section-card">
        <template #header><strong>预期结果</strong></template>
        <EditableText
          :model-value="bug.expected"
          placeholder="（无）"
          :rows="2"
          @save="(v: string) => $emit('save-field', 'expected', v)"
        />
      </el-card>
      <el-card class="section-card">
        <template #header><strong>实际结果</strong></template>
        <EditableText
          :model-value="bug.actual"
          placeholder="（无）"
          :rows="2"
          @save="(v: string) => $emit('save-field', 'actual', v)"
        />
      </el-card>
    </div>

    <!-- 环境 -->
    <el-card class="section-card">
      <template #header><strong>环境</strong></template>
      <EditableText
        :model-value="bug.environment"
        placeholder="（未指定）"
        :rows="1"
        @save="(v: string) => $emit('save-field', 'environment', v)"
      />
    </el-card>

    <!-- 来源测试信息 -->
    <el-card v-if="bug.source_case_id || bug.source_result_id" class="section-card">
      <template #header><strong>来源测试信息</strong></template>
      <div class="source-info">
        <div v-if="bug.source_case_id" class="source-row">
          <span class="source-label">关联用例</span>
          <span class="source-value">#{{ bug.source_case_id }}</span>
        </div>
        <div v-if="bug.source_result_id" class="source-row">
          <span class="source-label">触发结果</span>
          <span class="source-value">#{{ bug.source_result_id }}</span>
        </div>
        <div class="source-row">
          <span class="source-label">来源类型</span>
          <el-tag size="small" type="info">{{ bug.source_display }}</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 关联任务 -->
    <el-card v-if="bug.linked_task" class="section-card">
      <template #header><strong>关联任务</strong></template>
      <code class="linked-task-code">{{ bug.linked_task }}</code>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import type { BugDetail } from '@/api/bug'
import EditableText from '@/components/bug/EditableText.vue'

defineProps<{
  bug: BugDetail
}>()

defineEmits<{
  (e: 'save-field', field: string, value: any): void
}>()
</script>

<style scoped>
.detail-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.source-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.source-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
.source-label {
  color: var(--color-text-secondary);
  min-width: 70px;
}
.source-value {
  color: var(--color-text);
  font-family: var(--font-mono, monospace);
}
.linked-task-code {
  font-size: 13px;
  padding: 4px 8px;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-sm);
  word-break: break-all;
}
</style>
