<template>
  <div class="ai-chat-page">
    <div class="chat-layout">
      <!-- 左侧：对话列表 -->
      <div class="conversation-sidebar">
        <el-button type="primary" @click="newConversation" style="width:100%;margin-bottom:12px">
          <el-icon><Plus /></el-icon> 新对话
        </el-button>
        <div class="conv-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === currentConvId }"
            @click="switchConversation(conv)"
          >
            <span class="conv-title">{{ conv.title || '新对话' }}</span>
            <el-icon class="conv-delete" @click.stop="deleteConversation(conv.id)"><Delete /></el-icon>
          </div>
        </div>
        <el-empty v-if="!conversations.length && !convLoading" description="暂无对话" :image-size="40" />
      </div>

      <!-- 右侧：聊天区域 -->
      <div class="chat-main">
        <div class="chat-messages" ref="messagesContainer">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            class="message"
            :class="{ 'user-message': msg.role === 'user', 'ai-message': msg.role === 'assistant' }"
          >
            <div class="message-avatar">
              <div v-if="msg.role === 'user'" class="avatar-circle">
                <span>{{ authStore.user?.username?.substring(0, 2).toUpperCase() }}</span>
              </div>
              <div v-else class="avatar-circle ai-avatar">
                <el-icon :size="20"><ChatDotRound /></el-icon>
              </div>
            </div>
            <div class="message-content">
              <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
              <div v-if="msg.toolCalls?.length" class="msg-tools">
                <div v-for="(tc, i) in msg.toolCalls" :key="i" class="tool-call-card">
                  <el-icon><Check /></el-icon>
                  <span>{{ tc.result }}</span>
                </div>
              </div>
              <div v-if="msg.taskRefs?.length" class="msg-refs">
                📋 相关任务：
                <span v-for="(t, i) in msg.taskRefs" :key="i" class="task-ref-link" @click="goToTask(t.id)">
                  {{ t.title || t.id?.substring(0, 8) }}
                </span>
              </div>
              <div class="message-time">{{ formatTime(msg.timestamp) }}</div>
            </div>
          </div>

          <div v-if="isLoading" class="message ai-message">
            <div class="message-avatar"><div class="avatar-circle ai-avatar"><el-icon :size="20"><ChatDotRound /></el-icon></div></div>
            <div class="message-content">
              <div class="typing-indicator"><span></span><span></span><span></span></div>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <el-input v-model="inputMessage" type="textarea" :rows="3"
            placeholder="输入问题..." @keydown.enter.prevent="sendMessage" />
          <el-button type="primary" :loading="isLoading || isStreaming" :disabled="!inputMessage.trim() || isStreaming" @click="sendMessage">
            <el-icon><Promotion /></el-icon> 发送
          </el-button>
        </div>

        <!-- 快捷操作 -->
        <div class="quick-bar">
          <span class="label">快捷:</span>
          <el-tag v-for="q in quickQuestions" :key="q" class="quick-tag" @click="inputMessage = q">{{ q }}</el-tag>
          <el-divider direction="vertical" />
          <el-switch v-model="isStreaming" size="small" active-text="流式" style="--el-switch-on-color:var(--color-primary-light)" />
          <el-divider direction="vertical" />
          <span class="label">分析:</span>
          <el-button size="small" @click="runAnalysis('health')" :loading="analyzing === 'health'">健康度</el-button>
          <el-button size="small" @click="runAnalysis('weekly')" :loading="analyzing === 'weekly'">周报</el-button>
          <el-button size="small" @click="runAnalysis('risks')" :loading="analyzing === 'risks'">风险</el-button>
          <el-button size="small" @click="runAnalysis('sprint-summary')" :loading="analyzing === 'sprint-summary'">Sprint</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'AIChat' });
