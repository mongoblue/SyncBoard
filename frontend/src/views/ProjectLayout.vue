<!--
项目内通用布局壳。

左侧菜单根据 authStore.menus + 当前项目 ID 动态渲染。
右侧 <router-view> 显示当前子路由（看板/QA/设置 等 27 个页面）。

菜单通过 v-permission 指令控制按钮级显隐。
-->
<template>
  <div class="project-layout">
    <!-- 左侧菜单 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="brand">
          <el-icon :size="22" color="var(--color-primary)"><Collection /></el-icon>
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
            <el-icon class="item-icon" :size="16">
              <component :is="item.icon" />
            </el-icon>
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
            <el-icon class="item-icon" :size="16">
              <component :is="item.icon" />
            </el-icon>
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
            <el-icon class="item-icon" :size="16">
              <component :is="item.icon" />
            </el-icon>
            <span class="item-text">{{ item.name }}</span>
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
                  <el-icon class="item-icon" :size="16">
                    <component :is="getIconComponent(item.icon)" />
                  </el-icon>
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
                <el-icon class="item-icon" :size="16">
                  <component :is="getIconComponent(item.icon)" />
                </el-icon>
                <span class="item-text">{{ item.name }}</span>
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
            <el-icon class="item-icon" :size="16">
              <component :is="item.icon" />
            </el-icon>
            <span class="item-text">{{ item.name }}</span>
          </router-link>
        </div>
      </nav>

      <div class="sidebar-footer">
        <router-link to="/projects" class="back-button">
          <el-icon :size="16"><ArrowLeft /></el-icon>
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
          <span class="crumb-project">{{ projectName }}</span>
          <el-icon class="breadcrumb-separator" :size="12"><ArrowRight /></el-icon>
          <span class="crumb-page">{{ currentPageTitle }}</span>
        </div>
        <div class="top-actions">
          <div class="status-badge" :class="{ online: boardStore.isConnected }">
            <span class="status-dot"></span>
            <span class="status-text">{{ boardStore.isConnected ? '实时同步中' : '离线' }}</span>
          </div>
          <el-button type="danger" link size="small" @click="handleLogout" title="退出登录">
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

// 获取图标组件
const getIconComponent = (iconName?: string): Component => {
  if (iconName && iconMap[iconName]) {
    return iconMap[iconName];
  }
  return Document;
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
  { path: '/board', name: '看板', icon: markRaw(Grid) },
  { path: '/members', name: '成员管理', icon: markRaw(User) },
  { path: '/tags', name: '标签管理', icon: markRaw(Collection) },
];

const projectMenuItems = [
  { path: '/sprints', name: '迭代管理', icon: markRaw(Timer) },
  { path: '/quality', name: '质量报告', icon: markRaw(TrendCharts) },
  { path: '/bugs', name: 'Bug 管理', icon: markRaw(Warning) },
  { path: '/bugs/my', name: '我的 Bug', icon: markRaw(Warning) },
  { path: '/api-docs', name: 'API 文档', icon: markRaw(Document) },
  { path: '/stats', name: '统计报表', icon: markRaw(DataLine) },
];

const toolMenuItems = [
  { path: '/chat', name: '项目聊天', icon: markRaw(ChatLineRound) },
  { path: '/ai-chat', name: 'AI助手', icon: markRaw(ChatDotRound) },
  { path: '/notifications', name: '消息', icon: markRaw(Bell) },
  { path: '/settings', name: '设置', icon: markRaw(Setting) },
];

// 系统管理菜单
const systemMenuItems = [
  { path: '/system/menu', name: '菜单管理', icon: markRaw(Menu) },
  { path: '/system/role', name: '角色管理', icon: markRaw(UserFilled) },
  { path: '/system/user', name: '用户管理', icon: markRaw(User) },
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

/* ── Sidebar ── */
.sidebar {
  width: 232px;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border-light);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: 50;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--color-border-light);
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 0 4px;
}

.brand-text {
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: 16px;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.project-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}

.project-badge {
  width: 24px;
  height: 24px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.project-name {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Menu ── */
.menu {
  flex: 1;
  padding: 12px 8px;
  overflow-y: auto;
}

.menu-section {
  margin-bottom: 16px;
}

.section-title {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  padding: 6px 12px;
  margin-bottom: 2px;
}

.menu-directory {
  margin-bottom: 2px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  margin: 1px 0;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: background var(--transition-fast), color var(--transition-fast);
  cursor: pointer;
  position: relative;
  font-size: 13px;
  line-height: 1.4;
}

.menu-item:hover {
  background: var(--color-surface-hover);
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
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--color-primary);
  border-radius: 2px;
}

.menu-item.directory {
  margin-bottom: 0;
}

.expand-icon {
  margin-left: auto;
  color: var(--color-text-tertiary);
  transition: transform var(--transition-fast);
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.submenu {
  padding-left: 16px;
  margin-top: 2px;
}

.submenu-item {
  padding: 6px 12px;
  font-size: 12px;
  margin: 1px 0;
}

.submenu-item::before {
  display: none;
}

.item-icon {
  flex-shrink: 0;
  color: inherit;
}

.item-text {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Sidebar footer ── */
.sidebar-footer {
  padding: 12px 8px;
  border-top: 1px solid var(--color-border-light);
}

.back-button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 8px;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 13px;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.back-button:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.user-mini {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-top: 1px solid var(--color-border-light);
  padding-top: 12px;
  margin-top: 4px;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Main content ── */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg);
}

.top-bar {
  height: 52px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
}

.crumb-project {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.breadcrumb-separator {
  color: var(--color-text-tertiary);
}

.crumb-page {
  font-size: 14px;
  color: var(--color-text-secondary);
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--color-text-secondary);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-tertiary);
}

.status-badge.online .status-dot {
  background: var(--color-success);
}

.page-container {
  flex: 1;
  overflow: auto;
  padding: 24px 32px;
}
</style>
