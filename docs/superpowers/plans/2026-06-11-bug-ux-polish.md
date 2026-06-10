# Bug 管理禅道式 UX 打磨 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给现有 `bug_tracker` 三个前端页面补齐禅道式 UX 体验（行内操作、删除、关联任务显示、正文可点开改、指派人筛选、新建补齐、错误提示统一），后端最小补 1 行 serializer 字段。

**Architecture:** 1 处后端字段补全 + 1 个新小组件（`EditableText`）+ 1 个新工具函数（`extractErrorMessage`）+ 3 个页面改造。零新接口，零数据模型变更。

**Tech Stack:** Vue 3 + TypeScript + Element Plus + Pinia + Vitest (前端) ; Django 4 + DRF + pytest-django (后端)

---

## File Structure

**新增 (2)**
- `frontend/src/utils/error.ts` — `extractErrorMessage(e, fallback)` 工具函数
- `frontend/src/components/bug/EditableText.vue` — 点击进入编辑的 textarea 组件

**修改 (5)**
- `backend/bug_tracker/serializers.py` — `BugListSerializer.fields` 末尾追加 `'linked_task'`
- `frontend/src/api/bug.ts` — 类型补 `linked_task`；新增 `getProjectMembers()` 辅助
- `frontend/src/views/bug/BugList.vue` — 行内操作列 / 关联任务列 / 指派人筛选 / 新建补齐 / 错误透传
- `frontend/src/views/bug/BugDetail.vue` — 删除按钮 / 关联任务显示 / 4 个正文改 EditableText / 错误透传
- `frontend/src/views/bug/MyBugs.vue` — 行内操作列 / 关联任务列

**测试新增 (2)**
- `frontend/src/__tests__/error.test.ts`
- `backend/tests/test_bug_tracker.py` — 追加 `linked_task` 列表字段测试

---

## Task 1: 后端 serializer 暴露 `linked_task` + 前端基础 (utils / types / members helper)

**Files:**
- Modify: `backend/bug_tracker/serializers.py:43-48`
- Modify: `backend/tests/test_bug_tracker.py:86-92`
- Create: `frontend/src/utils/error.ts`
- Create: `frontend/src/__tests__/error.test.ts`
- Modify: `frontend/src/api/bug.ts:19-83, 113-155`

### Step 1: 写后端失败测试

在 `backend/tests/test_bug_tracker.py` 第 86 行 `test_list_filter_by_status` 之后插入新测试：

```python
    def test_list_returns_linked_task_field(self, auth_client, test_project, test_user):
        from room.models import Task, Column
        col = Column.objects.filter(project=test_project).first()
        task = Task.objects.create(column=col, title='联动任务')
        Bug.objects.create(
            project=test_project, title='B1', status='new',
            reporter=test_user, linked_task=task.id,
        )
        resp = auth_client.get(f'/api/bugs/?project={test_project.id}')
        assert resp.status_code == 200
        assert 'linked_task' in resp.data['results'][0]
        assert resp.data['results'][0]['linked_task'] == str(task.id)
```

### Step 2: 运行测试 — 预期失败

```bash
cd D:/Projects/SyncBoard/backend
pytest tests/test_bug_tracker.py::TestBugCRUD::test_list_returns_linked_task_field -v
```

预期：`AssertionError: 'linked_task' not in ...`

### Step 3: 修改 serializer

`backend/bug_tracker/serializers.py` 第 43-48 行 `BugListSerializer.Meta.fields` 列表末尾追加 `'linked_task'`：

```python
        fields = [
            'id', 'project', 'project_name', 'title',
            'status', 'status_display', 'severity', 'severity_display',
            'priority', 'priority_display', 'reporter', 'assignee',
            'source_test_type', 'created_at', 'updated_at',
            'linked_task',
        ]
```

### Step 4: 重新运行 — 预期通过

```bash
pytest tests/test_bug_tracker.py::TestBugCRUD::test_list_returns_linked_task_field -v
```

预期：`PASSED`

### Step 5: 提交

```bash
cd D:/Projects/SyncBoard
git add backend/bug_tracker/serializers.py backend/tests/test_bug_tracker.py
git commit -m "feat(bug): BugListSerializer 暴露 linked_task 字段"
```

