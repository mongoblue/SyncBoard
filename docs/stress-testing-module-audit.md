# SyncBoard 压力测试模块 — 开发与审计文档

> **审计日期**: 2026-07-02  
> **审计范围**: `backend/qa_center/` 中与性能/压力测试相关的全部代码，及 `frontend/src/` 中的对应 UI 层  
> **分支**: `dev`  
> **测试框架**: Locust (基于 Python 的 HTTP 压测框架)

---

## 目录

1. [模块架构概览](#1-模块架构概览)
2. [后端组件详解](#2-后端组件详解)
   - [2.1 数据模型](#21-数据模型)
   - [2.2 Locust 运行器](#22-locust-运行器)
   - [2.3 并发控制 (Semaphore)](#23-并发控制-semaphore)
   - [2.4 Celery 异步任务](#24-celery-异步任务)
   - [2.5 API 视图层](#25-api-视图层)
   - [2.6 序列化器](#26-序列化器)
   - [2.7 WebSocket 实时推送](#27-websocket-实时推送)
   - [2.8 DevOps 集成路径](#28-devops-集成路径)
3. [前端组件详解](#3-前端组件详解)
4. [完整数据流](#4-完整数据流)
   - [4.1 独立性能测试流程](#41-独立性能测试流程)
   - [4.2 DevOps 任务中的性能测试流程](#42-devops-任务中的性能测试流程)
5. [关键设计决策](#5-关键设计决策)
6. [审计发现与建议](#6-审计发现与建议)
   - [6.1 严重问题 (Critical)](#61-严重问题-critical)
   - [6.2 中等问题 (Medium)](#62-中等问题-medium)
   - [6.3 轻微问题 (Low)](#63-轻微问题-low)
   - [6.4 安全审计](#64-安全审计)
7. [文件清单](#7-文件清单)

---

## 1. 模块架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vue 3)                             │
│                                                                     │
│  PerformanceTestResult.vue  ─── 性能测试管理页面                     │
│  DevOpsPlatform.vue         ─── DevOps 平台（含性能测试入口）         │
│  TestConsole.vue            ─── 测试控制台（含"性能压测"下拉项）       │
│                                                                     │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │ REST API     │  │ WebSocket        │  │ ECharts 图表     │      │
│  │ axios calls  │  │ /ws/qa/perf/{id} │  │ RPS/RT/错误率   │      │
│  └──────┬───────┘  └────────┬─────────┘  └──────────────────┘      │
└─────────┼──────────────────┼────────────────────────────────────────┘
          │                  │
┌─────────┼──────────────────┼────────────────────────────────────────┐
│         ▼                  ▼                  BACKEND (Django)      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────┐          │
│  │                    URL Routing                        │          │
│  │  /qa/performance-cases/      PerformanceTestCase CRUD│          │
│  │  /qa/performance-results/    PerformanceTestResult RO│          │
│  │  /qa/devops/tasks/           TestTask (perf分支)      │          │
│  │  /qa/devops/quick-test/      QuickTest (perf分支)     │          │
│  └──────────────────────────┬───────────────────────────┘          │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────┐          │
│  │                  VIEW LAYER                           │          │
│  │  views_performance.py  ──→ 提交 Celery 任务            │          │
│  │  views_devops.py       ──→ TestExecutionService       │          │
│  └──────────────────────────┬───────────────────────────┘          │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────┐          │
│  │               CELERY WORKER (tasks.py)                │          │
│  │  run_performance_test()                               │          │
│  │    ├── LocustRunner.start_test()                      │          │
│  │    ├── 轮询 + WebSocket 实时推送                       │          │
│  │    ├── 写入 TestResult                                 │          │
│  │    └── 写入 PerformanceTestResult                      │          │
│  └──────────────────────────┬───────────────────────────┘          │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────┐          │
│  │               LOCUST SUBPROCESS                       │          │
│  │  subprocess.Popen("python -m locust ...")             │          │
│  │    ├── 生成 locustfile (动态 Python 代码)               │          │
│  │    ├── 写入 metrics JSON 到临时文件                     │          │
│  │    └── 收集: RPS/P50/P90/P95/P99/错误/分布/时间序列      │          │
│  └──────────────────────────────────────────────────────┘          │
│                                                                     │
│  ┌──────────────────────────────────────────────────────┐          │
│  │           CONCURRENCY CONTROL (PerfSemaphore)          │          │
│  │  Redis Lua 脚本 → ZSET 原子性 ACQUIRE/RELEASE           │          │
│  │  默认 5 并发上限, 10 分钟 TTL                           │          │
│  └──────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 后端组件详解

### 2.1 数据模型

#### PerformanceTestCase (`backend/qa_center/models.py:253-305`)

```python
class PerformanceTestCase(models.Model):
    name = models.CharField(max_length=200)
    url = models.CharField(max_length=1000)
    method = models.CharField(choices=[GET/POST/PUT/PATCH/DELETE])
    headers = models.JSONField()
    body = models.TextField()
    concurrent_users = models.IntegerField(default=10)
    duration_seconds = models.IntegerField(default=60)
    ramp_up_seconds = models.IntegerField(default=10)       # ⚠️ 定义但未使用
    requests_per_second = models.IntegerField(null=True)    # ⚠️ 定义但未使用
    expected_response_time_ms = models.IntegerField(default=1000)
    expected_throughput = models.FloatField(null=True)      # ⚠️ 定义但未使用
    expected_error_rate = models.FloatField(default=5.0)
```

**关键字段**：
- `concurrent_users` — 并发虚拟用户数（对应 Locust `--users`）
- `duration_seconds` — 压测持续时间（对应 Locust `--run-time`）
- `expected_error_rate` — 判定 pass/fail 的阈值

**⚠️ 未使用字段**：`ramp_up_seconds`、`requests_per_second`、`expected_throughput` 均已定义但未在 `LocustRunner` 或 `tasks.py` 中实际使用。`ramp_up_seconds` 对应 Locust 的 `--spawn-rate`，但当前 spawn_rate 由 `views_performance.execute()` 动态计算 (`max(1, int(users) // 10)`)，而非从用例字段读取。

#### PerformanceTestResult (`backend/qa_center/models.py:308-349`)

```python
class PerformanceTestResult(models.Model):
    total_requests / successful_requests / failed_requests
    avg/min/max/p50/p90/p95/p99_response_time_ms
    throughput / error_rate
    response_time_distribution = JSONField()   # 毫秒桶分布
    throughput_over_time = JSONField()          # [{t, rps}, ...]
    response_time_over_time = JSONField()       # [{t, avg, p95}, ...]
    error_details = JSONField()                 # [{message, count}, ...]
    test_case → FK(PerformanceTestCase)
    test_result → OneToOne(TestResult)          # 镜像指针
```

#### TestResult (通用模型，`models.py:56-156`)

性能测试执行时写入 `test_type='performance'` 的 `TestResult` 行，并通过 `PerformanceTestResult.test_result` 做 OneToOne 关联。

---

### 2.2 Locust 运行器 (`locust_runner.py`)

**文件**: `backend/qa_center/locust_runner.py` (505 行)

#### 核心类

| 类 | 职责 |
|---|---|
| `TestMetrics` | dataclass，承载实时指标 |
| `LocustRunner` | 控制 Locust 子进程的完整生命周期 |

#### 关键方法

```python
class LocustRunner:
    def generate_locustfile(test_case, metrics_file) -> str
        # 动态生成 Python locustfile，写入 temp dir
        # 按 execution_id 隔离文件，避免并发覆盖
        # 生成的 locustfile 内含:
        #   - HttpUser + @task 装饰器
        #   - events.request 监听器 → 收集指标 → write_metrics()
        #   - write_metrics() 每 1 秒采样一次，写入 JSON 文件

    def start_test(test_case, host, users, spawn_rate, run_time, use_web_ui) -> bool
        # 1. 获取 Redis 并发槽位
        # 2. 创建 metrics JSON 文件
        # 3. 生成 locustfile
        # 4. subprocess.Popen(["python", "-m", "locust", ...])
        # 5. 启动监控线程 (_monitor_process)

    def _monitor_process()
        # 后台线程，每 0.5s 从 JSON 文件读取指标
        # 更新 self.metrics → _notify_callbacks()
        # 进程退出时标记 state='stopped'

    def stop_test()
        # 终止子进程 → 清理临时文件 → 释放并发槽位

    def get_current_stats() → dict
    def get_full_payload() → dict  # 含时间序列 + 分布数据
```

#### 进程间通信 (IPC) 机制

```
Locust subprocess                LocustRunner (parent)
─────────────────                ──────────────────────
write_metrics() ──JSON──→  /tmp/syncboard-locust/locust_metrics_{id}.json
                                    │
                    _monitor_process() 每 0.5s 读取 ←──┘
```

**特点**：
- 子进程通过 Locust 事件钩子 (`@events.request.add_listener`) 实时写入指标
- 父进程通过轮询 JSON 文件读取指标（0.5s 间隔）
- 每秒采样一次时间序列数据，限长 600 点（约 10 分钟）
- 响应时间原始数据限长 10000 条（超过则截断到 5000）

#### 动态代码生成

`generate_locustfile()` 将 PerformanceTestCase 的属性内联到 Python 源码字符串中：

```python
locust_code = f'''# -*- coding: utf-8 -*-
from locust import HttpUser, task, between, events
...
METRICS_FILE = r"{metrics_file_escaped}"
_metrics_lock = threading.Lock()
_metrics_data = {{ ... }}  # 全局状态字典

def write_metrics(): ...     # 计算 P50/P90/P95/P99/吞吐/错误率/分布

@events.request.add_listener
def on_request(...): ...     # 每个请求完成时收集指标

class PerformanceTestUser(HttpUser):
    wait_time = between(0.1, 0.5)
    def on_start(self): self.headers = {headers_str}
    @task(1)
    def test_endpoint(self): ...  # {method} {url} with {body}
'''
```

**潜在风险**：`headers_str` 和 `body_str` 直接拼接到源码字符串中，虽然经过了 `repr()` 转义，但仍属于代码注入风险较高的模式。详见 [6.4 安全审计](#64-安全审计)。

---

### 2.3 并发控制 — PerfSemaphore (`semaphore.py`)

**文件**: `backend/qa_center/semaphore.py` (197 行)

#### 设计

| 维度 | 实现 |
|---|---|
| 存储 | Redis Sorted Set，key=`perf:semaphore:slots` |
| 原子操作 | Lua 脚本 `_ACQUIRE_LUA` / `_RELEASE_LUA` |
| 并发上限 | `PERF_MAX_CONCURRENT` (默认 5) |
| TTL | 600s (10 分钟) — worker 崩溃后自动释放槽位 |
| 降级策略 | Redis 不可用时 fail-open (不限并发) |

#### Lua 脚本

```lua
-- _ACQUIRE_LUA
local key = KEYS[1]; local limit = tonumber(ARGV[1])
local member = ARGV[2]; local ttl = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - ttl)  -- 清理过期
local count = redis.call('ZCARD', key)
if count >= limit then return 0 end                    -- 拒绝
redis.call('ZADD', key, now, member)                    -- 获取
redis.call('EXPIRE', key, ttl + 10)
return 1
```

#### 端口分配

`get_available_port(start=8090, end=8099)` — 为 Web UI 模式自动分配可用端口，使用 `socket.bind()` 探测。

#### 降级策略

- Redis 连接失败 → `_get_redis()` 返回 `None` → `acquire()` 直接返回 `True`
- Lua 脚本注册失败 → `self._redis = None` → 同样 fail-open
- `acquire()` 异常 → **fail-open** (返回 `True`)

**⚠️ 风险**：fail-open 策略在 Redis 故障时可能导致无限制并发压测，耗尽系统资源。

---

### 2.4 Celery 异步任务 (`tasks.py`)

**文件**: `backend/qa_center/tasks.py` (191 行)

#### 任务签名

```python
@shared_task(bind=True, name='qa_center.run_performance_test')
def run_performance_test(self, execution_id, test_case_id, host, users, spawn_rate, run_time) -> dict
```

#### 执行流程

```
1. 从 DB 加载 TestResult + PerformanceTestCase
2. 创建 LocustRunner(execution_id)
3. 注册 WebSocket 回调 (on_metrics → _ws_send)
4. runner.start_test() → 启动 Locust 子进程
5. 轮询循环:
   while runner.is_running():
       if _should_stop(execution_id):  # 检查 TestResult.aborted
           runner.stop_test()
           stopped_by_user = True
           break
       time.sleep(0.5)
6. 收集最终指标 (get_full_payload + get_current_stats)
7. 判定 pass/fail:
   - stopped_by_user → 'error'
   - error_rate < expected_error_rate → 'passed'
   - else → 'failed'
8. 写入 TestResult (status/duration/throughput/error_rate/test_log)
9. 写入 PerformanceTestResult (完整结构化指标 + 时间序列)
10. 推送最终状态 WebSocket → 返回 {'ok': True}
```

#### 停止机制

- 用户点击"停止" → `views_performance.stop()` 设置 `TestResult.aborted = True`
- Worker 中的 `_should_stop()` 每 0.5s 检查一次
- 检测到 aborted 后调用 `runner.stop_test()` 终止子进程
- 最终状态标记为 `error`（非 `failed`，以区分自然失败和手动停止）

#### WebSocket 推送

```python
def _ws_send(execution_id, payload):
    channel_layer.group_send(
        f"performance_test_{execution_id}",
        {"type": "test_update", "data": payload},
    )
```

使用 Django Channels 的 group 机制，目标组名 `performance_test_{execution_id}`。

---

### 2.5 API 视图层

#### PerformanceTestCaseViewSet (`views_performance.py:29-192`)

| 端点 | 方法 | 功能 |
|---|---|---|
| `/qa/performance-cases/` | GET | 列表（分页，支持 project/keyword 筛选） |
| `/qa/performance-cases/` | POST | 创建 |
| `/qa/performance-cases/{id}/` | GET/PUT/DELETE | 详情/更新/删除 |
| `/qa/performance-cases/{id}/execute/` | POST | 启动压测 |
| `/qa/performance-cases/{id}/stop/` | POST | 停止压测 |
| `/qa/performance-cases/{id}/status/` | GET | 查询执行状态 |
| `/qa/performance-cases/{id}/results/` | GET | 历史结果列表 |
| `/qa/performance-cases/{id}/linked-tasks/` | GET | 关联任务 |

**权限模型**：
- 所有接口 `IsAuthenticated`
- 通过 `ensure_project_id_access()` 校验项目级权限
- 在 `_get_case_execution()` 中校验 execution_id 与 case 的归属关系

#### PerformanceTestResultViewSet (`views_performance.py:195-231`)

只读 ViewSet，支持 `test_case` 和 `project` 参数筛选。

#### DevOps 路径 (QuickTest + TestTask)

通过 `TestExecutionService._run_performance_cases()` 以同步方式执行 Locust（非 Celery 路径），详见 [2.8](#28-devops-集成路径)。

---

### 2.6 序列化器 (`serializers.py`)

| 序列化器 | 用途 |
|---|---|
| `PerformanceTestCaseSerializer` | 详情（含 last_result 摘要） |
| `PerformanceTestCaseListSerializer` | 列表（精简字段） |
| `PerformanceTestResultSerializer` | 详情（完整时序数据） |
| `PerformanceTestResultListSerializer` | 列表（仅核心指标） |
| `PerformanceTestExecuteSerializer` | 执行请求响应 |

---

### 2.7 WebSocket 实时推送 (`consumers.py`)

#### PerformanceTestConsumer (`consumers.py:273-304`)

```
路由: ws/qa/performance/<execution_id>/
组名: performance_test_{execution_id}
消息类型: test_update → {data: {...metrics...}}
```

**连接流程**：
1. 拒绝匿名用户（`_close_if_anonymous`）
2. 校验 execution_id 对应的项目权限（`_get_performance_result_project` + `_user_can_access_project`）
3. 加入 Channels group
4. 发送 `{"type": "connected"}` 确认

**权限校验**：
```python
project = await _get_performance_result_project(self.execution_id)
if project is None or not await _user_can_access_project(self.scope['user'], project):
    await self.close(code=4003)  # Forbidden
```

---

### 2.8 DevOps 集成路径

#### TestExecutionService._run_performance_cases() (`test_execution_service.py:343-431`)

该路径用于 DevOps 的 QuickTest 和 TestTask 中执行性能测试：

```python
def _run_performance_cases(self, case_ids, project, user, events):
    for cid in case_ids:
        perf_case = PerformanceTestCase.objects.get(id=cid, project=project)
        runner = LocustRunner(execution_id=cid)
        runner.generate_locustfile(perf_case, ...)
        runner.run_locust(users=..., spawn_rate=..., run_time=...)  # ⚠️ 此方法不存在
        runner.wait_for_completion(timeout=...)
        metrics = runner.metrics
        # 判定 pass/fail: avg_rt <= expected_response_time_ms && error_rate <= expected_error_rate
```

**⚠️ 严重代码问题**：第 374-378 行调用了 `runner.run_locust()` 和 `runner.wait_for_completion()`，但 `LocustRunner` 类中**不存在这两个方法**。实际的方法是 `start_test()`、`is_running()` 和 `stop_test()`。这意味着 DevOps 路径下的性能测试执行会在运行时抛出 `AttributeError`。

#### QuickTest 路径

```
POST /qa/devops/quick-test/ {"type": "performance", "test_cases": [...]}
  → QuickTestView.post()
    → TestExecutionService.execute_quick_test()
      → _run_performance_cases()
```

#### TestTask 路径

```
POST /qa/devops/tasks/{id}/execute/
  → TestTaskExecuteView.post()
    → (Celery) execute_test_task.apply_async()
      或 (Thread) TestExecutionService.execute_test_task()
        → _run_performance_cases()
```

---

## 3. 前端组件详解

### PerformanceTestResult.vue (`frontend/src/views/qa/PerformanceTestResult.vue`)

994 行的 Vue 3 Composition API 组件，实现完整的性能测试管理界面。

#### 页面布局

```
┌──────────────┬──────────────────────────────────────┐
│  左侧面板     │  右侧面板 (Locust 风格仪表板)          │
│  (320px)     │                                      │
│              │  ┌──────────────────────────────────┐ │
│  用例列表     │  │ 工具栏: [开始测试] [停止测试]      │ │
│  - 筛选      │  ├──────────────────────────────────┤ │
│  - 搜索      │  │ 状态栏: 运行中 | 运行时间 00:30    │ │
│  - CRUD      │  ├──────────────────────────────────┤ │
│              │  │ 统计卡片 (6 个)                    │ │
│              │  │ RPS | 失败率 | 平均RT | 总请求...  │ │
│              │  ├──────────────────────────────────┤ │
│              │  │ 请求统计表格                       │ │
│              │  ├──────────────────────────────────┤ │
│              │  │ ECharts 实时图表 (RPS/RT/错误率)   │ │
│              │  ├──────────────────────────────────┤ │
│              │  │ 失败请求列表                       │ │
│              │  └──────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────┘
```

#### 数据获取

| 操作 | API |
|---|---|
| 加载用例列表 | `GET /qa/performance-cases/` |
| 加载项目列表 | `GET /projects/` |
| 创建用例 | `POST /qa/performance-cases/` |
| 编辑用例 | `PUT /qa/performance-cases/{id}/` |
| 删除用例 | `DELETE /qa/performance-cases/{id}/` |
| 启动测试 | `POST /qa/performance-cases/{id}/execute/` |
| 停止测试 | `POST /qa/performance-cases/{id}/stop/` |

#### WebSocket 实时通信

```typescript
const connectWebSocket = (executionId: number) => {
  ws = new WebSocket(buildWsUrl(`/ws/qa/performance/${executionId}/`))

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    currentStats.value = data                          // 实时指标
    requestStats.value = [{...}]                       // 表格行
    chartData.value.push({time, rps, avgResponseTime, errorRate})  // 图表数据
    updateChart()                                      // 增量更新 ECharts
  }
}
```

#### ECharts 集成

- 使用 `echarts.init()` 初始化
- 三线图：RPS（主轴）、响应时间（副轴）、错误率
- 图表数据限长 100 点
- 支持窗口 resize 自适应

#### 路由注册

```typescript
// frontend/src/router/index.ts
{ path: 'qa/performance',        component: PerformanceTestResult }
{ path: 'qa/performance-results', component: ... }
```

---

## 4. 完整数据流

### 4.1 独立性能测试流程

```
用户点击 "开始测试"
      │
      ▼
PerformanceTestResult.vue
  POST /qa/performance-cases/{id}/execute/
      │
      ▼
views_performance.PerformanceTestCaseViewSet.execute()
  ├── 创建 TestResult (status='running')
  └── run_performance_test.delay(execution_id, test_case_id, host, users, spawn_rate, run_time)
      │
      ▼ (Celery Worker)
tasks.run_performance_test()
  ├── 加载 TestResult + PerformanceTestCase
  ├── LocustRunner(execution_id)
  │     ├── PerfSemaphore.acquire() → Redis Lua 原子获取
  │     ├── generate_locustfile() → 写 Python 文件到 temp dir
  │     ├── subprocess.Popen("python -m locust --headless ...")
  │     └── _monitor_process() → 每 0.5s 读 JSON → _notify_callbacks()
  │           └── _ws_send() → Channels group → WebSocket → 前端 ECharts 实时更新
  │
  ├── 轮询 loop (每 0.5s 检查 _should_stop)
  │     └── 检测到 aborted → runner.stop_test() → 标记 stopped_by_user
  │
  ├── Locust 自动结束 (--run-time 到期)
  │
  ├── 收集 get_full_payload() + get_current_stats()
  ├── 判定 pass/fail (error_rate vs expected_error_rate)
  ├── 写入 TestResult (status/duration/throughput/test_log)
  ├── 写入 PerformanceTestResult (完整时序数据)
  └── _ws_send() 最终态推送
```

### 4.2 DevOps 任务中的性能测试流程

```
用户创建 TestTask (test_type='performance')
      │
      ▼
POST /qa/devops/tasks/{id}/execute/
      │
      ▼
TestTaskExecuteView.post()
  ├── 创建 TestResult (status='running', source='devops')
  └── (Celery 或 Thread) TestExecutionService.execute_test_task()
        └── _run_performance_cases()
              ├── for each perf_case:
              │     ├── LocustRunner(execution_id=cid)
              │     ├── runner.generate_locustfile()      ← OK
              │     ├── runner.run_locust()               ← ❌ 方法不存在!
              │     └── runner.wait_for_completion()      ← ❌ 方法不存在!
              │
              └── 汇总结果 → 写入 test_log
```

---

## 5. 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 压测引擎 | Locust (子进程) | 成熟的 Python 原生压测框架，易于集成 |
| IPC 方式 | JSON 文件 + 轮询 | 简单可靠，无需额外消息队列；避免了跨进程共享内存的复杂性 |
| 异步执行 | Celery (django-celery-beat) | 解耦 Web 请求与长时间运行任务 |
| 并发控制 | Redis Lua + ZSET | 原子操作，崩溃自动恢复 (TTL) |
| 实时推送 | Django Channels + WebSocket | 双向实时通信，支持 group 广播 |
| 前端图表 | ECharts | 开箱即用的高性能图表库 |
| 指标持久化 | 双表 (TestResult + PerformanceTestResult) | TestResult 统一入口，PerformanceTestResult 存储性能专用指标 |
| Locustfile 生成 | 字符串模板 (f-string) | 灵活但安全性需注意 |
| 停止机制 | DB flag (TestResult.aborted) | 跨进程通信最简单的方式 |
| 降级策略 | Redis 不可用时 fail-open | 保障可用性优先于资源保护 |

---

## 6. 审计发现与建议

### 6.1 严重问题 (Critical)

#### 🔴 C1: DevOps 路径中调用不存在的方法

**位置**: `backend/qa_center/services/devops/test_execution_service.py:374-378`

```python
runner.run_locust(                    # ❌ LocustRunner 无此方法
    users=perf_case.concurrent_users,
    spawn_rate=perf_case.concurrent_users,
    run_time=perf_case.duration_seconds,
)
runner.wait_for_completion(timeout=...) # ❌ LocustRunner 无此方法
```

`LocustRunner` 提供的正确方法是 `start_test()` + `is_running()` 轮询 + `stop_test()`。

**影响**: 通过 DevOps Task/QuickTest 触发的性能测试会在运行时报 `AttributeError: 'LocustRunner' object has no attribute 'run_locust'`，导致测试失败。

**建议**: 替换为正确的异步调用模式：
```python
started = runner.start_test(
    test_case=perf_case, host=host,
    users=perf_case.concurrent_users,
    spawn_rate=perf_case.concurrent_users,
    run_time=f"{perf_case.duration_seconds}s",
)
if not started:
    # handle error
    continue
while runner.is_running():
    time.sleep(0.5)
```

---

#### 🔴 C2: 动态代码生成存在注入风险

**位置**: `backend/qa_center/locust_runner.py:82-279`

`generate_locustfile()` 将用户提供的 `headers` 和 `body` 直接嵌入 Python 源码字符串。虽然 `body` 经过了 `json.loads()` 校验（仅 JSON 合法时走 `json.dumps()`），但 `headers` 通过 `json.dumps(headers_dict, ensure_ascii=False)` 嵌入。如果 headers 中包含 `\`、`'` 或 `{` `}` 字符，可能破坏生成的 Python 代码结构。

**当前防护**：
```python
headers_str = json.dumps(headers_dict, ensure_ascii=False)
# 嵌入为: self.headers = {"key": "value"}
```

`json.dumps()` 会正确转义字符串内的引号，因此 headers 的风险较低。但 body 的处理有一个分支走 `repr()`：
```python
body_code = f"data = {repr(body_str)}.encode('utf-8')"
```

`repr()` 能正确处理大多数情况，但极端复杂的 payload 仍不排除边缘问题。

**建议**：
- 对 headers 做 schema 验证（只允许简单字符串键值对）
- 考虑使用 Jinja2 模板替代 f-string 拼接
- 将敏感字符做额外转义审计

---

### 6.2 中等问题 (Medium)

#### 🟡 M1: 未使用的模型字段

**模型**: `PerformanceTestCase`
| 字段 | 状态 |
|---|---|
| `ramp_up_seconds` | 定义但未在 runner 中使用（spawn_rate 由 view 动态计算） |
| `requests_per_second` | 定义但完全未使用（Locust 无内置 RPS 限制） |
| `expected_throughput` | 定义但未在 pass/fail 判断中使用 |

**建议**: 要么实现这些字段的功能（例如将 `ramp_up_seconds` 映射到 Locust 的 `--spawn-rate`），要么在模型上添加注释说明为预留字段，或者删除减少误导。

---

#### 🟡 M2: fail-open 降级策略可能导致资源耗尽

**位置**: `backend/qa_center/semaphore.py:132-135`

```python
except Exception as exc:
    logger.error("Perf semaphore acquire error: %s", exc)
    return True  # Fail open
```

当 Redis 发生网络超时或其他异常时，`acquire()` 返回 `True`，等同于放行所有请求。在高负载场景下可能导致大量 Locust 子进程同时运行。

**建议**：
- 增加 `PERF_STRICT_MODE` 配置项，在生产环境 Redis 不可用时拒绝而非放行
- 至少记录告警指标（Prometheus/Datadog counter）

---

#### 🟡 M3: spawn_rate 计算逻辑过于简化

**位置**: `backend/qa_center/views_performance.py:90`

```python
spawn_rate = request.data.get('spawn_rate', max(1, int(users) // 10))
```

默认 spawn_rate 为 `users // 10`，对于大并发场景（如 1000 用户），spawn_rate 为 100，这意味着所有用户在 10 秒内全部启动完毕。这可能不够真实地模拟逐步增长的流量。

**建议**：
- 考虑将 `PerformanceTestCase.ramp_up_seconds` 映射为 spawn_rate: `spawn_rate = users / ramp_up_seconds`
- 或者暴露 spawn_rate 给前端自定义

---

#### 🟡 M4: 监控线程的 JSON 文件读取不是原子操作

**位置**: `backend/qa_center/locust_runner.py:301-303`

```python
with open(self.metrics_file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
```

Locust 子进程写入和父进程读取之间没有文件锁，可能读到不完整的 JSON（触发 `JSONDecodeError` 被静默吞掉）。

**当前缓解**: 写入使用了 `write_metrics()` 中的一次性 `json.dump()`，配合 `with open(...)` 的上下文管理器，在大多数操作系统上能保证原子性。但在 NFS/CIFS 等网络文件系统上不保证。

**建议**：
- 使用原子写入模式：写入临时文件 → `os.replace()` 重命名
- 或改用 `mmap` / 共享内存替代文件 IPC

---

#### 🟡 M5: 前端未处理 WebSocket 重连

**位置**: `frontend/src/views/qa/PerformanceTestResult.vue:428-472`

WebSocket 连接断开后不会自动重连。如果网络抖动导致连接断开，前端将停止接收实时指标。

**建议**：实现指数退避重连逻辑：
```typescript
ws.onclose = () => {
  if (isRunning.value) {
    setTimeout(() => connectWebSocket(executionId.value), 2000);
  }
}
```

---

#### 🟡 M6: `_run_performance_cases` 中执行的是同步 Local 模式而非 Celery

**位置**: `backend/qa_center/services/devops/test_execution_service.py:343-431`

DevOps Task 执行性能测试用例时，在 `TestExecutionService._run_performance_cases()` 中逐个顺序执行 Locust，而非通过 Celery 异步执行。这意味着一组性能用例会串行执行，且会阻塞整个 Task 的线程。

**建议**：重构为通过 Celery 异步执行每个性能用例，或者至少并行执行。

---

### 6.3 轻微问题 (Low)

#### 🟢 L1: 硬编码的临时目录路径

**位置**: `backend/qa_center/locust_runner.py:84`

```python
base_temp = os.path.join(tempfile.gettempdir(), 'syncboard-locust')
```

使用系统默认临时目录，在多 worker 部署时可能跨机器不共享。

**建议**：添加配置项 `LOCUST_TEMP_DIR` 允许自定义路径。

---

#### 🟢 L2: 监控线程 0.5s 轮询间隔不可配置

**位置**: `backend/qa_center/locust_runner.py:328`

```python
time.sleep(0.5)
```

在高频交易型压测场景下 0.5s 可能丢失短期尖刺。

**建议**：将轮询间隔设为可配置 (`PERF_MONITOR_INTERVAL_MS`)。

---

#### 🟢 L3: 缺少超时保护

`LocustRunner.start_test()` 中的 `subprocess.Popen` 没有超时机制。如果 Locust 进程因某种原因挂起（非崩溃），父进程的轮询循环永远不会退出。

**建议**：在 `_monitor_process` 中添加最大运行时间检查（例如 `run_time * 2`），超时后强制 `process.kill()`。

---

#### 🟢 L4: `generate_locustfile()` 中 print 语句包含乱码字符

**位置**: `backend/qa_center/locust_runner.py:330, 393-394`

```python
print(f"[Locust] ????: {' '.join(cmd)}")
print(f"[Locust] ????: {self.metrics_file_path}")
```

这些 print 语句中的中文字符被编码为 `?`，影响日志可读性。

**建议**：替换为标准日志：
```python
logger.info("Locust starting: %s", ' '.join(cmd))
```

---

#### 🟢 L5: 前端硬编码 API 路径

**位置**: `frontend/src/views/qa/PerformanceTestResult.vue:339`

```typescript
const res = await service.get('/qa/performance-cases/');
```

未使用 `frontend/src/api/` 下的统一 API 封装。

**建议**：将性能测试 API 封装到 `frontend/src/api/perftest.ts`，与 `devops.ts` 风格保持一致。

---

### 6.4 安全审计

| 检查项 | 状态 | 说明 |
|---|---|---|
| SQL 注入 | ✅ 安全 | 全部使用 Django ORM |
| XSS | ✅ 安全 | 前端使用 Vue 模板自动转义 |
| 权限校验 | ✅ 安全 | 所有视图层有 `ensure_project_id_access()` |
| WebSocket 权限 | ✅ 安全 | `PerformanceTestConsumer.connect()` 校验项目权限 |
| SSRF | ✅ 安全 | 测试目标 URL 由用户配置，属于预期行为；环境配置中有 `allowed_hosts/allowed_cidrs` 机制 |
| 代码注入 | ⚠️ 需关注 | `generate_locustfile()` 动态拼接 Python 代码（见 C2） |
| CSRF | ✅ 安全 | DRF Session + Token 认证 |
| 速率限制 | ⚠️ 部分 | 并发控制仅针对 Locust 进程数，未限制 API 调用频率 |
| 敏感信息泄露 | ✅ 安全 | 序列化器中对 `ci_token`/`api_token` 使用 `write_only` |

---

## 7. 文件清单

### 后端

| 文件 | 行数 | 职责 |
|---|---|---|
| `qa_center/locust_runner.py` | 505 | Locust 子进程管理与指标收集 |
| `qa_center/semaphore.py` | 197 | Redis 并发槽位 + 端口分配 |
| `qa_center/tasks.py` | 191 | Celery 异步性能测试执行 |
| `qa_center/views_performance.py` | 231 | 性能测试 CRUD + 执行/停止 API |
| `qa_center/models.py` | 1014 | PerformanceTestCase / PerformanceTestResult 模型 |
| `qa_center/serializers.py` | 1231 | 性能测试序列化器（440-538 行） |
| `qa_center/consumers.py` | 339 | PerformanceTestConsumer WebSocket |
| `qa_center/urls.py` | 101 | 路由注册 |
| `qa_center/routing.py` | ~25 | WebSocket 路由 |
| `qa_center/services/devops/test_execution_service.py` | ~590 | DevOps Task 中的性能执行路径 |
| `qa_center/views_devops.py` | 1422 | DevOps API 视图（含 QuickTest/Task 入口） |
| `qa_center/tests/test_performance_persistence.py` | 250 | 性能持久化单元测试 |

### 前端

| 文件 | 行数 | 职责 |
|---|---|---|
| `views/qa/PerformanceTestResult.vue` | 994 | 性能测试管理页面（用例 CRUD + 实时仪表板） |
| `views/qa/DevOpsPlatform.vue` | ~560 | DevOps 平台（性能测试入口卡片） |
| `components/TestConsole.vue` | ~ | 测试控制台（Locust 下拉项） |
| `api/devops.ts` | 314 | DevOps API 封装（含性能相关工具函数） |
| `types/devops.ts` | 242 | TypeScript 类型定义 |
| `router/index.ts` | ~ | 性能测试路由注册 |

---

## 附录: 测试覆盖情况

`test_performance_persistence.py` 包含 4 个测试用例：

| 测试 | 覆盖点 |
|---|---|
| `test_run_performance_test_persists_result` | 正常执行 → TestResult + PerformanceTestResult 双表写入 |
| `test_run_performance_test_marks_failed_when_error_rate_exceeds` | 错误率超阈值 → status='failed' |
| `test_should_stop_uses_aborted_flag_not_stopped_status` | `_should_stop()` 正确检测 aborted 标记 |
| `test_run_performance_test_marks_user_stopped_run_as_error_and_aborted` | 用户停止 → status='error' + aborted=True |

**未覆盖**：
- DevOps 路径的性能执行（`_run_performance_cases`）
- Semaphore 并发控制逻辑
- WebSocket 推送
- 前端组件

---

> **文档版本**: 1.0  
> **作者**: ZCode Audit  
> **下次审计建议**: 在 `_run_performance_cases` 修复后进行回归测试；考虑添加 Semaphore 集成测试。
