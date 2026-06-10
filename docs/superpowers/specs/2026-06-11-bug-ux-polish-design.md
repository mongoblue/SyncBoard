# Bug 管理禅道式 UX 打磨 设计 Spec

日期: 2026-06-11
范围: 纯前端 UX 打磨（1 处后端字段补全）
类型: UX 改进

## 1. 背景与目标

`bug_tracker` 三个前端页面 (BugList / BugDetail / MyBugs) 相比禅道 (ZenTao) 的差距：

- 详情页无删除按钮
- `linked_task` 字段已在数据模型里但 UI 不显示
- 详情正文 (`description` / `steps` / `expected` / `actual`) 是只读 `<pre>`，不可点开编辑
- 列表无行内操作列，禅道是行内"操作"下拉（编辑/流转/指派/删除）
- BugList 筛选栏无"指派人"维度
- 新建 Bug 不能在弹框内指派/关联任务
- 多个接口的错误提示是 `ElMessage.error('失败')`，应透传后端 `detail` / `error`

不引入新功能、不重构模块。

## 2. 方案概览

| 改动 | 范围 | 文件数 |
| --- | --- | --- |
| 后端 `BugListSerializer` 加 `linked_task` 字段 | 1 行 | 1 |
| 前端类型与 API 调用补齐 | 小 | 1 |
| BugList.vue (行内操作 + 关联任务列 + 指派人筛选 + 新建补齐 + 删除) | 中 | 1 |
| BugDetail.vue (删除按钮 + 正文可点开改 + linked_task 显示 + 错误透传) | 中 | 1 |
| MyBugs.vue (行内操作列 + 关联任务列) | 小 | 1 |

## 3. 详细设计

### 3.1 后端：`BugListSerializer` 暴露 `linked_task`

`backend/bug_tracker/serializers.py` 第 47 行的 `fields` 列表追加 `'linked_task'`：

```python
fields = [
    'id', 'project', 'project_name', 'title',
    'status', 'status_display', 'severity', 'severity_display',
    'priority', 'priority_display', 'reporter', 'assignee',
    'source_test_type', 'created_at', 'updated_at',
    'linked_task',   # ← 新增
]
```

> Bug 列表 api 返回的 `linked_task` 是 Task UUID 字符串。前端拿到后用 `router.push(\`/projects/{pid}/board?task=${linked_task}\`)` 跳转（如果项目有 Task 详情路由；若没有，文本显示即可，不强行跳转）。

### 3.2 前端 API / 类型补齐

`frontend/src/api/bug.ts`：

- `BugListItem` 加 `linked_task: string | null`
- `BugCreatePayload` 加 `linked_task?: string | null`
- `BugUpdatePayload` 用 `Partial<Omit<BugCreatePayload, 'project'>>` 显式声明并支持 `linked_task`
- 新增 `getProjectMembers(projectId): Promise<{user_id: number; username: string}[]>` — 内部 `service.get(\`/projects/\${projectId}/members/\`)`，返回后归一化为 `user_id/username`
- 现有 `deleteBug` 已存在 (`service.delete(\`\${BASE}/\${id}/\`)`) — 无需新增

### 3.3 BugList.vue

#### 3.3.1 行内操作列

新增 `<el-table-column label="操作" width="180" fixed="right">`，含：

- **流转** (`<el-dropdown>` 子项) — 显示 `bug.allowed_transitions`，点击直接 POST `/transition/` 不弹评论框（保持列表操作轻量；评论需求可在详情页做）
- **删除** — `el-popconfirm` 二次确认 → `deleteBug(row.id)` → `ElMessage.success` → `loadList()` + `loadStats()`

> 简化决策：列表行只暴露"快速流转"和"删除"两个最常用动作。"编辑"和"指派"统一在详情页做（避免在列表弹 4 个 dialog 的拥挤）。如果用户后续提出需求再加。

#### 3.3.2 关联任务列

新增 `<el-table-column label="关联任务" width="200" show-overflow-tooltip>`：

- 无值：显示 `—`
- 有值：显示 `row.linked_task` (Task UUID 短码前 8 位 + 提示悬停)

> 不强行跳转（因为 Task 详情路由结构以 `board` 为核心，UUID 不一定有独立详情页）。

#### 3.3.3 指派人筛选

`filter-bar` 末尾增加：

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

`projectMembers` 用 `onMounted` 调一次 `getProjectMembers(projectId)` 缓存。`loadList` 时如果 `filters.assignee` 有值则 `params.assignee = filters.assignee`。

#### 3.3.4 新建对话框补齐

`<el-dialog>` 内增加：

- `指派给` 字段 — `el-select` 同样用 `projectMembers`，可空
- `关联任务` 字段 — `el-input` 接受 UUID 字符串（`placeholder="任务 UUID（可选）"`），保存时塞进 `linked_task`

`createForm` reactive 增加 `assignee_id: number | null` + `linked_task: ''`，`openCreate` 时重置。

#### 3.3.5 错误提示统一

`handleSeedDemo` 已正确处理（`e.response.data.detail || e.response.data.error`）。新增 `confirmDelete` 处理：

```ts
const confirmDelete = async (row: BugListItem) => {
  try {
    await deleteBug(row.id);
    ElMessage.success('已删除');
    await Promise.all([loadList(), loadStats()]);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.response?.data?.error || '删除失败');
  }
};
```

### 3.4 BugDetail.vue

#### 3.4.1 删除按钮

顶部操作区在 "指派" 按钮之后加：

