<template>
  <div class="my-bugs">
    <header class="page-header">
      <div>
        <h1 class="page-title">我的 Bug</h1>
        <p class="page-subtitle">查看与我相关的所有 Bug</p>
      </div>
    </header>

    <el-tabs v-model="activeRole" @tab-change="loadList">
      <el-tab-pane label="指派给我" name="assignee">
        <div class="tab-hint">需要我处理（被指派的）Bug</div>
      </el-tab-pane>
      <el-tab-pane label="我报告的" name="reporter">
        <div class="tab-hint">我作为报告人创建或提交的 Bug</div>
      </el-tab-pane>
      <el-tab-pane label="我修复的" name="fixer">
        <div class="tab-hint">由我标记为已修复的 Bug</div>
      </el-tab-pane>
      <el-tab-pane label="我验证的" name="verifier">
        <div class="tab-hint">由我验证关闭的 Bug</div>
      </el-tab-pane>
    </el-tabs>

    <el-table :data="bugs" v-loading="loading" stripe @row-click="goDetail" row-class-name="clickable-row">
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column prop="project_name" label="项目" width="160" show-overflow-tooltip />
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="STATUS_TAG_TYPE[row.status as keyof typeof STATUS_TAG_TYPE]" size="small">{{ row.status_display }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="严重度" width="90">
        <template #default="{ row }">
          <el-tag :type="SEVERITY_TAG_TYPE[row.severity as keyof typeof SEVERITY_TAG_TYPE]" size="small">{{ row.severity_display }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="80">
        <template #default="{ row }">
          <el-tag :type="PRIORITY_TAG_TYPE[row.priority as keyof typeof PRIORITY_TAG_TYPE]" size="small">{{ row.priority_display }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="报告人" width="120">
        <template #default="{ row }">{{ row.reporter?.username || '-' }}</template>
      </el-table-column>
      <el-table-column label="指派给" width="120">
        <template #default="{ row }">{{ row.assignee?.username || '-' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="关联任务" width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.linked_task" :title="row.linked_task" class="linked-task-chip">
            #{{ row.linked_task.slice(0, 8) }}
          </span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-dropdown
            v-if="row.allowed_transitions?.length"
            trigger="click"
            @command="(cmd: BugStatus) => onQuickTransition(row, cmd)"
            style="margin-right: 8px"
          >
            <el-button size="small">
              流转<el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="s in row.allowed_transitions"
                  :key="s"
                  :command="s"
                >
                  → {{ STATUS_LABEL[s as BugStatus] }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-popconfirm
            title="确认删除此 Bug？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="confirmDelete(row)"
          >
            <template #reference>
              <el-button size="small" type="danger" plain>
                <el-icon><Delete /></el-icon> 删除
              </el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      class="pagination"
      @current-change="loadList"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { ArrowDown, Delete } from '@element-plus/icons-vue';
import {
  listMyBugs, deleteBug, transitionBug,
  STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE, STATUS_LABEL,
  type BugListItem, type BugStatus,
} from '@/api/bug';
import { extractErrorMessage } from '@/utils/error';

const route = useRoute();
const router = useRouter();
const projectId = route.params.projectId as string;

type Role = 'assignee' | 'reporter' | 'fixer' | 'verifier';
const activeRole = ref<Role>('assignee');

const loading = ref(false);
const bugs = ref<BugListItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;

const loadList = async () => {
  loading.value = true;
  try {
    const res = await listMyBugs(activeRole.value, {
      project: projectId,
      page: page.value,
      page_size: pageSize,
    });
    bugs.value = res.results;
    total.value = res.count;
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '加载失败'));
  } finally {
    loading.value = false;
  }
};

const goDetail = (row: BugListItem) => {
  router.push(`/projects/${projectId}/bugs/${row.id}`);
};

const confirmDelete = async (row: BugListItem) => {
  try {
    await deleteBug(row.id);
    ElMessage.success('已删除');
    await loadList();
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '删除失败'));
  }
};

const onQuickTransition = async (row: BugListItem, to: BugStatus) => {
  try {
    const updated = await transitionBug(row.id, to, '');
    Object.assign(row, {
      status: updated.status,
      status_display: updated.status_display,
      allowed_transitions: updated.allowed_transitions,
    });
    ElMessage.success(`已流转到 ${STATUS_LABEL[to]}`);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '流转失败'));
  }
};

const formatTime = (t: string) => t ? new Date(t).toLocaleString() : '-';

onMounted(loadList);
</script>

<style scoped>
.my-bugs { padding: 0; }
.tab-hint {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-bottom: 12px;
}
.clickable-row { cursor: pointer; }
.pagination { margin-top: 16px; justify-content: flex-end; display: flex; }
.linked-task-chip {
  color: var(--color-text-secondary);
  font-size: 13px;
}
.muted { color: var(--color-text-tertiary); }
</style>
