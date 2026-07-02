<template>
  <header class="workbench-header">
    <div class="header-info">
      <h1 class="page-title">缺陷工作台</h1>
      <p class="page-subtitle">集中跟踪、分派和验证当前项目中的缺陷</p>
    </div>
    <div class="header-actions">
      <el-button @click="$emit('refresh')">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <el-button type="primary" @click="$emit('create')">
        <el-icon><Plus /></el-icon>
        新建缺陷
      </el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue'

defineEmits<{
  (e: 'create'): void
  (e: 'refresh'): void
}>()
</script>

<style scoped>
.workbench-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.page-title {
  margin: 0;
  font: 600 22px/1.3 var(--font-heading);
  color: var(--color-text);
}
.page-subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
