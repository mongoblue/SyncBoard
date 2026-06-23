<template>
  <div class="bug-detail" v-loading="loading">
    <div v-if="bug" class="detail-wrapper">
      <!-- 顶部：标题 + 操作 -->
      <div class="detail-header">
        <div class="header-left">
          <el-button link @click="goBack" style="padding: 0; align-self: flex-start; color: var(--color-text-secondary)">
            <el-icon style="margin-right: 4px"><ArrowLeft /></el-icon> 返回列表
          </el-button>
          <div class="title-row">
            <span class="bug-id">#{{ bug.id }}</span>
            <h2 v-if="!editingTitle" class="bug-title" @dblclick="startEditTitle">{{ bug.title }}</h2>
            <el-input
              v-else
              v-model="editTitleValue"
              size="large"
              style="width: 480px"
              @blur="saveTitle"
              @keyup.enter="saveTitle"
            />
          </div>
          <div class="meta-row">
            <el-tag :type="STATUS_TAG_TYPE[bug.status]">{{ bug.status_display }}</el-tag>
            <el-tag :type="SEVERITY_TAG_TYPE[bug.severity]" size="small">严重度: {{ bug.severity_display }}</el-tag>
            <el-tag :type="PRIORITY_TAG_TYPE[bug.priority]" size="small">{{ bug.priority_display }}</el-tag>
            <el-tag size="small" type="info">来源: {{ bug.source_display }}</el-tag>
          </div>
        </div>

        <div class="header-actions">
          <!-- 状态流转 -->
          <el-dropdown
            v-if="bug.allowed_transitions?.length"
            trigger="click"
            @command="onTransition"
          >
            <el-button type="primary">
              流转状态<el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="s in bug.allowed_transitions"
                  :key="s"
                  :command="s"
                >
                  → {{ STATUS_LABEL[s] }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 指派 -->
          <el-button @click="assignDialogVisible = true">
            <el-icon><User /></el-icon> 指派
          </el-button>

          <!-- 删除 -->
          <el-popconfirm
            title="确定删除这个 Bug 吗？此操作无法撤销。"
            confirm-button-text="删除"
            cancel-button-text="取消"
            confirm-button-type="danger"
            @confirm="confirmDelete"
          >
            <template #reference>
              <el-button type="danger" plain>
                <el-icon><Delete /></el-icon> 删除
              </el-button>
            </template>
          </el-popconfirm>

          <el-button @click="loadDetail">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </div>

      <div class="content-grid">
        <!-- 左侧：详情 + 评论 -->
        <div class="left-pane">
          <el-card class="section-card">
            <template #header><strong>问题描述</strong></template>
            <EditableText
              v-model="bug.description"
              placeholder="（无）"
              :rows="3"
              @save="v => saveField('description', v)"
            />
          </el-card>

          <el-card class="section-card">
            <template #header><strong>复现步骤</strong></template>
            <EditableText
              v-model="bug.steps_to_reproduce"
              placeholder="（无）"
              :rows="4"
              @save="v => saveField('steps_to_reproduce', v)"
            />
          </el-card>

          <div class="two-col">
            <el-card class="section-card">
              <template #header><strong>预期结果</strong></template>
              <EditableText
                v-model="bug.expected"
                placeholder="（无）"
                :rows="2"
                @save="v => saveField('expected', v)"
              />
            </el-card>
            <el-card class="section-card">
              <template #header><strong>实际结果</strong></template>
              <EditableText
                v-model="bug.actual"
                placeholder="（无）"
                :rows="2"
                @save="v => saveField('actual', v)"
              />
            </el-card>
          </div>

          <!-- 评论 -->
          <el-card class="section-card">
            <template #header><strong>评论 ({{ bug.comments?.length || 0 }})</strong></template>
            <div v-if="!bug.comments?.length" class="empty-hint">暂无评论</div>
            <div v-else class="comment-list">
              <div v-for="c in bug.comments" :key="c.id" class="comment-item">
                <div class="comment-head">
                  <strong>{{ c.author?.username || '匿名' }}</strong>
                  <span class="comment-time">{{ formatTime(c.created_at) }}</span>
                </div>
                <div class="comment-body">{{ c.content }}</div>
              </div>
            </div>
            <el-divider />
            <el-input
              v-model="newComment"
              type="textarea"
              :rows="3"
              placeholder="添加评论…"
            />
            <div style="margin-top: 8px; text-align: right">
              <el-button
                type="primary"
                :loading="commentSubmitting"
                :disabled="!newComment.trim()"
                @click="submitComment"
              >发表评论</el-button>
            </div>
          </el-card>
        </div>

        <!-- 右侧：属性 + 时间线 -->
        <div class="right-pane">
          <el-card class="section-card">
            <template #header><strong>属性</strong></template>
            <div class="prop-row"><span class="prop-label">报告人</span><span>{{ bug.reporter?.username || '-' }}</span></div>
            <div class="prop-row"><span class="prop-label">指派给</span><span>{{ bug.assignee?.username || '-' }}</span></div>
            <div class="prop-row" v-if="bug.linked_task">
              <span class="prop-label">关联任务</span>
              <span :title="bug.linked_task" class="linked-task-chip">
                #{{ bug.linked_task.slice(0, 8) }}
              </span>
            </div>
            <div class="prop-row"><span class="prop-label">修复人</span><span>{{ bug.fixer?.username || '-' }}</span></div>
            <div class="prop-row"><span class="prop-label">验证人</span><span>{{ bug.verifier?.username || '-' }}</span></div>
            <el-divider />
            <div class="prop-row"><span class="prop-label">严重度</span>
              <el-select v-model="bug.severity" size="small" @change="saveField('severity', bug.severity)">
                <el-option v-for="s in SEVERITY_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </div>
            <div class="prop-row"><span class="prop-label">优先级</span>
              <el-select v-model="bug.priority" size="small" @change="saveField('priority', bug.priority)">
                <el-option v-for="p in PRIORITY_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </div>
            <div class="prop-row"><span class="prop-label">环境</span>
              <el-input v-model="bug.environment" size="small" style="width: 150px" @change="saveField('environment', bug.environment)" />
            </div>
            <el-divider />
            <div class="prop-row"><span class="prop-label">创建时间</span><span>{{ formatTime(bug.created_at) }}</span></div>
            <div class="prop-row"><span class="prop-label">更新时间</span><span>{{ formatTime(bug.updated_at) }}</span></div>
            <div class="prop-row" v-if="bug.closed_at"><span class="prop-label">关闭时间</span><span>{{ formatTime(bug.closed_at) }}</span></div>
          </el-card>

          <el-card class="section-card">
            <template #header><strong>变更历史</strong></template>
            <el-timeline v-if="bug.transitions?.length">
              <el-timeline-item
                v-for="t in bug.transitions"
                :key="t.id"
                :timestamp="formatTime(t.created_at)"
                placement="top"
              >
                <div>
                  <strong>{{ t.operator?.username || '系统' }}</strong>
                  {{ t.from_status ? `将状态从 ${STATUS_LABEL[t.from_status as BugStatus] || t.from_status} 改为` : '创建为' }}
                  <el-tag size="small">{{ STATUS_LABEL[t.to_status as BugStatus] || t.to_status }}</el-tag>
                </div>
                <div v-if="t.comment" class="transition-comment">{{ t.comment }}</div>
              </el-timeline-item>
            </el-timeline>
            <div v-else class="empty-hint">暂无变更</div>
          </el-card>
        </div>
      </div>
    </div>

    <!-- 流转评论对话框 -->
    <el-dialog v-model="transitionDialogVisible" :title="`流转到：${STATUS_LABEL[pendingStatus!] || ''}`" width="480px">
      <el-input
        v-model="transitionComment"
        type="textarea"
        :rows="3"
        placeholder="（可选）填写流转说明"
      />
      <template #footer>
        <el-button @click="transitionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="transitionSubmitting" @click="confirmTransition">确认</el-button>
      </template>
    </el-dialog>

    <!-- 指派对话框 -->
    <el-dialog v-model="assignDialogVisible" title="指派 Bug" width="420px">
      <el-form label-width="80px">
        <el-form-item label="指派给">
          <el-select v-model="assignUserId" filterable style="width: 100%">
            <el-option
              v-for="m in members"
              :key="m.user_id"
              :label="m.username"
              :value="m.user_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="assignComment" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="assignSubmitting" :disabled="!assignUserId" @click="confirmAssign">指派</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { ArrowLeft, ArrowDown, Refresh, User, Delete } from '@element-plus/icons-vue';
import {
  getBug, updateBug, deleteBug, transitionBug, assignBug, addBugComment,
  getProjectMembers,
  STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE, STATUS_LABEL,
  type BugDetail, type BugStatus, type ProjectMemberBrief,
} from '@/api/bug';
import EditableText from '@/components/bug/EditableText.vue';
import { extractErrorMessage } from '@/utils/error';

const route = useRoute();
const router = useRouter();
const bugId = Number(route.params.id);
const projectId = route.params.projectId as string;

const SEVERITY_OPTIONS = [
  { value: 'blocker', label: '阻塞' },
  { value: 'critical', label: '严重' },
  { value: 'major', label: '一般' },
  { value: 'minor', label: '次要' },
  { value: 'trivial', label: '轻微' },
];
const PRIORITY_OPTIONS = [
  { value: 'p0', label: 'P0' },
  { value: 'p1', label: 'P1' },
  { value: 'p2', label: 'P2' },
  { value: 'p3', label: 'P3' },
];

const loading = ref(false);
const bug = ref<BugDetail | null>(null);

const loadDetail = async () => {
  loading.value = true;
  try {
    bug.value = await getBug(bugId);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '加载 Bug 详情失败'));
  } finally {
    loading.value = false;
  }
};

