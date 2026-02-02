<template>
  <div class="board-wrapper">
    <div class="status-bar">
      <div class="left-section">
        <el-button 
          icon="Back" 
          circle 
          size="small" 
          style="margin-right: 15px"
          @click="router.push('/projects')"
        />
      </div>
      
      <div class="right-section" style="display:flex; align-items:center; gap:10px">
        <div class="members-list" v-if="boardStore.currentProject">
          <div class="avatar-circle owner" :title="'负责人: ' + boardStore.currentProject.owner_details.username">
              {{ boardStore.currentProject.owner_details.username.substring(0,2).toUpperCase() }}
          </div>
          <div 
              v-for="member in boardStore.currentProject.members_details" 
              :key="member.id"
              class="avatar-circle member"
              :title="'成员: ' + member.username"
          >
              {{ member.username.substring(0,2).toUpperCase() }}
          </div>
        </div>

        <el-button type="success" plain @click="openTestConsole">
          <el-icon style="margin-right: 5px"><Cpu /></el-icon>
          质量中心
        </el-button>

        <el-button type="primary" icon="Plus" @click="inviteDialogVisible = true">
          邀请成员
        </el-button>
      </div>

      <div class="status-indicator">
        <span class="dot" :class="{ online: boardStore.isConnected }"></span>
        <span>{{ boardStore.isConnected ? '实时连接正常' : '连接断开 (正在重连...)' }}</span>
      </div>
      
      <div class="user-profile">
            <span class="username">
              Hi, {{ authStore.user?.username }}
            </span>
            <el-button type="danger" link size="small" @click="handleLogout">
            退出登录
        </el-button>
      </div>
    </div>

    <div class="board-container">
      <div v-for="col in boardStore.Columns" :key="col.id" class="board-column">
        <div class="column-header">
          <div class="header-left">
            <h3>{{ col.title }}</h3>
            <span class="count">{{ col.tasks?.length || 0 }}</span>
          </div>

          <div class="header-right" style="display: flex; align-items: center; gap: 5px;">
            <el-tooltip content="[QA工具] 一键生成测试数据" placement="top">
              <el-button type="warning" link class="qa-btn" @click="handleDataFactory(col.id)">
                <el-icon :size="18"><MagicStick /></el-icon>
              </el-button>
            </el-tooltip>
            <el-button type="primary" link class="add-btn" @click="handleAddTask(col.id)">
              <el-icon :size="20"><Plus /></el-icon>
            </el-button>
          </div>
        </div>

        <draggable
          class="task-list"
          v-model="col.tasks"
          group="tasks"
          item-key="id"
          ghost-class="ghost"
          @change="(event:any) => onDragChange(event, col.id)"
        >
          <template #item="{ element }">
            <el-card class="task-card" shadow="hover" @click="openTaskDetail(element)">
              <template #header>
                <div class="card-header">
                  <span>{{ element.title }}</span>
                  <el-icon class="delete-btn" @click.stop="handleDeleteTask(element.id)">
                      <Delete />
                  </el-icon>
                </div>
              </template>
              <div class="tags-container" v-if="element.tags_details && element.tags_details.length">
                  <el-tag v-for="tag in element.tags_details" :key="tag.id" size="small" :color="tag.color" effect="dark" style="margin-right: 4px; border: none;">
                    {{ tag.name }}
                  </el-tag>
                </div>
                <div class="card-content">{{ element.content }}</div>
              <div class="card-footer" v-if="element.assignee">
                <div class="avatar-circle" :title="'User ID: ' + element.assignee">
                  {{ getUserName(element.assignee) }}
              </div>
              </div>
            </el-card>
          </template>
        </draggable>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" title="任务详情" width="50%" :before-close="handleClose">
      <el-form :model="editingTask" label-position="top">
        <el-form-item label="标题">
          <el-input v-model="editingTask.title" placeholder="输入标题"/>
        </el-form-item>
        <el-form-item label="执行人">
          <el-select v-model="editingTask.assignee" placeholder="选择负责人" clearable>
            <el-option v-for="user in boardStore.Users" :key="user.id" :label="user.username" :value="user.id"/>
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
            <el-select v-model="editingTask.tags" multiple placeholder="选择标签" collapse-tags>
              <el-option v-for="tag in boardStore.currentProject?.available_tags || []" :key="tag.id" :label="tag.name" :value="tag.id">
                <span :style="{ color: tag.color, fontWeight: 'bold' }">● {{ tag.name }}</span>
              </el-option>
            </el-select>
        </el-form-item>
        <el-form-item label="详细信息">
          <el-input v-model="editingTask.content" type="textarea" :rows="6" placeholder="支持Markdown纯文本描述"></el-input>
        </el-form-item>
      </el-form> 
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button @click="saveTaskDetail" type="primary">保存修改</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="inviteDialogVisible" title="邀请成员" width="30%">
      <el-input v-model="inviteUsername" placeholder="请输入要邀请成员的用户名"></el-input>
      <template #footer>
        <el-button @click="inviteDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleInvite">确认邀请</el-button>
      </template>
    </el-dialog>

    <TestConsole ref="testConsoleRef" />

  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useBoardStore } from '@/stores/Board';
