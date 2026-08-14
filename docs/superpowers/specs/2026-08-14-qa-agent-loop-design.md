# AI QA Agent 增强闭环 — 设计文档

- 日期：2026-08-14
- 状态：已获用户确认
- 定位：作品集核心项目（求职方向：测试开发/QA 工程师）

## 1. 背景与目标

SyncBoard（FlowSpace）已有：看板协作（Django + Vue 3 + WebSocket 实时同步）、QA 中心（API/UI/性能测试、断言引擎、变量提取、环境管理、结果持久化）、AI 助手（DeepSeek 流式对话 + 约 20 个工具的 Tool Calling，见 `backend/room/ai_utils.py`）、CI/CD 配置与流水线。

现状缺口：AI 助手是**单轮工具调用**，没有"需求 → 自动生成用例 → 真实执行 → 失败分析 → 自动建单"的闭环编排；工具层执行与 QA 中心执行引擎（`qa_center/run_plan_executor.py`、`ui_execution.py`、`workers/runner_supervisor.py`）没有联动。

目标：新增 **AI QA Agent 增强闭环**——事件触发，Agent 自动完成测试计划、用例生成、执行、失败智能分析、报告回写与自动建单，并配套 **Eval 评估集**量化 agent 质量。作为求职 QA 工程师岗位的作品集核心。

## 2. 范围

### 包含

1. 事件触发（看板列移动 / 手动 / CI/CD 完成）统一进入 AgentRun
2. 编排状态机：planning → executing → analyzing → reporting（Celery 异步）
3. 计划生成：收集项目上下文（源任务卡、API 文档、已有用例、测试环境）→ LLM 输出计划 JSON
4. 用例自动生成与执行：复用现有工具（`create_api_test_case` / `create_ui_test_case` / `execute_test_task`）与 QA 执行引擎，API + UI 全真实执行，截图留存
5. 失败分析：LLM 结构化输出 flaky 判定 / 根因分类 / 修复建议，失败聚类，自动建 bug 任务（带规则防噪）
6. 报告：Markdown 回写源任务卡评论，存 `AgentRun.summary`
7. 实时进度：AgentStep/AgentEvent 经 WebSocket 推送（复用现有通知通道）
8. Eval 集：用例生成准确率、根因分类准确率、flaky 判定准确率（混淆矩阵），pytest `-m eval` 运行，LLM 响应缓存可离线重放
9. 前端：任务卡 AgentRun 徽标/进度、QA 页 AgentRun 列表 + 步骤时间线

### 不包含（明确非目标）

- 人工确认门（human-in-the-loop 审批节点）——第二版
- 多智能体协作（规划/开发/QA/发布角色分工）——远期形态
- MCP 化（把现有工具包装成 MCP server）——闭环跑通后的加分展示项，第三阶段
- 修改现有 QA 执行引擎内部实现——只通过公开入口调用

## 3. 架构总览

新增独立 Django app `qa_agent`，与 `room`、`qa_center` 平级。职责单一：**编排**。

核心设计决策：**编排层不直接操作业务数据模型，只通过 `execute_tool`（`room.ai_utils`）与 `qa_center` 公开入口调用**。每一步天然可审计、可回放，是 agent 边界设计的核心论点。

```
[触发入口]
  1. 看板事件：任务卡移动到含"测试/待测"的列 → signal → create_run()
  2. 手动：QA 页面按钮 / AI 对话工具调用扩展 → create_run()
  3. CI/CD：PipelineRun 完成 → create_run()
        │
        ▼
  create_run() 工厂（统一校验项目成员/权限）→ AgentRun(queued)
        │
        ▼
  Celery: run_agent_pipeline(run_id)   ← 状态机线性推进
  ┌─────────────┐
  │ planning    │ 收集上下文 → LLM 计划 JSON → 存 plan
  ├─────────────┤
  │ executing   │ 按计划调用现有工具/执行引擎 → AgentStep 落库 + WebSocket 进度
  ├─────────────┤
  │ analyzing   │ 收集 TestResult+截图+日志 → LLM 结构化分析 → 聚类 → 自动建单
  ├─────────────┤
  │ reporting   │ 生成 Markdown 报告 → 回写任务卡评论 → 通知
  └─────────────┘
```

