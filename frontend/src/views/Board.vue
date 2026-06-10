<template>
  <div class="board-wrapper">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <div class="search-box">
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
        </div>

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
            <span :style="{ color: tag.color, fontWeight: 600 }">● {{ tag.name }}</span>
          </el-option>
        </el-select>

        <button
          v-if="hasActiveFilters"
          class="text-btn"
          @click="clearFilters"
        >
          <el-icon :size="12"><CircleClose /></el-icon>
          清除筛选
        </button>
      </div>

      <div class="toolbar-right">
        <div v-if="isBatchMode || selectedTasks.length > 0" class="batch-toolbar">
          <span v-if="selectedTasks.length > 0" class="batch-count">{{ selectedTasks.length }} 已选</span>
          <button v-if="selectedTasks.length > 0" class="ghost-btn ghost-btn-danger" @click="handleBatchDelete">
            <el-icon :size="12"><Delete /></el-icon>
            删除
          </button>
          <button class="ghost-btn" @click="toggleBatchMode">
            <el-icon :size="12"><Check /></el-icon>
            {{ isBatchMode ? '退出' : '选择' }}
          </button>
        </div>
        <button v-else class="ghost-btn" @click="toggleBatchMode">
          <el-icon :size="12"><Check /></el-icon>
          批量选择
        </button>

        <div class="status-indicator">
          <span class="status-dot" :class="{ online: boardStore.isConnected }"></span>
          <span class="status-text">{{ boardStore.isConnected ? '已连接' : '断开' }}</span>
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
        <template #item="{ element: col, index }">
          <div class="board-column" :class="'col-index-' + (index % 4)">
            <div class="column-accent-bar"></div>
            <div class="column-header">
              <div class="header-text">
                <span class="col-folio">N° {{ String(index + 1).padStart(2, '0') }}</span>
                <h3 class="col-title">{{ col.title }}</h3>
              </div>
              <div class="header-right">
                <span class="col-count">{{ String(getVisibleTasks(col).length).padStart(2, '0') }}</span>
                <button class="col-icon-btn" @click="handleAddTask(col.id)" title="新增任务">
                  <el-icon :size="16"><Plus /></el-icon>
                </button>
                <button class="col-icon-btn" @click="openRenameColumnDialog(col)" title="重命名">
                  <el-icon :size="14"><Edit /></el-icon>
                </button>
                <button class="col-icon-btn col-icon-btn-danger" @click="handleDeleteColumn(col.id)" title="删除列">
                  <el-icon :size="14"><Delete /></el-icon>
                </button>
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
                  <div class="card-meta">
                    <span class="task-folio">T-{{ String(element.id).slice(-3).padStart(3, '0') }}</span>
                    <div v-if="isBatchMode || selectedTasks.includes(element.id)" class="checkbox-wrap">
                      <el-checkbox v-model="selectedTasks" :label="element.id" @click.stop size="large" />
                    </div>
                    <button class="task-delete-btn" @click.stop="handleDeleteTask(element.id)" title="删除任务">
                      <el-icon :size="14"><Delete /></el-icon>
                    </button>
                  </div>
                  <div class="task-title" v-html="highlightText(element.title, searchQuery)"></div>
                  <div v-if="element.content" class="task-content" v-html="highlightText(element.content, searchQuery)"></div>
                  <div class="tags-container" v-if="element.tags_details?.length">
                    <span
                      v-for="tag in element.tags_details"
                      :key="tag.id"
                      class="task-tag"
                      :style="{ background: tag.color + '14', color: tag.color }"
                    >{{ tag.name }}</span>
                  </div>
                  <div class="card-footer" v-if="element.assignee_details">
                    <span class="assignee-avatar">{{ element.assignee_details.username?.charAt(0).toUpperCase() }}</span>
                    <span class="assignee-name">{{ element.assignee_details.username }}</span>
                  </div>
                </div>
              </template>
            </draggable>
          </div>
        </template>
      </draggable>

      <!-- 添加列按钮 -->
      <div class="add-column-card" @click="addColumnDialogVisible = true">
        <span class="add-folio">N° +</span>
        <span class="add-label">添加新列</span>
      </div>
    </div>

    <!-- 任务详情弹窗 -->
    <el-dialog v-model="dialogVisible" width="50%" class="app-dialog" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-folio">EDIT</span>
          <span class="dialog-title">任务详情</span>
        </div>
      </template>
      <el-form :model="editingTask" label-position="top">
        <el-form-item required>
          <template #label><span class="form-label">标题</span></template>
          <el-input v-model="editingTask.title" placeholder="输入标题" />
        </el-form-item>
        <el-form-item>
          <template #label><span class="form-label">执行人</span></template>
          <el-select v-model="editingTask.assignee" placeholder="选择负责人" clearable>
            <el-option
              v-for="user in projectMembers"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label><span class="form-label">标签</span></template>
          <el-select v-model="editingTask.tags" multiple placeholder="选择标签" collapse-tags>
            <el-option
              v-for="tag in boardStore.currentProject?.available_tags || []"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <span :style="{ color: tag.color, fontWeight: 600 }">● {{ tag.name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label><span class="form-label">详细信息</span></template>
          <el-input
            v-model="editingTask.content"
            type="textarea"
            :rows="6"
            placeholder="支持Markdown纯文本描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <button class="text-btn" @click="dialogVisible = false">取消</button>
          <button class="primary-btn" @click="saveTaskDetail">保存修改</button>
        </div>
      </template>
    </el-dialog>

    <!-- 添加列弹窗 -->
    <el-dialog v-model="addColumnDialogVisible" width="30%" class="app-dialog" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-folio">NEW</span>
          <span class="dialog-title">添加新列</span>
        </div>
      </template>
      <el-input v-model="newColumnTitle" placeholder="请输入列标题" />
      <template #footer>
        <div class="dialog-footer">
          <button class="text-btn" @click="addColumnDialogVisible = false">取消</button>
          <button class="primary-btn" @click="handleAddColumn">确认添加</button>
        </div>
      </template>
    </el-dialog>

    <!-- 新建任务弹窗 -->
    <el-dialog v-model="addTaskDialogVisible" width="500px" class="app-dialog" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-folio">NEW</span>
          <span class="dialog-title">新建任务</span>
        </div>
      </template>
      <el-form :model="newTaskForm" label-position="top">
        <el-form-item required>
          <template #label><span class="form-label">标题</span></template>
          <el-input v-model="newTaskForm.title" placeholder="输入任务标题" />
        </el-form-item>
        <el-form-item>
          <template #label><span class="form-label">描述</span></template>
          <el-input
            v-model="newTaskForm.content"
            type="textarea"
            :rows="3"
            placeholder="输入任务描述（可选）"
          />
        </el-form-item>
        <el-form-item>
          <template #label><span class="form-label">负责人</span></template>
          <el-select v-model="newTaskForm.assignee" placeholder="选择负责人（可选）" clearable style="width: 100%">
            <el-option
              v-for="user in projectMembers"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label><span class="form-label">标签</span></template>
          <el-select v-model="newTaskForm.tags" multiple placeholder="选择标签（可选）" collapse-tags style="width: 100%">
            <el-option
              v-for="tag in boardStore.currentProject?.available_tags || []"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <span :style="{ color: tag.color, fontWeight: 600 }">● {{ tag.name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <button class="text-btn" @click="addTaskDialogVisible = false">取消</button>
          <button class="primary-btn" @click="confirmAddTask">创建任务</button>
        </div>
      </template>
    </el-dialog>

    <!-- 重命名列弹窗 -->
    <el-dialog v-model="renameColumnDialogVisible" width="30%" class="app-dialog" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-folio">EDIT</span>
          <span class="dialog-title">重命名列</span>
        </div>
      </template>
      <el-input v-model="renameColumnTitle" placeholder="请输入新标题" />
      <template #footer>
        <div class="dialog-footer">
          <button class="text-btn" @click="renameColumnDialogVisible = false">取消</button>
          <button class="primary-btn" @click="handleRenameColumn">确认修改</button>
        </div>
      </template>
    </el-dialog>

    <!-- 任务详情抽屉 -->
    <TaskDetailDrawer :task="detailTask" :visible="detailVisible" @close="detailVisible = false" @updated="onTaskUpdated" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useBoardStore } from '@/stores/board';
import { DEFAULT_POSITION } from '@/types/kanban';
import { highlightText, sanitizeText } from '@/utils/sanitize';
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

// 新建任务表单
const newTaskForm = ref({
  title: '',
  content: '',
  assignee: null as number | null,
  tags: [] as number[],
});

// 搜索和筛选
const searchQuery = ref('');
const filterAssignee = ref<number | null>(null);
const filterTags = ref<number[]>([]);

// 编辑任务
const editingTask = ref({
  id: '',
  title: '',
  content: '',
  column: '',
  assignee: null as number | null,
  tags: [] as number[],
});

// ============ 计算属性 ============
const hasActiveFilters = computed(() => {
  return filterAssignee.value !== null || filterTags.value.length > 0 || searchQuery.value.trim() !== '';
});

// 项目成员（owner + members，去重）
const projectMembers = computed(() => {
  const owner = boardStore.currentProject?.owner_details;
  const members = (boardStore.currentProject?.members_details || []).map((u: any) => ({
    id: u.id,
    username: u.username,
    profile: u.profile,
  }));
  const all = owner ? [{ id: owner.id, username: owner.username, profile: owner.profile }, ...members] : members;
  const seen = new Set<number>();
  return all.filter((u) => u && u.id != null && !seen.has(u.id) && seen.add(u.id));
});

// ============ 方法 ============
const getVisibleTasks = (col: any) => {
  if (!col.tasks) return [];
  if (!hasActiveFilters.value) return col.tasks;
  return col.tasks.filter((task: any) => isTaskVisible(task));
};

const isTaskVisible = (task: any) => {
  // 搜索筛选
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase();
    const titleMatch = task.title?.toLowerCase().includes(query);
    const contentMatch = task.content?.toLowerCase().includes(query);
    if (!titleMatch && !contentMatch) return false;
  }

  // 负责人筛选
  if (filterAssignee.value !== null && task.assignee !== filterAssignee.value) {
    return false;
  }

  // 标签筛选
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

const clearSelection = () => {
  selectedTasks.value = [];
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
    // Sync detailTask with fresh data after save
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
  else if (!prevColumn) newPos = nextColumn.position / 2;
  else if (!nextColumn) newPos = prevColumn.position + DEFAULT_POSITION;
  else newPos = (prevColumn.position + nextColumn.position) / 2;

  const movedColumn = columns[newIndex];
  if (movedColumn) {
    await boardStore.renameColumn(movedColumn.id, movedColumn.title, newPos);
  }
};

// ============ 生命周期 ============
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

/* ============ Toolbar — hairline bottom, no card ============ */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0 16px;
  background: transparent;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 24px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-box {
  display: flex;
  align-items: center;
}

.search-input {
  width: 240px;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 0;
  box-shadow: 0 0 0 1px var(--color-border);
  background: transparent;
  transition: box-shadow var(--transition-fast);
}

.search-input :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--color-text-tertiary);
}

.search-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--color-text);
}