### Step 6: 写前端失败测试 — `extractErrorMessage`

`frontend/src/__tests__/error.test.ts` 新建：

```ts
import { describe, it, expect } from 'vitest'
import { extractErrorMessage } from '@/utils/error'

describe('extractErrorMessage', () => {
  it('returns detail from response.data.detail first', () => {
    const err = { response: { data: { detail: '权限不足' } } }
    expect(extractErrorMessage(err)).toBe('权限不足')
  })

  it('falls back to response.data.error when no detail', () => {
    const err = { response: { data: { error: '状态非法' } } }
    expect(extractErrorMessage(err)).toBe('状态非法')
  })

  it('falls back to err.message when no response', () => {
    const err = { message: 'Network Error' }
    expect(extractErrorMessage(err)).toBe('Network Error')
  })

  it('returns fallback string when nothing usable', () => {
    expect(extractErrorMessage({}, '默认失败')).toBe('默认失败')
  })

  it('detail wins over error when both present', () => {
    const err = { response: { data: { detail: '主', error: '次' } } }
    expect(extractErrorMessage(err)).toBe('主')
  })
})
```

### Step 7: 运行 — 预期失败

```bash
cd D:/Projects/SyncBoard/frontend
npm run test:run -- error.test.ts
```

预期：`FAIL ... Cannot find module '@/utils/error'`

### Step 8: 实现 `extractErrorMessage`

`frontend/src/utils/error.ts` 新建：

```ts
/**
 * 从 axios 错误对象里抽取可读的错误消息
 * 优先级: response.data.detail > response.data.error > err.message > fallback
 */
export function extractErrorMessage(e: any, fallback = '操作失败'): string {
  return e?.response?.data?.detail
      || e?.response?.data?.error
      || e?.message
      || fallback
}
```

### Step 9: 重新运行 — 预期通过

```bash
npm run test:run -- error.test.ts
```

预期：`5 passed`

### Step 10: 提交

```bash
cd D:/Projects/SyncBoard
git add frontend/src/utils/error.ts frontend/src/__tests__/error.test.ts
git commit -m "feat(frontend): 新增 extractErrorMessage 错误抽取工具"
```

### Step 11: 更新 `api/bug.ts` 类型 + 新增 `getProjectMembers`

编辑 `frontend/src/api/bug.ts`：

**(a)** `BugListItem` interface（第 19-35 行）末尾追加两个可选字段：

```ts
export interface BugListItem {
  id: number;
  project: string;
  project_name: string;
  title: string;
  status: BugStatus;
  status_display: string;
  severity: BugSeverity;
  severity_display: string;
  priority: BugPriority;
  priority_display: string;
  reporter: UserBrief | null;
  assignee: UserBrief | null;
  source_test_type: BugSource;
  created_at: string;
  updated_at: string;
  linked_task: string | null;  // ← 新增
  allowed_transitions?: BugStatus[];  // ← 新增 (后端 list 不返回，TS 占位)
}
```

**(b)** `BugCreatePayload` interface 追加字段：

```ts
export interface BugCreatePayload {
  project: string;
  title: string;
  description?: string;
  steps_to_reproduce?: string;
  expected?: string;
  actual?: string;
  environment?: string;
  severity?: BugSeverity;
  priority?: BugPriority;
  assignee_id?: number | null;
  linked_task?: string | null;  // ← 新增
}
```

**(c)** `updateBug` 签名显式声明接收 `linked_task`：

修改前：
```ts
export const updateBug = (id: number, payload: Partial<BugCreatePayload>): Promise<BugDetail> =>
```

修改后：
```ts
export type BugUpdatePayload = Partial<Omit<BugCreatePayload, 'project'>>

export const updateBug = (id: number, payload: BugUpdatePayload): Promise<BugDetail> =>
```

**(d)** 在 `seedDemoBugs` 之后追加 `getProjectMembers`：

