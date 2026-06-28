# SyncBoard 模块清单与问答指南

> 这是一份**对话脚本**——按模块列出可问的问题，从浅入深，一题一题地把项目讲透。
>
> 答案不在这里。答案在每次问答中产生。需要背景时回查 `docs/PROJECT_DEEP_DIVE.md`。

---

## 使用说明

**怎么用这份文档**：

1. 看一眼**完成度总览表**，对项目整体心里有数（哪里强、哪里弱、哪里是 mock）
2. 翻到任一模块，从 **L1 问题**开始问起
3. 答完 L1 → 进 L2 → 进 L3，每层难度递增
4. 答 L3 卡住 → 回看 `PROJECT_DEEP_DIVE.md` 对应章节

**三个难度层次**：

| 层级 | 含义 | 答出来说明什么 |
|---|---|---|
| **L1 理解层** | 5W1H、概念解释、"是什么" | 知道这个模块在干嘛 |
| **L2 实现层** | 关键代码、边界处理、"怎么做" | 看过源码、记得细节 |
| **L3 权衡层** | 设计取舍、坑、改造方向、"为什么" | 真懂、能 own 这块代码 |

---

## 模块完成度总览

| # | 模块 | 完成度 | 关键证据 | 主要风险 / 限制 |
|---|---|---|---|---|
| 1 | 看板 Board | ✅ 完整可用 | `room/views/board.py`、`Board.vue`(944行) | Board.vue 单文件过大 |
| 2 | WebSocket 实时层 | ✅ 完整可用 | `room/consumers*.py` + `qa_center/consumers.py` | 鉴权未抽公共封装 |
| 3 | AI 助手 | ✅ 完整可用 | `ai_utils.py`(924行)、`views/ai.py:137` | 流式刻意不带 Tool Calling |
| 4 | API 测试 | ✅ 完整可用 | `api_auto_executor.py`(375行) + `test_executor.py`(490行) | 新旧两套并存；timeout 写死 30s |
| 5 | UI 测试 (Playwright) | ✅ 完整可用 | `workers/recorder_worker.py`(770行)、`runner_supervisor.py`(258行) | 录制 JS 内嵌 770 行偏重 |
| 6 | 性能测试 (Locust) | ⚠️ **有限制** | `locust_runner.py`、`views_performance.py` | **单进程，同时只能跑 1 个用例** |
| 7 | DevOps Pipeline | ⚠️ **有 mock** | `views_devops.py:746 _simulate_run` | **Pipeline 触发是 random mock，没接真 CI** |
| 8 | 质量报告 (五维) | ✅ 完整可用 | `views_devops.py:812 ProjectQualityReportView` | 部署维度依赖 mock 数据 |
| 9 | RBAC 权限 | ✅ 完整可用 | `system/*` + `room/views/project_role.py` | 项目级只校验 owner，无中间角色 |
| 10 | Sprint 燃尽图 | ✅ 完整可用 | `room/views/sprint.py`(204行) | - |
| 11 | 通知 / 审计 | ✅ 完整可用 | `room/models.py:86/164/205` | activity 只有列表接口 |
| 12 | 搜索 (Haystack) | 🚧 **半成品** | `search_indexes.py` 19 行 | **只索引 Task，无 Project/Bug/Comment** |

**一句话总结**：12 个模块里，**9 个完整可用、1 个有限制（性能）、1 个有 mock（Pipeline）、1 个半成品（搜索）**。

---

## 1. 看板 Board

**一句话**：多项目独立看板，列 + 任务卡片 + 拖拽排序 + 详情抽屉（评论 / 动态 / 附件 / 关联测试）。

**完成度**：✅ 完整可用
**关键文件**：`backend/room/views/board.py`、`frontend/src/views/Board.vue`(944行)、`frontend/src/stores/board/`(模块化 596 行)
**已知问题**：`Board.vue` 单文件偏臃肿；拖拽位置用 float 分数算法（中位数插入）

### L1 理解层
- 看板的核心实体有哪些？Project / Column / Task 之间是什么关系？
- 拖拽排序怎么实现的？为什么 Task.position 是 float？
- 为什么 Project / Column / Task 的 PK 用 UUID 而不是自增 ID？

