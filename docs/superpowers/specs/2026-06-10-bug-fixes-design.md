# Bug 修复 + 质量报告语义修正 设计 Spec

日期: 2026-06-10
范围: 成员管理 / 看板筛选 / Bug 列表 / 质量报告
类型: Bug 修复（同时含少量功能补全）

## 1. 背景与目标

当前 4 个已知问题：

1. **成员管理 - 改角色不成功**：项目负责人在 Members 页面下拉切换成员角色，提示"角色已更新"，但 UI 仍显示旧角色，用户误以为后端没生效。
2. **看板筛选负责人 - 未与成员管理联动**：Board 页 `筛选负责人` 下拉显示系统全部用户，未限定为当前项目成员；新建/编辑任务时指派人下拉也是同样问题。
3. **Bug 列表页空数据**：CI seed 不创建 Bug，新装环境 / 流水线跑完后 Bug 列表是空表，无法直观演示完整生命周期。
4. **质量报告 Bug 密度错误**：使用 `Task.tags` 含名为 "bug" 的 Tag 来统计 Bug 数量，与 `bug_tracker.Bug` 主数据脱节，统计语义错误。

本次设计目标：逐一修复上述 4 项，附带最小可用的演示数据生成入口；不引入新功能、不重构既有模块。

## 2. 方案概览

| Bug | 范围 | 改动文件数 | 后端 | 前端 | 种子数据 |
| --- | --- | --- | --- | --- | --- |
| 1 改角色 | 最小 | 1 | 0 | 1 | 0 |
| 2 看板筛选联动 | 最小 | 1 | 0 | 1 | 0 |
| 3 Bug 列表空数据 | 适中 | 3 | 2（命令+端点） | 1 | +1 命令 |
| 4 质量报告 | 最小 | 1 | 1 | 0 | 0 |

## 3. 详细设计

### 3.1 成员管理 - 改角色不成功

**根因**：`Members.vue:209-218` 的 `changeRole` 函数 PUT 成功后未刷新本地 `members` 数组；el-select 仍绑定旧 `member.role` 值，渲染为旧角色。Backend `ProjectMemberListView.put` 实际已正确写入。

**改动**（`frontend/src/views/Members.vue`）：

- `changeRole` 成功分支后追加 `await fetchMembers()`，确保列表数据与后端一致。
- 失败分支改为 `catch (e: any) { ElMessage.error(e?.response?.data?.detail || '更新失败') }`，把后端实际错误透出（便于排查诸如"只有项目负责人可以修改成员角色"这类权限错误）。
- el-select 保持现状的受控写法（`:model-value="member.role || member.role_detail?.id"` + `@update:model-value`），仅动数据流。

**数据流**：

```
用户选新角色
  → el-select @update:model-value
    → changeRole(member, roleId)
      → service.put(/projects/{id}/members/, {user_id, role_id})
        → 成功: fetchMembers() 重拉 → members[] 更新 → el-select 重渲染显示新角色
        → 失败: ElMessage.error(后端 detail)
```

**测试**：
- 在 Members 页面切换某成员角色 → 应立刻看到新角色名（el-select 选中项 + chip）。
- 用非 owner 用户尝试调用 PUT → 应当收到 403 的 detail 文案。

### 3.2 看板筛选负责人 - 与成员管理联动

**根因**：`Board.vue:26` 的 `筛选负责人` el-option 来自 `boardStore.Users`（系统全部用户）。`新建/编辑任务` 里的指派人下拉也有同样问题。

**改动**（`frontend/src/views/Board.vue`）：

- 新增 `projectMembers` computed：从 `boardStore.currentProject` 聚合 `owner_details` 与 `members_details`，去重后返回 `{ id, username, profile }` 数组。
- 工具栏 `筛选负责人` el-option 改用 `projectMembers`。
- 新建任务 / 编辑任务 / 指派人等下拉同样替换。
- 不动后端、不动 boardStore。