```ts
export interface ProjectMemberBrief {
  user_id: number;
  username: string;
}

export const getProjectMembers = async (projectId: string): Promise<ProjectMemberBrief[]> => {
  const res: any = await service.get(`/projects/${projectId}/members/`)
  const list = Array.isArray(res) ? res : (res?.results || [])
  return list.map((m: any) => ({
    user_id: m.user_id || m.user?.id || m.user_detail?.id || m.id,
    username: m.username || m.user?.username || m.user_detail?.username || '',
  }))
}
```

### Step 12: 类型检查

```bash
cd D:/Projects/SyncBoard/frontend
npm run type-check
```

预期：无错误

### Step 13: 提交

```bash
cd D:/Projects/SyncBoard
git add frontend/src/api/bug.ts
git commit -m "feat(frontend): bug api 类型补 linked_task + getProjectMembers 辅助"
```

---

## Task 2: `EditableText.vue` 组件

**Files:**
- Create: `frontend/src/components/bug/EditableText.vue`
- Create: `frontend/src/__tests__/EditableText.test.ts`

### Step 1: 写组件测试

`frontend/src/__tests__/EditableText.test.ts` 新建：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EditableText from '@/components/bug/EditableText.vue'

describe('EditableText', () => {
  it('renders readonly pre by default with the value', () => {
    const wrapper = mount(EditableText, { props: { modelValue: 'hello' } })
    expect(wrapper.find('pre').text()).toBe('hello')
    expect(wrapper.find('textarea').exists()).toBe(false)
  })

  it('switches to textarea on click and emits update:modelValue on blur', async () => {
    const wrapper = mount(EditableText, { props: { modelValue: 'hello' } })
    await wrapper.find('pre').trigger('click')
    expect(wrapper.find('textarea').exists()).toBe(true)
    await wrapper.find('textarea').setValue('hello world')
    await wrapper.find('textarea').trigger('blur')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['hello world'])
    expect(wrapper.emitted('save')?.[0]).toEqual(['hello world'])
  })

  it('Escape cancels edit and restores original value', async () => {
    const wrapper = mount(EditableText, { props: { modelValue: 'original' } })
    await wrapper.find('pre').trigger('click')
    await wrapper.find('textarea').setValue('changed')
    await wrapper.find('textarea').trigger('keydown.esc')
    expect(wrapper.find('pre').text()).toBe('original')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('shows placeholder when value is empty', () => {
    const wrapper = mount(EditableText, {
      props: { modelValue: '', placeholder: '（无）' },
    })
    expect(wrapper.find('pre').text()).toBe('（无）')
  })
})
```

### Step 2: 运行 — 预期失败

```bash
cd D:/Projects/SyncBoard/frontend
npm run test:run -- EditableText.test.ts
```

预期：`FAIL ... Cannot find module '@/components/bug/EditableText.vue'`

### Step 3: 实现 `EditableText.vue`

`frontend/src/components/bug/EditableText.vue` 新建：

```vue
<template>
  <div class="editable-text">
    <pre
      v-if="!editing"
      class="editable-text__display"
      :class="{ 'is-empty': !modelValue }"
      @click="enterEdit"
    >{{ modelValue || placeholder }}</pre>
    <textarea
      v-else
      ref="textareaRef"
      v-model="draft"
      class="editable-text__input"
      :rows="rows"
      :placeholder="placeholder"
      @blur="commit"
      @keydown="onKeydown"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  rows?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'save', v: string): void
}>()

const editing = ref(false)
const draft = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const enterEdit = async () => {
  draft.value = props.modelValue
  editing.value = true
  await nextTick()
  textareaRef.value?.focus()
}

const commit = () => {
  if (!editing.value) return
  const value = draft.value
  editing.value = false
  if (value !== props.modelValue) {
    emit('update:modelValue', value)
    emit('save', value)
  }
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    e.preventDefault()
    editing.value = false
  } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    ;(e.target as HTMLTextAreaElement).blur()
  }
}
</script>

