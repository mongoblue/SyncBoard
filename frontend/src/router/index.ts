import { createRouter, createWebHistory } from 'vue-router'
// 引入 Auth Store，用于检查用户是否登录
import { useAuthStore } from '@/stores/Auth' 

const routes = [
    {
        path: '/',
        redirect: '/projects' // 根路径现在去项目列表
    },
    {
        path: '/projects',
        name: 'Projects',
        component: () => import("../views/Projects.vue"),
        meta: { requiresAuth: true }
    },
    {
        // ✨ 动态路由：:projectId
        path: '/projects/:projectId/board',
        name: 'Board',
        component: () => import("../views/Board.vue"),
        meta: { requiresAuth: true }
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

// 🛡️ 全局前置守卫：我是保安，没证件（Token/User）不让进
router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore();

    // 1. 尝试恢复登录状态 (应对 F5 刷新页面)
    // 如果 store 里没用户，但浏览器可能存了 cookie/session，尝试调 API 恢复
    if (!authStore.user && to.path !== '/login') {
        await authStore.checkAuth();
    }

    // 2. 鉴权逻辑
    if (to.meta.requiresAuth && !authStore.user) {
        // A. 如果要去的地方需要登录，且当前没登录 -> 踢回登录页
        next('/login');
    } else if (to.path === '/login' && authStore.user) {
        // B. 如果已经登录了，还想去登录页 -> 赶回首页
        next('/');
    } else {
        // C. 放行
        next();
    }
})

export default router