**联动点**：
- `boardStore.currentProject` 在路由切换 / `fetchProjectDetail` 时会更新，`projectMembers` 自动响应。
- `Members.vue` 的邀请/移除成员成功后，应同步 `boardStore.currentProject.members_details`（如 store 无现成动作，则在 `handleInvite` / `handleRemoveMember` 末尾补一次 `boardStore.fetchProject(projectId)` 调用；具体是否存在动作待实施前再 grep 确认）。

**测试**：
- 项目 A 有 3 个成员 + 1 个 owner；`筛选负责人` 应当只显示 4 人。
- 在 Members 邀请新成员加入项目 A 后，回到 Board 页面下拉自动出现新成员。
- 把某成员从项目 A 移除，Board 下拉中应立即消失（或下次 fetchProject 后消失）。

### 3.3 Bug 列表页空数据

**根因**：CI seed 脚本（`seed_ci_data.py`）只创建用户与项目骨架，不创建任何 Bug；新装环境 Bug 列表无数据可演示。

**改动**（共 4 个文件）：

#### 3.3.1 新增共享 seed 模块

`backend/bug_tracker/seed.py`（**新文件**）：

- 暴露 `seed_demo_bugs(project) -> int` 函数：
  - 检查 `Bug.objects.filter(project=project, source_test_type='manual', title__startswith='[DEMO]').exists()`，若已存在则跳过（幂等）。
  - 给 mongoblue / test_user（或其他项目成员）创建 8 条 `[DEMO]` 前缀的 Bug：
    - 状态覆盖：new / confirmed / fixing / closed / reopened
    - 严重度覆盖：blocker / critical / major / minor
    - 来源覆盖：manual / api_auto / performance / ui_auto
  - 返回新增条数。
- 由 management command 与 API view 共同复用。

#### 3.3.2 新增 management command

`backend/bug_tracker/management/commands/seed_bugs_demo.py`（**新文件**）：

- 接受可选 `--project <project_id>` 参数；不传时默认找 `CI Automantion Project`（与 `seed_ci_data.py` 一致）。
- 调用 `seed_demo_bugs(project)` 并打印 `✅ 已生成 N 条示例 Bug`。
- `bug_tracker/management/__init__.py` 和 `bug_tracker/management/commands/__init__.py`（如不存在）一并创建。

#### 3.3.3 串接 CI seed

`backend/room/management/commands/seed_ci_data.py` 末尾追加：

```python
from django.core.management import call_command
call_command('seed_bugs_demo')
```

#### 3.3.4 后端 API 端点

`backend/bug_tracker/views.py` 新增 `BugSeedDemoView(APIView)`：

- `POST /api/bugs/seed-demo/?project_id=X`
- 校验 `project_id` 存在且 `project.owner == request.user`，否则 403。
- 调用 `seed_demo_bugs(project)`，返回 `{added: N, total: M}`。

`backend/bug_tracker/urls.py` 注册路由：

```python
path('bugs/seed-demo/', BugSeedDemoView.as_view(), name='bug_seed_demo'),
```

#### 3.3.5 前端空态按钮

`frontend/src/views/bug/BugList.vue`：

- 当 `bugs.length === 0` 且 `total === 0` 时，在 el-table 之上显示一段提示 + 按钮 `导入示例 Bug`。
- 按钮调用 `seedDemoBugs(projectId)`（在 `frontend/src/api/bug.ts` 新增 `seedDemoBugs`）。
- 完成后 `loadList()` + `loadStats()` 重新拉数据。
- 按钮仅在 `boardStore.currentProject?.owner_details?.id === authStore.user?.id` 时显示。

**测试**：
- CI 流水线跑完 `seed_ci_data` 后，`GET /api/bugs/?project=<id>` 应返回 8 条结果。
- 重复跑 `seed_bugs_demo` 不重复插入。
- 在 BugList 空态点击 `导入示例 Bug`，表格应立刻出现 8 条记录。

### 3.4 质量报告 Bug 密度（最小修复）

**根因**：`views_devops.py:858-861` 使用 `Tag.objects.filter(name__iexact='bug')` 统计 `Task.tags` 含 "bug" 标签的 task 数，与 `bug_tracker.Bug` 主数据脱节；同时 `summary.bug_count` 字段也没用 `Bug` 表。

