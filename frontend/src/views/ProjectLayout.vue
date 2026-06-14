<template>
  <div class="project-layout">
    <!-- 左侧菜单 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="brand">
          <el-icon :size="24" color="#14b8a6"><Collection /></el-icon>
          <span class="brand-text">FlowSpace</span>
        </div>
        <div class="project-info">
          <div class="project-badge">
            <el-icon :size="16"><FolderOpened /></el-icon>
          </div>
          <h3 class="project-name">{{ projectName }}</h3>
        </div>
      </div>

      <nav class="menu">
        <!-- 工作区 -->
        <div class="menu-section">
          <span class="section-title">工作区</span>
          <router-link
            v-for="item in mainMenuItems"
            :key="item.path"
            :to="`/projects/${projectId}${item.path}`"
            class="menu-item"
            :class="{ active: isActive(item.path) }"
          >
            <div class="item-icon" :style="{ background: item.color + '20', color: item.color }">
              <el-icon :size="18" v-if="item.icon">
                <component :is="item.icon" />
              </el-icon>
              <el-icon :size="18" v-else><Document /></el-icon>
            </div>
            <span class="item-text">{{ item.name }}</span>
          </router-link>
        </div>

        <!-- 项目管理 -->
        <div class="menu-section">
          <span class="section-title">项目管理</span>
          <router-link
            v-for="item in projectMenuItems"
            :key="item.path"
            :to="`/projects/${projectId}${item.path}`"
            class="menu-item"
            :class="{ active: isActive(item.path) }"
          >
            <div class="item-icon" :style="{ background: item.color + '20', color: item.color }">
              <el-icon :size="18" v-if="item.icon">
                <component :is="item.icon" />
              </el-icon>
              <el-icon :size="18" v-else><Document /></el-icon>
            </div>
            <span class="item-text">{{ item.name }}</span>
          </router-link>
        </div>

        <!-- 工具菜单 -->
        <div class="menu-section">
          <span class="section-title">工具</span>
          <router-link
            v-for="item in toolMenuItems"
            :key="item.path"
            :to="`/projects/${projectId}${item.path}`"
            class="menu-item"
            :class="{ active: isActive(item.path) }"
          >
            <div class="item-icon" :style="{ background: item.color + '20', color: item.color }">
              <el-icon :size="18" v-if="item.icon">
                <component :is="item.icon" />
              </el-icon>
              <el-icon :size="18" v-else><Document /></el-icon>
            </div>
            <span class="item-text">{{ item.name }}</span>
            <el-icon v-if="isActive(item.path)" class="active-indicator" :size="14"><ArrowRight /></el-icon>
          </router-link>
        </div>

        <!-- 动态权限菜单（如果有） -->
        <template v-if="authStore.menus.length">
          <div class="menu-section" v-for="section in menuSections" :key="section.title" v-show="section.items.length > 0">
            <span class="section-title">{{ section.title }}</span>
            <template v-for="item in section.items" :key="item.path || item.id">
              <!-- 目录类型 - 可展开 -->
              <div v-if="item.type === 'directory' && item.children?.length" class="menu-directory">
                <div
                  class="menu-item directory"
                  :class="{ active: isDirectoryActive(item) }"
                  @click="toggleDirectory(item)"
                >
                  <div class="item-icon" :style="{ background: getIconColor(item) + '20', color: getIconColor(item) }">
                    <el-icon :size="18" v-if="item.icon">
                      <component :is="getIconComponent(item.icon)" />
                    </el-icon>
                    <el-icon :size="18" v-else><Document /></el-icon>
                  </div>
                  <span class="item-text">{{ item.name }}</span>
                  <el-icon class="expand-icon" :class="{ expanded: expandedMenus.includes(item.id) }" :size="14">
                    <ArrowDown />
                  </el-icon>
                </div>
                <!-- 子菜单 -->
                <div class="submenu" v-show="expandedMenus.includes(item.id)">
                  <router-link
                    v-for="child in item.children"
                    :key="child.path || child.id"
                    :to="`/projects/${projectId}${child.path}`"
                    class="menu-item submenu-item"
                    :class="{ active: isActive(child.path) }"
                  >
                    <span class="item-text">{{ child.name }}</span>
                    <el-icon v-if="isActive(child.path)" class="active-indicator" :size="12"><ArrowRight /></el-icon>
                  </router-link>
                </div>
              </div>

              <!-- 菜单类型 - 直接跳转 -->
              <router-link
                v-else-if="item.type === 'menu' || (item.type === 'directory' && !item.children?.length)"
                :to="`/projects/${projectId}${item.path}`"
                class="menu-item"
                :class="{ active: isActive(item.path) }"
              >
                <div class="item-icon" :style="{ background: getIconColor(item) + '20', color: getIconColor(item) }">
                  <el-icon :size="18" v-if="item.icon">
                    <component :is="getIconComponent(item.icon)" />
                  </el-icon>
                  <el-icon :size="18" v-else><Document /></el-icon>
                </div>
                <span class="item-text">{{ item.name }}</span>
                <el-icon v-if="isActive(item.path)" class="active-indicator" :size="14"><ArrowRight /></el-icon>
              </router-link>
            </template>
          </div>
        </template>

        <!-- 系统管理菜单 -->
        <div class="menu-section">
          <span class="section-title">系统管理</span>
          <router-link
            v-for="item in systemMenuItems"
            :key="item.path"
            :to="`/projects/${projectId}${item.path}`"
            class="menu-item"
            :class="{ active: isActive(item.path) }"
          >
            <div class="item-icon" :style="{ background: item.color + '20', color: item.color }">
              <el-icon :size="18" v-if="item.icon">
                <component :is="item.icon" />
              </el-icon>
              <el-icon :size="18" v-else><Document /></el-icon>
            </div>
            <span class="item-text">{{ item.name }}</span>
            <el-icon v-if="isActive(item.path)" class="active-indicator" :size="14"><ArrowRight /></el-icon>
          </router-link>
        </div>
      </nav>

      <div class="sidebar-footer">
        <router-link to="/projects" class="back-button">
          <el-icon :size="18"><ArrowLeft /></el-icon>
          <span>返回项目列表</span>
        </router-link>
        <div class="user-mini">
          <AvatarUpload :user="authStore.user!" @avatar-updated="handleAvatarUpdated" size="small" />
          <span class="user-name">{{ authStore.user?.username }}</span>
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <main class="main-content">
      <!-- 顶部栏 -->
      <header class="top-bar">
        <div class="breadcrumb">
          <div class="breadcrumb-item">
            <el-icon :size="16" color="#6366f1"><FolderOpened /></el-icon>
            <span class="project-title">{{ projectName }}</span>
          </div>
          <el-icon class="breadcrumb-separator" :size="14"><ArrowRight /></el-icon>
          <span class="page-title">{{ currentPageTitle }}</span>
        </div>
        <div class="top-actions">
          <div class="status-badge" :class="{ online: boardStore.isConnected }">
            <span class="status-dot"></span>
            <span class="status-text">{{ boardStore.isConnected ? '实时同步中' : '离线' }}</span>
          </div>
          <el-button type="danger" link size="small" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
          </el-button>
        </div>
      </header>

      <!-- 页面内容 -->
      <div class="page-container">
        <router-view v-slot="{ Component }">
          <keep-alive :include="['AIChat']">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, markRaw } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore, type MenuItem } from '@/stores/Auth';