<style scoped>
.editable-text { width: 100%; }
.editable-text__display {
  white-space: pre-wrap;
  font-family: inherit;
  margin: 0;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  min-height: 24px;
}
.editable-text__display:hover {
  background: var(--el-fill-color-lighter);
}
.editable-text__display.is-empty {
  color: var(--el-text-color-placeholder);
  font-style: italic;
}
.editable-text__input {
  width: 100%;
  font-family: inherit;
  font-size: inherit;
  padding: 6px 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  resize: vertical;
}
</style>
```

### Step 4: 重新运行 — 预期通过

```bash
npm run test:run -- EditableText.test.ts
```

预期：`4 passed`

### Step 5: 提交

```bash
cd D:/Projects/SyncBoard
git add frontend/src/components/bug/EditableText.vue frontend/src/__tests__/EditableText.test.ts
git commit -m "feat(frontend): EditableText 组件 - 点击进入编辑 textarea"
```

---

## Task 3: BugList.vue 禅道式打磨

**Files:**
- Modify: `frontend/src/views/bug/BugList.vue` (template 第 105-149 行 + script)

### Step 1: 修改 script setup 顶部

**(a)** 替换 imports（第 209-213 行）：

修改前：
```ts
import {
  listBugs, createBug, getBugStats, seedDemoBugs,
  STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE,
  type BugListItem, type BugStats, type BugSeverity, type BugPriority,
} from '@/api/bug';
```

修改后：
```ts
import {
  listBugs, createBug, deleteBug, transitionBug, getBugStats, seedDemoBugs,
  getProjectMembers,
  STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE, STATUS_LABEL,
  type BugListItem, type BugStats, type BugSeverity, type BugPriority,
  type BugStatus, type ProjectMemberBrief,
} from '@/api/bug';
import { ArrowDown, Delete } from '@element-plus/icons-vue';
import { extractErrorMessage } from '@/utils/error';
```

**(b)** `interface Filters`（第 258-264 行）追加：

```ts
interface Filters {
  keyword: string;
  status: string[];
  severity: string[];
  priority: string[];
  source_test_type: string;
  assignee: number | null;
}
```

**(c)** `filters` reactive 初始化追加：

```ts
const filters = reactive<Filters>({
  keyword: '',
  status: [],
  severity: [],
  priority: [],
  source_test_type: '',
  assignee: null,
});
```

**(d)** 在 `loading` ref 附近增加：

```ts
const projectMembers = ref<ProjectMemberBrief[]>([]);
```

**(e)** 替换 `loadList`（第 275-298 行）：

```ts
const loadList = async () => {
  loading.value = true;
  try {
    const params: Record<string, any> = {
      project: projectId,
      page: page.value,
      page_size: pageSize,
    };
    if (filters.keyword) params.keyword = filters.keyword;
    if (filters.status.length) params.status = filters.status.join(',');
    if (filters.severity.length) params.severity = filters.severity.join(',');
    if (filters.priority.length) params.priority = filters.priority.join(',');
    if (filters.source_test_type) params.source_test_type = filters.source_test_type;
    if (filters.assignee) params.assignee = filters.assignee;

    const res = await listBugs(params);
    bugs.value = res.results;
    total.value = res.count;
  } catch (e) {
    console.error(e);
    ElMessage.error(extractErrorMessage(e, '加载 Bug 列表失败'));
  } finally {
    loading.value = false;
  }
};
```

**(f)** 新增 `loadMembers` + 修改 `onMounted`：

```ts
const loadMembers = async () => {
  try {
    projectMembers.value = await getProjectMembers(projectId);
  } catch {
    // 指派人筛选不可用不影响主列表
  }
};

onMounted(() => {
  loadList();
  loadStats();
  loadMembers();
});
```

**(g)** 新增 `confirmDelete` + `onQuickTransition`：

```ts
const confirmDelete = async (row: BugListItem) => {
  try {
    await deleteBug(row.id);
    ElMessage.success('已删除');
    await Promise.all([loadList(), loadStats()]);
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
    });
    ElMessage.success(`已流转到 ${STATUS_LABEL[to]}`);
    await loadStats();
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '流转失败'));
  }
};
```

**(h)** 替换 `handleSeedDemo` 错误处理：

```ts
const handleSeedDemo = async () => {
  try {
    const res = await seedDemoBugs(projectId);
    ElMessage.success(`已导入 ${res.added} 条示例 Bug`);
    await loadList();
    await loadStats();
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '导入失败'));
  }
};
```

**(i)** 替换 `createForm` reactive + `openCreate` + `submitCreate`：

```ts
const createForm = reactive({
  title: '',
  description: '',
  steps_to_reproduce: '',
  expected: '',
  actual: '',
  environment: '',
  severity: 'major' as BugSeverity,
  priority: 'p2' as BugPriority,
  assignee_id: null as number | null,
  linked_task: '',
});