状态机守卫：LLM 调用失败重试 3 次（指数退避）；整体超时熔断；用户可取消（→ `cancelled`）。

## 4. 数据模型（3 张表）

| 模型 | 关键字段 | 作用 |
|------|----------|------|
| `AgentRun` | project FK、trigger（`manual`/`task_column`/`cicd`）、source_task FK、status（`queued→planning→executing→analyzing→reporting→done/failed/cancelled`）、plan JSON、summary、created_by、created_at、updated_at | 一次完整 Agent 任务的根记录，状态机主体 |
| `AgentStep` | run FK、step_type（`generate_cases`/`execute`/`analyze`/`report`）、status、input/output JSON、tool_name、duration_ms、created_at | 执行轨迹，前端时间线数据源 |
| `AgentEvent` | run FK、level（`info`/`warn`/`error`）、message、created_at | 实时进度流，WebSocket 推送 |

状态机非法转换拒绝（如 `done → executing`），单元测试覆盖。

## 5. 触发层

三个入口全部收敛到 `create_run()` 工厂：

1. **看板事件**：任务卡移动到标题含"测试/待测/待测试/QA"关键词的列（匹配策略同 `_find_done_column` 的关键词模糊匹配）→ 在现有 `TaskActivityLog` 挂载点追加 signal 钩子 → `create_run(trigger='task_column', source_task=task)`
2. **手动**：QA 页面"AI 执行"按钮（新 API `POST /api/qa-agent/runs/`）；AI 对话新增工具 `create_qa_agent_run`（"帮我跑一遍测试"），复用现有 `execute_tool` 注册机制
3. **CI/CD**：`PipelineRun` 状态变为 completed/failed 后自动触发回归 AgentRun（复用 `tasks_test_exec.py` 的 `poll_pipeline_status` 轮询逻辑）

## 6. 编排循环（Celery）

`run_agent_pipeline(run_id)`：

- **planning**：构建上下文（源任务卡描述/评论、项目 API 文档、已有用例列表、测试环境）→ LLM 生成计划 JSON（建哪些用例、跑哪些回归、分析要点）→ 校验结构（serializer）→ 存 `AgentRun.plan`。LLM 输出非法 → 重试 3 次 → 仍失败则降级为"仅执行已有用例"的最小计划，不阻断
- **executing**：按计划逐项调用 `execute_tool`（创建用例、执行测试任务）。每步写 `AgentStep`，经 WebSocket 推 `AgentEvent` 进度。执行失败（非用例失败，是编排/工具失败）→ 该步标记 error，继续剩余步骤
- **analyzing**：见 §7
- **reporting**：见 §8

重试与熔断：LLM 调用重试 3 次指数退避；单次 AgentRun 总超时（默认 30 分钟）→ `failed`；任何异常均落 `AgentStep` 与日志，不静默吞掉。

## 7. 失败分析（analyzing）

**输入**：失败用例的 `TestResult` + 截图（`TestScreenshot`）+ `error_message` + 用例定义（步骤/断言）+ 环境元信息。

**输出**（LLM 严格结构化 JSON，服务端 serializer 校验）：

```json
{
  "flaky": "deterministic | flaky | unknown",
  "root_cause": "bug_in_app | test_case_issue | environment_issue | unknown",
  "evidence": "判断依据摘要",
  "fix_suggestion": "选择器失效给修复建议；bug_in_app 给复现路径"
}
```

**失败聚类**：按 root_cause + 归一化错误信息聚合，同根因只建一张单。

**自动建单规则**（防噪音）：

