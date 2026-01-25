<template>
  <div class="chat-fab" @click="drawer = true">
    <el-badge :value="unreadCount" :hidden="unreadCount === 0 || drawer" class="chat-badge">
      <el-icon :size="20" color="white"><ChatDotRound /></el-icon>
    </el-badge>
  </div>

  <el-drawer 
    v-model="drawer" 
    title="项目讨论组" 
    :size="350"
    direction="rtl"
  >
    <div class="chat-container">
      <div class="messages" ref="msgListRef">
        <div v-if="!isConnected" class="status-tip">
          🔴 正在连接聊天室...
        </div>

        <div 
          v-for="(msg, index) in messages" 
          :key="index" 
          class="message-item"
          :class="{ 'my-msg': msg.user === currentUser }"
        >
          <div class="msg-user" v-if="msg.user !== currentUser">{{ msg.user }}</div>
          <div class="msg-bubble">
            {{ msg.content }}
            <span class="msg-time">{{ msg.time }}</span>
          </div>
        </div>
      </div>

      <div class="input-area">
        <el-input 
          v-model="inputMsg" 
          placeholder="说点什么..." 
          @keyup.enter="sendMessage"
          :disabled="!isConnected" 
        >
          <template #append>
            <el-button @click="sendMessage" :disabled="!isConnected">发送</el-button>
          </template>
        </el-input>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue';
import { useAuthStore } from '@/stores/Auth';
import { useBoardStore } from '@/stores/Board';
import { ChatDotRound } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';

const authStore = useAuthStore();
const boardStore = useBoardStore();

const drawer = ref(false);
const inputMsg = ref('');
const messages = ref<any[]>([]);
const unreadCount = ref(0);
const msgListRef = ref<HTMLElement | null>(null);
const isConnected = ref(false);

let socket: WebSocket | null = null;

const currentUser = computed(() => authStore.user?.username || 'Unknown');

const connectChat = () => {
  const projectId = boardStore.currentProjectId;
  if (!projectId) return;

  if (socket && socket.readyState === WebSocket.OPEN) return;
  if (socket) socket.close();

  console.log(`🚀 连接聊天室: 项目 [${projectId}]`);

  // ✨ 核心修复：自动获取当前浏览器的域名 (localhost 或 IP)
  // 这样 Cookie 才能发过去，后端才能认出你是谁
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname; 
  // 假设后端固定在 8000 端口。如果你在生产环境用了 Nginx 转发，这里可能不需要 :8000
  const port = '8000'; 
  
  socket = new WebSocket(`${protocol}//${host}:${port}/ws/chat/${projectId}/`);

  socket.onopen = () => {
    console.log('✅ 聊天室连接成功');
    isConnected.value = true;
  };

  // ✅ 修正 4: 正确解析后端返回的数据结构
  socket.onmessage = (event) => {
    try {
      const res = JSON.parse(event.data);
      
      // 后端发来的是历史记录列表 { type: 'history', data: [...] }
      if (res.type === 'history') {
        messages.value = res.data; 
      } 
      // 后端发来的是单条新消息 { type: 'message', data: {...} }
      else if (res.type === 'message') {
        messages.value.push(res.data);
        if (!drawer.value) {
          unreadCount.value++;
        }
      }
      
      scrollToBottom();
    } catch (e) {
      console.error("消息解析错误", e);
    }
  };
  
  socket.onclose = () => {
    console.log('🔴 聊天室断开');
    isConnected.value = false;
  };
};

const sendMessage = () => {
  if (!inputMsg.value.trim()) return;
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    ElMessage.error('聊天室未连接');
    return;
  }

  // ✅ 修正 5: 发送时保持字段名为 'message' (后端 receive 里取的是 message)
  // 但发送时间由后端生成，前端不用传
  socket.send(JSON.stringify({
    message: inputMsg.value,
    time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: "2-digit", minute: "2-digit" }) 
  }));
  
  inputMsg.value = ''; 
};

const scrollToBottom = () => {
  nextTick(() => {
    if (msgListRef.value) {
      msgListRef.value.scrollTop = msgListRef.value.scrollHeight;
    }
  });
};

watch(() => boardStore.currentProjectId, (newId) => {
  if (newId) {
    messages.value = [];
    connectChat();
  }
});

watch(drawer, (newVal) => {
  if (newVal) {
    unreadCount.value = 0;
    scrollToBottom();
  }
});

onUnmounted(() => {
  if (socket) socket.close();
});
</script>

<style scoped>
.chat-fab {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 50px;
  height: 50px;
  background: #409eff;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(0,0,0,0.2);
  z-index: 999;
  transition: transform 0.2s;
}
.chat-fab:hover { transform: scale(1.1); }
.chat-container { display: flex; flex-direction: column; height: 100%; }
.messages { flex: 1; overflow-y: auto; padding: 10px; background: #f5f7fa; margin-bottom: 10px; border-radius: 4px;}
.status-tip { text-align: center; font-size: 12px; color: #909399; margin-bottom: 10px;}
.message-item { margin-bottom: 15px; display: flex; flex-direction: column; align-items: flex-start; }
.msg-user { font-size: 12px; color: #999; margin-left: 4px; margin-bottom: 2px;}
.msg-bubble { background: white; padding: 8px 12px; border-radius: 8px; border-top-left-radius: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); max-width: 85%; word-break: break-all;}
.msg-time { font-size: 10px; color: #ccc; margin-left: 5px; }

.my-msg { align-items: flex-end; }
.my-msg .msg-bubble { background: #95d475; border-radius: 8px; border-top-right-radius: 2px; }
.my-msg .msg-user { display: none; }
</style>