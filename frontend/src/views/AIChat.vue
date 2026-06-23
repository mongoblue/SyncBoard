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
              <div v-else class="avatar-square">
                <el-icon :size="18"><ChatDotRound /></el-icon>
              </div>
            </div>
            <div class="message-content">
              <div v-if="msg.role === 'assistant'" class="message-meta">
                <span class="meta-name">AI 助手</span>
                <span class="meta-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-text">
                <span v-html="renderMarkdown(msg.content, msg.streaming)"></span>
                <span v-if="msg.streaming" class="stream-caret">▍</span>
              </div>
              <div v-if="msg.toolCalls?.length" class="msg-tools">
                <details
                  v-for="(tc, i) in msg.toolCalls"
                  :key="i"
                  class="tool-call-card"
                >
                  <summary class="tool-call-head">
                    <el-icon class="tool-call-icon"><Tools /></el-icon>
                    <span class="tool-name">{{ tc.tool || '工具调用' }}</span>
                    <span class="tool-status success">已完成</span>
                  </summary>
                  <div class="tool-call-body">
                    <div v-if="tc.args" class="tool-section">
                      <div class="tool-section-label">参数</div>
                      <pre>{{ formatJson(tc.args) }}</pre>
                    </div>
                    <div v-if="tc.result" class="tool-section">
                      <div class="tool-section-label">结果</div>
                      <pre>{{ formatJson(tc.result) }}</pre>
                    </div>
                  </div>
                </details>
              </div>
              <div v-if="msg.taskRefs?.length" class="msg-refs">
                <span class="refs-label">相关任务:</span>
                <span
                  v-for="(t, i) in msg.taskRefs"
                  :key="i"
                  class="task-ref-link"
                  @click="goToTask(t.id)"
                >
                  {{ t.title || t.id?.substring(0, 8) }}
                </span>
              </div>
              <div v-if="msg.role === 'user'" class="message-time">{{ formatTime(msg.timestamp) }}</div>
            </div>
          </div>

          <div v-if="isLoading" class="message ai-message">
            <div class="message-avatar"><div class="avatar-square"><el-icon :size="18"><ChatDotRound /></el-icon></div></div>
            <div class="message-content">
              <div class="typing-indicator"><span></span><span></span><span></span></div>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <el-input v-model="inputMessage" type="textarea" :rows="3"
            placeholder="输入问题..." @keydown.enter.prevent="sendMessage" />
          <el-button type="primary" :loading="isLoading || isSending" :disabled="!inputMessage.trim() || isSending" @click="sendMessage">
            <el-icon><Promotion /></el-icon> 发送
          </el-button>
        </div>

        <!-- 快捷操作 -->
        <div class="quick-bar">
          <span class="label">快捷:</span>
          <el-tag v-for="q in quickQuestions" :key="q" class="quick-tag" @click="inputMessage = q">{{ q }}</el-tag>
          <el-divider direction="vertical" />
          <el-switch v-model="streamingPref" size="small" active-text="流式" />
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
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/Auth';
import service from '@/utils/request';
import { ElMessage } from 'element-plus';
import { ChatDotRound, Promotion, Plus, Delete, Tools } from '@element-plus/icons-vue';
import { Marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const projectId = computed(() => route.params.projectId as string);

interface ChatMessage {
  role: string;
  content: string;
  timestamp: number;
  references?: string[];
  taskRefs?: any[];
  toolCalls?: any[];
  streaming?: boolean;
}

// 对话列表
const conversations = ref<any[]>([]);
const convLoading = ref(false);
const currentConvId = ref<number | null>(null);

// 消息
const messages = ref<ChatMessage[]>([]);
const inputMessage = ref('');
const isLoading = ref(false);
const streamingPref = ref(true);
const isSending = ref(false);
const analyzing = ref('');
const messagesContainer = ref<HTMLElement>();

// 活跃的打字机/流式 timer,切会话或卸载时统一清理
const activeTimers = new Set<number>();
const cancelActiveTimers = () => {
  activeTimers.forEach(id => window.clearInterval(id));
  activeTimers.clear();
};

const getCsrfToken = () => document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

const quickQuestions = ref([
  '项目中有哪些待办任务？',
  '总结一下项目当前进度',
  '谁负责的任务最多？',
  '有哪些任务还没分配负责人？',
]);

// Markdown 渲染:双 marked 实例 — 流式中走轻量 fast 版,流结束后走带高亮 full 版
const markedFast = new Marked();
markedFast.setOptions({ gfm: true, breaks: true });

const markedFull = new Marked();
markedFull.use(markedHighlight({
  langPrefix: 'hljs language-',
  highlight(code, lang) {
    const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
    try {
      return hljs.highlight(code, { language }).value;
    } catch {
      return code;
    }
  },
}));
markedFull.setOptions({ gfm: true, breaks: true });

const renderMarkdown = (text: string, isStreaming = false) => {
  try {
    const parser = isStreaming ? markedFast : markedFull;
    const raw = parser.parse(text || '') as string;
    return DOMPurify.sanitize(raw);
  } catch {
    return (text || '').replace(/\n/g, '<br>');
  }
};

// 打字机节奏:恒定 cps,不再随 buffer 长度自适应
const CHARS_PER_SECOND = 120;
const TICK_MS = 33;
const CHARS_PER_TICK = Math.max(1, Math.round(CHARS_PER_SECOND * TICK_MS / 1000));

const formatJson = (v: any): string => {
  if (typeof v === 'string') return v;
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
};

const formatTime = (ts: number) => new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
const scrollToBottom = () => nextTick(() => {
  if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
});
// 仅在用户已经接近底部时才自动滚动,避免向上翻历史时被强行拉回
const scrollToBottomIfNear = () => {
  const el = messagesContainer.value;
  if (!el) return;
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
  if (distance < 80) {
    nextTick(() => { el.scrollTop = el.scrollHeight; });
  }
};

// 打字机播放:恒定速度,把整段文本逐字渲染到 msg.content
const typewriterPlay = (msg: ChatMessage, fullText: string, onDone?: () => void) => {
  msg.streaming = true;
  msg.content = '';
  let i = 0;
  const timer = window.setInterval(() => {
    if (i >= fullText.length) {
      window.clearInterval(timer);
      activeTimers.delete(timer);
      msg.streaming = false;
      scrollToBottomIfNear();
      onDone?.();
      return;
    }
    const take = CHARS_PER_TICK;
    msg.content += fullText.slice(i, i + take);
    i += take;
    scrollToBottomIfNear();
  }, TICK_MS);
  activeTimers.add(timer);
};

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
  cancelActiveTimers();
  currentConvId.value = null;
  messages.value = [{ role: 'assistant', content: '你好！我是项目AI助手。可以帮你查询任务、分析项目健康度、生成周报。', timestamp: Date.now() }];
};