const openCreate = () => {
  Object.assign(createForm, {
    title: '', description: '', steps_to_reproduce: '',
    expected: '', actual: '', environment: '',
    severity: 'major', priority: 'p2',
    assignee_id: null, linked_task: '',
  });
  createDialogVisible.value = true;
};

const submitCreate = async () => {
  if (!createForm.title.trim()) {
    ElMessage.warning('请填写标题');
    return;
  }
  submitting.value = true;
  try {
    const payload: Record<string, any> = {
      project: projectId,
      title: createForm.title,
      description: createForm.description,
      steps_to_reproduce: createForm.steps_to_reproduce,
      expected: createForm.expected,
      actual: createForm.actual,
      environment: createForm.environment,
      severity: createForm.severity,
      priority: createForm.priority,
    };
    if (createForm.assignee_id) payload.assignee_id = createForm.assignee_id;
    if (createForm.linked_task.trim()) payload.linked_task = createForm.linked_task.trim();
    const bug = await createBug(payload);
    ElMessage.success('Bug 已创建');
    createDialogVisible.value = false;
    router.push(`/projects/${projectId}/bugs/${bug.id}`);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '创建失败'));
  } finally {
    submitting.value = false;
  }
};
```

### Step 2: 修改 template

**(a)** 在筛选栏末尾插入"指派人"下拉：

```html
<el-select
  v-model="filters.assignee"
  placeholder="指派人"
  clearable filterable
  style="width: 160px"
  @change="reload"
>
  <el-option
    v-for="m in projectMembers"
    :key="m.user_id"
    :label="m.username"
    :value="m.user_id"
  />
</el-select>
```

**(b)** 在"创建时间"列之后插入"关联任务"列与"操作"列：

```html
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
            → {{ STATUS_LABEL[s] }}
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
```

**(c)** 新建对话框在"严重程度"之前插入"指派给" + "关联任务"：

```html
<el-form-item label="指派给">
  <el-select v-model="createForm.assignee_id" placeholder="（可选）" clearable filterable style="width: 100%">
    <el-option
      v-for="m in projectMembers"
      :key="m.user_id"
      :label="m.username"
      :value="m.user_id"
    />
  </el-select>
</el-form-item>
<el-form-item label="关联任务">
  <el-input v-model="createForm.linked_task" placeholder="（可选）任务 UUID" />
</el-form-item>
```

**(d)** `<style scoped>` 末尾追加：

```css
.linked-task-chip {
  font-family: monospace;
  color: var(--el-text-color-secondary);
}
.muted { color: var(--el-text-color-placeholder); }
```

### Step 3: 类型检查

```bash
cd D:/Projects/SyncBoard/frontend
npm run type-check
```

预期：无错误

### Step 4: 浏览器手测

```bash
cd D:/Projects/SyncBoard/frontend
npm run dev
```

打开 `http://localhost:5173/projects/<projectId>/bugs`，验证：
- [ ] 行尾"删除"按钮显示，点击 popconfirm 二次确认 → 删后列表自动刷新
- [ ] 行尾"关联任务"列显示 #短码（仅当有 linked_task 时）
- [ ] 筛选栏多出"指派人"下拉，选项是项目成员
- [ ] "新建 Bug"对话框多出"指派给"和"关联任务"两个字段，能正常填入
- [ ] 任何操作失败时错误提示显示后端 detail

### Step 5: 提交

```bash
cd D:/Projects/SyncBoard
git add frontend/src/views/bug/BugList.vue
git commit -m "feat(bug): BugList 行内操作 / 关联任务列 / 指派人筛选 / 新建补齐 / 错误透传"
```

---

## Task 4: BugDetail.vue 禅道式打磨

**Files:**
- Modify: `frontend/src/views/bug/BugDetail.vue` (template 第 1-207 行 + script)

### Step 1: 替换顶部操作区 (template 第 30-62 行)

