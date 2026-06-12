import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/Auth'

const routes = [
    {
        path: '/',
        redirect: '/projects'
    },
    {
        path: '/projects',
        name: 'Projects',
        component: () => import("../views/Projects.vue"),
        meta: { requiresAuth: true }
    },
    {
        path: '/projects/:projectId',
        component: () => import("../views/ProjectLayout.vue"),
        meta: { requiresAuth: true },
        redirect: (to: any) => `/projects/${to.params.projectId}/board`,
        children: [
            {
                path: 'board',
                name: 'Board',
                component: () => import("../views/Board.vue"),
                meta: { permission: 'board:list' },
            },
            {
                path: 'members',
                name: 'Members',
                component: () => import("../views/Members.vue"),
                meta: { permission: 'member:list' },
            },
            {
                path: 'tags',
                name: 'Tags',
                component: () => import("../views/Tags.vue"),
                meta: { permission: 'tag:list' },
            },
            {
                path: 'stats',
                name: 'Stats',
                component: () => import("../views/Stats.vue"),
                meta: { permission: 'stats:list' },
            },
            {
                path: 'chat',
                name: 'Chat',
                component: () => import("../views/Chat.vue"),
                meta: { permission: 'chat:list' },
            },
            {
                path: 'ai-chat',
                name: 'AIChat',
                component: () => import("../views/AIChat.vue"),
                meta: { permission: 'ai:chat' },
            },
            {
                path: 'qa',
                name: 'QA',
                component: () => import("../views/QA.vue"),
                meta: { permission: 'qa:manage' },
            },
            {
                path: 'qa/api-cases',
                name: 'ApiCaseList',
                component: () => import("../views/qa/ApiCaseList.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/api-cases/create',
                name: 'ApiCaseCreate',
                component: () => import("../views/qa/ApiCaseDetail.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/api-cases/:id',
                name: 'ApiCaseDetail',
                component: () => import("../views/qa/ApiCaseDetail.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/ui-cases',
                name: 'UiCaseList',
                component: () => import("../views/qa/UiCaseList.vue"),
                meta: { permission: 'qa:ui:list' },
            },
            {
                path: 'qa/ui-cases/create',
                name: 'UiCaseCreate',
                component: () => import("../views/qa/UiCaseDetail.vue"),
                meta: { permission: 'qa:ui:list' },
            },
            {
                path: 'qa/ui-cases/:id',
                name: 'UiCaseDetail',
                component: () => import("../views/qa/UiCaseDetail.vue"),
                meta: { permission: 'qa:ui:list' },
            },
            {
                path: 'qa/test-results',
                name: 'TestResultList',
                component: () => import("../views/qa/TestResultList.vue"),
                meta: { permission: 'qa:result:list' },
            },
            {
                path: 'qa/test-runs',
                name: 'TestRunList',
                component: () => import("../views/qa/TestRunList.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/test-runs/:id',
                name: 'TestRunDetail',
                component: () => import("../views/qa/TestRunDetail.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/test-runs/:runId/cases/:caseResultId',
                name: 'ApiCaseRunDetail',
                component: () => import("../views/qa/ApiCaseRunDetail.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/test-results/:id',
                name: 'TestResultDetail',
                component: () => import("../views/qa/TestResultDetail.vue"),
                meta: { permission: 'qa:result:list' },
            },
            {
                path: 'qa/auto-results/:id',
                name: 'AutoResultDetail',
                component: () => import("../views/qa/AutoResultDetail.vue"),
                meta: { permission: 'qa:result:list' },
            },
            {
                path: 'qa/devops',
                name: 'DevOpsPlatform',
                component: () => import("../views/qa/DevOpsPlatform.vue"),
                meta: { permission: 'qa:devops:list' },
            },
            {
                path: 'qa/devops/tasks/:id',
                name: 'TestTaskDetail',
                component: () => import("../views/qa/TestTaskDetail.vue"),
                meta: { permission: 'qa:devops:list' },
            },
            {
                path: 'qa/performance',
                name: 'PerformanceTestList',
                component: () => import("../views/qa/PerformanceTestResult.vue"),
                meta: { permission: 'qa:performance:list' },
            },
            {
                path: 'qa/performance-results',
                name: 'PerformanceTestResults',
                component: () => import("../views/qa/PerformanceTestResult.vue"),
                meta: { permission: 'qa:performance:list' },
            },
            {
                path: 'bugs',
                name: 'BugList',
                component: () => import("../views/bug/BugList.vue"),
                meta: { permission: 'qa:manage' },
            },
            {
                path: 'bugs/my',
                name: 'MyBugs',
                component: () => import("../views/bug/MyBugs.vue"),
                meta: { permission: 'qa:manage' },
            },
            {
                path: 'bugs/:id',
                name: 'BugDetail',
                component: () => import("../views/bug/BugDetail.vue"),
                meta: { permission: 'qa:manage' },
            },
            {
                path: 'notifications',
                name: 'Notifications',
                component: () => import("../views/Notifications.vue"),
                meta: { permission: 'notification:list' },
            },
            {
                path: 'settings',
                name: 'Settings',
                component: () => import("../views/Settings.vue"),
                meta: { permission: 'settings:list' },
            },
            {
                path: 'sprints',
                name: 'Sprints',
                component: () => import("../views/ProjectSprints.vue"),
                meta: { permission: 'stats:list' },
            },
            {
                path: 'sprints/:sprintId',
                name: 'SprintBoard',
                component: () => import("../views/SprintBoard.vue"),
                meta: { permission: 'stats:list' },
            },
            {
                path: 'quality',
                name: 'QualityReport',
                component: () => import("../views/ProjectQualityReport.vue"),
                meta: { permission: 'qa:manage' },
            },
            {
                path: 'api-docs',
                name: 'ApiDocs',
                component: () => import("../views/ProjectApiDocs.vue"),
                meta: { permission: 'qa:manage' },
            },
            {
                path: 'system/menu',
                name: 'MenuManagement',
                component: () => import("../views/system/MenuManagement.vue"),
                meta: { permission: 'sys:menu:list' },
            },
            {
                path: 'system/role',
                name: 'RoleManagement',
                component: () => import("../views/system/RoleManagement.vue"),
                meta: { permission: 'sys:role:list' },
            },
            {
                path: 'system/user',
                name: 'UserManagement',
                component: () => import("../views/system/UserManagement.vue"),
                meta: { permission: 'sys:user:list' },
            },
        ]
    },
    {
        path: '/login',
        name: 'Login',
        meta: { title: '登录', hideUI: true },
        component: () => import("../views/Login.vue")
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore();

    // 1. 检查登录状态
    if (!authStore.user && to.path !== '/login') {
        await authStore.checkAuth();
    }

    // 2. 未登录 → 登录页
    if (to.meta.requiresAuth && !authStore.user) {
        next('/login');
        return;
    }

    // 3. 已登录访问登录页 → 项目列表
    if (to.path === '/login' && authStore.user) {
        next('/');
        return;
    }

    // 4. 权限检查: 路由有 meta.permission 但用户无此权限
    if (to.meta.permission && authStore.user) {
        const perm = to.meta.permission as string;
        if (!authStore.checkPermission(perm)) {
            // 重定向到当前项目的看板页
            const projectId = to.params.projectId;
            if (projectId) {
                next(`/projects/${projectId}/board`);
            } else {
                next('/projects');
            }
            console.warn(`[Router] 权限不足: 需要 "${perm}"，已重定向`);
            return;
        }
    }

    next();
})

export default router
