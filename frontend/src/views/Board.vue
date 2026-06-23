<!--
看板主视图 —— 项目内默认首页。

功能：
  - 多列 Kanban 布局，任务卡片在列内/跨列拖拽
  - 搜索 + 负责人/标签筛选
  - 批量选择/删除/移动
  - 点击任务卡片打开 TaskDetailDrawer
  - 实时同步：拖拽/增删通过 boardStore → REST API → WebSocket 广播

路由：/projects/:projectId/board
-->
<template>
  <div class="board-wrapper">
    <!-- 工具栏 -->
    <div class="board-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchQuery"
          placeholder="搜索任务..."
          clearable
          class="search-input"
        >
          <template #prefix>
            <el-icon :size="14"><Search /></el-icon>
          </template>
        </el-input>

        <el-select
          v-model="filterAssignee"
          placeholder="筛选负责人"
          clearable
          class="filter-select"
        >
          <el-option
            v-for="user in projectMembers"
            :key="user.id"
            :label="user.username"
            :value="user.id"
          />
        </el-select>

        <el-select
          v-model="filterTags"
          placeholder="筛选标签"
          multiple
          collapse-tags
          clearable
          class="filter-select"
        >
          <el-option
            v-for="tag in boardStore.currentProject?.available_tags || []"
            :key="tag.id"
            :label="tag.name"
            :value="tag.id"
          >
            <span class="tag-option">
              <span class="color-dot" :style="{ background: tag.color }"></span>
              {{ tag.name }}
            </span>
          </el-option>
        </el-select>

        <el-button v-if="hasActiveFilters" link @click="clearFilters">
          <el-icon style="margin-right: 4px"><CircleClose /></el-icon>
          清除筛选
        </el-button>
      </div>

      <div class="toolbar-right">
        <template v-if="isBatchMode || selectedTasks.length > 0">
          <span v-if="selectedTasks.length > 0" class="batch-count">已选 {{ selectedTasks.length }}</span>
          <el-button
            v-if="selectedTasks.length > 0"
            size="small"
            type="danger"
            plain
            @click="handleBatchDelete"
          >
            <el-icon style="margin-right: 4px"><Delete /></el-icon>
            删除
          </el-button>
          <el-button size="small" @click="toggleBatchMode">
            {{ isBatchMode ? '退出选择' : '选择' }}
          </el-button>
        </template>
        <el-button v-else size="small" @click="toggleBatchMode">
          <el-icon style="margin-right: 4px"><Check /></el-icon>
          批量选择
        </el-button>

        <div class="status-indicator">
          <span class="status-dot" :class="{ online: boardStore.isConnected }"></span>
          <span class="status-text">{{ boardStore.isConnected ? '已连接' : '已断开' }}</span>
        </div>
      </div>
    </div>

    <!-- 看板内容 -->
    <div class="board-container">
      <draggable
        v-model="boardStore.Columns"
        group="columns"
        item-key="id"
        handle=".column-header"
        ghost-class="column-ghost"
        @end="onColumnDragEnd"
        class="columns-wrapper"
      >
        <template #item="{ element: col }">
          <div class="board-column">
            <div class="column-header">
              <div class="header-text">
                <h3 class="col-title">{{ col.title }}</h3>
                <span class="col-count">{{ getVisibleTasks(col).length }}</span>
              </div>
              <div class="header-right">
                <el-button link size="small" @click="handleAddTask(col.id)" title="新增任务">
                  <el-icon :size="16"><Plus /></el-icon>
                </el-button>
                <el-button link size="small" @click="openRenameColumnDialog(col)" title="重命名">
                  <el-icon :size="14"><Edit /></el-icon>
                </el-button>
                <el-button link size="small" type="danger" @click="handleDeleteColumn(col.id)" title="删除列">
                  <el-icon :size="14"><Delete /></el-icon>
                </el-button>
              </div>
            </div>

            <!-- 任务列表 -->
            <draggable
              class="task-list"
              v-model="col.tasks"
              group="tasks"
              item-key="id"
              ghost-class="ghost"
              :disabled="hasActiveFilters"
              @change="(event: any) => onDragChange(event, col.id)"
            >
              <template #item="{ element }">
                <div
                  v-if="isTaskVisible(element)"
                  class="task-card"
                  :class="{ 'selected': selectedTasks.includes(element.id) }"
                  @click="openTaskDetail(element)"
                >
                  <div class="task-title" v-html="highlightText(element.title, searchQuery)"></div>
                  <div v-if="element.content" class="task-content" v-html="highlightText(element.content, searchQuery)"></div>
                  <div class="tags-container" v-if="element.tags_details?.length">
                    <span
                      v-for="tag in element.tags_details"
                      :key="tag.id"
                      class="task-tag"
                      :style="{ background: tag.color + '14', color: tag.color, borderColor: tag.color + '40' }"
                    >{{ tag.name }}</span>
                  </div>
                  <div class="card-footer">
                    <div v-if="element.assignee_details" class="assignee">
                      <span class="assignee-avatar">{{ element.assignee_details.username?.charAt(0).toUpperCase() }}</span>
                      <span class="assignee-name">{{ element.assignee_details.username }}</span>
                    </div>
                    <div v-else class="assignee-placeholder"></div>
                    <div class="card-actions">
                      <el-checkbox
                        v-if="isBatchMode || selectedTasks.includes(element.id)"
                        v-model="selectedTasks"
                        :value="element.id"
                        @click.stop
                      />
                      <el-button
                        link
                        size="small"
                        type="danger"
                        class="task-delete-btn"
                        @click.stop="handleDeleteTask(element.id)"
                        title="删除任务"
                      >
                        <el-icon :size="14"><Delete /></el-icon>
                      </el-button>
                    </div>
                  </div>
                </div>
              </template>
            </draggable>
          </div>
        </template>
      </draggable>

      <!-- 添加列按钮 -->
      <div class="add-column-card" @click="addColumnDialogVisible = true">
        <el-icon :size="20"><Plus /></el-icon>
        <span class="add-label">添加新列</span>
      </div>
    </div>

    <!-- 任务详情弹窗 -->
    <el-dialog v-model="dialogVisible" title="任务详情" width="50%">
      <el-form :model="editingTask" label-position="top">
        <div class="form-field">
          <label class="form-label">标题</label>
          <el-input v-model="editingTask.title" placeholder="输入任务标题" />
        </div>
        <div class="form-field">
          <label class="form-label">执行人</label>
          <el-select v-model="editingTask.assignee" placeholder="选择负责人" clearable style="width: 100%">
            <el-option
              v-for="user in projectMembers"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
        </div>
        <div class="form-field">
          <label class="form-label">标签</label>
          <el-select v-model="editingTask.tags" multiple placeholder="选择标签" collapse-tags style="width: 100%">
            <el-option
              v-for="tag in boardStore.currentProject?.available_tags || []"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <span class="tag-option">
                <span class="color-dot" :style="{ background: tag.color }"></span>
                {{ tag.name }}
              </span>
            </el-option>
          </el-select>
        </div>
        <div class="form-field">
          <label class="form-label">详细信息</label>
          <el-input
            v-model="editingTask.content"
            type="textarea"
            :rows="6"
            placeholder="支持 Markdown 纯文本描述"
          />
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTaskDetail">保存修改</el-button>
      </template>
    </el-dialog>

    <!-- 添加列弹窗 -->
    <el-dialog v-model="addColumnDialogVisible" title="添加新列" width="420px">
      <div class="form-field">
        <label class="form-label">列标题</label>
        <el-input v-model="newColumnTitle" placeholder="请输入列标题" />
      </div>
      <template #footer>
        <el-button @click="addColumnDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddColumn">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- 新建任务弹窗 -->
    <el-dialog v-model="addTaskDialogVisible" title="新建任务" width="500px">
      <el-form :model="newTaskForm" label-position="top">
        <div class="form-field">
          <label class="form-label">标题</label>
          <el-input v-model="newTaskForm.title" placeholder="输入任务标题" />
        </div>
        <div class="form-field">
          <label class="form-label">描述</label>
          <el-input
            v-model="newTaskForm.content"
            type="textarea"
            :rows="3"
            placeholder="输入任务描述（可选）"
          />
        </div>
        <div class="form-field">
          <label class="form-label">负责人</label>
          <el-select v-model="newTaskForm.assignee" placeholder="选择负责人（可选）" clearable style="width: 100%">
            <el-option
              v-for="user in projectMembers"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
        </div>
        <div class="form-field">
          <label class="form-label">标签</label>
          <el-select v-model="newTaskForm.tags" multiple placeholder="选择标签（可选）" collapse-tags style="width: 100%">
            <el-option
              v-for="tag in boardStore.currentProject?.available_tags || []"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <span class="tag-option">
                <span class="color-dot" :style="{ background: tag.color }"></span>
                {{ tag.name }}
              </span>
            </el-option>
          </el-select>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="addTaskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddTask">创建任务</el-button>
      </template>
    </el-dialog>

    <!-- 重命名列弹窗 -->
    <el-dialog v-model="renameColumnDialogVisible" title="重命名列" width="420px">
      <div class="form-field">
        <label class="form-label">新标题</label>
        <el-input v-model="renameColumnTitle" placeholder="请输入新标题" />
      </div>
      <template #footer>
        <el-button @click="renameColumnDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleRenameColumn">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- 任务详情抽屉 -->
    <TaskDetailDrawer :task="detailTask" :visible="detailVisible" @close="detailVisible = false" @updated="onTaskUpdated" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useBoardStore } from '@/stores/board';