// 标题编辑
const editingTitle = ref(false);
const editTitleValue = ref('');
const startEditTitle = () => {
  if (!bug.value) return;
  editTitleValue.value = bug.value.title;
  editingTitle.value = true;
};
const saveTitle = async () => {
  if (!bug.value) return;
  const newTitle = editTitleValue.value.trim();
  editingTitle.value = false;
  if (!newTitle || newTitle === bug.value.title) return;
  try {
    const updated = await updateBug(bugId, { title: newTitle });
    bug.value.title = updated.title;
    ElMessage.success('已更新');
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '更新失败'));
  }
};

const saveField = async (field: string, value: any) => {
  try {
    await updateBug(bugId, { [field]: value });
    ElMessage.success('已保存');
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '保存失败'));
    loadDetail();
  }
};

// 状态流转
const transitionDialogVisible = ref(false);
const transitionComment = ref('');
const pendingStatus = ref<BugStatus | null>(null);
const transitionSubmitting = ref(false);

const onTransition = (status: BugStatus) => {
  pendingStatus.value = status;
  transitionComment.value = '';
  transitionDialogVisible.value = true;
};

const confirmTransition = async () => {
  if (!pendingStatus.value) return;
  transitionSubmitting.value = true;
  try {
    bug.value = await transitionBug(bugId, pendingStatus.value, transitionComment.value);
    ElMessage.success('状态已更新');
    transitionDialogVisible.value = false;
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '流转失败'));
  } finally {
    transitionSubmitting.value = false;
  }
};

