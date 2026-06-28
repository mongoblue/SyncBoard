# SyncBoard 自动化测试平台 - v3 开发计划

> 日期: 2026-06-09
> 范围: 接口测试完整性 / 压力测试稳定化 / DevOps 批量执行 / Bug 完整生命周期
> 不在范围: UI 测试（用户明确说暂时不动）

---

## 一、项目现状盘点（已读 README + 关键源码）

### 已经具备
- 双套 API 测试模型：
  - 单接口：`ApiTestCase` + `ApiTestResult`（views_api_test.py，用 Django Test Client 内部调用）
  - 自动化套件：`ApiAutoTestSuite` / `ApiAutoTestCase` / `ApiAutoTestAssertion` / `ApiAutoTestResult` / `ApiAutoTestCaseResult`（api_auto_executor.py，用 requests 外部调用）
- 两套断言引擎：`assertion_engine.py`（jsonpath_ng）+ `api_auto_executor.py::AssertionExecutor`（jsonpath）
- 压测：`locust_runner.py` 通过 subprocess + 临时 JSON 文件做进程间通信
- DevOps：`TestTask` / `CiCdConfig` / `PipelineRun` + `DashboardStatsView`、`ProjectQualityReportView`
- 测试失败自动建 Bug：`bug_utils.py::create_bug_from_test_failure`，给 Task 打 `Bug` + `Auto-generated` 标签

### 四大短板（对应你的四个诉求）

#### 1) 接口测试不够"完整"
- **两套断言并存且能力不一致**：`AssertionExecutor` 支持 5 种类型，`AssertionEngine` 支持 status_code/jsonpath/header 但不支持 response_time。后端切换路径时行为不一致。
- **断言能力欠缺**：没有 schema 校验、不支持响应头断言（自动化套件路径）、不支持正则/类型断言、不支持响应体长度断言。
- **变量与依赖缺失**：无环境变量（base_url、token）、无前置脚本、无用例间数据传递（登录→拿token→调下一个接口）。用户当前要把完整 URL 写死在每条用例里。
- **请求能力欠缺**：不支持 query 参数独立配置（混在 URL 里）、不支持文件上传、不支持 Cookie 持久化、超时硬编码 30s。
- **结果展示薄弱**：`ApiTestResult.response_body` 是纯字符串、断言失败时前端没有 diff 视图、没有 cURL 复制、没有重新执行。

#### 2) 压力测试问题多
- **子进程 + 文件 IPC 脆弱**：locustfile 在 tempdir、metrics 写文件、监控线程轮询，并发执行多个压测会互相覆盖（`locustfile_current.py`、`locust_metrics_current.json` 是固定文件名）。
- **单接口压测**：locustfile 模板只支持一条用例，无法做"业务场景压测"（登录+下单+查询的混合）。
- **配置项暴露不全**：思考时间硬编码 `between(0.1, 0.5)`、ramp_up 实际未生效（命令里只用了 spawn-rate）。
- **结果没沉淀**：测试结束时数据停在 `LocustRunner.metrics`，没有规范地落库到 `PerformanceTestResult`（核心字段如 p50/p90/p95/p99 时序），看不到历史对比。
- **预期阈值不参与判定**：`expected_response_time_ms` / `expected_error_rate` 存了但没拿来判 pass/fail，自然也不会触发自动建 Bug。

#### 3) DevOps "十条接口一次跑完 + 结果中心清晰看" 缺口
- `TestTaskExecuteView._execute_test_task` 只把 case_ids 透传给 `execute_api_test_cases`，逻辑是顺序执行；用例数大时无并发、无超时控制、无中断。
- `TestResult.test_log` 把所有用例结果 JSON-dump 进一个 TextField，前端要解析字符串才能展示，无法分页、过滤、按用例查看断言详情。
- 没有"批量任务进度"接口（前端只能轮询整体 status，不知道现在跑到第几条）。
- 结果中心 `TestResultList.vue` 是平铺列表，看不出"这次执行包含 10 条用例，每条结果是什么"——批量执行的层次结构在数据库里压根没建模（缺中间表）。

#### 4) Bug 生命周期不完整
- `bug_utils.py` 创建出来的就是普通 `Task`，**没有任何 Bug 专属字段**：无严重程度、无优先级、无复现步骤、无环境、无状态机、无指派人变更历史、无"开发→测试"流转记录。
- 当前用列名 `done` 判断"是否关闭"，用 `Tag('Bug')` 标识"是否是 bug"——这是约定，不是模型。
- 没有 Bug 列表页（只能在看板上靠标签筛）。
- 没有禅道式状态机：`新建 → 已确认 → 已指派 → 修复中 → 已修复 → 待验证 → 已关闭 / 重新打开`。
- 没有"分配给谁、由谁修复、由谁验证"的角色字段（只有单一 `assignee`）。
- 没有 Bug 与测试结果的强关联（虽然 `related_tasks` 是 ManyToMany，但反查"这个 bug 是哪次测试在哪条用例上失败产生的"路径太绕）。

