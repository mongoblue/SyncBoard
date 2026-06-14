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

:root {
  --color-primary: #0F766E;
  --color-primary-light: #14B8A6;
  --color-primary-dark: #0D9488;
  --color-primary-bg: #F0FDFA;
  --color-primary-border: #99F6E4;
  --color-accent: #FF4F00;
  --color-accent-bg: #FFF3EC;
  --color-bg: #F7F7F8;
  --color-surface: #FFFFFF;
  --color-surface-sunken: #FAFAFA;
  --color-text: #0A0A0A;
  --color-text-secondary: #5C5C5C;
  --color-text-tertiary: #9A9A9A;
  --color-border: #E5E5E5;
  --color-border-strong: #1A1A1A;
  --color-border-light: #F0F0F0;
  --color-danger: #EF4444;
  --color-success: #22C55E;
  --color-warning: #F59E0B;
  --color-accent-bar-0: #0F766E;
  --color-accent-bar-1: #FF4F00;
  --color-accent-bar-2: #5C5C5C;
  --color-accent-bar-3: #14B8A6;
  --shadow-sm: none;
  --shadow-md: 0 8px 24px rgba(10, 10, 10, 0.08);
  --shadow-lg: 0 16px 40px rgba(10, 10, 10, 0.12);
  --radius-sm: 2px;
  --radius-md: 2px;
  --radius-lg: 4px;
  --font-heading: 'Inter', 'Helvetica Neue', Helvetica, system-ui, -apple-system, sans-serif;
  --font-body: 'Inter', 'Helvetica Neue', Helvetica, system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
  --transition-fast: 120ms ease;
  --transition-normal: 200ms ease;
}

[data-theme="dark"] {
  --color-primary: #14B8A6;
  --color-primary-light: #2DD4BF;
  --color-primary-dark: #0D9488;
  --color-primary-bg: #0F2F2B;
  --color-primary-border: #134E4A;
  --color-accent: #FF6B2C;
  --color-accent-bg: #2A1810;
  --color-bg: #0A0A0A;
  --color-surface: #141414;
  --color-surface-sunken: #0F0F0F;
  --color-text: #F5F5F5;
  --color-text-secondary: #A8A8A8;
  --color-text-tertiary: #6B6B6B;
  --color-border: #2A2A2A;
  --color-border-strong: #F5F5F5;
  --color-border-light: #1F1F1F;
  --color-danger: #F87171;
  --color-success: #34D399;
  --color-warning: #FBBF24;
  --color-accent-bar-0: #14B8A6;
  --color-accent-bar-1: #FF6B2C;
  --color-accent-bar-2: #A8A8A8;
  --color-accent-bar-3: #2DD4BF;
  --shadow-sm: none;
  --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.5);
  --shadow-lg: 0 16px 40px rgba(0, 0, 0, 0.6);
}

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