**改动**（`backend/qa_center/views_devops.py`）：

- 引入 `from bug_tracker.models import Bug`。
- 替换第 4 段统计：

```python
bug_count = Bug.objects.filter(project_id=project_id).count()
bug_density = round(bug_count / total_tasks * 100, 1) if total_tasks > 0 else 0
bug_score = 20 if bug_density < 10 else (15 if bug_density < 20 else (10 if bug_density < 30 else 5))
```

- 删除 `Tag.objects.filter(name__iexact='bug')` 旧逻辑。
- `summary.bug_count` 改用 `bug_count`。
- `dimensions` 中 `Bug密度` 维度的 detail 改为：`f'{bug_count} 个 Bug / {total_tasks} 任务 ({bug_density}%)'`。

**前端不动**：`ProjectQualityReport.vue` 字段名一致，无需改动。

**测试**：
- 给某项目新增 1 个 Bug 后，`GET /api/qa/devops/quality-report/?project_id=X` 的 `summary.bug_count` 应当 +1。
- `dimensions` 中 `Bug密度` 维度的 detail 文本应反映新计数。

## 4. 数据流总览

```
项目负责人
  ├─ Members.vue ─PUT /api/projects/{id}/members/──→ ProjectMemberListView.put
  │     └─ 成功: fetchMembers() 重拉
  │     └─ 失败: ElMessage.error(detail)
  │
  ├─ Board.vue ─筛选负责人(项目成员 only)──→ 仅前端过滤，不打后端
  │
  └─ BugList.vue ─POST /api/bugs/seed-demo/──→ BugSeedDemoView
        └─ 调用 seed_demo_bugs(project) → bug_tracker.Bug 表 +N 条

CI 流水线
  └─ python manage.py seed_ci_data
        ├─ 用户/项目骨架
        └─ call_command('seed_bugs_demo')  ← 串接
              └─ seed_demo_bugs(default_project)  ← 复用同一份逻辑

质量报告 GET /api/qa/devops/quality-report/
  └─ ProjectQualityReportView.get
        ├─ test_coverage (Task.linked_*)
        ├─ test_pass_rate (TestResult 最近 10 次)
        ├─ perf_score (PerformanceTestResult 最近 5 次)
        ├─ bug_score (← 改用 Bug.objects.filter(project_id=...).count)  ★ 本次改
        └─ deploy_rate (PipelineRun 最近 10 次)
```

## 5. 边界与不做的事

- **不做**：成员角色与系统 RBAC 的双向同步、看板新增权限维度
- **不做**：质量报告的"未关闭 Bug"新维度（用户已确认最小修复）
- **不做**：种子数据可视化管理界面
- **不做**：Bug 自动从 Task tag 迁移到 bug_tracker.Bug 表（历史数据兼容问题，本期不处理）
- **不破坏**：既有 el-select 行为、既有路由、既有 store 字段

## 6. 风险

- Members.vue `fetchMembers()` 每次改角色都全量拉一次（最多几十条），开销可忽略。
- Board.vue `projectMembers` 依赖 `boardStore.currentProject`，如果 store 中 `members_details` 与 `members` 不同步需要先解决（实施前 grep 确认）。
- Bug seed_demo 端点暴露在生产环境时**必须**只允许 owner 调用（已加入 owner 校验）。
- 质量报告改用 Bug 表后，存量用 "bug" Tag 标记的 task 不会再被计入；本次只修语义，不补迁移。

## 7. 验收清单

- [ ] 改成员角色后 UI 立刻反映
- [ ] 改角色失败时显示后端 detail
- [ ] 看板筛选负责人下拉只有项目成员
- [ ] 看板指派人下拉只有项目成员
- [ ] CI seed 跑完有 8 条 [DEMO] Bug
- [ ] 重复 seed 不重复插入
- [ ] BugList 空态的"导入示例"按钮仅 owner 可见且工作
- [ ] 质量报告 bug_count / Bug密度 detail 反映 bug_tracker.Bug 数据