import { useBoardStore } from '@/stores/board';
import AvatarUpload from '@/components/AvatarUpload.vue';
import {
  ArrowLeft,
  ArrowRight,
  ArrowDown,
  Grid,
  User,
  UserFilled,
  Menu,
  Collection,
  DataLine,
  Setting,
  ChatDotRound,
  Bell,
  ChatLineRound,
  Monitor,
  FolderOpened,
  SwitchButton,
  // 动态图标映射
  Folder,
  Document,
  Tools,
  Management,
  List,
  Operation,
  Timer,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue';
import type { Component } from 'vue';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const boardStore = useBoardStore();

const projectId = computed(() => route.params.projectId as string);
const projectName = computed(() => boardStore.currentProject?.name || '项目');

// 展开的菜单目录
const expandedMenus = ref<number[]>([]);

// 图标映射表
const iconMap: Record<string, Component> = {
  'Grid': Grid,
  'User': User,
  'Collection': Collection,
  'DataLine': DataLine,
  'Setting': Setting,
  'ChatDotRound': ChatDotRound,
  'Bell': Bell,
  'ChatLineRound': ChatLineRound,
  'Monitor': Monitor,
  'FolderOpened': FolderOpened,
  'Folder': Folder,
  'Document': Document,
  'Tools': Tools,
  'Management': Management,
  'List': List,
  'Operation': Operation,
};

// 默认颜色映射
const colorMap: Record<string, string> = {
  'board': '#14b8a6',
  'members': '#22c55e',
  'tags': '#3B82F6',
  'stats': '#a78bfa',
  'chat': '#22d3ee',
  'ai-chat': '#f472b6',
  'qa': '#fb923c',
  'notifications': '#f87171',
  'settings': '#9ca3af',
};

// 获取图标组件
const getIconComponent = (iconName?: string): Component => {
  if (iconName && iconMap[iconName]) {
    return iconMap[iconName];
  }
  return Document;
};

// 获取图标颜色
const getIconColor = (item: MenuItem): string => {
  // 如果有子菜单，使用第一个子菜单的路径来确定颜色
  const path = item.path || item.children?.[0]?.path || '';
  const key = path.replace('/', '').split('/')[0] || '';
  return colorMap[key] || '#6366f1';
};

// 切换目录展开/收起
const toggleDirectory = (item: MenuItem) => {
  const index = expandedMenus.value.indexOf(item.id);
  if (index > -1) {
    expandedMenus.value.splice(index, 1);
  } else {
    expandedMenus.value.push(item.id);
  }
};

// 检查目录是否处于激活状态（任一子菜单被选中）
const isDirectoryActive = (item: MenuItem): boolean => {
  if (!item.children) return false;
  const currentPath = route.path.replace(`/projects/${projectId.value}`, '');
  return item.children.some(child => child.path === currentPath);
};

// 默认菜单配置（当没有动态菜单时使用）
const mainMenuItems = [
  { path: '/board', name: '看板', icon: markRaw(Grid), color: '#14b8a6' },
  { path: '/members', name: '成员管理', icon: markRaw(User), color: '#22c55e' },
  { path: '/tags', name: '标签管理', icon: markRaw(Collection), color: '#3B82F6' },
];

const projectMenuItems = [
  { path: '/sprints', name: '迭代管理', icon: markRaw(Timer), color: '#f59e0b' },
  { path: '/quality', name: '质量报告', icon: markRaw(TrendCharts), color: '#14b8a6' },
  { path: '/bugs', name: 'Bug 管理', icon: markRaw(Warning), color: '#ef4444' },
  { path: '/bugs/my', name: '我的 Bug', icon: markRaw(Warning), color: '#f97316' },
  { path: '/api-docs', name: 'API 文档', icon: markRaw(Document), color: '#6366f1' },
  { path: '/stats', name: '统计报表', icon: markRaw(DataLine), color: '#a78bfa' },
];

const toolMenuItems = [
  { path: '/chat', name: '项目聊天', icon: markRaw(ChatLineRound), color: '#22d3ee' },
  { path: '/ai-chat', name: 'AI助手', icon: markRaw(ChatDotRound), color: '#f472b6' },
  { path: '/notifications', name: '消息', icon: markRaw(Bell), color: '#f87171' },
  { path: '/settings', name: '设置', icon: markRaw(Setting), color: '#9ca3af' },
];

// 系统管理菜单
const systemMenuItems = [
  { path: '/system/menu', name: '菜单管理', icon: markRaw(Menu), color: '#6366f1' },
  { path: '/system/role', name: '角色管理', icon: markRaw(UserFilled), color: '#8b5cf6' },
  { path: '/system/user', name: '用户管理', icon: markRaw(User), color: '#a78bfa' },
];

// 菜单分区 - 只包含后端特有的动态菜单
const menuSections = computed(() => {
  if (!authStore.menus.length) {
    return [];
  }

  // 收集所有默认菜单路径（包括子菜单）
  const defaultPaths = new Set<string>([
    ...mainMenuItems.map(m => m.path).filter((p): p is string => !!p),
    ...projectMenuItems.map(m => m.path).filter((p): p is string => !!p),
    ...toolMenuItems.map(m => m.path).filter((p): p is string => !!p),
    ...systemMenuItems.map(m => m.path).filter((p): p is string => !!p),
  ]);

  // 递归检查目录下的所有子菜单是否都在默认菜单中
  const isDirectoryFullyCovered = (menu: MenuItem): boolean => {
    if (!menu.children || menu.children.length === 0) return true;
    return menu.children.every(child => {
      if (child.type === 'directory') {
        return isDirectoryFullyCovered(child);
      }
      return defaultPaths.has(child.path || '');
    });
  };

  // 只保留后端特有的菜单
  const uniqueMenus = authStore.menus.filter(menu => {
    // 如果是目录类型，检查其所有子菜单是否都被默认菜单覆盖
    if (menu.type === 'directory') {
      return !isDirectoryFullyCovered(menu);
    }
    // 如果路径不在默认菜单中，保留
    return !defaultPaths.has(menu.path || '');
  });

  if (uniqueMenus.length === 0) {
    return [];
  }

  return [
    { title: '权限菜单', items: uniqueMenus },
  ];
});

// 当前页面标题
const currentPageTitle = computed(() => {
  const currentPath = route.path.replace(`/projects/${projectId.value}`, '');

  // 先从动态菜单中查找
  const findInMenus = (menus: MenuItem[]): string | null => {
    for (const menu of menus) {
      if (menu.path === currentPath) {
        return menu.name;
      }
      if (menu.children) {
        const found = findInMenus(menu.children);
        if (found) return found;
      }
    }
    return null;
  };

  const dynamicTitle = findInMenus(authStore.menus);
  if (dynamicTitle) return dynamicTitle;

  // 从默认菜单中查找
  const allItems = [...mainMenuItems, ...projectMenuItems, ...toolMenuItems];
  const item = allItems.find(i => i.path === currentPath);
  return item?.name || '看板';
});

// 判断是否当前激活的菜单
const isActive = (path?: string) => {
  if (!path) return false;
  const currentPath = route.path.replace(`/projects/${projectId.value}`, '');
  return currentPath === path;
};

// 加载项目信息
const loadProjectInfo = async () => {
  if (projectId.value) {
    boardStore.currentProjectId = projectId.value;
    await boardStore.fetchProjectInfo(projectId.value);
    await boardStore.fetchUsers();
  }
};

const handleAvatarUpdated = (avatarUrl: string) => {
  authStore.updateAvatar(avatarUrl);
};

const handleLogout = async () => {
  await authStore.logout();
  router.push('/login');
};

onMounted(() => {
  loadProjectInfo();
});

// 监听项目ID变化
watch(() => projectId.value, () => {
  loadProjectInfo();
});
</script>

<style scoped>
.project-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--color-bg);
}