import draggable from 'vuedraggable';
import { ElMessageBox, ElMessage } from 'element-plus';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/Auth';
import service from '@/utils/request';
import { Delete, Plus, Back,MagicStick } from '@element-plus/icons-vue'; // 确保引入图标
import { ElLoading } from 'element-plus';
import TestConsole from '@/components/TestConsole.vue';
import { Cpu } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const boardStore = useBoardStore();
const authStore = useAuthStore();

// 状态变量 (修复了 Visable -> Visible 拼写)
const dialogVisible = ref(false);
const inviteDialogVisible = ref(false);
const inviteUsername = ref("");

const editingTask = ref({
  id: '',
  title: "",
  content: '',
  column: '',
  assignee: null as number | null,
  tags: [] as number[],
});

const testConsoleRef = ref<InstanceType<typeof TestConsole> | null>(null);

// 3. 打开控制台的方法
const openTestConsole = () => {
  if (testConsoleRef.value) {
    testConsoleRef.value.open();
  }
};

onMounted(() => {
  const projectId = route.params.projectId as string;
  if (projectId) {
    boardStore.currentProjectId = projectId; // 确保 store 知道当前 id
    boardStore.fetchColumns(projectId);
    boardStore.fetchProjectInfo(projectId);
    boardStore.initSocket(projectId); // 注意：如果 websocket 需要房间号，请确认 initSocket 实现
    boardStore.fetchUsers();
  }
});

// ✨ 修复4：邀请逻辑修正
const handleInvite = async () => {
  if (!inviteUsername.value) {
    ElMessage.warning("请输入用户名");
    return;
  }
  try {
    // ✨ 关键修复：URL 中间加了斜杠 '/'
    await service.post('/api/projects/' + boardStore.currentProjectId + '/invite/', {
      username: inviteUsername.value
    });
    ElMessage.success("邀请发送成功");
    inviteDialogVisible.value = false;
    inviteUsername.value = ""; // 清空输入框
  } catch (e: any) {
    console.error(e);
    // 尝试显示后端返回的具体错误
    const msg = e.response?.data?.detail || "邀请失败";
    ElMessage.error(msg);
  }
};

const openTaskDetail = (task: any) => {
  const tagIds = task.tags_details ? task.tags_details.map((t: any) => t.id) : [];
  editingTask.value = { ...task, tags: tagIds };
  dialogVisible.value = true;
};

const handleClose = (done: () => void) => {
  done();
};

const saveTaskDetail = async () => {
  if (!editingTask.value.title) {
    ElMessage.warning("任务标题不能为空");
    return;
  }
  try {
    await boardStore.updateTask(editingTask.value.id, {
      title: editingTask.value.title,
      content: editingTask.value.content,
      assignee: editingTask.value.assignee,
      tags: editingTask.value.tags
    });
    ElMessage.success("任务更新成功");
    dialogVisible.value = false;
  } catch (e) {
    console.error(e);
  }
};

const handleDataFactory = async (columnId: string) => {
  try {
    const { value } = await ElMessageBox.prompt('请输入要生成的任务数量 (1-1000)', 'QA 数据工厂', {
      confirmButtonText: '立即生成',
      cancelButtonText: '取消',
      inputPattern: /^(?:[1-9][0-9]{0,2}|1000)$/,
      inputErrorMessage: '请输入 1-1000 之间的整数',
      inputValue: '10'
    });

    if (value) {
      // 开启全屏 Loading
      const loading = ElLoading.service({
        lock: true,
        text: `正在生产 ${value} 条测试数据，请稍候...`,
        background: 'rgba(0, 0, 0, 0.7)',
      });

      try {
        await service.post('/api/qa/data-factory/', {
          column_id: columnId,
          count: parseInt(value)
        });

        // 刷新数据
        await boardStore.fetchColumns(boardStore.currentProjectId);

        ElMessage.success(`成功生成 ${value} 条数据！`);
      } finally {
        // 无论成功失败，都关闭 Loading
        loading.close();
      }
    }
  } catch (e) {
    // Cancelled
  }
};

