<template>
  <div class="notifications-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">消息通知</h1>
        <p class="page-subtitle">共 {{ total }} 条 · {{ unreadCount }} 条未读</p>
      </div>
      <el-button
        v-if="unreadCount > 0"
        type="primary"
        @click="markAllAsRead"
      >
        <el-icon style="margin-right: 4px"><Check /></el-icon>
        全部已读
      </el-button>
    </header>

    <section class="notifications-block card">
      <div v-if="notifications.length === 0" class="empty-state">
        <el-icon :size="32" color="var(--color-text-tertiary)"><Bell /></el-icon>
        <p class="empty-text">暂无消息通知</p>
      </div>

      <div v-else class="notification-list">
        <article
          v-for="notification in notifications"
          :key="notification.id"
          class="notification-row"
          :class="{ unread: !notification.is_read }"
          @click="handleNotificationClick(notification)"
        >
          <div class="row-icon">
            <el-icon :size="18">
              <component :is="getIcon(notification.type)" />
            </el-icon>
          </div>
          <div class="row-content">
            <div class="notification-title">{{ notification.title }}</div>
            <div class="notification-message">{{ notification.message }}</div>
          </div>
          <div class="row-time">
            <span>{{ formatTime(notification.created_at) }}</span>
          </div>
          <div class="row-status">
            <span v-if="!notification.is_read" class="unread-dot" title="未读"></span>
          </div>
        </article>
      </div>

      <div v-if="notifications.length > 0" class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="loadNotifications"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import service from '@/utils/request';
import { ElMessage } from 'element-plus';
import {
  Bell,
  User,
  Document,
  Check,
  Warning
} from '@element-plus/icons-vue';

const route = useRoute();

const projectId = computed(() => route.params.projectId as string);

const notifications = ref<any[]>([]);
const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);

const unreadCount = computed(() => {
  return notifications.value.filter(n => !n.is_read).length;
});

const getIcon = (type: string) => {
  const iconMap: Record<string, any> = {
    'task': Document,
    'member': User,
    'system': Bell,
    'success': Check,
    'warning': Warning,
  };
  return iconMap[type] || Bell;
};

const loadNotifications = async () => {
  try {
    const response = await service.get(`/notifications/?project=${projectId.value}&page=${currentPage.value}&page_size=${pageSize.value}`);
    notifications.value = response.results || [];
    total.value = response.count || 0;
  } catch (error: any) {
    if (error.response?.status === 404) {
      notifications.value = [];
      total.value = 0;
      return;
    }
    console.error('加载通知失败', error);
  }
};

const markAsRead = async (notificationId: number) => {
  try {
    await service.post(`/notifications/${notificationId}/read/`);
    const notification = notifications.value.find(n => n.id === notificationId);
    if (notification) {
      notification.is_read = true;
    }
  } catch (error: any) {
    if (error.response?.status === 404) return;
    console.error('标记已读失败', error);
  }
};

const markAllAsRead = async () => {
  try {
    await service.post(`/notifications/mark-all-read/?project=${projectId.value}`);
    notifications.value.forEach(n => n.is_read = true);
    ElMessage.success('已全部标记为已读');
  } catch (error: any) {
    if (error.response?.status === 404) {
      ElMessage.info('通知功能暂不可用');
      return;
    }
    console.error('标记全部已读失败', error);
  }
};

const handleNotificationClick = (notification: any) => {
  if (!notification.is_read) {
    markAsRead(notification.id);
  }
};

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - date.getTime();

  if (diff < 3600000) {
    const minutes = Math.floor(diff / 60000);
    return minutes < 1 ? '刚刚' : `${minutes} 分钟前`;
  }

  if (diff < 86400000) {
    return `${Math.floor(diff / 3600000)} 小时前`;
  }

  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
};

onMounted(() => {
  loadNotifications();
});
</script>

<style scoped>
.notifications-page {
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-border-light);
  gap: 16px;
}

.notifications-block {
  overflow: hidden;
}

.notification-list {
  display: flex;
  flex-direction: column;
}

.notification-row {
  display: grid;
  grid-template-columns: 40px 1fr 100px 24px;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-border-light);
  cursor: pointer;
  transition: background var(--transition-fast);
  position: relative;
}

.notification-row:last-child {
  border-bottom: none;
}

.notification-row:hover {
  background: var(--color-surface-hover);
}

.notification-row.unread {
  background: var(--color-primary-bg);
}

.notification-row.unread::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--color-primary);
}

.notification-row.unread:hover {
  background: var(--color-primary-bg);
  filter: brightness(0.97);
}

.row-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}

.notification-row.unread .row-icon {
  color: var(--color-primary);
}

.row-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.notification-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notification-message {
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-time {
  font-size: 12px;
  color: var(--color-text-tertiary);
  text-align: right;
}

.row-status {
  display: flex;
  justify-content: center;
}

.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  display: inline-block;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 64px 20px;
  text-align: center;
}

.empty-text {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.pagination {
  display: flex;
  justify-content: center;
  padding: 16px;
  border-top: 1px solid var(--color-border-light);
}

/* Responsive */
@media (max-width: 768px) {
  .notification-row {
    grid-template-columns: 32px 1fr 16px;
    grid-template-rows: auto auto;
    gap: 8px;
    padding: 12px 16px;
  }
  .row-time {
    grid-column: 2 / 3;
    text-align: left;
  }
  .row-status {
    grid-row: 1 / 3;
  }
}
</style>
