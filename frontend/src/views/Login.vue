<template>
  <div class="login-container">
    <div class="login-box">
      <h2>SyncBoard</h2>
      <p class="subtitle">高效团队协作平台</p>
      
      <el-form :model="form" class="login-form">
        <el-form-item>
          <el-input 
            v-model="form.username" 
            placeholder="用户名" 
            prefix-icon="User"
            size="large"
          />
        </el-form-item>
        <el-form-item>
          <el-input 
            v-model="form.password" 
            type="password" 
            placeholder="密码" 
            prefix-icon="Lock"
            size="large"
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
          立即登录
        </el-button>
      </el-form>
      
      <div class="tips">
        <p>默认管理员: admin / 你的密码</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/Auth'; 
import { ElMessage } from 'element-plus';

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
    router.push('/'); // 登录成功跳转到首页(看板)
  } else {
    ElMessage.error('登录失败，请检查账号密码');
  }
};
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-box {
  width: 400px;
  padding: 40px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.1);
  text-align: center;
}

h2 {
  margin-bottom: 10px;
  color: #333;
}

.subtitle {
  color: #666;
  margin-bottom: 30px;
}

.login-btn {
  width: 100%;
}

.tips {
  margin-top: 20px;
  font-size: 12px;
  color: #999;
}
</style>