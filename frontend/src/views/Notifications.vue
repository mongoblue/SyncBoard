<template>
  <div class="notifications-page">
    <header class="page-header">
      <div class="header-left">
        <span class="header-folio">N° 01</span>
        <div class="header-titles">
          <h1 class="page-title">消息通知</h1>
          <p class="page-subtitle">
            共 {{ total }} 条 · {{ unreadCount }} 条未读
          </p>
        </div>
      </div>
      <button
        v-if="unreadCount > 0"
        class="primary-btn"
        @click="markAllAsRead"
      >
        <el-icon :size="12"><Check /></el-icon>
        全部已读
      </button>
    </header>

    <section class="notifications-block">
      <div v-if="notifications.length === 0" class="empty-state">
        <span class="empty-folio">EMPTY</span>
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
          <div class="row-cell row-cell-type">
            <span class="cell-folio">{{ (notification.type || 'sys').toUpperCase() }}</span>
          </div>
          <div class="row-cell row-cell-icon">
            <el-icon :size="16">
              <component :is="getIcon(notification.type)" />
            </el-icon>
          </div>
          <div class="row-cell row-cell-content">
            <div class="notification-title">{{ notification.title }}</div>
            <div class="notification-message">{{ notification.message }}</div>
          </div>
          <div class="row-cell row-cell-time">
            <span class="time-text">{{ formatTime(notification.created_at) }}</span>
          </div>
          <div class="row-cell row-cell-status">
            <span v-if="!notification.is_read" class="unread-mark" title="未读">●</span>
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
  gap: 24px;
}

/* ── Page header ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
  gap: 24px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.header-folio {
  font: 600 11px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
  padding-top: 6px;
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  margin: 0;
  font: 600 26px/1.2 var(--font-heading);
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.page-subtitle {
  margin: 0;
  font: 500 12px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
  background: var(--color-text);
  border: 1px solid var(--color-text);
  color: var(--color-text-inverse);
  cursor: pointer;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.primary-btn:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

/* ── Notifications block ── */
.notifications-block {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.notification-list {
  display: flex;
  flex-direction: column;
}

.notification-row {
  display: grid;
  grid-template-columns: 60px 32px 1fr 120px 32px;
  align-items: center;
  gap: 0;
  padding: 0;
  border-bottom: 1px solid var(--color-border-light);
  cursor: pointer;
  transition: background var(--transition-fast);
  min-height: 64px;
}

.notification-row:last-child {
  border-bottom: none;
}

.notification-row:hover {
  background: var(--color-surface-sunken);
}

.notification-row.unread {
  background: var(--color-accent-bg);
}

.notification-row.unread:hover {
  background: var(--color-accent-bg);
  opacity: 0.92;
}

.row-cell {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  min-width: 0;
  border-right: 1px solid var(--color-border-light);
  height: 100%;
}

.row-cell:last-child {
  border-right: none;
  justify-content: center;
  padding: 14px 12px;
}

.row-cell-type {
  justify-content: flex-start;
}

.cell-folio {
  font: 600 9px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.row-cell-icon {
  justify-content: center;
  color: var(--color-text-secondary);
  padding: 14px 8px;
}

.notification-row.unread .row-cell-icon {
  color: var(--color-accent);
}

.row-cell-content {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 14px 20px;
}

.notification-title {
  font: 600 13px/1.3 var(--font-heading);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}

.notification-message {
  font: 400 12px/1.5 var(--font-body);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}

.row-cell-time {
  justify-content: flex-end;
  font-variant-numeric: tabular-nums;
}

.time-text {
  font: 500 11px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.unread-mark {
  font-size: 10px;
  color: var(--color-accent);
  line-height: 1;
}

/* ── Empty state ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 20px;
  text-align: center;
}

.empty-folio {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.empty-text {
  margin: 0;
  font: 400 14px/1.5 var(--font-body);
  color: var(--color-text-secondary);
}

/* ── Pagination ── */
.pagination {
  display: flex;
  justify-content: center;
  padding: 20px;
  border-top: 1px solid var(--color-border);
}

.pagination :deep(.el-pagination .btn-prev),
.pagination :deep(.el-pagination .btn-next),
.pagination :deep(.el-pager li) {
  background: transparent;
  color: var(--color-text-secondary);
  border-radius: 0;
  font: 500 12px/1 var(--font-mono);
}

.pagination :deep(.el-pager li.is-active) {
  background: var(--color-text);
  color: var(--color-text-inverse);
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .notification-row {
    grid-template-columns: 50px 28px 1fr 100px 28px;
  }
}

@media (max-width: 768px) {
  .notification-row {
    grid-template-columns: 1fr 32px;
    grid-template-rows: auto auto;
  }
  .row-cell-type,
  .row-cell-icon,
  .row-cell-time {
    display: none;
  }
  .row-cell-content {
    border-right: none;
    border-bottom: 1px solid var(--color-border-light);
  }
  .row-cell-status {
    border-left: 1px solid var(--color-border-light);
  }
}
</style>