.search-input :deep(.el-input__inner) {
  font-variant-numeric: tabular-nums;
}

.filter-select {
  width: 160px;
}

.filter-select :deep(.el-input__wrapper) {
  border-radius: 0;
  box-shadow: 0 0 0 1px var(--color-border);
  background: transparent;
}

.filter-select :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--color-text-tertiary);
}

.filter-select :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--color-text);
}

.text-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 0;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  transition: color var(--transition-fast);
}

.text-btn:hover {
  color: var(--color-text);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-count {
  font: 500 11px/1 var(--font-mono);
  color: var(--color-accent);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 12px;
  background: transparent;
  border: 1px solid var(--color-border);
  cursor: pointer;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  transition: all var(--transition-fast);
}

.ghost-btn:hover {
  color: var(--color-text);
  border-color: var(--color-text);
}

.ghost-btn.ghost-btn-danger:hover {
  color: var(--color-danger);
  border-color: var(--color-danger);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font: 500 11px/1 var(--font-mono);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--color-text-tertiary);
}

.status-dot.online {
  background-color: var(--color-success);
}

/* ============ Board container ============ */
.board-container {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  flex: 1;
  padding: 0 0 24px;
}

.columns-wrapper {
  display: flex;
  gap: 16px;
}

/* ============ Column ============ */
.board-column {
  min-width: 320px;
  max-width: 320px;
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  max-height: 100%;
  border: 1px solid var(--color-border);
  position: relative;
}