// 指派
const assignDialogVisible = ref(false);
const assignUserId = ref<number | null>(null);
const assignComment = ref('');
const assignSubmitting = ref(false);
const members = ref<ProjectMemberBrief[]>([]);

const loadMembers = async () => {
  try {
    members.value = await getProjectMembers(projectId);
  } catch {
    // 项目无权限或接口异常时不阻塞
  }
};

const confirmAssign = async () => {
  if (!assignUserId.value) return;
  assignSubmitting.value = true;
  try {
    bug.value = await assignBug(bugId, assignUserId.value, assignComment.value);
    ElMessage.success('已指派');
    assignDialogVisible.value = false;
    assignUserId.value = null;
    assignComment.value = '';
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '指派失败'));
  } finally {
    assignSubmitting.value = false;
  }
};

// 评论
const newComment = ref('');
const commentSubmitting = ref(false);

const submitComment = async () => {
  const content = newComment.value.trim();
  if (!content) return;
  commentSubmitting.value = true;
  try {
    await addBugComment(bugId, content);
    newComment.value = '';
    await loadDetail();
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '发表失败'));
  } finally {
    commentSubmitting.value = false;
  }
};

const goBack = () => router.push(`/projects/${projectId}/bugs`);
const formatTime = (t: string) => t ? new Date(t).toLocaleString() : '-';

const confirmDelete = async () => {
  try {
    await deleteBug(bugId);
    ElMessage.success('已删除');
    router.push(`/projects/${projectId}/bugs`);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '删除失败'));
  }
};

onMounted(() => {
  loadDetail();
  loadMembers();
});
</script>

<style scoped>
.bug-detail { padding: 0; }
.detail-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-border-light);
}
.header-left { display: flex; flex-direction: column; gap: 8px; }
.title-row { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.bug-id { font-size: 14px; color: var(--color-text-tertiary); font-weight: 500; }
.bug-title {
  margin: 0;
  font: 600 20px/1.3 var(--font-heading);
  color: var(--color-text);
  cursor: pointer;
}
.meta-row { display: flex; gap: 8px; align-items: center; margin-top: 4px; flex-wrap: wrap; }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; }
.content-grid {
  display: grid; grid-template-columns: 1fr 320px; gap: 16px;
}
.left-pane, .right-pane { display: flex; flex-direction: column; gap: 12px; }
.section-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.prop-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0; font-size: 13px;
  color: var(--color-text);
}
.prop-label { color: var(--color-text-secondary); }
.empty-hint {
  color: var(--color-text-tertiary);
  text-align: center; padding: 12px; font-size: 13px;
}
.comment-list { display: flex; flex-direction: column; gap: 12px; }
.comment-item {
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  padding: 12px 14px;
  border-radius: var(--radius-md);
}
.comment-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px;
  font-size: 13px;
}
.comment-time { color: var(--color-text-tertiary); font-size: 12px; }
.comment-body { white-space: pre-wrap; font-size: 13px; color: var(--color-text); }
.transition-comment {
  color: var(--color-text-secondary);
  margin-top: 4px;
  font-size: 13px;
}
.linked-task-chip {
  color: var(--color-text-secondary);
  font-size: 13px;
}
@media (max-width: 1000px) {
  .content-grid { grid-template-columns: 1fr; }
}
</style>