### L2 实现层
- 拖一个任务到两个任务中间，新 position 怎么算？
- 多个用户同时拖到同一位置，会冲突吗？怎么处理？
- `Board.vue` 怎么管理拖拽状态？用了 vuedraggable 还是自己写的？
- 拖完之后，前端是先 PATCH 后渲染，还是先渲染后 PATCH？

### L3 权衡层
- float position 长时间使用会精度退化（无限插入中间），怎么修？
- `Board.vue` 944 行偏臃肿，怎么拆？拆成哪几个组件合理？
- 如果要支持"任务跨项目移动"，要改哪几处？

---

## 2. WebSocket 实时层

**一句话**：8 条 WS 路径（看板 / 聊天 / 全局通知 / QA 大盘 / 录制器 / 性能 / 运行进度 / UI 运行），统一鉴权 + 心跳 + 重连。

**完成度**：✅ 完整可用
**关键文件**：`backend/room/consumers.py`(133行)、`consumers_chat.py`(121)、`consumers_global.py`(57)、`backend/qa_center/consumers.py`(235)、`frontend/src/stores/composables/useWebSocket.ts`(139)
**已知问题**：4 个 consumer 鉴权代码重复，没抽公共 mixin

### L1 理解层
- WebSocket 在 SyncBoard 里有哪 8 条路径？每条干啥用？
- 项目里的核心架构原则"REST 写数据 + WS 只发 refresh 信号"是什么意思？为什么这样设计？
- 心跳 30s 是怎么定的？Channels 默认 idle timeout 是多少？

### L2 实现层
- 拖任务从列 A 到列 B，refresh 怎么扩散到其他在线用户？写完整时序（前端 → REST → WS → 其他客户端）。
- 鉴权失败为什么 `close(4003)` 而不是 401？
- `useWebSocket.ts` 是单例还是每页面一个？观察者模式怎么实现的？
- 一个用户开两个标签，消息会重复推送吗？业务上有问题吗？

### L3 权衡层
- 为什么 WS 只发"refresh"不发数据？换成发数据有什么好处坏处？
- Recorder 为什么不复用 `useWebSocket` 单例，要自己起一个 socket？
- 如果 Redis 挂了，看板还能拖任务吗？前端会怎么表现？
- 想加一个"@提及 push 通知"功能，应该走哪条 WS、需要新建吗？

---

## 3. AI 助手

**一句话**：DeepSeek API + RAG + Tool Calling（17 个工具）+ 流式 SSE，能在 chat 里"创建任务 / 跑测试 / 拉接口文档"。

**完成度**：✅ 完整可用
**关键文件**：`backend/room/ai_utils.py`(924行)、`backend/room/views/ai.py`、`frontend/src/views/AIChat.vue`
**已知问题**：流式接口刻意不带 Tool Calling（注释 `保持低延迟`）；`tool_rounds < 3` 兜底；context 不走 ES

### L1 理解层
- AI 在 SyncBoard 做什么？有几个入口（chat / stream / analyze）？
- 什么是 Tool Calling？跟 RAG 是什么关系？
- 流式 SSE 和普通 POST 分别用在哪里？

### L2 实现层
- `build_project_context` 一次拼几个 section？token 怎么估算和控制？
- `AVAILABLE_TOOLS` 有多少个工具？怎么注册给 DeepSeek？
- `_chat_with_tools` 循环最多几轮？拿到 `tool_calls` 后怎么塞回 messages？
- DeepSeek 调用失败有几种异常分类？分别返回什么用户文案？
- 流式接口 `get_streaming_answer` 用 `yield` 怎么转成 SSE？

### L3 权衡层
- 为什么流式接口刻意不带 Tool Calling？分两条路有什么好处和代价？
- System prompt 反复强调 "ID 是 UUID"，是基于什么真实问题？
- `build_project_context` 直接查 DB 不走 Elasticsearch，牺牲了什么？为什么？
- 用 DeepSeek 而不用 OpenAI，是基于什么考虑？SDK 怎么兼容的？
- 想加一个"自动生成迭代周报"工具，需要改哪几个文件？

---

## 4. API 测试

**一句话**：新旧两套执行器并存——旧版 `test_executor.py`（用于 DevOps + 旧用例），新版 `api_auto_executor.py`（变量池 + 模板引擎 + 统一断言 + 自动建 Bug）。

