<template>
  <el-table
    :data="bugs"
    v-loading="loading"
    stripe
    @selection-change="(rows: BugListItem[]) => $emit('selection-change', rows)"
  >
    <!-- 多选 -->
    <el-table-column type="selection" width="40" />

    <!-- 缺陷标题 -->
    <el-table-column label="缺陷" min-width="260" show-overflow-tooltip>
      <template #default="{ row }">
        <div class="bug-title-cell">
          <button class="bug-title-link" type="button" @click="$emit('open-detail', row)">
            {{ row.title }}
          </button>
          <div class="bug-meta-inline">
            <span class="bug-id-chip">#{{ row.id }}</span>
            <el-tag size="small" type="info" class="source-tag">
              {{ sourceLabel(row.source_test_type) }}
            </el-tag>
            <span v-if="row.linked_task" class="linked-task-hint" :title="row.linked_task">
              关联任务
            </span>
          </div>
        </div>
      </template>
    </el-table-column>

    <!-- 状态 -->
    <el-table-column label="状态" width="110">
      <template #default="{ row }">
        <el-dropdown
          v-if="row.allowed_transitions?.length"
          trigger="click"
          @command="(toStatus: string) => $emit('open-transition', row, toStatus)"
          @click.stop
        >
          <span class="status-tag-clickable">
            <BugStatusTag :status="row.status" />
            <el-icon class="tag-arrow"><ArrowDown /></el-icon>
          </span>
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
        <BugStatusTag v-else :status="row.status" />
      </template>
    </el-table-column>

    <!-- 严重程度 -->
    <el-table-column label="严重度" width="120">
      <template #default="{ row }">
        <el-select
          :model-value="row.severity"
          size="small"
          class="table-select"
          @change="(value: BugSeverity) => $emit('change-severity', row, value)"
          @click.stop
        >
          <el-option
            v-for="s in SEVERITY_OPTIONS"
            :key="s.value"
            :label="s.label"
            :value="s.value"
          />
        </el-select>
      </template>
    </el-table-column>

    <!-- 优先级 -->
    <el-table-column label="优先级" width="100">
      <template #default="{ row }">
        <el-select
          :model-value="row.priority"
          size="small"
          class="table-select"
          @change="(value: BugPriority) => $emit('change-priority', row, value)"
          @click.stop
        >
          <el-option
            v-for="p in PRIORITY_OPTIONS"
            :key="p.value"
            :label="p.label"
            :value="p.value"
          />
        </el-select>
      </template>
    </el-table-column>

    <!-- 负责人 -->
    <el-table-column label="负责人" width="140">
      <template #default="{ row }">
        <el-select
          :model-value="row.assignee?.id || null"
          size="small"
          class="table-select"
          placeholder="未指派"
          filterable
          @change="(userId: number) => $emit('open-assign', row, userId)"
          @click.stop
        >
          <el-option
            v-for="m in projectMembers"
            :key="m.user_id"
            :label="m.username"
            :value="m.user_id"
          />
        </el-select>
      </template>
    </el-table-column>

    <!-- 报告人 -->
    <el-table-column label="报告人" width="100">
      <template #default="{ row }">
        {{ row.reporter?.username || '-' }}
      </template>
    </el-table-column>

    <!-- 更新时间 -->
    <el-table-column label="更新时间" width="160">
      <template #default="{ row }">
        {{ formatTime(row.updated_at) }}
      </template>
    </el-table-column>

    <!-- 操作 -->
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <div class="row-actions" @click.stop>
          <el-button size="small" link type="primary" @click="$emit('open-detail', row)">
            详情
          </el-button>
          <el-button
            v-if="row.allowed_transitions?.length"
            size="small"
            link
            type="warning"
            @click="$emit('open-transition', row)"
          >
            流转
          </el-button>
          <el-button size="small" link @click="$emit('open-assign', row)">
            指派
          </el-button>
          <el-dropdown trigger="click">
            <el-button size="small" link>
              <el-icon><MoreFilled /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item>
                  <el-popconfirm
                    title="确认删除此 Bug？此操作无法撤销。"
                    confirm-button-text="删除"
                    cancel-button-text="取消"
                    @confirm="$emit('delete', row)"
                  >
                    <template #reference>
                      <span class="delete-menu-item">删除</span>
                    </template>
                  </el-popconfirm>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { ArrowDown, MoreFilled } from '@element-plus/icons-vue'
import {
  STATUS_LABEL,
  type BugListItem,
  type BugSeverity,
  type BugPriority,
  type BugStatus,
  type ProjectMemberBrief,
} from '@/api/bug'
import BugStatusTag from './BugStatusTag.vue'

defineProps<{
  bugs: BugListItem[]
  loading: boolean
  projectMembers: ProjectMemberBrief[]
}>()

defineEmits<{
  (e: 'open-detail', bug: BugListItem): void
  (e: 'change-severity', bug: BugListItem, severity: BugSeverity): void
  (e: 'change-priority', bug: BugListItem, priority: BugPriority): void
  (e: 'open-transition', bug: BugListItem, toStatus?: string): void
  (e: 'open-assign', bug: BugListItem, userId?: number): void
  (e: 'delete', bug: BugListItem): void
  (e: 'selection-change', bugs: BugListItem[]): void
}>()

const SEVERITY_OPTIONS = [
  { value: 'blocker', label: '阻塞' },
  { value: 'critical', label: '严重' },
  { value: 'major', label: '一般' },
  { value: 'minor', label: '次要' },
  { value: 'trivial', label: '轻微' },
]

const PRIORITY_OPTIONS = [
  { value: 'p0', label: 'P0' },
  { value: 'p1', label: 'P1' },
  { value: 'p2', label: 'P2' },
  { value: 'p3', label: 'P3' },
]

const sourceLabel = (s: string) =>
  ({
    manual: '手工',
    api_auto: '接口自动化',
    performance: '性能',
    ui_auto: 'UI 自动化',
  } as Record<string, string>)[s] || s

const formatTime = (t: string) => (t ? new Date(t).toLocaleString() : '-')

</script>

<style scoped>
.bug-title-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bug-title-link {
  max-width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-primary);
  cursor: pointer;
  font: inherit;
  font-weight: 500;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bug-title-link:hover {
  text-decoration: underline;
}
.bug-meta-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.bug-id-chip {
  color: var(--color-text-tertiary);
  font-family: var(--font-mono, monospace);
}
.source-tag {
  font-size: 11px;
}
.linked-task-hint {
  color: var(--color-text-tertiary);
  font-size: 11px;
  padding: 0 4px;
  background: var(--color-surface-sunken);
  border-radius: var(--radius-sm);
}
.status-tag-clickable {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  cursor: pointer;
}
.tag-arrow {
  font-size: 10px;
  color: var(--color-text-tertiary);
}
.table-select {
  width: 100%;
}
.row-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}
.delete-menu-item {
  color: var(--color-danger);
  cursor: pointer;
}
</style>
