<template>
  <div class="chat-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">项目聊天</h1>
        <p class="page-subtitle">项目成员实时沟通频道</p>
      </div>
      <div class="connection-status">
        <span class="status-dot" :class="{ online: isConnected }"></span>
        <span>{{ isConnected ? '已连接' : '连接中...' }}</span>
      </div>
    </header>

    <div class="chat-container">
      <div class="messages" ref="msgListRef">
        <div v-if="messages.length === 0" class="empty-tip">
          <el-icon :size="48"><ChatDotRound /></el-icon>
          <p>暂无消息，开始聊天吧！</p>
        </div>

        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="message-item"
          :class="{ 'my-msg': msg.user === currentUser }"
        >
          <div class="msg-avatar" v-if="msg.user !== currentUser">
            <div class="avatar-circle">
              {{ msg.user?.substring(0, 2).toUpperCase() }}
            </div>
          </div>
          <div class="msg-content">
            <div class="msg-user" v-if="msg.user !== currentUser">{{ msg.user }}</div>
            <div class="msg-bubble">
              {{ msg.content }}
              <span class="msg-time">{{ msg.time }}</span>
            </div>
          </div>
          <div class="msg-avatar" v-if="msg.user === currentUser">
            <div class="avatar-circle me">
              {{ msg.user?.substring(0, 2).toUpperCase() }}
            </div>
          </div>
        </div>
      </div>

      <div class="input-area">
        <el-input
          v-model="inputMsg"
          type="textarea"
          :rows="3"
          placeholder="输入消息..."
          @keyup.enter.prevent="sendMessage"
          :disabled="!isConnected"
        />
        <el-button
          type="primary"
          :disabled="!inputMsg.trim() || !isConnected"
          @click="sendMessage"
        >
          <el-icon><Promotion /></el-icon>
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/Auth';
import { ChatDotRound, Promotion } from '@element-plus/icons-vue';

const route = useRoute();
const authStore = useAuthStore();

const projectId = computed(() => route.params.projectId as string);
const currentUser = computed(() => authStore.user?.username || 'Unknown');

const inputMsg = ref('');
const messages = ref<any[]>([]);
const isConnected = ref(false);
const msgListRef = ref<HTMLElement | null>(null);

let socket: WebSocket | null = null;

// 连接聊天
const connectChat = () => {
  if (!projectId.value) return;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const hostname = window.location.hostname;
  const port = '8000';

  socket = new WebSocket(`${protocol}//${hostname}:${port}/ws/chat/${projectId.value}/`);

  socket.onopen = () => {
    isConnected.value = true;
  };

  socket.onmessage = (event) => {
    try {
      const res = JSON.parse(event.data);
      if (res.type === 'history') {
        messages.value = res.data;
      } else if (res.type === 'message') {
        messages.value.push(res.data);
      }
      scrollToBottom();
    } catch (e) {}
  };

  socket.onclose = () => {
    isConnected.value = false;
  };

  socket.onerror = () => {
    isConnected.value = false;
  };
};

const sendMessage = () => {
  if (!inputMsg.value.trim() || !socket) return;
  socket.send(
    JSON.stringify({
      message: inputMsg.value,
      time: new Date().toLocaleTimeString(),
    })
  );
  inputMsg.value = '';
};

const scrollToBottom = () => {
  nextTick(() => {
    if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight;
  });
};

// 监听项目ID变化
watch(
  () => projectId.value,
  (newId) => {
    if (newId) {
      if (socket) {
        socket.close();
        socket = null;
      }
      messages.value = [];
      connectChat();
    }
  },
  { immediate: true }
);

onUnmounted(() => {
  if (socket) socket.close();
});
</script>

<style scoped>
.chat-page {
  padding: 0;
  height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-danger);
  transition: background var(--transition-fast);
}

.status-dot.online { background: var(--color-success); }

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  background: var(--color-surface-sunken);
}

.empty-tip {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  gap: 12px;
}

.message-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.message-item.my-msg { flex-direction: row-reverse; }

.msg-avatar { flex-shrink: 0; }

.avatar-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-heading);
}

.avatar-circle.me {
  background: var(--color-primary);
  color: var(--color-text-inverse);
}

.msg-content { max-width: 70%; }

.msg-user {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
  padding-left: 4px;
}

.msg-bubble {
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
  padding: 10px 14px;
  border-radius: 12px;
  word-wrap: break-word;
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-text);
}

.my-msg .msg-bubble {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-border);
  color: var(--color-text);
}

.msg-time {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-left: 8px;
}

.input-area {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-surface);
}

.input-area .el-textarea { flex: 1; }
</style>