const switchConversation = async (conv: any) => {
  cancelActiveTimers();
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
  if (!msg || isLoading.value || isSending.value) return;

  messages.value.push({ role: 'user', content: msg, timestamp: Date.now() });
  inputMessage.value = '';
  scrollToBottom();

  if (streamingPref.value) {
    await sendMessageStream(msg);
  } else {
    await sendMessageNormal(msg);
  }
};

const sendMessageNormal = async (msg: string) => {
  isLoading.value = true;
  isSending.value = true;
  try {
    const response = await service.post('/ai/chat/', {
      project_id: projectId.value, question: msg, conversation_id: currentConvId.value,
    });
    const refs = response.references || [];
    const taskRefs = refs.filter((r: any) => r.title || r.status);
    const toolCalls = refs.filter((r: any) => r.tool);
    const fullText = response.answer || '抱歉，无法回答。';
    const aiMsg: ChatMessage = {
      role: 'assistant', content: '',
      timestamp: Date.now(), taskRefs, toolCalls,
    };
    messages.value.push(aiMsg);
    isLoading.value = false;
    typewriterPlay(aiMsg, fullText, () => { isSending.value = false; });
    if (!currentConvId.value && response.conversation_id) {
      currentConvId.value = response.conversation_id;
      fetchConversations();
    }
  } catch {
    ElMessage.error('请求失败');
    isLoading.value = false;
    isSending.value = false;
  } finally { scrollToBottom(); }
};

const sendMessageStream = async (msg: string) => {
  isSending.value = true;
  const aiMsg: ChatMessage = { role: 'assistant', content: '', timestamp: Date.now(), references: [], streaming: true };
  messages.value.push(aiMsg);

  let buffer = '';
  let streamDone = false;
  const flushTimer = window.setInterval(() => {
    if (buffer.length === 0) {
      if (streamDone) {
        window.clearInterval(flushTimer);
        activeTimers.delete(flushTimer);
        aiMsg.streaming = false;
        isSending.value = false;
        scrollToBottomIfNear();
      }
      return;
    }
    // 兜底:buffer 严重积压(流已结束很久还没追上)时加速,避免无限拖延
    const take = buffer.length > 600
      ? Math.max(CHARS_PER_TICK, Math.ceil(buffer.length / 100))
      : CHARS_PER_TICK;
    aiMsg.content += buffer.slice(0, take);
    buffer = buffer.slice(take);
    scrollToBottomIfNear();
  }, TICK_MS);
  activeTimers.add(flushTimer);

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
              buffer += data.chunk;
            }
          } catch {}
        }
      }
    }
  } catch { buffer += '\n[流式响应中断]'; }
  finally { streamDone = true; }
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
    const aiMsg: ChatMessage = { role: 'assistant', content: '', timestamp: Date.now() };
    messages.value.push(aiMsg);
    typewriterPlay(aiMsg, result);
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