const getUserName = (userId: number) => {
  const user = boardStore.Users.find(u => u.id === userId);
  return user ? user.username.substring(0, 2).toUpperCase() : '?';
};

const handleAddTask = async (columnId: string) => {
  try {
    const { value } = await ElMessageBox.prompt('请输入任务标题', '新建任务', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPattern: /\S/,
      inputErrorMessage: '标题不能为空',
    });

    if (value) {
      await boardStore.createTask(columnId, value);
      ElMessage.success('任务已创建');
    }
  } catch (e) {
    // Cancelled
  }
};

const handleDeleteTask = async (taskID: string) => {
  try {
    await ElMessageBox.confirm('确定要删除此任务吗？', '删除任务', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await boardStore.deleteTask(taskID);
    ElMessage.success('任务已删除');
  } catch (e) {
    // Cancelled
  }
};

const handleLogout = async () => {
  await authStore.logout();
  router.push('/login');
  ElMessage.success('已安全退出');
};

// 拖拽逻辑保持不变
const calculatePosition = (tasks: any[], newIndex: number): number => {
  const prevTask = tasks[newIndex - 1];
  const nextTask = tasks[newIndex + 1];
  let position = 0;
  if (!prevTask && !nextTask) position = 65535;
  else if (!prevTask) position = nextTask.position / 2;
  else if (!nextTask) position = prevTask.position + 65535;
  else position = (prevTask.position + nextTask.position) / 2;
  return position;
};

const onDragChange = (event: any, columnId: string) => {
  if (event.added) {
    const task = event.added.element;
    const newIndex = event.added.newIndex;
    const column = boardStore.Columns.find(col => col.id === columnId);
    if (column) {
      const newPos = calculatePosition(column.tasks, newIndex);
      boardStore.updateTask(task.id, { column: columnId, position: newPos });
    }
  }
  if (event.moved) {
    const { element, newIndex } = event.moved;
    const column = boardStore.Columns.find(col => col.id === columnId);
    if (column) {
      const newPos = calculatePosition(column.tasks, newIndex);
      boardStore.updateTask(element.id, { position: newPos });
    }
  }
};
</script>

<style scoped>
/* 样式部分保持你的基本一致，但修复语法 */
.board-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.status-bar {
  padding: 0 20px;
  height: 50px; 
  background: #fff;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
  justify-content: space-between; 
  font-size: 14px;
  color: #666;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #ff4d4f;
  transition: background-color 0.3s;
}

.dot.online {
  background-color: #52c41a;
}

.board-container {
  display: flex;
  gap: 20px;
  padding: 20px;
  overflow-x: auto;
  flex: 1;
  background-color: #f5f7fa;
}

.board-column {
  min-width: 300px;
  background-color: #ebecf0;
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  max-height: 100%;
}

.column-header {
  padding: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-left h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.count {
  background: rgba(0,0,0,0.05);
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  color: #666;
}

.add-btn {
  padding: 4px;
  border-radius: 4px;
  transition: background 0.3s;
  color: #5e6c84;
}
.add-btn:hover {
  background-color: rgba(9, 30, 66, 0.08);
  color: #172b4d;
}

.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 5px;
  min-height: 50px;
}

.task-card {
  margin-bottom: 10px;
  cursor: grab;
  border: none;
}

.task-card:active {
  cursor: grabbing;
}

.ghost {
  opacity: 0.5;
  background: #c8ebfb;
  border: 2px dashed #0079bf;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.delete-btn {
  cursor: pointer;
  color: #909399;
  font-size: 14px;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
}

.delete-btn:hover {
  color: #f56c6c;
  background-color: rgba(245, 108, 108, 0.1);
}

.card-footer {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}

.avatar-circle {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-color: #409eff;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: bold;
  border: 2px solid #fff;
  box-shadow: 0 0 5px rgba(0,0,0,0.1);
}
.user-profile {
  display: flex;
  align-items: center;
  gap: 15px;
}

.username {
  font-weight: 600;
  color: #333;
}
.members-list {
    display: flex;
    margin-right: 15px;
}
.members-list .avatar-circle {
    margin-left: -8px; /* 让头像稍微重叠一点，比较好看 */
    border: 2px solid white;
}
.members-list .owner {
    background-color: #f56c6c; /* 负责人红色 */
    z-index: 10;
}
.members-list .member {
    background-color: #909399; /* 成员灰色 */
}
</style>