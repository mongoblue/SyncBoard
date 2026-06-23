<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <aside class="brand-panel">
      <div class="brand-content">
        <div class="brand-mark">
          <el-icon :size="28" color="var(--color-primary)"><Collection /></el-icon>
          <span class="brand-name">FlowSpace</span>
        </div>
        <h1 class="brand-headline">高效团队协作平台</h1>
        <p class="brand-tagline">看板、迭代、测试与质量报告 · 一站式打通研发全流程。</p>
        <ul class="brand-features">
          <li>实时看板与任务协作</li>
          <li>迭代规划与质量报告</li>
          <li>API / UI / 性能测试一体化</li>
        </ul>
      </div>
      <div class="brand-footer">© {{ currentYear }} FlowSpace</div>
    </aside>

    <!-- 右侧登录卡 -->
    <main class="form-panel">
      <div class="login-card">
        <h2 class="login-title">登录</h2>
        <p class="login-subtitle">输入账号继续访问工作区</p>

        <el-form :model="form" class="login-form" @submit.prevent="handleLogin">
          <div class="form-field">
            <label class="form-label">用户名</label>
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              :prefix-icon="User"
              size="large"
            />
          </div>
          <div class="form-field">
            <label class="form-label">密码</label>
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              :prefix-icon="Lock"
              size="large"
              show-password
              @keyup.enter="handleLogin"
            />
          </div>

          <el-button
            type="primary"
            class="login-btn"
            size="large"
            :loading="loading"
            @click="handleLogin"
          >
            {{ loading ? '登录中...' : '登录' }}
          </el-button>
        </el-form>

        <p class="login-hint">默认管理员：admin / 你的密码</p>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/Auth';
import { ElMessage } from 'element-plus';
import { Collection, User, Lock } from '@element-plus/icons-vue';

const router = useRouter();
const authStore = useAuthStore();

const loading = ref(false);
const form = ref({
  username: '',
  password: ''
});

const currentYear = computed(() => new Date().getFullYear());

const handleLogin = async () => {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名和密码');
    return;
  }

  loading.value = true;
  const success = await authStore.login(form.value);
  loading.value = false;

  if (success) {
    ElMessage.success('欢迎回来！');
    router.push('/');
  } else {
    ElMessage.error('登录失败，请检查账号密码');
  }
};
</script>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  background: var(--color-bg);
}

/* ── Brand panel ── */
.brand-panel {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 48px;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border-light);
}

.brand-content {
  max-width: 440px;
  margin-top: 80px;
}

.brand-mark {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 64px;
}

.brand-name {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.brand-headline {
  font-family: var(--font-heading);
  font-size: 32px;
  font-weight: 600;
  line-height: 1.25;
  color: var(--color-text);
  margin: 0 0 16px;
  letter-spacing: -0.02em;
}

.brand-tagline {
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin: 0 0 28px;
}

.brand-features {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.brand-features li {
  position: relative;
  padding-left: 18px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.brand-features li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 9px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary);
}

.brand-footer {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

/* ── Form panel ── */
.form-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 36px 32px;
}

.login-title {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0 0 6px;
  letter-spacing: -0.01em;
}

.login-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0 0 24px;
}

.login-form {
  display: flex;
  flex-direction: column;
}

.login-btn {
  width: 100%;
  height: 40px;
  margin-top: 8px;
}

.login-hint {
  margin: 20px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
  text-align: center;
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .brand-panel {
    display: none;
  }
}
</style>