把 `header-actions` 块中"指派"按钮之后插入"删除"按钮，"刷新"按钮之前：

```html
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
    title="确认删除此 Bug？该操作不可撤销"
    confirm-button-text="删除"
    cancel-button-text="取消"
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
```

### Step 2: 替换 4 个只读 `<pre>` 为 `<EditableText>`

**(a)** "问题描述" 卡片：

```html
<el-card class="section-card">
  <template #header><strong>问题描述</strong></template>
  <EditableText
    v-model="bug.description"
    placeholder="（无）"
    :rows="3"
    @save="v => saveField('description', v)"
  />
</el-card>
```

**(b)** "复现步骤" 卡片：`v-model="bug.steps_to_reproduce"`, `:rows="4"`

**(c)** "预期结果" / "实际结果"：`:rows="2"` + 对应字段名

### Step 3: 在右侧"属性"卡里加"关联任务"行

在 "指派给" prop-row 之后插入：

```html
<div class="prop-row" v-if="bug.linked_task">
  <span class="prop-label">关联任务</span>
  <span :title="bug.linked_task" class="linked-task-chip">
    #{{ bug.linked_task.slice(0, 8) }}
  </span>
</div>
```

### Step 4: 修改 script setup

**(a)** 替换 imports（第 213-219 行）：

修改前：
```ts
import { ArrowLeft, ArrowDown, Refresh, User } from '@element-plus/icons-vue';
import service from '@/utils/request';
import {
  getBug, updateBug, transitionBug, assignBug, addBugComment,
  STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE, STATUS_LABEL,
  type BugDetail, type BugStatus,
} from '@/api/bug';
```

修改后：
```ts
import { ArrowLeft, ArrowDown, Refresh, User, Delete } from '@element-plus/icons-vue';
import {
  getBug, updateBug, deleteBug, transitionBug, assignBug, addBugComment,
  STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE, STATUS_LABEL,
  type BugDetail, type BugStatus,
} from '@/api/bug';
import EditableText from '@/components/bug/EditableText.vue';
import { extractErrorMessage } from '@/utils/error';
```

> `loadMembers` 函数中用 `service.get` 那段保留不动（后续清理在另外 PR）。

**(b)** 替换 `loadDetail` catch：

```ts
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
```

**(c)** 替换 `saveTitle` catch：

```ts
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
```

**(d)** 替换 `saveField`：

```ts
const saveField = async (field: string, value: any) => {
  try {
    await updateBug(bugId, { [field]: value } as any);
    if (bug.value && field in (bug.value as any)) {
      (bug.value as any)[field] = value;
    }
    ElMessage.success('已保存');
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '保存失败'));
    loadDetail();
  }
};
```

**(e)** 替换 `confirmTransition` catch：

```ts
const confirmTransition = async () => {
  if (!pendingStatus.value) return;
  transitionSubmitting.value = true;
  try {
    bug.value = await transitionBug(bugId, pendingStatus.value, transitionComment.value);
    ElMessage.success('状态已更新');
    transitionDialogVisible.value = false;
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '流转失败'));
  } finally {
    transitionSubmitting.value = false;
  }
};
```

**(f)** 替换 `confirmAssign` catch：

```ts
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
```

**(g)** 替换 `submitComment` catch：

```ts
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
```

**(h)** 追加 `confirmDelete`：

```ts
const confirmDelete = async () => {
  try {
    await deleteBug(bugId);
    ElMessage.success('已删除');
    router.push(`/projects/${projectId}/bugs`);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '删除失败'));
  }
};
```

### Step 5: `<style scoped>` 末尾追加

```css
.linked-task-chip {
  font-family: monospace;
  color: var(--el-text-color-secondary);
}
```

### Step 6: 类型检查

```bash
cd D:/Projects/SyncBoard/frontend
npm run type-check
```

预期：无错误

### Step 7: 浏览器手测

```bash
cd D:/Projects/SyncBoard/frontend
npm run dev
```

