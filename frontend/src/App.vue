<template>
  <ChatDrawer v-if="!route.meta.hideUI" />
  <div class="navbar">
    <div class="logo">FlowSpace</div>
    <div class="actions">
      <div class="bell-wrapper">
        🔔 
        <span v-if="notifyStore.unreadCount > 0" class="badge">
          {{ notifyStore.unreadCount }}
        </span>
      </div>
    </div>
  </div>

  <router-view />
</template>

<script setup lang="ts">
import { onMounted,watch } from 'vue';
import { useNotificationStore } from './stores/notification';
import { useRoute } from 'vue-router';
import ChatDrawer from './components/ChatDrawer.vue'; // 确认路径
import { useAuthStore } from './stores/Auth';

const route = useRoute();
const notifyStore = useNotificationStore();
const authStore = useAuthStore();

watch(() => authStore.user, (newUser) => {
  if (newUser) {
    notifyStore.InitNotificationSocket();
  }
}, { immediate: true });

onMounted(() => {
  // ✅ 无论在哪个页面，一旦加载 App 就启动通知监听
  notifyStore.InitNotificationSocket();
})
</script>

<style scoped>
.navbar {
  height: 50px;
  background: #fff;
  border-bottom: 1px solid #ddd;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.logo { font-weight: bold; font-size: 18px; }
.bell-wrapper { position: relative; cursor: pointer; font-size: 20px;}
.badge {
  position: absolute;
  top: -5px;
  right: -5px;
  background: red;
  color: white;
  border-radius: 50%;
  font-size: 12px;
  padding: 2px 5px;
}
</style>