import { DEFAULT_POSITION } from '@/types/kanban';
import { highlightText } from '@/utils/sanitize';
import TaskDetailDrawer from '@/components/TaskDetailDrawer.vue';
import draggable from 'vuedraggable';
import { ElMessageBox, ElMessage } from 'element-plus';
import { Delete, Plus, Edit, CircleClose, Check, Search } from '@element-plus/icons-vue';

const route = useRoute();
const boardStore = useBoardStore();

const projectId = computed(() => route.params.projectId as string);

// ============ 状态变量 ============
const dialogVisible = ref(false);
const addColumnDialogVisible = ref(false);
const renameColumnDialogVisible = ref(false);
const addTaskDialogVisible = ref(false);
const newColumnTitle = ref('');
const renameColumnId = ref('');
const renameColumnTitle = ref('');
const selectedTasks = ref<string[]>([]);
const isBatchMode = ref(false);
const currentColumnId = ref('');

const newTaskForm = ref({
  title: '',
  content: '',
  assignee: null as number | null,
  tags: [] as number[],
});

const searchQuery = ref('');
const filterAssignee = ref<number | null>(null);
const filterTags = ref<number[]>([]);

const editingTask = ref({
  id: '',
  title: '',
  content: '',
  column: '',
  assignee: null as number | null,
  tags: [] as number[],
});

