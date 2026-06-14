<template>
  <div class="login-container">
    <!-- 背景装饰 -->
    <div class="bg-orb orb-1"></div>
    <div class="bg-orb orb-2"></div>
    <div class="bg-grid"></div>

    <div class="login-box">
      <div class="logo-section">
        <div class="logo-icon">
          <el-icon :size="32"><Collection /></el-icon>
        </div>
        <h2>FlowSpace</h2>
        <p class="subtitle">高效团队协作平台</p>
      </div>

      <el-form :model="form" class="login-form">
        <el-form-item>
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            size="large"
            class="login-input"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            size="large"
            class="login-input"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-button
          type="primary"
          class="login-btn"
          size="large"
          :loading="loading"
          @click="handleLogin"
        >
          <span v-if="!loading">登 录</span>
          <span v-else>登录中...</span>
        </el-button>
      </el-form>

      <div class="tips">
        <span>默认管理员: admin / 你的密码</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
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
/* ── 背景 ── */
.login-container {
  height: 100vh;
  height: 100dvh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(160deg, #0D9488 0%, #14B8A6 40%, #2DD4BF 70%, #5EEAD4 100%);
  position: fixed;
  inset: 0;
  overflow: hidden;
}

/* 装饰光晕 */
.bg-orb {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
}

.orb-1 {
  width: 560px;
  height: 560px;
  background: radial-gradient(circle, rgba(255,255,255,0.12) 0%, transparent 70%);
  top: -180px;
  right: -120px;
}

.orb-2 {
  width: 360px;
  height: 360px;
  background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
  bottom: -80px;
  left: -60px;
}

/* 网格纹理 */
.bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
}

/* ── 登录卡片 ── */
.login-box {
  width: 420px;
  padding: 52px 44px 40px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 20px;
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.06),
    0 20px 60px rgba(0, 0, 0, 0.08),
    0 0 0 1px rgba(255, 255, 255, 0.5) inset;
  text-align: center;
  position: relative;
  z-index: 10;
  backdrop-filter: blur(10px);
}

/* ── Logo ── */
.logo-section {
  margin-bottom: 36px;
}

.logo-icon {
  width: 68px;
  height: 68px;
  background: linear-gradient(135deg, #0F766E 0%, #14B8A6 100%);
  color: white;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
  box-shadow: 0 8px 24px rgba(15, 118, 110, 0.25);
}

h2 {
  margin: 0 0 6px 0;
  font-family: var(--font-heading);
  font-size: 30px;
  font-weight: 700;
  color: #0F172A;
  letter-spacing: -0.3px;
}

.subtitle {
  color: #64748B;
  font-size: 14px;
  margin: 0;
  font-weight: 400;
}

/* ── 表单 ── */
.login-form {
  margin-top: 32px;
  text-align: left;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.login-input :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 4px 14px;
  box-shadow: none;
  border: 1px solid #E2E8F0;
  background: #F8FAFC;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

.login-input :deep(.el-input__wrapper:hover) {
  border-color: #14B8A6;
  background: #FFFFFF;
}

.login-input :deep(.el-input__wrapper.is-focus) {
  border-color: #14B8A6;
  background: #FFFFFF;
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.12);
}

.login-input :deep(.el-input__prefix) {
  color: #94A3B8;
}

.login-input :deep(.el-input__wrapper.is-focus .el-input__prefix) {
  color: #14B8A6;
}

/* ── 登录按钮 ── */
.login-btn {
  width: 100%;
  height: 48px;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, #0F766E 0%, #14B8A6 100%);
  border: none;
  box-shadow: 0 4px 14px rgba(15, 118, 110, 0.3);
  transition: transform 0.2s, box-shadow 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 6px;
  letter-spacing: 4px;
}

.login-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(15, 118, 110, 0.4);
  background: linear-gradient(135deg, #0F766E 0%, #14B8A6 100%);
}

.login-btn:active {
  transform: translateY(0);
}

/* ── 提示 ── */
.tips {
  margin-top: 28px;
  font-size: 12px;
  color: #94A3B8;
}
</style>