import { ref, computed, onMounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/Auth';
import service from '@/utils/request';
import { ElMessage } from 'element-plus';
import { ChatDotRound, Promotion, Plus, Delete } from '@element-plus/icons-vue';
import { marked } from 'marked';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const projectId = computed(() => route.params.projectId as string);

// 对话列表
const conversations = ref<any[]>([]);
const convLoading = ref(false);
const currentConvId = ref<number | null>(null);

// 消息
const messages = ref<Array<{ role: string; content: string; timestamp: number; references?: string[]; taskRefs?: any[]; toolCalls?: any[] }>>([]);
const inputMessage = ref('');
const isLoading = ref(false);
const isStreaming = ref(false);
const analyzing = ref('');
const messagesContainer = ref<HTMLElement>();

const getCsrfToken = () => document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

const quickQuestions = ref([
  '项目中有哪些待办任务？',
  '总结一下项目当前进度',
  '谁负责的任务最多？',
  '有哪些任务还没分配负责人？',
]);

const renderMarkdown = (text: string) => {
  try { return marked.parse(text) as string; } catch { return text.replace(/\n/g, '<br>'); }
};
const formatTime = (ts: number) => new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
const scrollToBottom = () => nextTick(() => {
  if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
});

const goToTask = (taskId: string) => {
  if (!taskId) return;
  router.push({ name: 'Board', params: { projectId: projectId.value }, query: { taskId } });
};

// 对话管理
const fetchConversations = async () => {
  convLoading.value = true;
  try {
    const data = await service.get(`/ai/conversations/?project_id=${projectId.value}`);
    conversations.value = Array.isArray(data) ? data : (data as any).results || [];
  } catch { /* silent */ }
  finally { convLoading.value = false; }
};

const newConversation = () => {
  currentConvId.value = null;
  messages.value = [{ role: 'assistant', content: '你好！我是项目AI助手。可以帮你查询任务、分析项目健康度、生成周报。', timestamp: Date.now() }];
};

const switchConversation = async (conv: any) => {
  currentConvId.value = conv.id;
  try {
    const data = await service.get(`/ai/conversations/${conv.id}/`);
    const msgs = data.messages || data.results || [];
    messages.value = msgs.map((m: any) => ({
      role: m.role,
      content: m.content,
      timestamp: new Date(m.created_at).getTime(),
      references: m.references || [],
    }));
  } catch {
    messages.value = [];
  }
};

const deleteConversation = async (id: number) => {
  try {
    await service.delete(`/ai/conversations/${id}/`);
    conversations.value = conversations.value.filter(c => c.id !== id);
    if (currentConvId.value === id) newConversation();
    ElMessage.success('已删除');
  } catch { ElMessage.error('删除失败'); }
};

// 发送消息
const sendMessage = async () => {
  const msg = inputMessage.value.trim();
  if (!msg || isLoading.value || isStreaming.value) return;

  messages.value.push({ role: 'user', content: msg, timestamp: Date.now() });
  inputMessage.value = '';
  scrollToBottom();

  if (isStreaming.value) {
    await sendMessageStream(msg);
  } else {
    await sendMessageNormal(msg);
  }
};

const sendMessageNormal = async (msg: string) => {
  isLoading.value = true;
  try {
    const response = await service.post('/ai/chat/', {
      project_id: projectId.value, question: msg, conversation_id: currentConvId.value,
    });
    const refs = response.references || [];
    const taskRefs = refs.filter((r: any) => r.title || r.status);
    const toolCalls = refs.filter((r: any) => r.tool);
    messages.value.push({
      role: 'assistant', content: response.answer || '抱歉，无法回答。',
      timestamp: Date.now(), taskRefs, toolCalls,
    });
    if (!currentConvId.value && response.conversation_id) {
      currentConvId.value = response.conversation_id;
      fetchConversations();
    }
  } catch { ElMessage.error('请求失败'); }
  finally { isLoading.value = false; scrollToBottom(); }
};

const sendMessageStream = async (msg: string) => {
  isStreaming.value = true;
  const aiMsg = { role: 'assistant' as const, content: '', timestamp: Date.now(), references: [] as string[] };
  messages.value.push(aiMsg);

  try {
    const resp = await fetch('/api/ai/chat/stream/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
      credentials: 'include',
      body: JSON.stringify({ project_id: projectId.value, question: msg, conversation_id: currentConvId.value }),
    });
    const reader = resp.body?.getReader();
    const decoder = new TextDecoder();
    if (!reader) throw new Error('No reader');

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value, { stream: true });
      for (const line of text.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.done) {
              if (data.conversation_id) { currentConvId.value = data.conversation_id; fetchConversations(); }
              aiMsg.references = data.references || [];
            } else if (data.chunk) {
              aiMsg.content += data.chunk;
              scrollToBottom();
            }
          } catch {}
        }
      }
    }
  } catch { aiMsg.content += '\n[流式响应中断]'; }
  finally { isStreaming.value = false; scrollToBottom(); }
};

