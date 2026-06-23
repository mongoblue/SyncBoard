<template>
  <div class="app-container">
    <div v-if="!isProjectLayout" class="navbar">
      <div class="logo">
        <el-icon :size="28" color="#14b8a6"><Collection /></el-icon>
        <span>FlowSpace</span>
      </div>
      <div class="nav-actions">
        <!-- Dark Mode Toggle -->
        <el-button link @click="toggleDark">
          <el-icon :size="20"><component :is="isDark ? 'Sunny' : 'Moon'" /></el-icon>
        </el-button>
        <div v-if="authStore.user" class="user-info">
          <AvatarUpload :user="authStore.user" @avatar-updated="handleAvatarUpdated" />
          <span class="username">{{ authStore.user.username }}</span>
          <el-button type="danger" link size="small" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出
          </el-button>
        </div>
      </div>
    </div>
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/Auth';
import AvatarUpload from '@/components/AvatarUpload.vue';
import { Collection, SwitchButton, Moon, Sunny } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const isDark = ref(false);

const isProjectLayout = computed(() => {
  return route.path.includes('/projects/') && route.params.projectId;
});

const toggleDark = () => {
  isDark.value = !isDark.value;
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : '');
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light');
};

const handleAvatarUpdated = (avatarUrl: string) => {
  authStore.updateAvatar(avatarUrl);
};

const handleLogout = async () => {
  await authStore.logout();
  router.push('/login');
};

onMounted(() => {
  // 恢复 dark mode 设置
  const saved = localStorage.getItem('theme');
  if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    isDark.value = true;
    document.documentElement.setAttribute('data-theme', 'dark');
  }
  if (!authStore.user && route.path !== '/login') {
    authStore.checkAuth();
  }
});

watch(() => authStore.user, (newUser) => {
  if (!newUser && route.meta.requiresAuth) {
    router.push('/login');
  }
});
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

/* Theme tokens defined in src/styles/variables.css (single source of truth) */

body {
  font-family: var(--font-body);
  background: var(--color-bg);
  color: var(--color-text);
  line-height: 1.6;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.app-container { min-height: 100vh; }

.navbar {
  height: 56px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 20px;
  color: var(--color-primary);
}

.nav-actions { display: flex; align-items: center; gap: 12px; }

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 14px;
  background: var(--color-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.username { font-size: 14px; font-weight: 500; color: var(--color-text); }

/* Responsive */
@media (max-width: 768px) {
  .navbar { padding: 0 16px; }
  .logo span { display: none; }
  .user-info { padding: 4px 10px; gap: 8px; }
  .username { display: none; }
}
</style>