const hasActiveFilters = computed(() => {
  return filterAssignee.value !== null || filterTags.value.length > 0 || searchQuery.value.trim() !== '';
});

const projectMembers = computed(() => {
  const owner = boardStore.currentProject?.owner_details;
  const members = (boardStore.currentProject?.members_details || []).map((u: any) => ({
    id: u.id,
    username: u.username,
    profile: u.profile,
  }));
  const all = owner ? [{ id: owner.id, username: owner.username, profile: owner.profile }, ...members] : members;
  const seen = new Set<number>();
  return all.filter((u: any) => u && u.id != null && !seen.has(u.id) && seen.add(u.id));
});

const getVisibleTasks = (col: any) => {
  if (!col.tasks) return [];
  if (!hasActiveFilters.value) return col.tasks;
  return col.tasks.filter((task: any) => isTaskVisible(task));
};

const isTaskVisible = (task: any) => {
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase();
    const titleMatch = task.title?.toLowerCase().includes(query);
    const contentMatch = task.content?.toLowerCase().includes(query);
    if (!titleMatch && !contentMatch) return false;
  }
  if (filterAssignee.value !== null && task.assignee !== filterAssignee.value) {
    return false;
  }
  if (filterTags.value.length > 0) {
    const hasMatchingTag = filterTags.value.some((tagId) => task.tags?.includes(tagId));
    if (!hasMatchingTag) return false;
  }
  return true;
};