---

## 二、开发计划（按优先级 P0 → P2，分四个里程碑）

### 里程碑 M1：Bug 完整生命周期（P0 - 最高优先级）

> 你最看重的，先做。改动相对独立，对其他模块零侵入。

#### 1.1 数据模型
新建 `bug_tracker` Django app，定义 `Bug` 模型（不复用 Task，避免污染看板）：

```python
class Bug(models.Model):
    STATUS = [
        ('new', '新建'),
        ('confirmed', '已确认'),
        ('assigned', '已指派'),
        ('fixing', '修复中'),
        ('fixed', '已修复'),
        ('verifying', '待验证'),
        ('closed', '已关闭'),
        ('reopened', '重新打开'),
        ('rejected', '已拒绝'),
    ]
    SEVERITY = [('blocker','阻塞'),('critical','严重'),('major','一般'),('minor','次要'),('trivial','轻微')]
    PRIORITY = [('p0','P0'),('p1','P1'),('p2','P2'),('p3','P3')]

    project       = FK(Project)
    title         = CharField
    description   = TextField
    steps_to_reproduce = TextField   # 复现步骤
    expected      = TextField        # 预期结果
    actual        = TextField        # 实际结果
    environment   = CharField        # dev/staging/prod
    severity      = CharField(choices=SEVERITY, default='major')
    priority      = CharField(choices=PRIORITY, default='p2')
    status        = CharField(choices=STATUS, default='new')

    reporter      = FK(User, related_name='reported_bugs')      # 测试提的人
    assignee      = FK(User, related_name='assigned_bugs')      # 当前指派给谁
    fixer         = FK(User, related_name='fixed_bugs', null=True) # 修复者
    verifier      = FK(User, related_name='verified_bugs', null=True) # 验证者

    # 关联测试来源（可空，手动建的 bug 没有）
    source_test_type = CharField(choices=[('api_auto','接口自动化'),('performance','性能'),('manual','手工')], default='manual')
    source_case_id   = IntegerField(null=True)   # ApiAutoTestCase / PerformanceTestCase id
    source_result_id = IntegerField(null=True)   # 对应 result id

    # 关联看板任务（可选，方便排期）
    linked_task = FK('room.Task', null=True, on_delete=SET_NULL)

    created_at, updated_at, closed_at

class BugTransition(models.Model):
    """状态流转记录 - 谁、什么时候、从什么状态、到什么状态、为什么"""
    bug = FK(Bug, related_name='transitions')
    operator = FK(User)
    from_status, to_status = CharField, CharField
    comment = TextField(blank=True)
    created_at = DateTimeField(auto_now_add=True)

class BugComment(models.Model):
    bug, author, content, created_at
```

#### 1.2 状态机校验
后端用一个 `BUG_TRANSITIONS` 字典定义允许的流转，禁止非法跳转：

```
new       → confirmed, rejected
confirmed → assigned
assigned  → fixing, rejected
fixing    → fixed
fixed     → verifying
verifying → closed, reopened
reopened  → assigned
closed    → reopened   (回归发现问题)
```

#### 1.3 API
- `POST   /api/bugs/`                      创建 bug（测试提）
- `GET    /api/bugs/?project=&status=&assignee=&severity=&reporter=`  列表 + 筛选 + 分页
- `GET    /api/bugs/{id}/`                 详情（含 transitions + comments）
- `PATCH  /api/bugs/{id}/`                 改字段
- `POST   /api/bugs/{id}/transition/`      流转状态 `{to_status, comment}`，后端校验状态机
- `POST   /api/bugs/{id}/assign/`          指派 `{user_id}`
- `POST   /api/bugs/{id}/comments/`        加评论
- `GET    /api/bugs/my/?role=assignee|reporter|fixer|verifier`  我相关的 bug

#### 1.4 前端
新增页面：
- `views/bug/BugList.vue`        全项目 bug 列表 + 多维筛选 + 状态徽章
- `views/bug/BugDetail.vue`      详情 + 状态流转按钮（按当前状态动态显示可流转目标）+ 时间线
- `views/bug/MyBugs.vue`         「分配给我的」「我提的」「我修的」「待我验证」四个 tab
- 顶栏通知小红点：bug 被指派 / 被 reopen 时通知到人

#### 1.5 改造 `bug_utils.py`
把现有"测试失败→建 Task"改造成"测试失败→建 `Bug` 记录（status=new, source_test_type=api_auto）"，自动 assignee=测试用例的 `created_by`，并把 `source_case_id` / `source_result_id` 写进去——这样测试报告→bug→修复→验证形成闭环。