**完成度**：✅ 完整可用
**关键文件**：`backend/qa_center/api_auto_executor.py`(375行)、`test_executor.py`(490行)、`unified_assertions.py`(715行)、`template_engine.py`(151行)、`bug_utils.py`(129行)
**已知问题**：新版 `timeout=30` 硬编码、`headers` 不 copy 有 mutate 风险、`unified_assertions.py:621` 有"未实现的断言类型"占位

### L1 理解层
- 一个 API 测试用例包含哪些字段？怎么和"项目"和"任务"关联？
- 旧版 `test_executor` 和新版 `api_auto_executor` 有什么本质差异？为什么并存？
- 变量池是什么？三层优先级是哪三层？

### L2 实现层
- 新版 `_execute_case` 一次执行做哪几步（render → 发请求 → 断言 → 提取）？
- `{{var}}` 找不到变量时是返回空串还是保留原样？为什么？
- `resolve_url` 怎么处理 `base_url` 拼接（绝对 URL vs 相对路径）？
- `_smart_eq` 为什么要单独处理 bool？（`True == 1` 在 Python 里成立）
- Suite 里 case A 拿 token、case B 使用，怎么传递？写出 extractor + variable 链路。
- 失败自动建 Bug 怎么去重？相同 case 失败 100 次会建 100 个 Bug 吗？

### L3 权衡层
- `timeout=30` 写死，慢接口怎么办？为什么 `run_plan_executor` 那边用了 `case.timeout_seconds` 这边没用？
- `headers = case.headers` 不 copy 直接引用有什么风险？
- 旧版执行器什么时候下线？现在还有谁在引用？
- 跨 suite 变量传递没做，意味着什么？为什么不做？
- 断言类型 `_smart_eq` 容错"30" == 30，但有什么场景下这种容错会咬人？

---

## 5. UI 测试 (Playwright 录制 / 回放)

**一句话**：Django 主进程 → subprocess(Playwright) → stdin/stdout JSON Lines → WebSocket 推前端。录制时注入 JS 抓 DOM 事件，回放时单步执行。

**完成度**：✅ 完整可用
**关键文件**：`workers/recorder_worker.py`(770行)、`runner_worker.py`(283)、`runner_supervisor.py`(258)、`recorder_supervisor.py`(115)、`qa_center/consumers.py`(RecorderConsumer 部分)
**已知问题**：录制 JS 内嵌 770 行偏重；watchdog 5min 写死；Chromium 子进程清理依赖启动时扫描 `.playwright-temp/`

### L1 理解层
- UI 测试整体架构：录制和回放各走什么链路？
- 为什么用 subprocess 而不是 asyncio 协程跑 Playwright？
- "稳定 selector" 是什么意思？为什么要过滤 `el-id-*`？

### L2 实现层
- 用户在 Chromium 里点 el-select 的下拉项，事件怎么传到前端步骤列表？写完整时序。
- `_RUNNERS` 全局表用来干什么？为什么需要 Lock？
- `_EVENTS` 历史事件缓存 60 秒，目的是什么？前端断开重连怎么用它？
- watchdog Timer 5 分钟超时，会怎么终结子进程？stderr drain 单独线程是为什么？
- 中止录制时 Playwright Chromium 没关干净，会留下什么进程？怎么清理？

### L3 权衡层
- stdin/stdout JSON Lines vs Redis pub/sub，为什么选前者？
- 5 个用户同时录制，进程怎么管？会串吗？资源开销怎么样？
- 录制时为什么 click input wrapper 不录、等 change 才录 fill？
- el-select 用 `wrapper + has-text("选项文本")` 还原 selector，选项文本改了会怎样？
- 录制脚本 770 行内嵌 JS 维护起来难，有什么拆分方案？

---

## 6. 性能测试 (Locust)

**一句话**：动态生成 `locustfile_current.py`（注入 `events.test_start / test_stop / request` 三个钩子）→ subprocess 跑 Locust headless → 文件 IPC 写 metrics → monitor 线程 0.5s 读 → group_send 推前端 ECharts。

