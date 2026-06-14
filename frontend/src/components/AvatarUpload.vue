<template>
  <div class="avatar-uploader">
    <el-upload
      class="avatar-uploader-component"
      action="/api/users/avatar/"
      :show-file-list="false"
      :on-success="handleSuccess"
      :on-error="handleError"
      :before-upload="beforeUpload"
      :headers="uploadHeaders"
      name="avatar"
      accept="image/jpeg,image/png"
    >
      <img v-if="avatarUrl" :src="avatarUrl" class="avatar" />
      <el-icon v-else class="avatar-uploader-icon"><Plus /></el-icon>
    </el-upload>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';

const props = defineProps<{
  user: {
    id: number;
    username: string;
    profile?: {
      avatar?: string;
    };
  };
}>();

const emit = defineEmits<{
  'avatar-updated': [avatarUrl: string];
}>();

const avatarUrl = computed(() => {
  return props.user.profile?.avatar || '';
});

// 获取 CSRF Token
const getCookie = (name: string): string | null => {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(';').shift() || null;
  return null;
};

const uploadHeaders = computed(() => {
  const csrfToken = getCookie('csrftoken');
  return {
    'X-CSRFToken': csrfToken || '',
  };
});

const beforeUpload = (file: File) => {
  const isJPG = file.type === 'image/jpeg';
  const isPNG = file.type === 'image/png';
  const isLt2M = file.size / 1024 / 1024 < 2;

  if (!isJPG && !isPNG) {
    ElMessage.error('只支持 JPG/PNG 格式!');
    return false;
  }
  if (!isLt2M) {
    ElMessage.error('图片大小不能超过 2MB!');
    return false;
  }
  return true;
};

const handleSuccess = (response: any) => {
  if (response.success && response.data?.avatar_url) {
    ElMessage.success('头像上传成功');
    emit('avatar-updated', response.data.avatar_url);
  } else {
    ElMessage.error(response.error || '上传失败');
  }
};

const handleError = (error: any) => {
  console.error('上传错误:', error);
  const errorMsg = error?.message || '上传失败，请检查网络连接';
  ElMessage.error(errorMsg);
};
</script>

<style scoped>
.avatar-uploader {
  display: inline-block;
}

.avatar-uploader-component {
  border: 1px dashed var(--el-border-color);
  border-radius: 50%;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: var(--el-transition-duration-fast);
  width: 80px;
  height: 80px;
}

.avatar-uploader-component:hover {
  border-color: var(--el-color-primary);
}

.avatar-uploader-icon {
  font-size: 28px;
  color: var(--color-text-tertiary);
  width: 80px;
  height: 80px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar {
  width: 80px;
  height: 80px;
  display: block;
  object-fit: cover;
}
</style>