.column-accent-bar {
  height: 2px;
  flex-shrink: 0;
  background: var(--color-border);
}

.col-index-0 .column-accent-bar { background: var(--color-accent-bar-0); }
.col-index-1 .column-accent-bar { background: var(--color-accent-bar-1); }
.col-index-2 .column-accent-bar { background: var(--color-accent-bar-2); }
.col-index-3 .column-accent-bar { background: var(--color-accent-bar-3); }

.column-header {
  padding: 16px 14px 12px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  cursor: grab;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-surface);
}

.column-header:active {
  cursor: grabbing;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.col-folio {
  font: 600 10px/1 var(--font-mono);
  letter-spacing: 0.12em;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  text-transform: uppercase;
}

.col-title {
  margin: 0;
  font: 600 14px/1.2 var(--font-heading);
  color: var(--color-text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.col-count {
  font: 500 11px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  padding: 4px 6px;
  border: 1px solid var(--color-border);
  margin-right: 6px;
  min-width: 28px;
  text-align: center;
}

.col-icon-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  color: var(--color-text-tertiary);
  transition: all var(--transition-fast);
  border-radius: 0;
  padding: 0;
}

.col-icon-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border);
}

.col-icon-btn.col-icon-btn-danger:hover {
  color: var(--color-danger);
  border-color: var(--color-danger);
}