```html
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
```

```ts
const confirmDelete = async () => {
  try {
    await deleteBug(bugId);
    ElMessage.success('已删除');
    router.push(`/projects/${projectId}/bugs`);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.response?.data?.error || '删除失败');
  }
};
```

#### 3.4.2 关联任务显示

右侧"属性"卡（"指派给"行之上）新增一行：

```html
<div class="prop-row" v-if="bug.linked_task">
  <span class="prop-label">关联任务</span>
  <span :title="bug.linked_task" class="linked-task-chip">
    #{{ bug.linked_task.slice(0, 8) }}
  </span>
</div>
```

#### 3.4.3 详情正文可点开改

把 4 个只读 `<pre>` 替换为"点击进入编辑"组件模式：

```html
<el-card class="section-card">
  <template #header>
    <strong>问题描述</strong>
  </template>
  <EditableText
    v-model="bug.description"
    placeholder="（无）"
    :rows="3"
    @save="v => saveField('description', v)"
  />
</el-card>
```

抽出一个小组件 `EditableText.vue`（新增文件 `frontend/src/components/bug/EditableText.vue`）：

- 接收 `modelValue: string`、占位符、行数
- 默认渲染只读 `<pre>`，点击进入 `<el-input type="textarea" :rows="rows">` 模式
- `@blur` 或 `Ctrl+Enter` 触发 `update:modelValue` + emit `save`
- `Esc` 取消编辑并恢复原值

字段对应：description / steps_to_reproduce / expected / actual 全部用 `EditableText` 替换。

#### 3.4.4 错误透传

现有三处 `catch` 把 `ElMessage.error('...')` 改为带后端 detail 的版本（`assign` / `transition` / `saveTitle` / `saveField` / `submitComment` 全部统一）。新增 `extractErrorMessage(e: any, fallback: string): string` 工具函数到 `frontend/src/utils/error.ts`：

```ts
export function extractErrorMessage(e: any, fallback = '操作失败'): string {
  return e?.response?.data?.detail
      || e?.response?.data?.error
      || e?.message
      || fallback;
}
```

BugList.vue / MyBugs.vue 同样复用。

### 3.5 MyBugs.vue

#### 3.5.1 行内操作列

复用 BugList 一样的"操作"列（流转 + 删除），但因为是跨项目视图，"关联任务"列已经隐含项目名，不重复显示。

#### 3.5.2 关联任务列

直接复用 `BugList.vue` 的列实现（短码 + tooltip）。如想 DRY 可考虑抽 `BugActionColumn.vue` 组件，本期不强求（避免过度抽象）。

### 3.6 视觉一致性

- 删除按钮用 `type="danger" plain`（次要操作风格，红色提示但不刺眼）
- 操作列放最右并 `fixed="right"`
- 关联任务短码灰色字体（`color: var(--el-text-color-secondary)`）
- `EditableText` hover 时加 `cursor: pointer` + 浅色背景提示"点击编辑"

## 4. 数据流总览

```
列表行点"流转"
  → row.allowed_transitions
  → onQuickTransition(row, toStatus)
  → transitionBug(row.id, toStatus, '')
  → 服务端返回更新后的 BugDetail
  → 局部替换 row（status / status_display） + loadStats() 刷新统计
  → ElMessage.success('状态已更新')

列表行 / 详情页点"删除"
  → el-popconfirm 二次确认
  → deleteBug(bugId)
  → 成功: 列表页 loadList + loadStats; 详情页 router.push 回列表
  → 失败: extractErrorMessage → ElMessage.error(后端 detail)

详情正文点击
  → EditableText 切到编辑态
  → blur 或 Ctrl+Enter 触发 updateBug
  → 成功: v-model 已同步, ElMessage.success
  → 失败: 恢复原值 + ElMessage.error(detail)
```

## 5. 边界与不做的事

- **不做**：删除权限收紧（后端当前任何登录用户可删 — 不在本期改）
- **不做**：列表行"指派"快捷入口（统一在详情页）
- **不做**：列表行"编辑"快捷入口（统一在详情页）
- **不做**：`EditableText` 改成富文本/Markdown 编辑器（保持 `<el-input type="textarea">`）
- **不做**：批量删除（暂不需要）
- **不破坏**：既有路由、既有 el-select 行为、既有 store 字段

## 6. 风险

- 后端 `BugListSerializer` 加字段需迁移吗？**不需要** — 字段在 `Bug` model 上已存在（`linked_task = models.UUIDField(null=True, blank=True)`），serializer 只是暴露。
- `EditableText` 抽组件后 4 个字段共用，如果一个 bug 难定位，4 个都要看 — 但组件逻辑只 ~30 行，权衡后值。
- 列表"快速流转"无评论弹框：禅道也没强制要，可以接受。

## 7. 验收清单

- [ ] BugList 行内"删除"按钮可工作，popconfirm 二次确认
- [ ] BugList 行内"流转"下拉可工作，点击直接改状态
- [ ] BugList 新增"关联任务"列
- [ ] BugList 筛选栏有"指派人"下拉
- [ ] BugList 新建对话框可同时选"指派人" + 填"关联任务 UUID"
- [ ] BugDetail 顶部有"删除"按钮（危险样式）
- [ ] BugDetail 右侧属性有"关联任务"行（有值时显示）
- [ ] BugDetail 4 个正文字段可点开编辑
- [ ] 所有 catch 块都透传后端 detail
- [ ] MyBugs 行内也有"操作"列
