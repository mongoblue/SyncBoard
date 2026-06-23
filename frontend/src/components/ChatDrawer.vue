<template>
  <div class="chat-fab" @click="drawer = true">
    <el-badge :value="totalUnread" :hidden="totalUnread === 0 || drawer" class="chat-badge">
      <el-icon :size="20" color="white"><ChatDotRound /></el-icon>
    </el-badge>
  </div>

  <el-drawer 
    v-model="drawer" 
    :title="currentChatProject ? currentChatProject.name : '消息列表'" 
    :size="350"
    direction="rtl"
  >
    <div v-if="!currentChatProject" class="chat-list-container">
      <div v-if="projectList.length === 0" class="empty-tip">暂无参与的项目</div>
      
      <div 
        v-for="proj in projectList" 
        :key="proj.id" 
        class="chat-list-item"
        @click="enterChat(proj)"
      >
        <div class="proj-avatar">{{ proj.name.substring(0,2).toUpperCase() }}</div>
        <div class="proj-info">
          <div class="proj-name">{{ proj.name }}</div>
          <div class="proj-preview">点击进入聊天...</div>
        </div>
        <el-icon><ArrowRight /></el-icon>
      </div>
    </div>

    <div v-else class="chat-container">
      <div class="chat-header-bar">
        <el-button link @click="leaveChat">
           &lt; 返回列表
        </el-button>
        <span class="status-dot" :class="{ online: isConnected }"></span>
      </div>

      <div class="messages" ref="msgListRef">
        <div v-if="!isConnected" class="status-tip">🔴 连接中...</div>
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
          placeholder="发送消息..." 
          @keyup.enter="sendMessage"
          :disabled="!isConnected"
        >
          <template #append>
            <el-button @click="sendMessage">发送</el-button>
          </template>
        </el-input>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onUnmounted } from 'vue';
import { useAuthStore } from '@/stores/Auth';
import { useBoardStore } from '@/stores/board';
import { ChatDotRound, ArrowRight } from '@element-plus/icons-vue';
import service from '@/utils/request';

const authStore = useAuthStore();
const boardStore = useBoardStore();

const drawer = ref(false);
const inputMsg = ref('');
const messages = ref<any[]>([]);
const isConnected = ref(false);
const msgListRef = ref<HTMLElement | null>(null);

// 项目列表 (用于项目外显示)
const projectList = ref<any[]>([]);
// 当前正在聊天的项目 (如果为 null，显示列表)
const currentChatProject = ref<any>(null);

let socket: WebSocket | null = null;
const currentUser = computed(() => authStore.user?.username || 'Unknown');
const totalUnread = ref(0); // 简化处理，暂时只做总数

// 1. 获取用户参与的项目列表
const fetchMyProjects = async () => {
  try {
    const res = await service.get('/projects/');
    const projectArray = Array.isArray(res) ? res : [];
    projectList.value = projectArray;
  } catch (e) {
    console.error(e);
  }
};

// 2. 进入某个项目的聊天
const enterChat = (project: any) => {
  currentChatProject.value = project;
  messages.value = []; // 先清空，等待 Socket 传回历史记录
  connectChat(project.id);
};

// 3. 返回列表
const leaveChat = () => {
  if (socket) {
    socket.close();
    socket = null;
  }
  currentChatProject.value = null;
  isConnected.value = false;
};

// 4. 连接 Socket
const connectChat = (projectId: string) => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;

  socket = new WebSocket(`${protocol}//${host}/ws/chat/${projectId}/`);

  socket.onopen = () => { isConnected.value = true; };
  
  socket.onmessage = (event) => {
    try {
      const res = JSON.parse(event.data);
      if (res.type === 'history') {
        messages.value = res.data;
      } else if (res.type === 'message') {
        messages.value.push(res.data);
      }
      scrollToBottom();
    } catch(e) {}
  };

  socket.onclose = () => { isConnected.value = false; };
};

const sendMessage = () => {
  if (!inputMsg.value.trim() || !socket) return;
  socket.send(JSON.stringify({ 
      message: inputMsg.value, 
      // 这里的 time 只是发给后端参考，后端会重写时间
      time: new Date().toLocaleTimeString() 
  }));
  inputMsg.value = '';
};

const scrollToBottom = () => {
  nextTick(() => {
    if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight;
  });
};

// ✨ 监听 BoardStore 的变化：如果用户进入了看板页面，自动进入对应聊天
watch(() => boardStore.currentProjectId, async (newId) => {
  if (newId) {
    // 确保有项目列表数据
    if (projectList.value.length === 0) await fetchMyProjects();
    
    const target = projectList.value.find(p => p.id == newId || p.id == Number(newId));
    if (target) {
      enterChat(target);
    }
  } else {
    // 退出看板时，不强制退出聊天，而是允许用户手动点“返回”
    // 或者你可以选择这里自动 leaveChat()，看你喜好
    // leaveChat(); 
  }
});

onMounted(() => {
  fetchMyProjects();
});

onUnmounted(() => {
  if (socket) socket.close();
});
</script>

<style scoped>
.chat-fab { position: fixed; bottom: 24px; right: 24px; width: 48px; height: 48px; background: var(--color-primary); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; z-index: 2000; box-shadow: var(--shadow-md); transition: background var(--transition-fast); }
.chat-fab:hover { background: var(--color-primary-hover); }
.chat-list-container { padding: 8px; }
.chat-list-item { display: flex; align-items: center; padding: 10px; border-bottom: 1px solid var(--color-border-light); cursor: pointer; transition: background var(--transition-fast); border-radius: var(--radius-md); }
.chat-list-item:hover { background: var(--color-surface-hover); }
.proj-avatar { width: 36px; height: 36px; background: var(--color-primary-bg); color: var(--color-primary); border-radius: var(--radius-md); display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 12px; margin-right: 10px; font-family: var(--font-heading); }
.proj-info { flex: 1; }
.proj-name { font-size: 14px; font-weight: 600; color: var(--color-text); }
.proj-preview { font-size: 12px; color: var(--color-text-tertiary); margin-top: 2px; }
.empty-tip { padding: 24px; text-align: center; color: var(--color-text-tertiary); font-size: 13px; }
.chat-container { display: flex; flex-direction: column; height: 100%; }
.chat-header-bar { padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--color-border-light); }
.messages { flex: 1; overflow-y: auto; padding: 12px; background: var(--color-surface-sunken); }
.status-tip { text-align: center; color: var(--color-text-tertiary); font-size: 12px; padding: 8px 0; }
.message-item { margin-bottom: 12px; display: flex; flex-direction: column; align-items: flex-start; }
.my-msg { align-items: flex-end; }
.msg-bubble { background: var(--color-surface); border: 1px solid var(--color-border-light); padding: 8px 12px; border-radius: 12px; max-width: 85%; word-wrap: break-word; font-size: 13px; color: var(--color-text); line-height: 1.5; }
.my-msg .msg-bubble { background: var(--color-primary-bg); border-color: var(--color-primary-border); }
.msg-user { font-size: 12px; color: var(--color-text-tertiary); margin-bottom: 2px; padding-left: 4px; }
.msg-time { font-size: 11px; color: var(--color-text-tertiary); margin-left: 6px; }
.status-dot { width: 8px; height: 8px; background: var(--color-danger); border-radius: 50%; }
.status-dot.online { background: var(--color-success); }
.input-area { padding: 12px; border-top: 1px solid var(--color-border-light); background: var(--color-surface); }
</style>