打开任一 Bug 详情页，验证：
- [ ] 顶部"删除"按钮（红框）显示 → popconfirm → 确认后跳回列表
- [ ] 右侧属性卡多出"关联任务"行（仅当 bug 有 linked_task 时）
- [ ] 4 个正文（问题描述/复现步骤/预期/实际）点击进入编辑 → 失焦自动保存 → 成功 toast
- [ ] 按 Esc 取消编辑恢复原值
- [ ] 任何接口失败时错误提示显示后端 detail

### Step 8: 提交

```bash
cd D:/Projects/SyncBoard
git add frontend/src/views/bug/BugDetail.vue
git commit -m "feat(bug): BugDetail 删除按钮 / linked_task 显示 / 正文可点开改 / 错误透传"
```

---

## Task 5: MyBugs.vue 禅道式打磨

**Files:**
- Modify: `frontend/src/views/bug/MyBugs.vue`

### Step 1: 替换 script imports

修改前：
```ts
import {
  listMyBugs, STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE,
  type BugListItem,
} from '@/api/bug';
```

修改后：
```ts
import { ArrowDown, Delete } from '@element-plus/icons-vue';
import {
  listMyBugs, deleteBug, transitionBug,
  STATUS_TAG_TYPE, SEVERITY_TAG_TYPE, PRIORITY_TAG_TYPE, STATUS_LABEL,
  type BugListItem, type BugStatus,
} from '@/api/bug';
import { extractErrorMessage } from '@/utils/error';
```

### Step 2: 替换 `loadList` catch + 在 `goDetail` 之后追加新函数

```ts
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
    });
    ElMessage.success(`已流转到 ${STATUS_LABEL[to]}`);
  } catch (e) {
    ElMessage.error(extractErrorMessage(e, '流转失败'));
  }
};

const formatTime = (t: string) => t ? new Date(t).toLocaleString() : '-';
```

### Step 3: 在 template 末尾（创建时间列之后）插入"关联任务"列与"操作"列

```html
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
            → {{ STATUS_LABEL[s] }}
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
```

### Step 4: `<style scoped>` 末尾追加

```css
.linked-task-chip { font-family: monospace; color: var(--el-text-color-secondary); }
.muted { color: var(--el-text-color-placeholder); }
```

### Step 5: 类型检查

```bash
cd D:/Projects/SyncBoard/frontend
npm run type-check
```

预期：无错误

### Step 6: 浏览器手测

```bash
cd D:/Projects/SyncBoard/frontend
npm run dev
```

打开 `/projects/<projectId>/bugs/my`，验证：
- [ ] 列表多出"关联任务"列 + "操作"列
- [ ] 操作列的"删除"按钮可工作
- [ ] 切换 tab 后列依然在

### Step 7: 提交

```bash
cd D:/Projects/SyncBoard
git add frontend/src/views/bug/MyBugs.vue
git commit -m "feat(bug): MyBugs 行内操作 / 关联任务列 / 错误透传"
```

---

## Task 6: 端到端冒烟

### Step 1: 跑后端测试

```bash
cd D:/Projects/SyncBoard/backend
pytest tests/test_bug_tracker.py -v
```

预期：所有用例通过

### Step 2: 跑前端单元测试

```bash
cd D:/Projects/SyncBoard/frontend
npm run test:run
```

预期：所有用例通过

### Step 3: 类型检查

```bash
npm run type-check
```

预期：无错误

### Step 4: 浏览器全量回归

启动 dev server (`npm run dev`) 后逐页验证：

| 页面 | 验证项 |
| --- | --- |
| BugList | 列表渲染、筛选、新建、行内删除、关联任务列、指派人筛选 |
| BugDetail | 加载、流转、指派、删除、关联任务显示、4 个正文可编辑、评论 |
| MyBugs | 4 个 tab 切换、列表渲染、行内删除、关联任务列 |

### Step 5: 推送到 origin

```bash
cd D:/Projects/SyncBoard
git push origin dev
```

---

## Self-Review Checklist

1. **Spec coverage** — 9 项验收点全部对应到 Task 3-5 的具体步骤
2. **Placeholder scan** — 无 TBD/TODO/类似 Task N
3. **Type consistency** — `BugListItem.linked_task` / `BugUpdatePayload` / `extractErrorMessage` / `getProjectMembers` / `allowed_transitions` 五处跨任务命名一致
