<template>
  <el-card class="activity-timeline-card">
    <template #header>
      <strong>活动记录 ({{ timeline.length }})</strong>
    </template>

    <!-- Timeline -->
    <div v-if="timeline.length === 0" class="empty-hint">暂无活动</div>

    <div v-else class="timeline">
      <div
        v-for="item in timeline"
        :key="item.id"
        class="timeline-item"
        :class="item.type"
      >
        <!-- 左侧图标 -->
        <div class="timeline-icon">
          <div v-if="item.type === 'comment'" class="icon-comment">
            <el-icon :size="14"><ChatDotRound /></el-icon>
          </div>
          <div v-else class="icon-transition">
            <el-icon :size="14"><Right /></el-icon>
          </div>
        </div>

        <!-- 内容 -->
        <div class="timeline-body">
          <!-- Comment -->
          <template v-if="item.type === 'comment'">
            <div class="event-header">
              <strong>{{ item.author?.username || '匿名' }}</strong>
              <span class="event-time">{{ formatTime(item.created_at) }}</span>
            </div>
            <div class="comment-content">{{ item.content }}</div>
          </template>

          <!-- Transition -->
          <template v-else>
            <div class="event-header">
              <span class="event-actor">{{ item.operator?.username || '系统' }}</span>
              <span class="event-time">{{ formatTime(item.created_at) }}</span>
            </div>
            <div class="transition-desc">
              <template v-if="!item.from_status">
                创建了缺陷，状态为
                <BugStatusTag :status="item.to_status as BugStatus" />
              </template>
              <template v-else>
                将状态从
                <BugStatusTag :status="item.from_status as BugStatus" />
                改为
                <BugStatusTag :status="item.to_status as BugStatus" />
              </template>
            </div>
            <div v-if="item.comment" class="transition-comment">{{ item.comment }}</div>
          </template>
        </div>
      </div>
    </div>

    <el-divider />

    <!-- Comment input -->
    <div class="comment-input-area">
      <el-input
        v-model="newComment"
        type="textarea"
        :rows="3"
        placeholder="添加评论…"
      />
      <div class="comment-actions">
        <el-button
          type="primary"
          :loading="commentSubmitting"
          :disabled="!newComment.trim()"
          @click="handleSubmit"
        >
          发表评论
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChatDotRound, Right } from '@element-plus/icons-vue'
import { STATUS_LABEL, type BugComment, type BugTransition, type BugStatus } from '@/api/bug'
import BugStatusTag from './BugStatusTag.vue'

const props = defineProps<{
  comments: BugComment[]
  transitions: BugTransition[]
}>()

const emit = defineEmits<{
  (e: 'add-comment', content: string): void
}>()

const newComment = ref('')
const commentSubmitting = ref(false)

interface TimelineItem {
  id: string
  type: 'comment' | 'transition'
  created_at: string
  // comment fields
  author?: BugComment['author']
  content?: string
  // transition fields
  operator?: BugTransition['operator']
  from_status?: string
  to_status?: string
  comment?: string
}

const timeline = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = [
    ...props.comments.map((c) => ({
      id: `comment-${c.id}`,
      type: 'comment' as const,
      created_at: c.created_at,
      author: c.author,
      content: c.content,
    })),
    ...props.transitions.map((t) => ({
      id: `transition-${t.id}`,
      type: 'transition' as const,
      created_at: t.created_at,
      operator: t.operator,
      from_status: t.from_status,
      to_status: t.to_status,
      comment: t.comment,
    })),
  ]
  // 时间正序（旧→新）
  items.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  return items
})

const formatTime = (t: string) => (t ? new Date(t).toLocaleString() : '-')

const handleSubmit = () => {
  const content = newComment.value.trim()
  if (!content) return
  commentSubmitting.value = true
  emit('add-comment', content)
  // Input is cleared only when parent reloads data and comments length increases
}

// Clear input when comments array length increases (successful save)
// Reset submitting state when comments array is replaced (success or failure)
let prevLen = props.comments.length
watch(
  () => props.comments,
  (newComments) => {
    const newLen = newComments.length
    if (newLen > prevLen) {
      newComment.value = ''
    }
    prevLen = newLen
    commentSubmitting.value = false
  },
  { deep: false }  // shallow compare — detects array replacement from parent reload
)

// Expose submitting for parent
defineExpose({ commentSubmitting })
</script>

<style scoped>
.activity-timeline-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}
.empty-hint {
  color: var(--color-text-tertiary);
  text-align: center;
  padding: 24px;
  font-size: 13px;
}
.timeline {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.timeline-item {
  display: flex;
  gap: 12px;
  padding: 10px 0;
}
.timeline-icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}
.icon-comment {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}
.icon-transition {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-surface-sunken);
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
}
.timeline-body {
  flex: 1;
  min-width: 0;
}
.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 13px;
}
.event-actor {
  font-weight: 500;
  color: var(--color-text);
}
.event-time {
  color: var(--color-text-tertiary);
  font-size: 11px;
}
.comment-content {
  white-space: pre-wrap;
  font-size: 13px;
  color: var(--color-text);
  padding: 8px 12px;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}
.transition-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.transition-comment {
  color: var(--color-text-secondary);
  font-size: 12px;
  margin-top: 4px;
  padding-left: 4px;
  border-left: 2px solid var(--color-border);
}
.comment-input-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.comment-actions {
  text-align: right;
}
</style>