#### 1.6 工作量预估
- 后端 model + migration + serializer + view + 状态机校验 + 测试：**3 天**
- 前端 3 个页面 + 状态流转 UI：**3 天**
- bug_utils 改造 + 自动化测试入口联调：**1 天**

---

### 里程碑 M2：DevOps 批量执行 + 结果中心可观测（P0）

> "十条接口一次跑完 + 结果清晰"

#### 2.1 复用现有 `ApiAutoTestSuite`，补足批量执行能力
现状已有套件→用例→断言→结果四层模型，方向对，但执行器需要增强：

**改 `api_auto_executor.py`：**
- 增加 `parallel: bool` 和 `max_workers: int` 参数，用 `concurrent.futures.ThreadPoolExecutor` 并发执行用例
- 用例间共享一个 `requests.Session`（保持 cookie / 连接复用）
- 增加执行进度上报：每完成一个用例，通过 WebSocket 推送到 `/ws/qa/dashboard/`，前端可看进度条
- 增加"遇错继续 / 遇错中止"开关 `stop_on_failure`
- 单用例超时改成可配置（用例表加 `timeout_seconds` 字段）

**新增"批量执行计划"概念：**
新加模型 `TestRunPlan`，用来描述一次"勾选 N 条用例一次跑完"——它不要求预先建套件：
```python
class TestRunPlan(models.Model):
    project, name, case_ids (JSONField), parallel, max_workers, stop_on_failure
    created_by, created_at
```
对应接口 `POST /api/qa/run-plans/` + `POST /api/qa/run-plans/{id}/execute/`。这样用户可以"项目里勾 10 条 → 起名 → 跑 → 看结果"，不必为临时组合建一个 Suite。

#### 2.2 结果中心层次化展示
**后端：** `ApiAutoTestCaseResult` 已经存在，给它补一个列表接口：
- `GET /api/qa/auto-results/{result_id}/cases/?passed=&page=`
  分页返回每条用例的执行明细（status_code、response_time、断言通过率、错误摘要），不再把全部塞进 `test_log` 字符串。

**前端改造 `TestResultDetail.vue`：**
- 顶部：执行概览卡片（通过/失败/错误数、总耗时、通过率）
- 中部：用例结果表格（支持按状态过滤、按耗时排序、行展开看 request/response/断言详情）
- 右侧抽屉：单条用例的请求/响应原文 + 断言 diff（实际 vs 期望，红绿高亮）+「重新执行此用例」按钮
- 顶部「一键为所有失败用例建 Bug」按钮（调 M1 的 bug 接口）

#### 2.3 DevOps 仪表板增强
`DevOpsPlatform.vue` 现在只展示"最近执行 + 统计"，需要：
- 增加「批量执行入口」：选项目 → 多选用例（带搜索、tag 过滤）→ 配置并发数 → 启动
- 实时进度条（订阅 `/ws/qa/dashboard/`）
- 历史执行列表点击直跳新的结果详情页

#### 2.4 工作量
- 后端执行器并发 + 进度上报 + 批量计划 + 用例明细接口：**3 天**
- 前端结果详情重构 + 批量执行 UI + 进度可视化：**3 天**

---

### 里程碑 M3：接口测试完整性（P1）

#### 3.1 统一断言引擎
删除 `assertion_engine.py`，全部走 `api_auto_executor.py::AssertionExecutor`，并扩展：
- 新增 `header_equals` / `header_exists`
- 新增 `body_size`（响应体字节数）
- 新增 `regex_match`（正则匹配字段值）
- 新增 `type_check`（断言字段类型：int/str/list/dict/bool/null）
- 新增 `schema_validate`（用 jsonschema 校验整个响应）
- 把单接口 `views_api_test.py::run` 也切到统一引擎，行为一致

#### 3.2 环境与变量
新增模型：
```python
class TestEnvironment(models.Model):
    project, name (dev/staging/prod), base_url, variables (JSONField: {key: value})
class TestGlobalVar(models.Model):
    project, name, value, is_secret
```
执行器在替换变量时：`{{base_url}}/api/users/{{user_id}}` → 实际值。用例编辑器里 URL/headers/body 都支持 `{{var}}` 语法。

#### 3.3 用例间数据传递（提取器）
给 `ApiAutoTestCase` 加一张子表 `ApiAutoTestExtractor`：
```python
extractor = (case, name='token', json_path='$.data.access_token', save_to='session')
```
后续用例可用 `{{token}}` 引用。这是"自动化"的核心能力。