onBeforeUnmount(() => {
  cancelActiveTimers();
});
</script>

<style scoped>
.ai-chat-page { height: calc(100vh - 140px); padding: 0; }
.chat-layout {
  display: flex; gap: 0; height: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.conversation-sidebar {
  width: 240px; padding: 12px;
  border-right: 1px solid var(--color-border-light);
  background: var(--color-surface);
  display: flex; flex-direction: column;
}
.conv-list { flex: 1; overflow-y: auto; }
.conv-item {
  padding: 8px 10px; cursor: pointer;
  border-radius: var(--radius-md);
  margin-bottom: 2px; font-size: 13px;
  display: flex; justify-content: space-between; align-items: center;
  color: var(--color-text);
}
.conv-item:hover { background: var(--color-surface-hover); }
.conv-item.active { background: var(--color-primary-bg); color: var(--color-primary); }
.conv-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.conv-delete { color: var(--color-text-tertiary); cursor: pointer; }
.conv-delete:hover { color: var(--color-danger); }

.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--color-surface); }
.chat-messages { flex: 1; overflow-y: auto; padding: 24px 32px; background: var(--color-surface); }

/* 消息基础布局 */
.message { display: flex; gap: 12px; margin-bottom: 24px; }
.user-message { flex-direction: row-reverse; }

/* 头像 */
.avatar-circle {
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--color-primary-bg); color: var(--color-primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; font-family: var(--font-heading);
  flex-shrink: 0;
}
.avatar-square {
  width: 32px; height: 32px; border-radius: var(--radius-md);
  background: var(--color-primary); color: var(--color-text-inverse);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}

/* 助手消息：去气泡，全宽文档样式 */
.ai-message .message-content {
  flex: 1; min-width: 0;
  background: transparent; border: none; padding: 0;
  font-size: 14px; line-height: 1.65;
  color: var(--color-text);
}

/* 用户消息：保留气泡 */
.user-message .message-content {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  font-size: 14px; line-height: 1.6;
  color: var(--color-text);
}

/* 助手 meta 行 */
.message-meta {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px;
}
.meta-name { font: 600 13px/1.4 var(--font-heading); color: var(--color-text); }
.meta-time { font-size: 12px; color: var(--color-text-tertiary); }

.message-text { word-break: break-word; }
.message-time { font-size: 11px; color: var(--color-text-tertiary); margin-top: 4px; }

/* 流式光标 */
.stream-caret {
  display: inline-block;
  width: 8px;
  color: var(--color-primary);
  animation: blink 1s step-end infinite;
  margin-left: 2px;
  vertical-align: text-bottom;
  font-weight: 600;
}
@keyframes blink { 50% { opacity: 0; } }