/* 左侧菜单 */
.sidebar {
  width: 240px;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: 50;
}

.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid var(--color-border-light);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.brand-text {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 20px;
  color: var(--color-primary);
}

.project-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--color-surface-sunken);
  border-radius: 2px;
  border: 1px solid var(--color-border);
}

.project-badge {
  width: 32px;
  height: 32px;
  background: var(--color-text);
  border-radius: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-inverse);
  flex-shrink: 0;
}

.project-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu {
  flex: 1;
  padding: 16px 12px;
  overflow-y: auto;
}

.menu-section {
  margin-bottom: 24px;
}

.section-title {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  letter-spacing: 0.3px;
  padding: 0 12px;
  margin-bottom: 8px;
}

.menu-directory {
  margin-bottom: 4px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 10px;
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: all 0.25s ease;
  cursor: pointer;
  position: relative;
}

.menu-item:hover {
  background: var(--color-primary-bg);
  color: var(--color-text);
}

.menu-item.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  font-weight: 600;
}

.menu-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 24px;
  background: var(--color-accent);
}

.menu-item.directory {
  margin-bottom: 0;
}

.expand-icon {
  margin-left: auto;
  transition: transform 0.25s ease;
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.submenu {
  padding-left: 20px;
  margin-top: 4px;
}

.submenu-item {
  padding: 8px 12px;
  font-size: 13px;
  margin-bottom: 2px;
}

.submenu-item::before {
  display: none;
}

.item-icon {
  width: 28px;
  height: 28px;
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.25s ease;
  color: var(--color-text-tertiary);
}

.menu-item.active .item-icon,
.menu-item:hover .item-icon {
  color: var(--color-text);
}

.menu-item:hover .item-icon {
  transform: scale(1.1);
}

.item-text {
  flex: 1;
  font-size: 14px;
}

.active-indicator {
  color: var(--color-primary);
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-bg);
}

.back-button {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 0;
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 13px;
  transition: all 0.25s ease;
  background: transparent;
  border: 1px solid var(--color-border);
}

.back-button:hover {
  color: var(--color-text);
  border-color: var(--color-text);
}

.user-mini {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: transparent;
  border-radius: 0;
  border-top: 1px solid var(--color-border);
  padding-top: 16px;
  margin-top: 8px;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
}

/* 右侧内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg);
}

.top-bar {
  height: 56px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  flex-shrink: 0;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 12px;
}

.breadcrumb-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--color-bg);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.project-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.breadcrumb-separator {
  color: var(--color-text-tertiary);
}

.page-title {
  font-size: 14px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  background: transparent;
  border: none;
  font: 500 11px/1 var(--font-mono);
  color: var(--color-text-secondary);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  transition: all 0.3s ease;
}

.status-badge.online {
  color: var(--color-text-secondary);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 0;
  background: var(--color-text-tertiary);
  transition: all 0.3s ease;
}

.status-badge.online .status-dot {
  background: var(--color-success);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.page-container {
  flex: 1;
  overflow: auto;
  padding: 24px;
}
</style>