/* ============ Task list ============ */
.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 50px;
  background: var(--color-surface-sunken);
}

/* ============ Task card ============ */
.task-card {
  margin-bottom: 8px;
  cursor: pointer;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 0;
  padding: 12px 14px;
  transition: border-color var(--transition-fast);
  position: relative;
}

.task-card:last-child {
  margin-bottom: 0;
}

.task-card:hover {
  border-color: var(--color-text);
}

.task-card.selected {
  border-color: var(--color-accent);
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  min-height: 16px;
  gap: 8px;
}

.task-folio {
  font: 500 10px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.08em;
  font-variant-numeric: tabular-nums;
  text-transform: uppercase;
}

.checkbox-wrap {
  margin-left: auto;
}

.task-delete-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-tertiary);
  padding: 2px;
  margin-left: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all var(--transition-fast);
}

.checkbox-wrap + .task-delete-btn {
  margin-left: 0;
}

.task-card:hover .task-delete-btn {
  opacity: 1;
}

.task-delete-btn:hover {
  color: var(--color-danger);
}

.task-title {
  font: 600 13px/1.5 var(--font-heading);
  color: var(--color-text);
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
  padding: 2px 6px;
  font: 500 10px/1.4 var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
}

.assignee-avatar {
  width: 20px;
  height: 20px;
  background: var(--color-text);
  color: var(--color-text-inverse);
  font: 600 10px/1 var(--font-mono);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.assignee-name {
  font: 500 11px/1 var(--font-body);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ============ Add column ============ */
.add-column-card {
  min-width: 320px;
  height: 88px;
  background: transparent;
  border: 1px dashed var(--color-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color var(--transition-fast);
  gap: 8px;
}

.add-column-card:hover {
  border-color: var(--color-text);
}

.add-column-card:hover .add-folio,
.add-column-card:hover .add-label {
  color: var(--color-text);
}

.add-folio {
  font: 600 11px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.12em;
  font-variant-numeric: tabular-nums;
  text-transform: uppercase;
  transition: color var(--transition-fast);
}

.add-label {
  font: 500 12px/1 var(--font-heading);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  transition: color var(--transition-fast);
}

/* ============ Drag states ============ */
.ghost {
  opacity: 0.4;
  background: var(--color-bg);
  border: 1px dashed var(--color-text-tertiary);
}

.column-ghost {
  opacity: 0.4;
  background: var(--color-bg);
  border: 1px dashed var(--color-text-tertiary);
}

/* ============ App Dialog — Swiss form ============ */
.app-dialog {
  --el-dialog-bg-color: var(--color-surface);
  --el-dialog-padding-primary: 0;
}

.app-dialog :deep(.el-dialog) {
  border-radius: 0;
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-md);
}

.app-dialog :deep(.el-dialog__header) {
  padding: 18px 24px;
  margin: 0;
  border-bottom: 1px solid var(--color-border);
}

.app-dialog :deep(.el-dialog__title) {
  display: none;
}

.app-dialog :deep(.el-dialog__headerbtn) {
  display: none;
}

.app-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.app-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--color-border);
  margin: 0;
}

.dialog-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.dialog-folio {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.dialog-title {
  font: 600 15px/1 var(--font-heading);
  color: var(--color-text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.form-label {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-secondary);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.app-dialog :deep(.el-form-item__label) {
  padding-bottom: 8px;
  line-height: 1;
  font-weight: normal;
}

.app-dialog :deep(.el-form-item) {
  margin-bottom: 20px;
}

.app-dialog :deep(.el-input__wrapper),
.app-dialog :deep(.el-textarea__wrapper) {
  border-radius: 0;
  box-shadow: 0 1px 0 0 var(--color-border);
  background: transparent;
  padding-left: 0;
  padding-right: 0;
  transition: box-shadow var(--transition-fast);
}

.app-dialog :deep(.el-input__wrapper:hover),
.app-dialog :deep(.el-textarea__wrapper:hover) {
  box-shadow: 0 1px 0 0 var(--color-text-tertiary);
}

.app-dialog :deep(.el-input__wrapper.is-focus),
.app-dialog :deep(.el-textarea__wrapper.is-focus) {
  box-shadow: 0 1px 0 0 var(--color-text);
}

.app-dialog :deep(.el-input__inner),
.app-dialog :deep(.el-textarea__inner) {
  font-variant-numeric: tabular-nums;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  align-items: center;
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 20px;
  background: var(--color-text);
  border: 1px solid var(--color-text);
  color: var(--color-text-inverse);
  cursor: pointer;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.primary-btn:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.dialog-footer .text-btn {
  font-size: 11px;
}
</style>