- `bug_in_app` + `deterministic` → 在看板自动建 bug 任务（标题 `[AI-QA] <源任务> 失败用例`，负责人取源任务负责人，关联 AgentRun，内容附失败详情与复现路径；放入项目第一列，同现有 `create_task` 工具的列 fallback 逻辑）
- `flaky` / `test_case_issue` → 不建单，进入"待修复用例"清单，写进报告
- `unknown` → 不建单，报告列出

**容错**：LLM 输出解析失败 → fallback 到规则分析（关键词匹配 timeout/connection/selector 等），analyze 永不阻断主流程。

## 8. 报告（reporting）

Markdown 报告（测试范围、通过率、失败明细表、聚类摘要、待修复用例清单）：
- 回写源任务卡评论（若有 source_task）
- 存 `AgentRun.summary`
- 通过现有通知通道推送（站内通知/WebSocket）

## 9. Eval 集

目录 `qa_agent/eval/`：

- `fixtures/`：固定种子项目数据（任务卡、API 文档样例、已有用例）
- `golden/`：人工标注金标准——N 个需求 → 期望用例集合（方法/URL/断言）；M 个失败样本 → 期望分析结果（flaky/root_cause）
- `run_eval.py`（pytest，`-m eval` 标记，不阻塞主 CI）：
  - 用例生成准确率：方法/URL/断言匹配的精确率 + 召回率
  - 根因分类准确率、flaky 判定准确率（混淆矩阵）
- LLM 响应缓存到 JSON，可离线重放，控制成本

交付标准：作品集故事线"用 Eval 集量化 agent 质量，从 X% 迭代到 Y%"，至少跑出两轮数据。

## 10. 测试策略

| 层级 | 内容 |
|------|------|
| 单元 | 状态机非法转换拒绝；create_run 三入口工厂；LLM JSON 解析与校验；fallback 规则分析 |
| 集成 | mock LLM 跑通 `queued→done` 全流程，断言三张表落库 + 自动建单规则生效 |
| 真实 LLM 冒烟 | `-m live` 手动标记，不阻塞 CI |
| E2E | 复用现有 Playwright 基建，手动触发入口到进度可见 |

## 11. 路线图（6-8 周）

| 里程碑 | 内容 |
|--------|------|
| M1（1-2 周） | `qa_agent` app 骨架 + 3 张表 + 状态机 + Celery 任务 + 手动触发 API |
| M2（2-3 周） | planning（上下文 + 计划生成）+ executing（API 用例闭环跑通） |
| M3（1 周） | UI 用例接入执行 + 截图收集 |
| M4（1-2 周） | analyzing（分析 + 聚类 + 自动建单）+ reporting + WebSocket 进度 UI |
| M5（1 周） | Eval 集 + 指标 + 作品集文档/演示脚本 |

## 12. 前端改动

- 任务卡：AgentRun 徽标/进度（复用现有通知/WebSocket 模式）
- QA 页：AgentRun 列表页 + 步骤时间线（AgentStep 数据源）
- 全部复用现有 Element Plus + Pinia 模式

## 13. 权限与安全

- 沿用现有项目成员校验（`_check_project_member`）
- API 全局限流复用现有 DRF throttle
- LLM 提示词不注入明文密钥；环境变量（`qa_center.environment_security`）已遮蔽逻辑继续生效

## 14. 风险与缓解

| 风险 | 缓解 |
|------|------|
| LLM 计划/分析输出不稳定 | 结构化 schema + serializer 校验 + 重试 + fallback |
| 自动建单噪音 | 规则闸门（仅 bug_in_app+deterministic），聚类去重 |
| UI 测试环境不稳定（flaky） | flaky 判定入报告，不建单 |
| 长任务可靠性 | Celery + 超时熔断 + 状态机可取消/可查 |
| 范围蔓延 | 非目标清单（§2）在评审时强制对照 |
