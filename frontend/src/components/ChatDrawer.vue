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
import { useBoardStore } from '@/stores/Board';
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
    const res = await service.get('/api/projects/');
    projectList.value = res.data || res;
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
  const hostname = window.location.hostname;
  const port = '8000';
  
  socket = new WebSocket(`${protocol}//${hostname}:${port}/ws/chat/${projectId}/`);

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
/* 样式部分 */
.chat-fab { position: fixed; bottom: 20px; right: 20px; width: 50px; height: 50px; background: #409eff; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; z-index: 2000; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.chat-list-container { padding: 10px; }
.chat-list-item { display: flex; align-items: center; padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; transition: background 0.2s; }
.chat-list-item:hover { background: #f5f7fa; }
.proj-avatar { width: 40px; height: 40px; background: #409eff; color: white; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 10px; }
.proj-info { flex: 1; }
.proj-name { font-size: 14px; font-weight: bold; color: #333; }
.proj-preview { font-size: 12px; color: #999; }
.chat-container { display: flex; flex-direction: column; height: 100%; }
.chat-header-bar { padding: 5px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; }
.messages { flex: 1; overflow-y: auto; padding: 10px; background: #f5f7fa; }
.message-item { margin-bottom: 15px; display: flex; flex-direction: column; align-items: flex-start; }
.my-msg { align-items: flex-end; }
.msg-bubble { background: white; padding: 8px 12px; border-radius: 8px; max-width: 85%; box-shadow: 0 1px 2px rgba(0,0,0,0.1); word-wrap: break-word; }
.my-msg .msg-bubble { background: #95d475; }
.msg-user { font-size: 12px; color: #999; margin-bottom: 2px; }
.msg-time { font-size: 10px; color: #ccc; margin-left: 5px; }
.status-dot { width: 8px; height: 8px; background: red; border-radius: 50%; }
.status-dot.online { background: #67c23a; }
</style>