const clearFilters = () => {
  searchQuery.value = '';
  filterAssignee.value = null;
  filterTags.value = [];
};

const toggleBatchMode = () => {
  isBatchMode.value = !isBatchMode.value;
  if (!isBatchMode.value) {
    selectedTasks.value = [];
  }
};

const handleBatchDelete = async () => {
  if (selectedTasks.value.length === 0) return;
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedTasks.value.length} 个任务吗？`,
      '批量删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    );
    const ok = await boardStore.batchDeleteTasks(selectedTasks.value);
    if (ok) selectedTasks.value = [];
  } catch (e) {}
};

const handleAddColumn = async () => {
  if (!newColumnTitle.value.trim()) {
    ElMessage.warning('请输入列标题');
    return;
  }
  await boardStore.createColumn(projectId.value, newColumnTitle.value);
  newColumnTitle.value = '';
  addColumnDialogVisible.value = false;
};

const openRenameColumnDialog = (col: any) => {
  renameColumnId.value = col.id;
  renameColumnTitle.value = col.title;
  renameColumnDialogVisible.value = true;
};

const handleRenameColumn = async () => {
  if (!renameColumnTitle.value.trim()) {
    ElMessage.warning('请输入列标题');
    return;
  }
  await boardStore.renameColumn(renameColumnId.value, renameColumnTitle.value);
  renameColumnDialogVisible.value = false;
};

const handleDeleteColumn = async (columnId: string) => {
  try {
    await ElMessageBox.confirm('确定要删除此列吗？列下的所有任务也会被删除。', '删除列', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await boardStore.deleteColumn(columnId);
  } catch (e) {}
};

const handleAddTask = (columnId: string) => {
  currentColumnId.value = columnId;
  newTaskForm.value = {
    title: '',
    content: '',
    assignee: null,
    tags: [],
  };
  addTaskDialogVisible.value = true;
};

const confirmAddTask = async () => {
  if (!newTaskForm.value.title.trim()) {
    ElMessage.warning('请输入任务标题');
    return;
  }
  try {
    await boardStore.createTask(currentColumnId.value, newTaskForm.value.title, {
      content: newTaskForm.value.content,
      assignee: newTaskForm.value.assignee,
      tags: newTaskForm.value.tags,
    });
    ElMessage.success('任务已创建');
    addTaskDialogVisible.value = false;
  } catch (e) {
    console.error(e);
  }
};

const handleDeleteTask = async (taskID: string) => {
  try {
    await ElMessageBox.confirm('确定要删除此任务吗？', '删除任务', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    const ok = await boardStore.deleteTask(taskID);
    if (ok) ElMessage.success('任务已删除');
  } catch (e) {}
};

const detailTask = ref<any>(null);
const detailVisible = ref(false);

const openTaskDetail = (task: any) => {
  detailTask.value = task;
  detailVisible.value = true;
};

const onTaskUpdated = async () => {
  if (projectId.value) {
    await boardStore.fetchColumns(projectId.value);
    if (detailTask.value) {
      for (const col of boardStore.Columns) {
        const found = col.tasks?.find((t: any) => t.id === detailTask.value.id);
        if (found) {
          detailTask.value = found;
          break;
        }
      }
    }
  }
};

const saveTaskDetail = async () => {
  if (!editingTask.value.title) {
    ElMessage.warning('任务标题不能为空');
    return;
  }
  try {
    await boardStore.updateTask(editingTask.value.id, {
      title: editingTask.value.title,
      content: editingTask.value.content,
      assignee: editingTask.value.assignee,
      tags: editingTask.value.tags,
    });
    ElMessage.success('任务更新成功');
    dialogVisible.value = false;
  } catch (e) {
    console.error(e);
  }
};

const calculatePosition = (tasks: any[], newIndex: number): number => {
  const prevTask = tasks[newIndex - 1];
  const nextTask = tasks[newIndex + 1];
  if (!prevTask && !nextTask) return DEFAULT_POSITION;
  if (!prevTask) return nextTask.position / 2;
  if (!nextTask) return prevTask.position + DEFAULT_POSITION;
  return (prevTask.position + nextTask.position) / 2;
};

const onDragChange = (event: any, columnId: string) => {
  if (event.added) {
    const task = event.added.element;
    const newIndex = event.added.newIndex;
    const column = boardStore.Columns.find((col) => col.id === columnId);
    if (column) {
      const newPos = calculatePosition(column.tasks, newIndex);
      boardStore.updateTask(task.id, { column: columnId, position: newPos });
    }
  }
  if (event.moved) {
    const { element, newIndex } = event.moved;
    const column = boardStore.Columns.find((col) => col.id === columnId);
    if (column) {
      const newPos = calculatePosition(column.tasks, newIndex);
      boardStore.updateTask(element.id, { position: newPos });
    }
  }
};

const onColumnDragEnd = async (event: any) => {
  const { newIndex } = event;
  const columns = boardStore.Columns;
  const prevColumn = columns[newIndex - 1];
  const nextColumn = columns[newIndex + 1];
  let newPos = 0;

  if (!prevColumn && !nextColumn) newPos = DEFAULT_POSITION;
  else if (!prevColumn) newPos = nextColumn!.position / 2;
  else if (!nextColumn) newPos = prevColumn.position + DEFAULT_POSITION;
  else newPos = (prevColumn.position + nextColumn.position) / 2;

  const movedColumn = columns[newIndex];
  if (movedColumn) {
    await boardStore.renameColumn(movedColumn.id, movedColumn.title, newPos);
  }
};

onMounted(() => {
  if (projectId.value) {
    boardStore.currentProjectId = projectId.value;
    boardStore.fetchColumns(projectId.value);
    boardStore.fetchUsers();
    boardStore.initSocket(projectId.value);
  }
});
</script>

<style scoped>
.board-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 144px);
}

/* ── Toolbar ── */
.board-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--color-border-light);
  gap: 16px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.search-input {
  width: 240px;
}

.filter-select {
  width: 160px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-count {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-text-tertiary);
}

.status-dot.online {
  background-color: var(--color-success);
}

.tag-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

/* ── Board container ── */
.board-container {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  flex: 1;
  padding-bottom: 16px;
}

.columns-wrapper {
  display: flex;
  gap: 16px;
}

/* ── Column ── */
.board-column {
  min-width: 320px;
  max-width: 320px;
  background: var(--color-surface-sunken);
  display: flex;
  flex-direction: column;
  max-height: 100%;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.column-header {
  padding: 12px 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: grab;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-surface);
}

.column-header:active {
  cursor: grabbing;
}

.header-text {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.col-title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-count {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-weight: 500;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border-light);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  min-width: 24px;
  text-align: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* ── Task list ── */
.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 50px;
}

/* ── Task card ── */
.task-card {
  margin-bottom: 8px;
  cursor: pointer;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: 12px 14px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.task-card:last-child {
  margin-bottom: 0;
}

.task-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.task-card.selected {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.task-title {
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.4;
  margin-bottom: 6px;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.task-content {
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  margin-bottom: 8px;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.task-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
  min-height: 24px;
}

.assignee {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.assignee-placeholder {
  flex: 1;
}

.assignee-avatar {
  width: 22px;
  height: 22px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.assignee-name {
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.task-delete-btn {
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.task-card:hover .task-delete-btn {
  opacity: 1;
}

/* ── Add column ── */
.add-column-card {
  min-width: 280px;
  height: 100px;
  background: transparent;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
  gap: 8px;
  color: var(--color-text-tertiary);
}

.add-column-card:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-bg);
}

.add-label {
  font-size: 13px;
  font-weight: 500;
}

/* ── Drag states ── */
.ghost {
  opacity: 0.4;
  background: var(--color-primary-bg);
  border: 1px dashed var(--color-primary);
}

.column-ghost {
  opacity: 0.4;
  background: var(--color-primary-bg);
  border: 1px dashed var(--color-primary);
}
</style>