**完成度**：⚠️ **基本可用，有重要限制**
**关键文件**：`backend/qa_center/locust_runner.py`、`views_performance.py`
**已知问题**：
- **同时只能跑 1 个用例**（固定文件名 `locustfile_current.py`，`self.process` 单例）
- `response_times` deque maxlen=10000，高 N 时 p99 不准
- percentile 用 sorted 排序，O(N log N)
- 主写子读同一文件无锁，偶发读到半 JSON（靠 try/except 兜底）

### L1 理解层
- 性能测试整体架构：从前端点"开始压测"到 ECharts 出图，走了几步？
- 为什么用文件 IPC 而不用 Redis 传 metrics？
- TestMetrics dataclass 里有哪些核心指标（p50/90/95/99 / throughput / error_rate）？

### L2 实现层
- `generate_locustfile` 怎么把 test_case 拼成 Python 代码字符串？
- `@events.request.add_listener` 在做什么？每个 request 都触发吗？为什么"每 10 次 write 一次"？
- monitor 线程 0.5s 一次，怎么判断 Locust 子进程已退出？
- p99 怎么算的？写出代码或公式。
- 子进程写 JSON 时主进程读到半个文件会怎样？怎么兜底？

### L3 权衡层
- 同时跑两个性能测试会怎样？现在为什么不支持？要支持改哪？
- response_times maxlen=10000，1000 req/s 跑 1 分钟就溢出，p99 会失真，怎么改更精确？
- 文件 IPC 不支持跨机器，多 Django 实例部署怎么办？
- 想加 SLA 告警（p95 > 500ms 就告警），改哪几处？
- 前端 WS 断开，性能测试还跑完吗？指标会丢吗？

---

## 7. DevOps Pipeline

**一句话**：四块业务——Dashboard 大盘 / CI/CD 配置 CRUD / Pipeline 触发与 Webhook / TestTask 编排。**Pipeline 触发是 mock，没接真 Jenkins**。

**完成度**：⚠️ **基本可用，含明显 mock**
**关键文件**：`backend/qa_center/views_devops.py`(908行)
**已知问题**：
- `_simulate_run` (`views_devops.py:746`) 是 `time.sleep(3) + random.random()` 随机生成 passed/failed，**没真调 Jenkins/GitLab**
- 真实路径只有 Webhook 回调能用（外部 CI 主动推过来）
- TestTask 后台用 `threading.Thread(daemon=True)`，Django 重启即丢任务
- Webhook `permission_classes=[]` 公开端点，靠 X-CI-Token 校验

### L1 理解层
- DevOps 模块四块业务分别是什么？数据流大致如何？
- Pipeline 和 TestTask 是什么关系？
- 什么是 CI/CD Webhook 回调？什么时候用？

### L2 实现层
- `PipelineRunTriggerView` 触发后做了什么？`_simulate_run` 干嘛的？
- Webhook 端点用 `permission_classes=[]` 怎么鉴权的？token 在 header 还是 body？
- `TestTaskExecuteView` 启动后台执行用 threading 还是 Celery？为什么？
- `_send_notification` 双写（WS + DB）是怎么实现的？为什么活跃用户限 50 个？

### L3 权衡层
- Pipeline 触发是 mock，五维评分里的"部署成功率"还有意义吗？
- 怎么从 mock 切到真实 Jenkins？需要改哪几处？
- threading 后台任务 Django 重启就丢，怎么改 Celery？改造代价多大？
- Webhook `permission_classes=[]` + token 校验有什么漏洞？怎么加固（HMAC 签名 / IP 白名单 / timestamp 防重放）？
- Dashboard 接口 30 天循环查 N 次 DB，数据量大会卡，怎么优化？

---

## 8. 质量报告（五维评分）

**一句话**：五个维度各 20 分——测试覆盖率 / 通过率 / 性能 / Bug 密度 / 部署成功率，雷达图 + 趋势图。

**完成度**：✅ 完整可用（但部署维度依赖 mock 数据）
**关键文件**：`backend/qa_center/views_devops.py:812 ProjectQualityReportView`
**已知问题**：阈值硬编码（P95 < 500/1000/2000）；部署成功率分子分母来自 `_simulate_run` 的 PipelineRun

### L1 理解层
- 五维评分是哪五维？分数 0~100 怎么分配？
- 雷达图前端怎么画？用了 ECharts 哪个组件？

