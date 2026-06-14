<template>
  <div class="stats-page">
    <div class="page-header">
      <h2>统计报表</h2>
    </div>

    <!-- 概览卡片 -->
    <div class="stats-overview">
      <el-card class="stat-card" shadow="never">
        <div class="stat-icon" style="background: var(--color-primary-bg); color: var(--color-primary);">
          <el-icon :size="24"><Document /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ totalTasks }}</div>
          <div class="stat-label">总任务数</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="never">
        <div class="stat-icon" style="background: #f0fdf4; color: var(--color-success);">
          <el-icon :size="24"><Check /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ completedTasks }}</div>
          <div class="stat-label">已完成</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="never">
        <div class="stat-icon" style="background: #fffbeb; color: var(--color-warning);">
          <el-icon :size="24"><User /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ totalMembers }}</div>
          <div class="stat-label">项目成员</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="never">
        <div class="stat-icon" style="background: var(--color-bg); color: var(--color-text-tertiary);">
          <el-icon :size="24"><Collection /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ totalTags }}</div>
          <div class="stat-label">标签数量</div>
        </div>
      </el-card>
    </div>

    <!-- 列统计 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <span>各列任务分布</span>
      </template>
      <el-table :data="columnStats" style="width: 100%">
        <el-table-column prop="title" label="列名称" />
        <el-table-column prop="taskCount" label="任务数" width="120" />
        <el-table-column label="占比" width="200">
          <template #default="{ row }">
            <el-progress :percentage="row.percentage" :color="row.color" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 成员任务统计 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <span>成员任务分布</span>
      </template>
      <el-empty v-if="memberStats.length === 0" description="暂无分配的任务" />
      <el-table v-else :data="memberStats" style="width: 100%">
        <el-table-column label="成员">
          <template #default="{ row }">
            <div class="member-cell">
              <div class="avatar-circle" :style="{ background: row.color }">
                <img v-if="row.avatar" :src="row.avatar" />
                <span v-else>{{ row.name.substring(0, 2).toUpperCase() }}</span>
              </div>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="taskCount" label="负责任务数" width="120" />
        <el-table-column label="占比" width="200">
          <template #default="{ row }">
            <el-progress :percentage="row.percentage" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useBoardStore } from '@/stores/board';
import { Document, Check, User, Collection } from '@element-plus/icons-vue';

const route = useRoute();
const boardStore = useBoardStore();

const projectId = computed(() => route.params.projectId as string);

// 总任务数
const totalTasks = computed(() => {
  let count = 0;
  boardStore.Columns.forEach(col => {
    count += col.tasks?.length || 0;
  });
  return count;
});

// 已完成任务数（假设最后一列是"已完成"）
const completedTasks = computed(() => {
  const lastColumn = boardStore.Columns[boardStore.Columns.length - 1];
  return lastColumn?.tasks?.length || 0;
});

// 总成员数
const totalMembers = computed(() => {
  const members = boardStore.currentProject?.members_details?.length || 0;
  return members + 1; // +1 是负责人
});

// 标签数
const totalTags = computed(() => {
  return boardStore.currentProject?.available_tags?.length || 0;
});

// 列统计
const columnStats = computed(() => {
  const total = totalTasks.value;
  const colors = [getComputedStyle(document.documentElement).getPropertyValue('--color-primary-light').trim() || '#14B8A6', getComputedStyle(document.documentElement).getPropertyValue('--color-success').trim() || '#22C55E', getComputedStyle(document.documentElement).getPropertyValue('--color-warning').trim() || '#F59E0B', getComputedStyle(document.documentElement).getPropertyValue('--color-danger').trim() || '#EF4444', getComputedStyle(document.documentElement).getPropertyValue('--color-text-tertiary').trim() || '#94A3B8'];
  return boardStore.Columns.map((col, index) => {
    const count = col.tasks?.length || 0;
    return {
      title: col.title,
      taskCount: count,
      percentage: total > 0 ? Math.round((count / total) * 100) : 0,
      color: colors[index % colors.length],
    };
  });
});

// 成员统计
const memberStats = computed(() => {
  const stats: Record<number, { name: string; avatar: string; count: number; color: string }> = {};
  const colors = [getComputedStyle(document.documentElement).getPropertyValue('--color-primary-light').trim() || '#14B8A6', getComputedStyle(document.documentElement).getPropertyValue('--color-success').trim() || '#22C55E', getComputedStyle(document.documentElement).getPropertyValue('--color-warning').trim() || '#F59E0B', getComputedStyle(document.documentElement).getPropertyValue('--color-danger').trim() || '#EF4444', getComputedStyle(document.documentElement).getPropertyValue('--color-text-tertiary').trim() || '#94A3B8', getComputedStyle(document.documentElement).getPropertyValue('--color-primary-light').trim() || '#14B8A6'];

  // 初始化所有成员
  boardStore.Users.forEach((user, index) => {
    stats[user.id] = {
      name: user.username,
      avatar: user.profile?.avatar || '',
      count: 0,
      color: colors[index % colors.length] || '#409eff',
    };
  });

  // 统计任务
  boardStore.Columns.forEach(col => {
    col.tasks?.forEach((task: any) => {
      if (task.assignee && stats[task.assignee]) {
        stats[task.assignee]!.count++;
      }
    });
  });

  const result = Object.values(stats)
    .filter(s => s.count > 0)
    .sort((a, b) => b.count - a.count);

  const total = result.reduce((sum, r) => sum + r.count, 0);
  return result.map(r => ({
    ...r,
    taskCount: r.count,
    percentage: total > 0 ? Math.round((r.count / total) * 100) : 0,
  }));
});

onMounted(() => {
  boardStore.fetchColumns(projectId.value);
  boardStore.fetchUsers();
});
</script>

<style scoped>
.stats-page {
  max-width: 1000px;
}

.page-header {
  margin-bottom: 25px;
}

.page-header h2 {
  margin: 0;
  font-family: var(--font-heading); font-size: 22px; font-weight: 600;
  color: var(--color-text);
}

.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 25px;
}

.stat-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px;
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-family: var(--font-heading); font-size: 28px;
  font-weight: 600;
  color: var(--color-text);
  line-height: 1;
}

.stat-label {
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin-top: 5px;
}

.section-card {
  margin-bottom: 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.section-card :deep(.el-card__header) {
  font-family: var(--font-heading);
  font-weight: 600;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border-light);
}

.member-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  overflow: hidden;
}

.avatar-circle img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
