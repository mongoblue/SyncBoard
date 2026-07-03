# SyncBoard 压力测试模块 — 开发与审计文档 v2

> **审计日期**: 2026-07-02  
> **审计范围**: `backend/qa_center/` 中全部性能/压力测试代码，及 `frontend/src/` 对应 UI 层  
> **分支**: `dev`  
> **架构版本**: v1 — 三层执行架构（Engine → Worker → Runner）  
> **测试框架**: Locust  

---

## 目录

1. [架构总览](#1-架构总览)
2. [三层执行架构](#2-三层执行架构)
3. [组件详解](#3-组件详解)
   - [3.1 数据模型](#31-数据模型)
   - [3.2 执行引擎 (ExecutionEngine)](#32-执行引擎-executionengine)
   - [3.3 工作器 (ExecutionWorker)](#33-工作器-executionworker)
   - [3.4 适配器 (LocustRunner)](#34-适配器-locustrunner)
   - [3.5 并发控制 (PerfSemaphore)](#35-并发控制-perfsemaphore)
   - [3.6 测试任务 (TestJob)](#36-测试任务-testjob)
   - [3.7 Celery 薄壳 (tasks.py)](#37-celery-薄壳-taskspy)
   - [3.8 API 视图层](#38-api-视图层)
   - [3.9 WebSocket 实时推送](#39-websocket-实时推送)
   - [3.10 DevOps 集成路径](#310-devops-集成路径)
4. [统一调用链路](#4-统一调用链路)
5. [前端组件](#5-前端组件)
6. [完整数据流](#6-完整数据流)
7. [设计决策与权衡](#7-设计决策与权衡)
8. [审计发现](#8-审计发现)
   - [8.1 已修复问题](#81-已修复问题)
   - [8.2 剩余问题](#82-剩余问题)
   - [8.3 安全审计](#83-安全审计)
9. [测试覆盖](#9-测试覆盖)
10. [文件清单](#10-文件清单)
11. [演进路线图](#11-演进路线图)

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Vue 3)                                │
│                                                                         │
│  PerformanceTestResult.vue  ──── 性能测试管理页面                        │
│  DevOpsPlatform.vue         ──── DevOps 平台入口                         │
│  TestConsole.vue            ──── 测试控制台                              │
│                                                                         │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ REST API     │  │ WebSocket        │  │ ECharts 图表     │          │
│  │ axios calls  │  │ /ws/qa/perf/{id} │  │ RPS/RT/错误率   │          │
│  └──────┬───────┘  └────────┬─────────┘  └──────────────────┘          │
└─────────┼──────────────────┼───────────────────────────────────────────┘
          │                  │
┌─────────┼──────────────────┼───────────────────────────────────────────┐
│         ▼                  ▼              BACKEND (Django)              │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                       URL Routing                             │      │
│  │  /qa/performance-cases/        PerformanceTestCase CRUD       │      │
│  │  /qa/performance-results/      PerformanceTestResult RO       │      │
│  │  /qa/devops/tasks/{id}/execute/  TestTask (perf分支)           │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                             │                                           │
│              ┌──────────────┴──────────────┐                            │
│              ▼                              ▼                            │
│  ┌──────────────────────┐    ┌──────────────────────────┐              │
│  │ views_performance.py │    │ test_execution_service.py │              │
│  │ (Case 路径)           │    │ (DevOps 路径)              │              │
│  └──────────┬───────────┘    └────────────┬─────────────┘              │
│             │                             │                              │
│             └──────────┬──────────────────┘                              │
│                        ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                ExecutionEngine.submit(job)                     │      │
│  │                    唯一执行入口                                 │      │
│  │                                                                │      │
│  │  async_mode=True  ──→ Celery Task ──→ _execute_sync()         │      │
│  │  async_mode=False ──────────────────→ _execute_sync()         │      │
│  └────────────────────────────┬─────────────────────────────────┘      │
│                               ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                ExecutionWorker.run()                           │      │
│  │                                                                │      │
│  │  _start()  → LocustRunner.start_test()                        │      │
│  │  _wait()   → 轮询 + read_stats() → on_metrics() → WS 推送     │      │
│  │  _collect()→ read_stats() + read_full_payload()               │      │
│  └────────────────────────────┬─────────────────────────────────┘      │
│                               ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │           LocustRunner (纯适配器 — 可替换)                      │      │
│  │                                                                │      │
│  │  generate_locustfile() → subprocess.Popen("python -m locust") │      │
│  │  read_stats()          → 从 JSON 文件读取指标                   │      │
│  └──────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 三层执行架构

重构后形成清晰的三层：

```
┌──────────────────────────────────────────────────────────────┐
│  ExecutionEngine  — 编排层                                    │
│  - 接收 TestJob，决定 async/sync 路由                          │
│  - 并发控制 (PerfSemaphore)                                   │
│  - TestResult 生命周期管理 (create / update)                  │
│  - 结果持久化 (TestResult + PerformanceTestResult 双表写入)    │
│  - WebSocket 最终态推送                                       │
│  不感知 LocustRunner                                          │
└───────────────┬──────────────────────────────────────────────┘
                │ create & drive
                ▼
┌──────────────────────────────────────────────────────────────┐
│  ExecutionWorker  — 执行层                                     │
│  - 持有 LocustRunner（唯一持有者）                              │
│  - 管理单次测试完整生命周期：start → poll → stop → collect     │
│  - 轮询 read_stats() → 转发 on_metrics 回调                   │
│  - 检测 _check_should_stop() 信号                             │
│  - 返回 (stats, payload, stopped_by_user)                     │
│  业务逻辑完备，Runner 无关                                     │
└───────────────┬──────────────────────────────────────────────┘
                │ internal adapter
                ▼
┌──────────────────────────────────────────────────────────────┐
│  LocustRunner  — 适配层（纯 I/O，零业务逻辑）                    │
│  - 动态生成 locustfile                                       │
│  - subprocess.Popen 管理                                     │
│  - 被动读 JSON 文件指标                                       │
│  - 无回调 / 无判定 / 无持久化 / 无并发控制                      │
│  可替换为 K8sJobRunner / DockerRunner / ...                   │
└──────────────────────────────────────────────────────────────┘
```

### 职责矩阵

| 职责 | Engine | Worker | Runner |
|---|---|---|---|
| 并发控制 (Semaphore) | ✅ | — | — |
| TestResult 创建 | ✅ | — | — |
| WS 实时推送 | ✅ 静态方法 | ✅ 调用回调 | — |
| 子进程管理 | — | ✅ 调用 | ✅ Popen |
| 轮询等待 | — | ✅ `_wait()` | ✅ `is_running()` |
| 停止信号检测 | — | ✅ `_check_should_stop` | — |
| 指标读取 | — | ✅ 调用 | ✅ JSON 文件 |
| 双表持久化 | ✅ | — | — |
| pass/fail 判定 | ✅ | — | — |
| locustfile 生成 | — | — | ✅ |

---

## 3. 组件详解

### 3.1 数据模型

#### PerformanceTestCase (`models.py:253-305`)

```python
class PerformanceTestCase(models.Model):
    name        = CharField          # 用例名称
    url         = CharField          # 目标 URL
    method      = CharField          # GET/POST/PUT/PATCH/DELETE
    headers     = JSONField          # 请求头
    body        = TextField          # 请求体
    concurrent_users       = IntegerField(default=10)   # 并发虚拟用户
    duration_seconds       = IntegerField(default=60)   # 压测持续时间
    ramp_up_seconds        = IntegerField(default=10)   # ⚠️ 预留，未使用
    requests_per_second    = IntegerField(null=True)     # ⚠️ 预留，未使用
    expected_response_time_ms = IntegerField(default=1000)
    expected_throughput    = FloatField(null=True)       # ⚠️ 预留，未使用
    expected_error_rate    = FloatField(default=5.0)     # pass/fail 阈值
```

#### PerformanceTestResult (`models.py:308-349`)

```python
class PerformanceTestResult(models.Model):
    total_requests / successful_requests / failed_requests
    avg/min/max/p50/p90/p95/p99_response_time_ms
    throughput / error_rate
    response_time_distribution  = JSONField()  # 50ms 桶分布
    throughput_over_time        = JSONField()  # [{t, rps}, ...]
    response_time_over_time     = JSONField()  # [{t, avg, p95}, ...]
    error_details               = JSONField()  # [{message, count}, ...]
    test_case  → FK(PerformanceTestCase)
    test_result → OneToOne(TestResult)
```

#### TestResult (通用模型, `models.py:56-156`)

性能测试写入 `test_type='performance'` 的 TestResult，通过 OneToOne 关联 PerformanceTestResult。

---

### 3.2 执行引擎 (ExecutionEngine)

**文件**: `qa_center/execution/engine.py` (~220 行)

```python
class ExecutionEngine:
    def submit(job: TestJob) → ExecutionResult | AsyncResult
    def _submit_async(job)          → AsyncResult       # Celery 分发
    def _execute_sync(job)          → ExecutionResult    # 核心执行逻辑
    def _resolve_execution_id(job)  → int               # 自动创建 TestResult
    def _persist_results(...)        → ExecutionResult    # 双表写入
    @staticmethod _ws_send(id, data)                     # Channels 推送
```

**关键方法 `_execute_sync`**:

```
1. PerfSemaphore.acquire()         → 获取并发槽位
2. _resolve_execution_id()         → 确保 TestResult 存在
3. ExecutionWorker(job, on_metrics) → 创建 Worker
4. worker.run()                    → 驱动执行
5. _persist_results()              → TestResult + PerformanceTestResult
6. _ws_send(final_state)           → 推送最终态
7. PerfSemaphore.release()         → 释放并发槽位
```

**async_mode 路由**:

| 调用方 | async_mode | 执行方式 | 返回 |
|---|---|---|---|
| `views_performance.execute()` (USE_CELERY_TASKS=True) | True | Celery Worker | AsyncResult |
| `views_performance.execute()` (USE_CELERY_TASKS=False) | False | 后台线程 | 无（fire-and-forget） |
| `tasks.run_performance_test()` | False | Celery Worker 内同步 | ExecutionResult |
| `test_execution_service._run_performance_cases()` | False | DevOps 线程同步 | ExecutionResult |

---

### 3.3 工作器 (ExecutionWorker)

**文件**: `qa_center/execution/worker.py` (~110 行)

```python
class ExecutionWorker:
    def __init__(job, on_metrics: Callable | None)
    def run()   → (stats, payload, stopped_by_user)
    def _start()  → bool            # LocustRunner.start_test()
    def _wait()                      # 轮询 + 读指标 + 回调
    def _collect() → (stats, payload, stopped_by_user)
    def _check_should_stop() → bool # TestResult.aborted
    def force_stop()                 # 异常恢复
```

**`_wait()` 轮询逻辑**:

```python
while runner.is_running():
    if self._on_metrics:
        stats = runner.read_stats()   # 被动读 JSON
        self._on_metrics(stats)       # 推送 WS
    if self._check_should_stop():     # DB abort 标记
        runner.stop_test()
        break
    time.sleep(0.5)
```

Worker 是 `LocustRunner` 的**唯一持有者**——整个代码库中仅有 `worker.py:71` 一行 `LocustRunner(...)` 实例化代码。

---

### 3.4 适配器 (LocustRunner)

**文件**: `qa_center/locust_runner.py` (~230 行)

纯子进程适配器，零业务逻辑：

```python
class LocustRunner:
    # ── 子进程管理 ──
    generate_locustfile(test_case, metrics_file) → str  # 动态生成 .py
    start_test(test_case, host, users, spawn_rate, run_time) → bool
    stop_test() → bool                                   # terminate + 清理
    is_running() → bool                                  # poll() is None

    # ── 被动指标读取 ──
    read_stats() → dict           # 从 JSON 文件读当前指标
    read_full_payload() → dict    # 从 JSON 文件读完整（含时序）

    @property web_port → int      # Web UI 端口
```

**已删除项**（重构后）:

| 删除 | 原用途 | 替代 |
|---|---|---|
| `TestMetrics` dataclass | 公开数据结构 | JSON 文件直接读取 |
| `register_callback()` | 回调注册 | Worker 轮询 `read_stats()` |
| `_notify_callbacks()` | 回调通知 | Worker 轮询 `read_stats()` |
| `_monitor_process()` 线程 | 后台读文件 | Worker 主动轮询 |
| `_semaphore` / `_acquired_slot` | 并发控制 | Engine 层管理 |

**可替换性**: 实现相同接口即可替换底层执行器（如 K8sJobRunner）。

---

### 3.5 并发控制 (PerfSemaphore)

**文件**: `qa_center/semaphore.py` (~197 行)

| 维度 | 实现 |
|---|---|
| 存储 | Redis Sorted Set (`perf:semaphore:slots`) |
| 原子操作 | Lua 脚本 ACQUIRE / RELEASE |
| 并发上限 | `PERF_MAX_CONCURRENT` (默认 5) |
| TTL | 600s — worker 崩溃自动恢复 |
| 降级 | Redis 不可用时 fail-open（记录日志） |

**管理位置**: Engine 层的 `_execute_sync()` 入口/出口，不再在 LocustRunner 内。

---

### 3.6 测试任务 (TestJob)

**文件**: `qa_center/execution/job.py` (~90 行)

```python
@dataclass(frozen=True)
class TestJob:
    test_case: PerformanceTestCase
    host: str
    users: int = 10
    spawn_rate: int = 1
    run_time: str = "60s"
    async_mode: bool = True
    execution_id: int | None = None
    project: Project | None = None
    user: User | None = None
    source: str = 'single'          # 'single' | 'devops'
    task_id: str = ''

    @staticmethod
    def from_test_case(test_case, **overrides) → TestJob  # 工厂方法
```

#### ExecutionResult

```python
@dataclass
class ExecutionResult:
    ok: bool
    status: str                     # 'passed' | 'failed' | 'error'
    execution_id: int
    stats: dict                     # read_stats()
    payload: dict                   # read_full_payload()
    test_result_id: int
    perf_result_id: int | None
    error: str | None
    stopped_by_user: bool
```

---

### 3.7 Celery 薄壳 (tasks.py)

**文件**: `qa_center/tasks.py` (~50 行，重构前 191 行)

```python
@shared_task(bind=True, name='qa_center.run_performance_test')
def run_performance_test(self, execution_id, test_case_id, host, users, spawn_rate, run_time):
    test_case = PerformanceTestCase.objects.get(id=test_case_id)
    job = TestJob(test_case=test_case, host=host, users=users,
                  spawn_rate=spawn_rate, run_time=run_time,
                  async_mode=False, execution_id=execution_id)
    engine = ExecutionEngine()
    result = engine.submit(job)
    return {'ok': result.ok, 'status': result.status, 'execution_id': execution_id}
```

任务签名保持不变，向后兼容。所有执行逻辑已上移至 Engine + Worker。

---

### 3.8 API 视图层

#### PerformanceTestCaseViewSet (`views_performance.py`)

| 端点 | 方法 | 功能 |
|---|---|---|
| `/qa/performance-cases/` | GET/POST | 列表/创建 |
| `/qa/performance-cases/{id}/` | GET/PUT/DELETE | 详情/更新/删除 |
| `/qa/performance-cases/{id}/execute/` | POST | **启动压测** |
| `/qa/performance-cases/{id}/stop/` | POST | 停止压测（设置 aborted 标记） |
| `/qa/performance-cases/{id}/status/` | GET | 查询执行状态 |
| `/qa/performance-cases/{id}/results/` | GET | 历史结果 |
| `/qa/performance-cases/{id}/linked-tasks/` | GET | 关联任务 |

**execute() 环境自适应**:

```python
use_celery = getattr(settings, 'USE_CELERY_TASKS', False)
if use_celery:
    job = TestJob(..., async_mode=True)    # Celery
else:
    job = TestJob(..., async_mode=False)   # 后台线程
    thread = threading.Thread(target=_execute_sync_in_thread, args=(job,), daemon=True)
    thread.start()
```

---

### 3.9 WebSocket 实时推送

#### PerformanceTestConsumer (`consumers.py:273-304`)

```
路由: ws/qa/performance/<execution_id>/
组名: performance_test_{execution_id}
消息类型: test_update → {data: {...metrics...}}
```

**连接流程**: 匿名拒绝 → 项目权限校验 → 加入 Channels group → 推送确认。

**推送时机**: Worker 的 `_wait()` 循环中每 0.5s 调用 `read_stats()` → `on_metrics()` → `_ws_send()`。

---

### 3.10 DevOps 集成路径

#### TestExecutionService._run_performance_cases()

通过 `ExecutionEngine.submit(async_mode=False)` 逐个同步执行：

```python
for cid in case_ids:
    job = TestJob.from_test_case(perf_case, host=host,
                                  async_mode=False, source='devops',
                                  task_id=task_id)
    engine = ExecutionEngine()
    exec_result = engine.submit(job)  # 同步返回 ExecutionResult
    # 类型守卫: isinstance(exec_result, ExecutionResult)
    # 结构化错误码: CASE_NOT_FOUND / ENGINE_EXCEPTION / ZERO_REQUESTS / ...
```

**不再直接调用 LocustRunner**——所有 DevOps 性能测试统一通过 Engine。

---

## 4. 统一调用链路

```
                        ┌──────────────────────────┐
                        │   3 条入口路径             │
                        └──────────┬───────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
  ┌──────────────┐    ┌─────────────────────┐    ┌──────────────────────┐
  │ Case 单用例   │    │ Celery Worker       │    │ DevOps Task          │
  │ (View)       │    │ (tasks.py)          │    │ (TestExecService)    │
  │              │    │                     │    │                      │
  │ async_mode=  │    │ async_mode=         │    │ async_mode=          │
  │   True/False │    │   False             │    │   False              │
  └──────┬───────┘    └──────────┬──────────┘    └──────────┬───────────┘
         │                       │                          │
         └───────────────────────┼──────────────────────────┘
                                 │
                                 ▼
                   ┌─────────────────────────┐
                   │  ExecutionEngine.submit()│
                   │     唯一入口              │
                   └────────────┬────────────┘
                                │
                   ┌────────────┴────────────┐
                   │                         │
              async_mode=True           async_mode=False
                   │                         │
                   ▼                         ▼
           ┌──────────────┐        ┌──────────────────┐
           │ Celery Task  │        │ _execute_sync()   │
           │ (薄壳)        │───────→│ (核心逻辑)         │
           └──────────────┘        └────────┬─────────┘
                                           │
                              ┌────────────┴────────────┐
                              │  PerfSemaphore.acquire   │
                              │  ExecutionWorker(job)    │
                              │  worker.run()            │
                              │  _persist_results()      │
                              │  PerfSemaphore.release   │
                              └────────────┬────────────┘
                                           │
                              ┌────────────┴────────────┐
                              │  Worker._start()        │
                              │    → LocustRunner()     │
                              │    → start_test()       │
                              │  Worker._wait()         │
                              │    → loop: read_stats() │
                              │    → on_metrics()       │
                              │    → _check_should_stop │
                              │  Worker._collect()      │
                              │    → read_full_payload  │
                              └─────────────────────────┘
```

---

## 5. 前端组件

### PerformanceTestResult.vue (`frontend/src/views/qa/PerformanceTestResult.vue`)

994 行的 Vue 3 Composition API 组件：

```
┌──────────────┬──────────────────────────────────────┐
│  左侧面板     │  右侧面板 (Locust 风格仪表板)          │
│  (320px)     │                                      │
│              │  工具栏: [开始测试] [停止测试]          │
│  用例列表     │  状态栏: 运行中 | 运行时间              │
│  - 项目筛选  │  统计卡片 ×6: RPS / 失败率 / 平均RT... │
│  - 关键词搜索│  请求统计表格                          │
│  - CRUD     │  ECharts 实时图表 (RPS/RT/错误率)      │
│              │  失败请求列表                          │
└──────────────┴──────────────────────────────────────┘
```

**数据获取**: 通过 `axios` → `/qa/performance-cases/` REST API  
**实时推送**: `WebSocket` → `/ws/qa/performance/{executionId}/`  
**图表**: `ECharts` 三线图（RPS + 响应时间 + 错误率）

### DevOps 入口

- `DevOpsPlatform.vue` — 性能测试功能卡片
- `TestConsole.vue` — "性能压测 (Locust)" 下拉项

---

## 6. 完整数据流

### Case 单用例路径（生产环境）

```
1. 用户点击 "开始测试"
2. POST /qa/performance-cases/{id}/execute/
3. PerformanceTestCaseViewSet.execute()
   ├── 创建 TestResult (status='running')
   └── ExecutionEngine.submit(TestJob(async_mode=True))
       └── _submit_async()
           └── run_performance_test.delay(execution_id, ...)

4. Celery Worker 收到任务
   └── run_performance_test()
       ├── 加载 PerformanceTestCase
       └── ExecutionEngine.submit(TestJob(async_mode=False))
           └── _execute_sync()
               ├── PerfSemaphore.acquire()
               ├── ExecutionWorker(job, on_metrics=ws_callback)
               │   └── worker.run()
               │       ├── _start() → LocustRunner.start_test()
               │       │   ├── generate_locustfile()
               │       │   └── subprocess.Popen("python -m locust --headless ...")
               │       ├── _wait()
               │       │   └── while is_running():
               │       │       ├── read_stats() → on_metrics() → _ws_send()
               │       │       └── _check_should_stop()
               │       └── _collect()
               │           └── read_stats() + read_full_payload()
               ├── _persist_results()
               │   ├── TestResult (status/throughput/error_rate/test_log)
               │   └── PerformanceTestResult (完整指标 + 时序)
               ├── _ws_send(final_state)
               └── PerfSemaphore.release()

5. WebSocket 实时推送
   └── frontend onmessage → 更新统计卡片 + ECharts
```

### Case 单用例路径（开发环境）

```
1-3. 同生产环境
3.   ExecutionEngine.submit(TestJob(async_mode=False))
     └── 后台线程 _execute_sync_in_thread(job)
         └── engine.submit(job)  # 同步执行
             └── _execute_sync()  # 同上 4 的完整流程

4. API 立即返回 (fire-and-forget)
5. 后台线程完成压测 → WS 推送 → 前端更新
```

### DevOps Task 路径

```
1. POST /qa/devops/tasks/{id}/execute/
2. TestExecutionService.execute_test_task()
   └── _run_performance_cases(case_ids, ..., task_id=str(task.id))
       └── for each case:
           ├── TestJob.from_test_case(case, async_mode=False, source='devops')
           ├── ExecutionEngine.submit(job) → ExecutionResult (同步阻塞)
           ├── 类型守卫: isinstance(result, ExecutionResult)
           └── 结构化结果 → results[] + events[]
```

---

## 7. 设计决策与权衡

| 决策 | 选择 | 权衡 |
|---|---|---|
| 三层架构 | Engine → Worker → Runner | 复杂度增加 1 层，但每层可独立测试和替换 |
| LocustRunner 纯适配器 | 无回调/无判定/无持久化 | 为 K8sJobRunner 预留插拔接口 |
| IPC 方式 | JSON 文件 + 被动轮询 | 简单可靠，无需消息队列；高并发下可能有 I/O 压力 |
| 并发控制 | Redis Lua + ZSET | 原子操作，TTL 自愈；Redis 不可用时 fail-open |
| 实时推送 | Channels WebSocket | 双向实时；依赖 Redis 作为 Channels 后端 |
| 环境自适应 | `USE_CELERY_TASKS` 切换 async_mode | 开发环境不依赖 Celery；生产环境用 Celery 解耦 |
| 指标持久化 | 双表 (TestResult + PerformanceTestResult) | TestResult 统一入口，PerformanceTestResult 专用指标 |
| locustfile 生成 | f-string 模板 | 灵活但需注意注入风险 |
| 停止机制 | DB flag (TestResult.aborted) | 跨进程最简单；有 0.5s 延迟 |
| 降级策略 | Redis 不可用时 fail-open | 可用性优先；生产环境应配置告警 |

---

## 8. 审计发现

### 8.1 已修复问题

| 问题 | 严重度 | 修复 |
|---|---|---|
| ① DevOps 调用不存在的 `runner.run_locust()` / `wait_for_completion()` | 🔴 Critical | 统一为 `ExecutionEngine.submit(async_mode=False)` |
| ② Case 和 DevOps 两套执行路径分裂 | 🔴 Critical | 统一为 ExecutionEngine 唯一入口 |
| ③ LocustRunner 承担过多职责（回调/判定/并发/持久化） | 🟡 Medium | 剥离为纯适配器，业务逻辑移至 Engine+Worker |
| ④ 开发环境无 Celery 时页面数据死寂 | 🟡 Medium | 增加 `USE_CELERY_TASKS` 检查 + 线程 fallback |
| ⑤ DevOps `_run_performance_cases` 中 `task_id` 始终为空字符串 | 🟡 Medium | 改为调用方显式传入 `task_id` |
| ⑥ 缺少类型守卫——AsyncResult 可能被误当 ExecutionResult 使用 | 🟡 Medium | 增加 `isinstance(exec_result, ExecutionResult)` 检查 |
| ⑦ 乱码 print 语句 | 🟢 Low | 修复中文编码 + 改用 logger |

### 8.2 剩余问题

| 问题 | 严重度 | 建议 |
|---|---|---|
| R1: 动态代码生成注入风险 | 🟡 Medium | `generate_locustfile()` 用 f-string 拼接用户输入。建议: headers schema 验证 + Jinja2 模板替代 |
| R2: fail-open 降级策略 | 🟡 Medium | Redis 不可用时 PerfSemaphore 放行所有请求。建议: 增加 `PERF_STRICT_MODE` 配置项 |
| R3: 未使用模型字段 | 🟢 Low | `ramp_up_seconds` / `requests_per_second` / `expected_throughput` 定义但未使用。建议: 实现或标记为预留 |
| R4: spawn_rate 默认值粗糙 | 🟢 Low | `max(1, users // 10)` 对大并发不够真实。建议: 映射 `ramp_up_seconds` |
| R5: 前端无 WS 重连 | 🟢 Low | 连接断开后不自动重连。建议: 指数退避重连 |
| R6: 硬编码临时目录 | 🟢 Low | `tempfile.gettempdir()` 不可配置。建议: 增加 `LOCUST_TEMP_DIR` 配置 |
| R7: 无超时保护 | 🟢 Low | Locust 子进程挂起时轮询永不退出。建议: `run_time * 2` 超时强制 kill |
| R8: 轮询间隔不可配置 | 🟢 Low | 0.5s 硬编码。建议: `PERF_MONITOR_INTERVAL_MS` |

### 8.3 安全审计

| 检查项 | 状态 | 说明 |
|---|---|---|
| SQL 注入 | ✅ | 全 Django ORM |
| XSS | ✅ | Vue 模板自动转义 |
| 权限校验 | ✅ | `ensure_project_id_access()` 全覆盖 |
| WS 权限 | ✅ | 匿名拒绝 + 项目权限校验 |
| SSRF | ✅ | 目标 URL 由用户配置，环境级 `allowed_hosts/allowed_cidrs` |
| 代码注入 | ⚠️ | `generate_locustfile()` f-string 拼接（见 R1） |
| CSRF | ✅ | DRF Session + Token |
| 敏感信息 | ✅ | `ci_token`/`api_token` write_only |

---

## 9. 测试覆盖

### 现有测试

| 文件 | 测试数 | 覆盖点 |
|---|---|---|
| `test_performance_persistence.py` | 4 | 正常执行、错误率超阈值、停止信号检测、用户停止 |
| `test_locust_runner.py` | 5 | 初始化、is_running、stop_test、read_stats、read_full_payload |

### 测试策略

测试 mock `qa_center.execution.worker.LocustRunner`——通过替换 Worker 持有的 Runner 实现全链路测试，无需启动真实 Locust 子进程。

---

## 10. 文件清单

### 新增文件（execution 包）

| 文件 | 行数 | 职责 |
|---|---|---|
| `execution/__init__.py` | ~20 | 包导出 |
| `execution/job.py` | ~90 | TestJob + ExecutionResult 数据结构 |
| `execution/engine.py` | ~220 | ExecutionEngine 编排层 |
| `execution/worker.py` | ~110 | ExecutionWorker 执行层 |

### 修改文件

| 文件 | 变更摘要 |
|---|---|
| `locust_runner.py` | 505→230 行：删除 TestMetrics/callbacks/线程/semaphore，改为纯适配器 |
| `tasks.py` | 191→50 行：Celery 任务变为薄壳 |
| `views_performance.py` | 增加环境自适应（Celery/线程 fallback）+ `_execute_sync_in_thread` 辅助 |
| `test_execution_service.py` | `_run_performance_cases` 重写：Engine 统一执行 + 类型守卫 + 结构化错误码 + task_id 显式传递 |
| `test_performance_persistence.py` | Mock 路径更新至 `worker.LocustRunner`，FakeRunner 匹配新 API |
| `test_locust_runner.py` | 匹配纯适配器 API（无 metrics 属性，read_stats/read_full_payload） |

### 不变文件

| 文件 | 说明 |
|---|---|
| `models.py` | 表结构无变化 |
| `serializers.py` | 无变化 |
| `consumers.py` | PerformanceTestConsumer 无变化 |
| `urls.py` / `routing.py` | 无变化 |
| `semaphore.py` | 无变化（仅调用点从 Runner 移至 Engine） |
| `frontend/` 全部 | 零改动 |

---

## 11. 演进路线图

```
v1 (当前)                     v2 (规划)                     v3 (规划)
═══════════                   ══════════                   ══════════
三层架构                      分布式执行                    全托管平台
Engine→Worker→Runner          Engine→K8sJobRunner          Engine→EventStream
                                                          (Kafka/NATS)
├─ LocustRunner (subprocess)  ├─ K8s Job 替代 subprocess   ├─ Event-driven metrics
├─ JSON file IPC              ├─ S3/MinIO 指标存储          ├─ 多租户隔离
├─ Channels WS                ├─ 水平扩展 worker            ├─ 自适应并发控制
└─ PerfSemaphore (Redis)      └─ Prometheus metrics 导出    └─ 成本核算 + 配额
```

**v1 已达平台级压测系统标准**: 统一入口、三层解耦、可替换执行器、环境自适应、双表持久化、实时推送。

---

> **文档版本**: 2.0 (post-refactoring)  
> **前一版本**: v1.0 (pre-refactoring audit)  
> **下次审计**: 建议在 K8sJobRunner 实现后进行