/* 助手 markdown 渲染样式 */
.ai-message .message-text :deep(p) { margin: 0 0 12px; line-height: 1.65; }
.ai-message .message-text :deep(p:last-child) { margin-bottom: 0; }
.ai-message .message-text :deep(h1) { font: 600 20px/1.3 var(--font-heading); margin: 16px 0 8px; color: var(--color-text); }
.ai-message .message-text :deep(h2) { font: 600 17px/1.3 var(--font-heading); margin: 14px 0 8px; color: var(--color-text); }
.ai-message .message-text :deep(h3) { font: 600 15px/1.3 var(--font-heading); margin: 12px 0 6px; color: var(--color-text); }
.ai-message .message-text :deep(h4) { font: 600 14px/1.3 var(--font-heading); margin: 10px 0 6px; color: var(--color-text); }
.ai-message .message-text :deep(h1:first-child),
.ai-message .message-text :deep(h2:first-child),
.ai-message .message-text :deep(h3:first-child),
.ai-message .message-text :deep(h4:first-child) { margin-top: 0; }
.ai-message .message-text :deep(ul),
.ai-message .message-text :deep(ol) { margin: 0 0 12px; padding-left: 24px; }
.ai-message .message-text :deep(li) { margin-bottom: 4px; line-height: 1.65; }
.ai-message .message-text :deep(li > p) { margin: 0; }
.ai-message .message-text :deep(li > ul),
.ai-message .message-text :deep(li > ol) { margin: 4px 0 4px; }
.ai-message .message-text :deep(blockquote) {
  margin: 0 0 12px;
  padding: 4px 0 4px 16px;
  border-left: 3px solid var(--color-border);
  color: var(--color-text-secondary);
}
.ai-message .message-text :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border-light);
  margin: 16px 0;
}
.ai-message .message-text :deep(a) { color: var(--color-text-link); text-decoration: none; }
.ai-message .message-text :deep(a:hover) { text-decoration: underline; }
.ai-message .message-text :deep(strong) { font-weight: 600; color: var(--color-text); }
.ai-message .message-text :deep(em) { font-style: italic; }
.ai-message .message-text :deep(code) {
  font: 12px/1.5 var(--font-mono);
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: 4px;
  padding: 1px 6px;
  color: var(--color-text);
}
.ai-message .message-text :deep(pre) {
  margin: 0 0 12px;
  padding: 12px 16px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  border-radius: 6px;
  overflow-x: auto;
}
.ai-message .message-text :deep(pre code) {
  background: none; border: none; padding: 0;
  font: 12px/1.6 var(--font-mono);
  color: var(--color-text);
}
.ai-message .message-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 12px;
  font-size: 13px;
}
.ai-message .message-text :deep(th),
.ai-message .message-text :deep(td) {
  padding: 6px 12px;
  border: 1px solid var(--color-border-light);
  text-align: left;
}
.ai-message .message-text :deep(th) {
  background: var(--color-surface-sunken);
  font-weight: 600;
}

/* 用户气泡内 markdown */
.user-message .message-text :deep(p) { margin: 0; }
.user-message .message-text :deep(code) {
  background: rgba(255, 255, 255, 0.5);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 13px;
  font-family: var(--font-mono);
}

/* 工具调用卡 */
.msg-tools { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.tool-call-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.tool-call-card[open] { box-shadow: var(--shadow-sm); }
.tool-call-head {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; cursor: pointer;
  font-size: 13px;
  list-style: none;
  user-select: none;
}
.tool-call-head::-webkit-details-marker { display: none; }
.tool-call-head::before {
  content: '▸';
  font-size: 10px;
  color: var(--color-text-tertiary);
  transition: transform var(--transition-fast);
  display: inline-block;
}
.tool-call-card[open] .tool-call-head::before { transform: rotate(90deg); }
.tool-call-icon { color: var(--color-primary); }
.tool-name { font-weight: 500; color: var(--color-text); flex: 1; font-family: var(--font-mono); font-size: 12px; }
.tool-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-weight: 500;
}
.tool-status.success { background: var(--color-success-bg); color: var(--color-success); }
.tool-status.running { background: var(--color-info-bg); color: var(--color-info); }
.tool-status.error { background: var(--color-danger-bg); color: var(--color-danger); }
.tool-call-body {
  padding: 12px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-surface-sunken);
}
.tool-section + .tool-section { margin-top: 8px; }
.tool-section-label {
  font-size: 11px;
  color: var(--color-text-secondary);
  font-weight: 500;
  margin-bottom: 4px;
  text-transform: none;
}
.tool-section pre {
  margin: 0;
  padding: 8px 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  font: 12px/1.5 var(--font-mono);
  color: var(--color-text);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 任务引用 */
.msg-refs {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 8px;
  display: flex; flex-wrap: wrap; gap: 6px;
  align-items: center;
}
.refs-label { color: var(--color-text-tertiary); }
.task-ref-link {
  color: var(--color-primary);
  cursor: pointer;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-bg);
}
.task-ref-link:hover { background: var(--color-primary-border); }

/* typing indicator */
.typing-indicator { display: flex; gap: 4px; padding: 8px 0; }
.typing-indicator span {
  width: 6px; height: 6px;
  background: var(--color-text-tertiary);
  border-radius: 50%;
  animation: typing 1.4s infinite;
}
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }

.chat-input-area {
  display: flex; gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-surface);
}
.chat-input-area .el-textarea { flex: 1; }
.quick-bar {
  padding: 8px 16px 12px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border-light);
  font-size: 13px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
}
.quick-bar .label { color: var(--color-text-secondary); margin-right: 6px; }
.quick-tag { margin-right: 4px; cursor: pointer; }
</style>