### L2 实现层
- "测试覆盖率" 维度的分子分母是什么？（关联了任务的测试 / 总任务？）
- "Bug 密度" 怎么算？包含哪些状态的 Bug（open / in_progress / closed）？
- "性能" 维度阈值是怎么定的？P95 < 500ms = 满分？
- 30 天趋势数据是实时算还是缓存？

### L3 权衡层
- 部署成功率依赖 mock 数据，这个维度有意义吗？怎么改让它有意义？
- 阈值硬编码（P95 < 500ms）合理吗？不同项目（前端 / 后端 / 大数据）阈值应该一样吗？
- 五维评分的权重都是 20%，合理吗？业务上哪个最重要？
- 想加第六维"代码质量"（SonarQube 集成），怎么扩展？

---

## 9. RBAC 权限

**一句话**：两级权限——系统级（Menu / Role / SystemUserProfile 通过 `HasSystemPermission` 强制）+ 项目级（ProjectRole / ProjectMember 四级 owner/admin/editor/viewer）。

**完成度**：✅ 完整可用
**关键文件**：`backend/system/models.py`(105行)、`system/views.py`(253)、`system/permissions.py:HasSystemPermission`(32)、`room/views/project_role.py`(124，**只校验 owner**)
**已知问题**：项目级实际**只校验 `project.owner == request.user`**，没有真正的"项目管理员"中间角色生效——表上有 ProjectRole 4 级，但接口里没区分

### L1 理解层
- 两级权限分别管什么？为什么要分两级？
- 系统级 RBAC 三个核心模型（Menu / Role / SystemUserProfile）各自干啥？
- 前端是怎么做权限控制的（路由守卫 + `v-permission` 指令）？

### L2 实现层
- `HasSystemPermission` 怎么判断当前用户能不能访问某个 API？(View × HTTP method 映射)
- 项目级权限当前是怎么校验的？看 `project_role.py` 的实际逻辑。
- WebSocket 鉴权怎么做？跟 REST 一致吗？
- 前端 `v-permission` 指令是响应式的吗？刷新 token 后能自动更新吗？

### L3 权衡层
- 项目级 ProjectRole 4 级表都设计了，但实际只看 owner，是有意还是 TODO？
- 想真正启用 admin / editor / viewer 区分，要改哪些 View？工作量多大？
- 审计日志（AuditLog）有了，但没用中间件统一记录，怎么改？
- 想加"临时访客"（带过期的只读访问），怎么扩展模型？

---

## 10. Sprint 迭代 + 燃尽图

**一句话**：Sprint CRUD + 任务关联 + 燃尽图（理想线 vs 实际剩余）。

**完成度**：✅ 完整可用
**关键文件**：`backend/room/views/sprint.py`(204行)、`frontend/src/views/SprintBoard.vue`
**已知问题**：空 sprint 返回空数组（边界处理 OK）

### L1 理解层
- Sprint 是什么？跟 Task 怎么关联（SprintTask M2M）？
- 燃尽图的横轴 / 纵轴 / 理想线 / 实际线分别表示什么？

### L2 实现层
- `SprintBurndownView` 怎么算每天的"剩余任务数"？
- 一个任务中途从 Sprint 里移出，燃尽图会怎么显示？
- 燃尽图前端用 ECharts 还是其他库画的？

### L3 权衡层
- 燃尽图按任务数算 vs 按 story points 算，差异在哪？现在用的哪个？
- 想加"Sprint 速率（velocity）"指标，怎么实现？
- 跨 Sprint 任务（一个任务横跨两个 Sprint）怎么处理？

---

## 11. 通知 / 审计 / 任务动态

**一句话**：三套独立日志——Notification（用户消息）/ AuditLog（系统操作）/ TaskActivityLog（任务变更时间线）。

**完成度**：✅ 完整可用
**关键文件**：`backend/room/models.py:86 Notification`、`:164 TaskActivityLog`、`:205 AuditLog`、`room/views/notification.py`、`activity.py`(32行)
**已知问题**：activity.py 只 32 行（只有列表接口）；没用中间件统一审计

### L1 理解层
- 三套日志各自记录什么？写入路径是什么？
- 通知的实时推送和持久化是怎么并存的（WS + DB 双写）？