#### 3.4 请求能力补全
- `ApiAutoTestCase` 拆出 `query_params` 字段（JSON），与 URL 分离
- 支持文件上传：`form_files` 字段
- 支持 Cookie 持久化（套件级 session）
- 超时可配置（用例字段 `timeout_seconds`，默认 30）

#### 3.5 前端用例编辑器增强
- Tab 化：Params / Headers / Body / Auth / Assertions / Extractors / Pre-script
- 断言可视化编辑（不再让用户写 JSON）
- 响应预览支持 JSON 树形展示 + JSONPath 实时测试器
- "Copy as cURL" 按钮

#### 3.6 工作量
- 后端模型 + 断言引擎扩展 + 变量替换 + extractor：**4 天**
- 前端编辑器重构：**4 天**

---

### 里程碑 M4：压力测试稳定化（P1）

#### 4.1 修掉固定文件名冲突
`locust_runner.py` 当前用 `locustfile_current.py` / `locust_metrics_current.json` 固定路径——并发执行第二个压测会覆盖第一个。改为按 `execution_id` 分目录：
```
tempdir/syncboard-locust/{execution_id}/locustfile.py
tempdir/syncboard-locust/{execution_id}/metrics.json
```
`LocustRunner` 实例从单例改成"每次执行新建一个，按 execution_id 索引"。

#### 4.2 业务场景压测
新增模型 `PerformanceScenario`，一个场景 = 多条 `PerformanceScenarioStep`，每步是一条 HTTP 请求 + 权重 + 思考时间。locustfile 生成器改成读 scenario 而非单 case。

#### 4.3 阈值判定 + 自动建 Bug
执行结束时，对照 `expected_response_time_ms`（用 P95 比对）和 `expected_error_rate`，超阈值就把 `TestResult.status='failed'`，并调 `bug_utils` 建 Bug（source_test_type='performance'）。

#### 4.4 结果落库
执行结束后，把 `TestMetrics` 完整写入 `PerformanceTestResult`，包括时序数组（throughput_over_time、response_time_over_time），不再只活在内存里。前端可看历史对比图。

#### 4.5 配置项放开
- `wait_time` (思考时间 min/max) 暴露到用例字段
- `ramp_up_seconds` 真正生效（locust 命令加 `--spawn-rate` 计算：users/ramp_up）

#### 4.6 工作量
- 修文件冲突 + 按执行隔离：**1 天**
- 业务场景模型 + locustfile 生成器：**3 天**
- 阈值判定 + 结果落库 + 自动建 Bug 联调：**2 天**

---

### 里程碑 M5（可选 P2）：质量看板回路
- 项目 `BugDashboard`：未关闭 bug 数 / 严重度分布 / 解决周期均值 / 重开率
- 把 bug 密度指标接入现有 `ProjectQualityReportView`（取代当前按 Tag 数 bug 的方式）
- 报告导出（HTML/PDF）

---

## 三、推荐执行顺序与时间线

| 周次 | 里程碑 | 产出 |
|------|--------|------|
| 第1周 | M1 Bug 生命周期（后端）| Bug 模型/状态机/API/迁移 |
| 第2周 | M1 Bug 生命周期（前端）+ bug_utils 改造 | 三个页面 + 闭环 demo |
| 第3周 | M2 DevOps 批量执行（后端）| 并发执行器 + 进度上报 + 明细接口 |
| 第4周 | M2 结果中心重构（前端）| 用例级展示 + 批量入口 |
| 第5周 | M3 接口测试完整性（后端）| 统一断言 + 变量 + extractor |
| 第6周 | M3 编辑器（前端）| 可视化断言 + JSONPath 测试器 |
| 第7周 | M4 压测稳定化 | 隔离 + 场景 + 阈值 + 落库 |
| 第8周 | M5（可选）+ 整体回归 | 质量看板 + bug fix |

---

## 四、风险与建议

1. **数据迁移**：M1 引入 `Bug` 表后，历史用 Task 当 bug 的数据要不要回填？建议写一次性脚本：扫所有打了 `Bug` 标签的 Task，自动建对应 `Bug` 记录并 `linked_task` 指回去，原 Task 保留。
2. **不要再复用 Task 当 Bug**：明确分家，否则状态机和看板拖拽逻辑会互相干扰。
3. **两套断言一定要先统一再扩展**——别在两边都加新类型。
4. **压测固定文件名是隐藏 bug**，建议 M4 提前到 M2 之后做，避免演示批量执行时撞车。
5. **WebSocket 进度上报**已有 `/ws/qa/dashboard/`，复用即可，不要再开新通道。

---

## 五、本次未涵盖（按你的要求）
- UI 测试模块完全不动（保留 Playwright 录制器现状）
- 不涉及 AI 模块、看板核心、权限系统改造