// 分析报告
const runAnalysis = async (type: string) => {
  analyzing.value = type;
  try {
    const endpoints: Record<string, string> = {
      health: '/ai/analyze/health/',
      weekly: '/ai/analyze/weekly/',
      risks: '/ai/analyze/risks/',
      'sprint-summary': '/ai/analyze/sprint-summary/',
    };
    const response = await service.post(endpoints[type] || endpoints.health!, { project_id: projectId.value });
    const result = response.analysis || response.weekly_report || '分析完成';
    messages.value.push({ role: 'assistant', content: result, timestamp: Date.now() });
    if (response.conversation_id) {
      currentConvId.value = response.conversation_id;
      fetchConversations();
    }
  } catch {
    ElMessage.error('分析失败');
  } finally { analyzing.value = ''; }
};

onMounted(() => {
  fetchConversations();
  newConversation();
});
</script>

<style scoped>
.ai-chat-page { height: calc(100vh - 140px); }
.chat-layout { display: flex; gap: 0; height: 100%; background: var(--color-surface); border-radius: var(--radius-lg); overflow: hidden; border: 1px solid var(--color-border); }

.conversation-sidebar { width: 220px; padding: 12px; border-right: 1px solid var(--color-border); background: var(--color-bg); display: flex; flex-direction: column; }
.conv-list { flex: 1; overflow-y: auto; }
.conv-item { padding: 8px 10px; cursor: pointer; border-radius: var(--radius-sm); margin-bottom: 4px; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
.conv-item:hover, .conv-item.active { background: var(--color-primary-bg); }
.conv-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.conv-delete { color: var(--color-text-tertiary); cursor: pointer; }
.conv-delete:hover { color: var(--color-danger); }

.chat-main { flex: 1; display: flex; flex-direction: column; }
.chat-messages { flex: 1; overflow-y: auto; padding: 20px; background: var(--color-bg); }
.message { display: flex; gap: 12px; margin-bottom: 16px; }
.user-message { flex-direction: row-reverse; }
.avatar-circle { width: 36px; height: 36px; border-radius: 50%; background: var(--color-primary-bg); color: var(--color-primary); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; font-family: var(--font-heading); }
.ai-avatar { background: var(--color-primary); }
.message-content { max-width: 70%; padding: 10px 14px; border-radius: var(--radius-md); background: var(--color-surface); box-shadow: var(--shadow-sm); font-size: 14px; line-height: 1.6; }
.user-message .message-content { background: var(--color-primary); color: white; }
.message-text :deep(p) { margin: 0 0 4px; }
.message-text :deep(code) { background: var(--color-border-light); padding: 1px 4px; border-radius: 3px; font-size: 13px; }
.msg-refs { font-size: 12px; color: var(--color-text-tertiary); margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.task-ref-link { color: var(--color-primary-light); cursor: pointer; text-decoration: underline; margin-left: 4px; }
.task-ref-link:hover { color: var(--color-primary-dark); }
.msg-tools { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.tool-call-card { display: flex; align-items: center; gap: 6px; padding: 6px 10px; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: var(--radius-sm); font-size: 13px; color: #065f46; }
.tool-call-card .el-icon { color: var(--color-success); }
.message-time { font-size: 11px; color: var(--color-text-tertiary); margin-top: 4px; }
.user-message .message-time { color: var(--color-primary-bg); }

.typing-indicator { display: flex; gap: 4px; padding: 4px 0; }
.typing-indicator span { width: 7px; height: 7px; background: var(--color-text-tertiary); border-radius: 50%; animation: typing 1.4s infinite; }
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-8px); } }

.chat-input-area { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--color-border); }
.chat-input-area .el-textarea { flex: 1; }
.quick-bar { padding: 6px 16px 10px; background: #fff; border-top: 1px solid var(--color-border-light); font-size: 13px; }
.quick-bar .label { color: var(--color-text-tertiary); margin-right: 8px; }
.quick-tag { margin-right: 6px; cursor: pointer; }
</style>