### L2 实现层
- TaskActivityLog 在哪些操作时被写入？(创建 / 更新 / 移动 / 分配 / 评论 / 附件...)
- Notification.bulk_create 给前 50 个活跃用户，怎么定义"活跃"？
- AuditLog 记录哪些字段（user / action / resource / ip / timestamp）？

### L3 权衡层
- 三套日志能合成一套吗？为什么分开？
- 用户量大（10w+）时 Notification.bulk_create 50 条会不会有性能问题？要改成按项目筛吗？
- 想加"日志保留 90 天自动清理"，用什么机制（Celery beat / DB partition）？

---

## 12. 搜索 (Haystack + Elasticsearch)

**一句话**：Haystack + ES7 Ngram 中文分词，**目前只索引 Task**。

**完成度**：🚧 **半成品**
**关键文件**：`backend/room/search_indexes.py`(19行，只 1 个 TaskIndex)、`views_search.py`(34行)
**已知问题**：
- 只索引 Task 一个模型
- 没有 Project / Bug / TaskComment / ProjectApiDoc 索引
- AI 域刻意不走 ES（避免 ES 挂了 AI 也挂）

### L1 理解层
- 项目里搜索能搜什么？现在只搜 Task 是因为啥？
- 为什么用 Ngram 而不是 ik_analyzer 之类的中文分词？

### L2 实现层
- `TaskIndex` 索引了哪些字段？哪些是 NgramField 哪些是 CharField？
- 索引更新走的是 Celery signal_processor 异步还是同步？
- 搜索接口 `views_search.py` 怎么写的？返回结构是什么？

### L3 权衡层
- 想加 Bug / Comment / ApiDoc 搜索，怎么扩展？工作量多大？
- AI 域刻意不走 ES（直接查 DB），牺牲了什么？什么时候应该改回走 ES？
- ES 挂了搜索接口会怎样？前端能容错吗？

---

## 推荐问答顺序

按这个顺序问，认知节奏最顺：

1. **看板（1）** — 简单，建立对话节奏，搞清楚 UUID / float position 这些基础
2. **WebSocket（2）** — 核心架构原则（"REST 写数据 + WS 只通知"）
3. **AI 助手（3）** — 最有技术含量的部分，Tool Calling + 流式
4. **API 测试（4）** — QA 三件套之一，新旧执行器对比是好戏
5. **UI 测试（5）** — 最复杂，子进程 + JSON Lines + WS 的组合拳
6. **性能测试（6）** — 简短，但有"单进程限制"这个明确缺陷可讲
7. **DevOps Pipeline（7）** — 含 mock，**要诚实**地把"未接真 CI"讲出来
8. **质量报告（8）** — 综合产物
9. **RBAC（9）** — 比较常规，但项目级"只校验 owner"是个亮点缺陷
10. **Sprint（10）** — 简短
11. **通知 / 审计（11）** — 简短
12. **搜索（12）** — 收尾，承认是半成品

**面试 / 答辩时**：建议主推 2 / 3 / 5（WS / AI / UI 测试），这三块技术含量最高。
**坦诚加分项**：主动提 6 / 7 / 12 的限制（性能单进程、Pipeline mock、搜索半成品），比被问出来再说更好。

---

## 交叉引用

每个模块的"标准答案"和代码细节都在 `docs/PROJECT_DEEP_DIVE.md` 对应章节：

| 模块 | DEEP_DIVE 章节 |
|---|---|
| WebSocket | 第 1 章 |
| AI 助手 | 第 2 章 |
| API 测试 | 第 3 章 |
| UI 测试 | 第 4 章 |
| 性能测试 | 第 5 章 |
| DevOps | 第 6 章 |
| 端到端串讲 | 第 7 章 |
| UUID 表 | 附录 A |
| WS 路径总表 | 附录 B |
| 必读 6 文件 | 附录 C |

看板 / RBAC / Sprint / 通知 / 搜索 这五块在 DEEP_DIVE 没单独章节，回查源码即可（路径见上）。

---

**准备好了吗？** 从模块 1 的 L1 第一题开始：

> "看板的核心实体有哪些？Project / Column / Task 之间是什么关系？"
