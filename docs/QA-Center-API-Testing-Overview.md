# QA Center API 测试开发现状全貌

> **生成日期**: 2026-06-30  
> **分支**: dev  
> **维护者**: mongoblue  
> **当前成熟度**: 6.5/10（feature-complete，尚未 production-reliable）

---

## 目录

1. [系统概览](#一系统概览)
2. [架构全景图](#二架构全景图)
3. [数据模型](#三数据模型)
4. [核心执行引擎](#四核心执行引擎)
5. [执行架构](#五执行架构)
6. [CI/CD Pipeline](#六cicd-pipeline)
7. [性能测试](#七性能测试)
8. [安全机制](#八安全机制)
9. [基础设施](#九基础设施)
10. [前端视图](#十前端视图)
11. [测试覆盖](#十一测试覆盖)
12. [开发演进](#十二开发演进)
13. [已知差距](#十三已知差距)
14. [附录](#附录)

---

## 一、系统概览

### 1.1 定位

QA Center 是 SyncBoard（项目协作看板）内置的全功能测试平台，覆盖 **API 测试**、**UI 测试**、**性能测试**、**CI/CD 集成**、**Bug 追踪** 五大领域，提供从用例管理到执行、断言、报告的全生命周期支持。

### 1.2 技术栈

| 层 | 技术 |
|----|------|
| **后端框架** | Django 6 + Django REST Framework |
| **异步任务** | Celery + Redis |
| **WebSocket** | Django Channels + channels-redis |
| **数据库** | MySQL 8 |
| **搜索引擎** | Elasticsearch 7 |
| **前端** | Vue 3 + TypeScript + Pinia + Element Plus + Vite |
| **E2E 测试** | Playwright (sync API) + pytest |
| **性能测试** | Locust（子进程模式） |
| **CI 集成** | Jenkins / GitLab API v4 |
| **断言库** | jsonpath-ng, jsonschema（soft dependency） |

### 1.3 新旧双系统共存

QA Center 中存在 **两套 API 测试模型**：

| | 旧系统 | 新系统 |
|----|--------|--------|
| **用例模型** | `ApiTestCase` | `ApiAutoTestSuite` → `ApiAutoTestCase` |
| **结果模型** | `ApiTestResult` | `ApiAutoTestResult` → `ApiAutoTestCaseResult` |
| **断言存储** | JSON 字段内嵌 | 独立模型 `ApiAutoTestAssertion` |
| **提取器存储** | — | 独立模型 `ApiAutoTestExtractor` |
| **HTTP 客户端** | Django Test Client | `requests` 库（真实 HTTP） |
| **执行器** | `test_executor.py` | `api_auto_executor.py` |
| **用途** | 兼容旧 DevOps 流程 | 新版变量链式传递、提取器 |

> 统一断言层 (`unified_assertions.py`) 同时服务于两套系统。

---

## 二、架构全景图

### 2.1 六条执行路径

```
┌──────────────────────────────────────────────────────────────────────┐
│                      QA Center 执行架构                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  [前端触发]                                                            │
│      │                                                                │
│      ├─(1) 旧单例执行 ──► Django Test Client ──► ApiTestResult         │
│      │                     + TestRun + TestRunCaseResult              │
│      │                     + TestResult（四重写入）                      │
│      │                                                                │
│      ├─(2) 旧批量执行 ──► ThreadPoolExecutor ──► ApiTestResult         │
│      │                     + TestRunCaseResult                         │
│      │                     （202 立即返回）                              │
│      │                                                                │
│      ├─(3) 新自动执行 ──► ApiAutoTestExecutor                          │
│      │     (suite)         requests.request()                         │
│      │                     SSRF 校验                                   │
│      │                     变量链式传递                                 │
│      │                     ──► ApiAutoTestCaseResult                   │
│      │                         + ApiAutoTestResult                     │
│      │                                                                │
│      ├─(4) RunPlan 执行 ──► TestRunPlanExecutor                       │
│      │                      requests.Session（Cookie 复用）             │
│      │                      串行/并行模式                               │
│      │                      WebSocket 进度广播                          │
│      │                      ──► ApiAutoTestCaseResult                  │
│      │                                                                │
│      ├─(5) 性能测试 ──► Celery Task ──► Locust 子进程                  │
│      │                     Redis 信号量并发控制                         │
│      │                     ──► TestResult + PerformanceTestResult      │
│      │                                                                │
│      └─(6) CI/CD ──► PipelineRun ──► Jenkins/GitLab 真实管道           │
│                       poll_pipeline_status (自调度 Celery 轮询)         │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块依赖关系

```
                       ┌──────────────┐
                       │   Views      │  (15 个 ViewSet + 显式路径)
                       └──────┬───────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
   ┌──────▼──────┐   ┌───────▼───────┐   ┌───────▼───────┐
   │  Executors  │   │   Pipeline    │   │  Performance  │
   │             │   │               │   │               │
   │ auto_exec   │   │  CiClient ABC │   │ locust_runner │
   │ run_plan    │   │  Jenkins      │   │ semaphore     │
   │ test (old)  │   │  GitLab       │   │ tasks.py      │
   └──────┬──────┘   └───────────────┘   └───────────────┘
          │
   ┌──────┴──────────────────────────┐
   │         Core Engines            │
   │                                 │
   │  template_engine    (变量渲染)   │
   │  unified_assertions (11种断言)   │
   │  extractors         (5种提取源)  │
   │  request_builder    (参数构建)   │
   └─────────────────────────────────┘
```

### 2.3 模块文件清单（42 个 Python 文件）

| 层 | 文件 | 说明 |
|----|------|------|
| **Models** | `models.py` | 21 个模型，1059 行 |
| **Serializers** | `serializers.py` | DRF 序列化器，981 行 |
| **Views** | `views_api_test.py`, `views_api_auto_test.py`, `views_devops.py`, `views_performance.py`, `views_run_plan.py`, `views_environment.py`, `views_test_run.py`, `views_test_result.py`, `views_test_link.py`, `views_ui_test.py`, `views.py` | 9 个视图文件 |
| **Pipeline** | `pipeline/__init__.py`, `jenkins.py`, `gitlab.py`, `state_mapping.py` | CI 集成 |
| **Executors** | `api_auto_executor.py`, `run_plan_executor.py`, `test_executor.py` | 执行引擎 |
| **Tasks** | `tasks.py`, `tasks_test_exec.py` | Celery 异步任务 |
| **Core Engines** | `template_engine.py`, `unified_assertions.py`, `assertion_engine.py`, `extractors.py`, `request_builder.py` | 核心引擎 |
| **Infrastructure** | `semaphore.py`, `throttling.py`, `webhooks.py`, `metrics.py`, `ssrf.py`, `bug_utils.py` | 基础设施 |
| **WebSocket** | `consumers.py`, `routing.py` | 实时通信 |
| **Tests** | `tests/conftest.py` + 7 个 test 文件 | 测试覆盖 |

---

## 三、数据模型

### 3.1 新 API 自动测试模型（推荐使用）

```
ApiAutoTestSuite (套件)
  ├── name, description, is_active
  ├── FK: Project, User
  │
  └── ApiAutoTestCase (用例，按 sort_order 排序执行)
       ├── name, description, url
       ├── method: GET / POST / PUT / PATCH / DELETE / HEAD / OPTIONS
       ├── headers (JSON), content_type, body
       ├── expected_status, is_active, sort_order
       ├── timeout_seconds, enable_cookie_session
       ├── form_files (JSON), query_params (JSON)
       ├── FK: ApiAutoTestSuite, User
       │
       ├── ApiAutoTestAssertion (断言，多条)
       │    ├── assertion_type: status_code / json_equals / json_exists
       │    │                  / json_contains / response_time
       │    ├── comparison_operator: eq / ne / gt / gte / lt / lte / contains
       │    ├── json_path, expected_value, error_message, sort_order
       │    └── FK: ApiAutoTestCase
       │
       └── ApiAutoTestExtractor (提取器，变量链传递)
            ├── name (变量名)
            ├── source: body / header / status / cookie / response_time
            ├── expression, default_value, sort_order
            └── FK: ApiAutoTestCase

ApiAutoTestResult (套件级结果)
  ├── status: pending / running / passed / failed / error
  ├── total_cases, passed_cases, failed_cases, error_cases, duration_ms
  ├── FK: ApiAutoTestSuite, User
  │
  └── ApiAutoTestCaseResult (用例级结果)
       ├── status_code, response_body, response_headers (JSON)
       ├── response_time_ms, passed, assertion_details (JSON)
       ├── error_message
       └── FK: ApiAutoTestCase, ApiAutoTestResult
```

### 3.2 旧 API 测试模型（向后兼容）

```
ApiTestCase
  ├── name, url, method, headers (JSON), body
  ├── expected_status, content_type
  ├── expected_response (JSON)        ← 断言内嵌于此字段
  ├── response_extractions (JSON)     ← 提取器内嵌于此字段
  ├── is_active
  ├── FK: Project, User (created_by)
  └── M2M: Task

ApiTestResult
  ├── status_code, response_body, response_headers (JSON)
  ├── response_time_ms, passed, error_message
  ├── assertion_results (JSON)
  └── FK: ApiTestCase, User
```

### 3.3 执行与统一结果模型

| 模型 | 用途 |
|------|------|
| `TestRun` | 批量执行记录（trigger: manual/scheduled/cicd/regression），含 pass_rate、duration_ms、config_snapshot、curl_template |
| `TestRunCaseResult` | 单次执行中单个用例的结果（request_snapshot + curl + sequence + case_type） |
| `TestResult` | 通用测试结果（test_type: api/ui/performance/regression），含 worker 追踪字段（task_id, error_code, error_traceback, worker_pid, temp_dir_path, aborted） |
| `TestScreenshot` | 测试截图（image + step_index） |

> **注意**: `TestRun` 和 `TestRunCaseResult` 链接旧 `ApiTestCase` 模型。新的自动测试结果使用 `ApiAutoTestResult`。两者都写入 `TestResult` 表用于 DevOps 仪表板。

### 3.4 DevOps 模型

| 模型 | 用途 |
|------|------|
| `TestTask` | 定时/Webhook/手动测试任务（cron_expression, webhook_url, test_config JSON, execution_count, notification_settings） |
| `CiCdConfig` | CI/CD 集成配置（Jenkins/GitLab/GitHub，含 ci_url, ci_token 加密, ci_project, ci_job_name, verify_ssl, auto_trigger） |
| `PipelineRun` | 管道执行记录（external_run_id, commit_sha, branch, jobs_summary JSON, log_output, test_results_summary JSON）。唯一约束: `(cicd_config, external_run_id)` |

### 3.5 环境与配置模型

| 模型 | 约束 |
|------|------|
| `TestEnvironment` | `(project, name)` 唯一，含 base_url + variables (JSON)，支持 is_default |
| `TestGlobalVar` | `(project, key)` 唯一，支持 is_secret 脱敏 |
| `TestRunPlan` | 批量执行计划，含 case_ids (JSON)、parallel、max_workers、stop_on_failure、case_timeout_seconds |

### 3.6 性能测试模型

```
PerformanceTestCase
  ├── name, url, method, headers, body
  ├── concurrent_users, duration_seconds, ramp_up_seconds
  ├── requests_per_second
  ├── expected_response_time_ms, expected_throughput, expected_error_rate
  ├── FK: Project, M2M: Task
  │
  └── PerformanceTestResult (1:1 → TestResult)
       ├── total_requests, successful_requests, failed_requests
       ├── avg / min / max / p50 / p90 / p95 / p99_response_time_ms
       ├── throughput, error_rate
       ├── 时序数据: response_time_distribution (50ms 桶，40 桶)
       ├── throughput_over_time, response_time_over_time (1s 采样，600 点)
       └── error_details (最近 10 条)
```

---

## 四、核心执行引擎

### 4.1 模板引擎 (`template_engine.py`, 152 行)

使用 `{{var_name}}` 语法，兼容 Postman/Apifox 惯例。

**变量优先级**（从高到低）：

```
1. Overrides（运行时变量，如上游提取器输出）
       ↓
2. TestEnvironment.variables（环境级）
       ↓
3. TestGlobalVar（项目级全局变量）
       ↓
4. TestEnvironment.base_url（自动暴露为 {{base_url}}）
```

**核心 API**：

| 函数 | 功能 |
|------|------|
| `build_variable_pool(env, globals, overrides)` | 合并所有变量源为单一字典 |
| `render_string(text, variables)` | 替换 `{{var}}` 占位符（未匹配保留原文） |
| `render_value(value, variables)` | 递归渲染 dict/list/tuple/str |
| `resolve_url(url, variables)` | 渲染 URL，相对路径自动拼接 base_url |
| `find_unresolved(text)` | 返回未解析的占位符列表 |

**变量名规则**: `[A-Za-z_][A-Za-z0-9_]*`，大小写敏感，花括号内空格容错。

### 4.2 统一断言 (`unified_assertions.py`, 690 行)

最终断言引擎，新旧系统共用。

**11 种断言类型**：

| 类型 | 说明 | 默认运算符 |
|------|------|-----------|
| `status_code` | HTTP 状态码 | eq |
| `response_time` | 响应时间 (ms) | lt |
| `json_equals` | JSON 字段值 | eq |
| `json_exists` | JSON 字段存在性 | exists |
| `json_contains` | JSON 字段包含 | contains |
| `header_equals` | 响应头值 | eq |
| `header_exists` | 响应头存在性 | exists |
| `body_size` | 响应体大小 (bytes) | lte |
| `regex_match` | 正则匹配响应体或 JSON 路径 | — |
| `type_check` | JSON 字段类型验证 | — |
| `schema_validate` | JSON Schema 验证 (jsonschema) | — |

**智能判等 (`_smart_eq`)**：

- `bool` 永远不等于 `int`（`True != 1`）
- 数字/字符串跨类型比较（`30 == "30"`）
- JSON 字符串自动解析回退
- Header 查找大小写不敏感

**核心 API**：

```python
normalize_one(raw) -> Assertion              # 输入归一化（兼容旧 dict 格式和新模型实例）
evaluate(Assertion, ResponseContext) -> AssertionResult
run_assertions(assertions_list, ResponseContext) -> list[dict]
```

> 设计决策：运算符同时支持符号 (`==`, `!=`, `>`) 和缩写 (`eq`, `ne`, `gt`)；单条断言异常隔离，不级联影响其他断言。

### 4.3 提取器 (`extractors.py`, 110 行)

运行时从 HTTP 响应中提取变量，传入下游用例。

**5 种数据源**：

| 源 | 表达式 | 返回值 |
|----|--------|--------|
| `body` | JSONPath | JSON 字段值 |
| `header` | 头名称（大小写不敏感） | Header 值 |
| `status` | （忽略） | Integer 状态码 |
| `cookie` | Cookie 名 | Cookie 值 |
| `response_time` | （忽略） | Float ms |

**核心 API**：

```python
extract_value(source, expression, response_json, headers, cookies, response_time, default_value)
    -> Any  # 单值提取，失败返回 default_value（不抛异常）

run_extractors(extractors_list, response_json, headers, cookies)
    -> dict[str, Any]  # 批量提取，返回 {name: value}

summarize_extractions(extracted_dict)
    -> list[dict]  # 前端友好格式，value_preview 截断 200 字符
```

> 设计原则：任何提取失败都返回 `default_value`，不抛异常 —— 确保单点失败不破坏整条测试链。

### 4.4 请求构建器 (`request_builder.py`, 152 行)

| 函数 | 功能 |
|------|------|
| `normalize_query_params(raw, variables)` | 归一化 4 种输入格式（dict / dict-with-lists / list-of-pairs / list-of-objects）为 `list[tuple[str, str]]`，保留重复 key |
| `build_file_tuples(raw, variables)` | 构建 `requests.files=` 兼容的元组，支持 base64 编码和模板变量渲染 |

### 4.5 Bug 自动创建 (`bug_utils.py`, 130 行)

`create_bug_from_test_failure(test_case, test_result, error_message)`：

- 去重：检查同一 `(project, source_test_type, source_case_id)` 是否已有 open bug
- 自动创建 Bug（severity=major, priority=p1, status=new）
- 写入 BugTransition 记录
- 发送站内通知 + WebSocket 广播到 `system_broadcast`

---

## 五、执行架构

### 5.1 四条执行路径对比

| 特性 | 旧单例 | 旧批量 | 新自动 (Suite) | RunPlan |
|------|--------|--------|---------------|---------|
| **HTTP 客户端** | Django Test Client | Django Test Client | `requests.request()` | `requests.Session` |
| **并行** | 否 | `ThreadPoolExecutor` | 否（串行） | 可选（1–32 workers） |
| **变量链** | 否 | 否 | ✅ 提取器链式传递 | ✅ 串行模式传递 |
| **Cookie 复用** | 否 | 否 | 否 | ✅ (enable_cookie_session) |
| **WebSocket 进度** | 否 | 否 | 否 | ✅ `qa_dashboard_{project_id}` |
| **SSRF 保护** | 否 | 否 | ✅ | ✅ |
| **stop_on_failure** | N/A | N/A | N/A | ✅ |
| **结果存储** | 四重写入 | ApiTestResult | ApiAutoTestCaseResult | ApiAutoTestCaseResult |

### 5.2 新自动执行器 (`api_auto_executor.py`, 429 行) 执行流程

```
[Template Engine]                     [Request Builder]
  variables = env + globals + overrides  normalize_query_params()
  url = resolve_url(url, variables)      build_file_tuples()
  headers = render_value(headers, vars)
  body = render_string(body, vars)
        │
        ▼
[SSRF Validation]
  validate_target_url(url)               ← 七层防御检查
        │
        ▼
[HTTP Request]  ──►  requests.request(method, url, headers, params, json/data, files, timeout=30s)
        │
        ▼
[Unified Assertions]                 [Extractors]
  ctx = ResponseContext.from_raw()     run_extractors(extractors, response_json, headers, cookies)
  run_assertions(assertions, ctx)      → {name: value}
  → [{passed, assertion_type,          → merge into variables pool
      actual_value, ...}]                for next case
        │
        ▼
[Write Result]  ──►  ApiAutoTestCaseResult + 原子更新 ApiAutoTestResult 计数器
        │
        ▼
[Bug Auto-Create]  ──►  bug_utils.create_bug_from_test_failure() on failure
```

> `ApiAutoTestExecutor` 也包含 `AssertionExecutor`（自包含比较运算符类）和 `JsonPathExtractor`（jsonpath-ng 优先，手动提取回退）。

### 5.3 RunPlan 执行器 (`run_plan_executor.py`, 459 行)

相比 `ApiAutoTestExecutor` 的额外特性：

- 使用共享 `requests.Session` 实现 Cookie/连接复用
- 支持 `ThreadPoolExecutor` 并行执行（1–32 workers 可配）
- 支持 `stop_on_failure` 取消剩余用例
- 尊重逐用例 `timeout_seconds`（回退 plan.case_timeout_seconds）
- 每用例完成后通过 WebSocket 广播进度事件
- 自动创建隐藏占位 `ApiAutoTestSuite`（`__run_plan__#{plan_id}`）满足 FK 约束
- 串行模式：从用例 N 提取的变量流向用例 N+1；并行模式：提取记录日志但不传播

### 5.4 Celery 任务

| 任务 | 文件 | 队列 | time_limit | 说明 |
|------|------|------|-----------|------|
| `run_batch_api_tests(batch_id)` | `tasks_test_exec.py` | `qa_long` | 1800s | 批量执行（幂等，检查 BatchExecution status） |
| `execute_test_task(task_id)` | `tasks_test_exec.py` | `qa_long` | — | 执行调度任务（防双重执行） |
| `poll_pipeline_status(run_id, fail_count)` | `tasks_test_exec.py` | `qa_pipeline` | — | 自调度管道轮询（指数退避） |
| `run_performance_test(execution_id, ...)` | `tasks.py` | default | — | Locust 子进程生命周期管理 |

### 5.5 功能开关

```python
# backend/backend/settings.py
USE_CELERY_TASKS = os.environ.get("USE_CELERY_TASKS", "False").lower() == "true"
USE_REAL_CI      = os.environ.get("USE_REAL_CI", "False").lower() == "true"
USE_SEMAPHORE    = os.environ.get("USE_SEMAPHORE", "False").lower() == "true"
PERF_MAX_CONCURRENT = int(os.environ.get("PERF_MAX_CONCURRENT", "5"))
```

> 开关关闭时：Celery → `threading.Thread` 回退，CI → `_MockCiClient` 回退，信号量 → 无限制回退。全部 `False` 为默认安全值。

---

## 六、CI/CD Pipeline

### 6.1 架构模式：抽象工厂 + 策略

```
             ┌──────────────────────┐
             │   CiClient (ABC)     │  抽象基类 (pipeline/__init__.py)
             │  - trigger()         │
             │  - get_status()      │
             │  - get_jobs()        │
             │  - get_logs()        │
             │  - cancel()          │
             │  - verify_webhook()  │
             └──────┬───────────────┘
                    │
       ┌────────────┼────────────┐
       │            │            │
┌──────▼──────┐ ┌───▼──────┐ ┌──▼──────────┐
│ JenkinsClient│ │GitLabClient│ │_MockCiClient│
│ Blue Ocean  │ │ API v4    │ │ (3s 执行     │
│ + classic   │ │           │ │  random 结果)│
│ API fallback│ │           │ │              │
└─────────────┘ └──────────┘ └─────────────┘
```

**工厂函数**:
```python
def get_client(config: CiCdConfig) -> CiClient:
    if not settings.USE_REAL_CI:
        return _MockCiClient(config)
    if config.ci_type == 'jenkins':
        return JenkinsClient(config)
    if config.ci_type == 'gitlab':
        return GitLabClient(config)
```

### 6.2 状态映射 (`state_mapping.py`, 77 行)

| 统一状态 | Jenkins | GitLab |
|----------|---------|--------|
| `queued` | QUEUED | created / waiting_for_resource / preparing / pending / scheduled |
| `running` | RUNNING, PAUSED | running |
| `passed` | SUCCESS, UNSTABLE | success |
| `failed` | FAILURE | failed |
| `cancelled` | ABORTED | canceled |
| `skipped` | NOT_BUILT | skipped |

> `TERMINAL_STATUSES = {passed, failed, cancelled, skipped}` 用于轮询终止判断。

### 6.3 管道完整生命周期

```
[触发] POST /devops/cicd-config/{id}/trigger/
  │
  ├─ 去重检查（手动触发：30s 窗口）
  ├─ 创建 PipelineRun (status=queued/running, is_mock 基于 USE_REAL_CI)
  │
  ├─ USE_REAL_CI=True:
  │    └─ get_client(config).trigger() → CiTriggerResult
  │       poll_pipeline_status.delay(run_id)
  │         │
  │         ├─ 终端状态 → fetch jobs + logs → 写入结果 → 完成
  │         └─ 非终端 → countdown 重新调度自己
  │             指数退避: 30s × 2^fail_count (max 300s)
  │             连续 5 次失败 → 标记 failed
  │
  └─ USE_REAL_CI=False (Mock):
       └─ threading.Thread → _simulate_run()
           3s sleep + random.random() 模拟 pass/fail
```

### 6.4 Webhook 路径（外部 CI 回调）

```
POST /devops/cicd-config/{id}/webhook/  (permission_classes=[])
  │
  ├─ check_webhook_rate_limit()     每配置 5次/60s 滑动窗口
  ├─ verify_webhook_signature()     HMAC-SHA256 常数时间比较
  ├─ verify token header
  ├─ check_webhook_dedup()          (ci_config_id, external_run_id) 5min TTL
  └─ 创建/更新 PipelineRun
```

---

## 七、性能测试

### 7.1 Locust 子进程架构

```
[Django Worker]                          [Locust 子进程]
     │                                         │
     ├─ Celery Task: run_performance_test      │
     │       │                                  │
     │       ├─ acquire semaphore ─────────────►│
     │       │  (Redis ZSET + Lua 原子操作)      │
     │       │                                  │
     │       ├─ 生成 locustfile_{uuid}.py ──────►│
     │       │   （动态生成，含 events 钩子）      │
     │       │                                  │
     │       ├─ subprocess.Popen(locust) ──────►│  Locust 运行
     │       │       │                          │  写入 JSON 指标文件
     │       │       │                          │
     │       │  ┌────┴────────────────────┐     │
     │       │  │ 监控线程 (0.5s 轮询)     │◄────┘
     │       │  │ 读取 JSON → TestMetrics │
     │       │  │ → WebSocket 实时推送     │
     │       │  └────────────────────────┘     │
     │       │                                  │
     │       ├─ 轮询 _should_stop()              │
     │       │   (检查 TestResult.aborted)       │
     │       │                                  │
     │       └─ stop_test() ───────────────────►│ SIGTERM
     │          release semaphore                │ cleanup tempfiles
     │          write PerformanceTestResult      │
```

### 7.2 采集指标

| 类别 | 指标 |
|------|------|
| **汇总** | total/successful/failed requests, avg/min/max/p50/p90/p95/p99 response time, throughput (req/s), error_rate (%) |
| **时序** | throughput_over_time, response_time_over_time（1s 采样，最多 600 点） |
| **分布** | response_time_distribution（50ms 桶 × 40） |
| **错误** | error_details（最近 10 条） |

### 7.3 信号量并发控制 (`semaphore.py`, 197 行)

- Redis ZSET + 3 个 Lua 脚本（acquire / release / heartbeat）
- 原子操作防止竞态条件
- TTL 600s 防止 worker 崩溃导致的 slot 泄漏
- 默认 `PERF_MAX_CONCURRENT=5`
- Redis 不可用时 fail-open（不阻塞执行）

**端口管理**:
```python
get_available_port(start=8090, end=8099) → int  # 为 Locust Web UI 寻找空闲端口
```

---

## 八、安全机制

### 8.1 SSRF 防护 (`ssrf.py`, 214 行)

**七层防御体系**：

| 层级 | 措施 |
|------|------|
| 1 | **Scheme 白名单**：仅允许 http/https |
| 2 | **@ 绕过检测**：拒绝 URL authority 中含 `@` |
| 3 | **URL 归一化**：lowercase scheme/netloc，strip fragment |
| 4 | **直接 IP 阻止**：拒绝 URL 中硬编码 IP 地址（强制走 DNS） |
| 5 | **DNS 解析 + IP 分类**：阻止 14 个 IPv4 段（10.0.0.0/8, 127.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, link-local, multicast 等）+ 4 个 IPv6 段（loopback, link-local, unique local, multicast） |
| 6 | **Metadata endpoint 阻止**：169.254.169.254 (AWS/GCP/Azure)、100.100.100.200 (Alibaba) |
| 7 | **DNS rebinding 检测**：两次 DNS 解析结果比较 |

**`SSRFProtectedSession`**: 继承 `requests.Session`，禁用自动重定向，每次请求（含重定向目标）均执行 URL 校验。

### 8.2 Webhook 安全 (`webhooks.py`, 162 行)

| 函数 | 功能 |
|------|------|
| `verify_webhook_signature(payload_body, signature_header, secret)` | HMAC-SHA256 签名验证，常数时间比较防时序攻击 |
| `check_webhook_dedup(ci_config_id, external_run_id)` | Django cache 去重，5 分钟 TTL，返回 True 表示重复 |
| `check_webhook_rate_limit(ci_config_id)` | 滑动窗口限流，每配置最多 5 次/60s，返回 (blocked, current_count) |

### 8.3 API 节流 (`throttling.py`, 35 行)

四个 `UserRateThrottle` 子类：

| 类 | 速率 | 作用域 | 用途 |
|----|------|--------|------|
| `BurstRateThrottle` | 10/min | `qa_burst` | 通用 API |
| `TestExecuteThrottle` | 5/min | `qa_test_execute` | 测试执行端点 |
| `PipelineThrottle` | 3/min | `qa_pipeline` | 管道触发/webhook |
| `WebhookThrottle` | 2/min | `qa_webhook` | 外部 Webhook 回调 |

### 8.4 Token 与密钥掩码

- `CiCdConfigSerializer`: `ci_token` / `api_token` 只写（write_only），`ci_token_display` 返回 `****` 掩码版本
- `TestGlobalVarSerializer`: `is_secret=True` 时 `value_display` 返回 `********`
- `TestCaseVariable.validate()`: 变量名强制 `[A-Za-z_][A-Za-z0-9_]*` 格式

---

## 九、基础设施

### 9.1 Celery 任务队列

| 队列 | 用途 | 典型任务 |
|------|------|---------|
| `qa_long` | 长耗时批处理 | `run_batch_api_tests`, `execute_test_task` |
| `qa_pipeline` | 管道轮询 | `poll_pipeline_status` |
| default | 性能测试 | `run_performance_test` |

### 9.2 WebSocket 实时通信

**5 个 Consumer，7 个 URL 模式**：

| Consumer | URL | 用途 | 广播组 |
|----------|-----|------|--------|
| `QAConsumer` | `/ws/qa/dashboard/{project_id}/` | RunPlan 进度广播 | `qa_dashboard_{project_id}` |
| `RecorderConsumer` | `/ws/qa/recorder/{project_id}/` | UI 测试录制器 | — |
| `PerformanceTestConsumer` | `/ws/qa/performance/{execution_id}/` | 性能实时指标 | — |
| `TestRunProgressConsumer` | `/ws/qa/test-run/{run_id}/` | TestRun 逐用例进度 | — |
| `UiRunConsumer` | `/ws/qa/run/{task_id}/` | UI 执行进度 | — |

**安全约束**:
- 所有 Consumer 在 `connect()` 时验证认证（未认证 close code `4003`）
- Dashboard 路由校验项目 owner/member 权限
- ASGI 边界配置 `AllowedHostsOriginValidator`

### 9.3 可观测性 (`metrics.py`, 141 行)

| 功能 | 说明 |
|------|------|
| `generate_trace_id()` | 生成 UUID 作为全链路追踪标识 |
| `task_tracker(task_name, execution_id, trace_id)` | 上下文管理器，记录 task_started / task_finished / task_failed + duration_ms、trace_id、execution_id |
| `log_execution(event, trace_id, execution_id, level, **extra)` | Celery 任务结构化日志辅助函数 |

---

## 十、前端视图

### 10.1 页面组织

```
frontend/src/
├── views/
│   ├── QA.vue                              # 质量中心入口（状态卡片 + 终端日志 WebSocket）
│   │
│   └── qa/
│       ├── ApiCaseList.vue                  # API 用例列表（过滤、分页、行内执行）
│       ├── ApiCaseDetail.vue                # 旧版用例编辑（表单 + 断言 + 内联执行）
│       ├── ApiCaseRunDetail.vue             # 新版单次执行详情（请求/响应/断言/cURL）
│       ├── AutoResultDetail.vue             # 批量执行结果（概览 + 用例表 + 抽屉）
│       ├── UiCaseList.vue                   # UI 用例列表
│       ├── UiCaseDetail.vue                 # UI 用例编辑（录制器 + 步骤编辑 + 截图）
│       ├── PerformanceTestResult.vue        # Locust 仪表板（ECharts + 实时统计）
│       ├── TestResultList.vue               # 全局结果列表（统计卡片 + 多维过滤）
│       ├── TestResultDetail.vue             # 通用结果详情（性能百分位 + 截图画廊）
│       ├── TestRunList.vue                  # 批量执行记录列表
│       ├── TestRunDetail.vue                # 批量执行详情（进度条 + WebSocket）
│       ├── DevOpsPlatform.vue               # DevOps 平台仪表板
│       └── TestTaskDetail.vue               # 测试任务详情
│
├── views/qa/components/
│   ├── BatchRunExecuteDialog.vue            # 批量执行对话框（两阶段：配置 + 进度）
│   ├── CiCdConfigDialog.vue                # CI/CD 配置 CRUD
│   ├── TestTaskDialog.vue                  # 测试任务创建/编辑
│   ├── RecorderPanel.vue                   # UI 录制面板
│   ├── RequestPanel.vue                    # 请求展示（方法标签、URL、头、体）
│   ├── ResponsePanel.vue                   # 响应展示（状态码标签、头、JSON 语法高亮）
│   ├── TestsPanel.vue                      # 断言结果（pass/fail 颜色 + 展开详情）
│   ├── CurlPanel.vue                       # cURL 命令（复制 + 下载 .sh）
│   └── RunProgressBar.vue                  # 执行进度条
│
├── api/
│   ├── autoresult.ts                       # 自动测试结果 CRUD + 从失败创建 Bug
│   ├── devops.ts                           # 仪表板统计 + CI/CD + 任务管理 + 工具函数
│   ├── runplan.ts                          # 执行计划 CRUD + 可选用例
│   └── testrun.ts                          # TestRun 列表/详情 + 取消/重跑/批跑/单跑
│
└── composables/
    └── useRecorderSocket.ts                # UI 录制器 WebSocket 状态机
```

### 10.2 关键页面功能说明

| 页面 | 核心功能 |
|------|---------|
| **QA.vue** | 状态卡片（通过/失败/运行中）+ 六大功能入口卡片 + WebSocket 日志终端 |
| **PerformanceTestResult.vue** | 左右分栏（用例列表 + 实时仪表板），Locust 风格统计表（Method、#Requests、#Fails、Median、Avg、Min、Max、RPS），ECharts 折线图（RPS / Response Time / Error Rate），Failures 表 |
| **AutoResultDetail.vue** | 概览卡片（总/通过/失败/错误数 + 通过率 + 耗时）+ 可筛选用例表 + 抽屉（概览/断言 diff/响应体 三标签页） |
| **TestResultDetail.vue** | 通用详情：性能百分位面板（P50/P90/P95/P99）、请求/响应面板、UI 步骤时间线、断言结果表、截图画廊 |
| **DevOpsPlatform.vue** | 三功能卡片 + 最近执行表 + 统计面板 + 测试任务表（含实时轮询）+ Pipeline 时间线 |

### 10.3 色彩约定

| 场景 | 颜色 |
|------|------|
| 通过 | 绿色 / success |
| 失败 | 红色 / danger |
| 警告/错误 | 黄色 / warning |
| 运行/待执行 | 蓝色 / info |
| GET 方法 | info |
| POST 方法 | success |
| PUT 方法 | warning |
| DELETE 方法 | danger |
| 2xx 状态码 | success |
| 4xx/5xx 状态码 | danger |

---

## 十一、测试覆盖

### 11.1 后端测试（7 个文件）

| 测试文件 | 覆盖内容 | 行数 |
|----------|---------|------|
| `test_api_auto_executor.py` | `AssertionExecutor.execute_assertion()` 状态码 eq pass/fail、非 JSON body、模板变量替换 | 80 |
| `test_extractors.py` | `extract_value()` body 单字段/嵌套/数组/路径不存在、status 源、两次响应链式提取 | 86 |
| `test_locust_runner.py` | `LocustRunner` 初始化、`stop_test()` 进程终止（mock 验证） | 21 |
| `test_performance_persistence.py` | 全集成：`run_performance_test` → TestResult + PerformanceTestResult 持久化、pass/fail 阈值、用户 abort | 250 |
| `test_run_plan_executor.py` | `_get_or_create_plan_suite()` 创建/复用占位 suite、`TestRunPlanExecutor` 初始化 + `_broadcast` | 43 |
| `test_template_engine.py` | `build_variable_pool()` 优先级（overrides > environment > globals）、`render_string()`/`render_value()` 各种场景 | 73 |
| `test_unified_assertions.py` | `evaluate()` status_code eq/ne、JSONPath 简单/嵌套/数组 contains/fail、header exists contains | 77 |

### 11.2 前端单元测试（4 个文件）

| 测试文件 | 覆盖内容 |
|----------|---------|
| `ApiCaseRunDetail.test.ts` | 容器渲染、断言结果展示（passed/failed）、空响应体处理 |
| `DevOpsPlatform.test.ts` | 头部操作按钮、CI/CD 集成卡片、统计面板（total cases, pass rate） |
| `PerformanceTestResult.test.ts` | 性能指标卡片渲染（avg/P50/P95/P99/QPS/error rate）、图表占位符、阈值对比 |
| `QaQuickTestProjectScope.test.ts` | `QA.vue` 完整挂载、WebSocket URL 含正确 project_id、`startTest('api')` 调用含 project_id |

### 11.3 E2E 测试（6 个 QA 相关文件）

| 文件 | 覆盖流程 |
|------|---------|
| `test_api_test_flow.py` | 创建 API 用例 → 执行 → 验证通过/失败结果 |
| `test_api_batch_flow.py` | 批量执行对话框 → 选用例 → 执行 → 验证进度指示器 |
| `test_devops_flow.py` | 创建 CI/CD Jenkins 配置 → 触发管道 → 验证状态 + 质量报告 section |
| `test_performance_flow.py` | 创建性能用例 → 执行 → 验证 running 状态 + 指标表 |
| `test_ui_test_flow.py` | 录制器 → 点击操作 → 停止 → 保存 → 回放 → 验证截图 |
| `test_bug_flow.py` | 创建 Bug → 状态转换 → 详情验证 |

> 所有 E2E 测试使用 `ensure_project()` 创建/获取项目后导航到 `/{project_id}/qa` 进入 QA 区域。

### 11.4 已知测试缺口

| 缺口 | 严重度 |
|------|--------|
| SSRF `validate_target_url` 无测试 | 🔴 |
| Webhook 签名验证无测试 | 🔴 |
| 信号量 acquire/release/heartbeat 无测试 | 🔴 |
| 节流类无测试 | 🟡 |
| Pipeline（JenkinsClient / GitLabClient）无集成测试 | 🔴 |
| `ApiAutoTestExecutor.execute()` 全流程无测试 | 🔴 |
| `TestRunPlanExecutor` 执行流程无测试（仅初始化） | 🔴 |
| API 视图无 HTTP 级测试 | 🟡 |

---

## 十二、开发演进

### 12.1 里程碑时间线

| 日期 | 里程碑 | 关键产出 |
|------|--------|---------|
| 2026-06-11 | **API 测试优化** | 统一断言引擎、TestRun/TestRunCaseResult 双写模型、cURL 生成、趋势仪表板 |
| 2026-06-15 | **UI 测试深度修复** | Playwright 子进程 IPC、录制器双向通信、9 种结构化错误码 |
| 2026-06-26 | **验证闭环** | API 提取器、性能持久化、E2E 冒烟测试 |
| 2026-06-27 | **验证闭环（精化）** | "可证明可运行" 验收标准 |
| 2026-06-28 | **P1 功能修复** | 统计 choices 崩溃修复、质量报告字段名修正、提取器传播、性能状态标准化 |
| 2026-06-29 | **生产升级设计 v4** | 7 大问题识别、P0/P1/P2 优先级、Celery 迁移方案、真实 CI 方案、信号量方案、SSRF 方案 |
| 2026-06-30 | **数据迁移** | `migrate_qa_data` 命令（backfill is_mock）+ `backfill_test_runs` 命令 |

### 12.2 生产升级计划概览（v4 Design Spec）

```
┌────────────────────────────────────────────────────────────┐
│              QA Center Production Upgrade                   │
│                   (16 Tasks × 3 Phases)                     │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 0: 环境准备                                          │
│  Task 0: Celery config + requirements + feature flags      │
│                                                             │
│  Phase 1: P0 核心加固 (Tasks 1–13)                          │
│  ├─ Tasks 1–6:  Core test coverage (conftest + 6 test)     │
│  ├─ Task 7:     Celery task migration (3 tasks)            │
│  ├─ Task 8:     Pipeline real CI (ABC + Jenkins + GitLab)  │
│  ├─ Task 9:     Webhook security + PipelineWebhookEvent    │
│  ├─ Task 10:    Performance semaphore (3 Lua scripts)      │
│  ├─ Task 11:    SSRF hardening (7-layer defense)           │
│  ├─ Task 12:    Observability (metrics.py + task_tracker)  │
│  └─ Task 13:    Data migration (migrate_qa_data)           │
│                                                             │
│  Phase 2: P1 质量基线 + 验收 (Tasks 14–16)                  │
│  ├─ Task 14:    E2E tests (6 scenarios)                    │
│  ├─ Task 15:    Frontend tests + throttling + de-mock      │
│  └─ Task 16:    Full test suite + acceptance verification  │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 十三、已知差距

### 13.1 功能层面

| 差距 | 严重度 | 说明 |
|------|--------|------|
| Pipeline CI 为 Mock | 🔴 P0 | `_MockCiClient._simulate_run()` 使用 `time.sleep + random.random()` 模拟 |
| 后台任务用 threading.Thread | 🔴 P0 | Django 进程重启时任务丢失，无重试机制 |
| 性能测试单进程无并发控制 | 🟡 P1 | `USE_SEMAPHORE=False` 状态下无限制 |
| Webhook 签名验证未启用 | 🔴 P0 | 仅检查 token header |
| 五维质量报告为 Mock | 🟡 P1 | 未接入真实测试数据 |
| SSRF 防护已实现但未全量启用 | 🔴 P0 | 仅新自动执行器和 RunPlan 执行器使用 |

### 13.2 架构债务

| 项目 | 说明 |
|------|------|
| **双模型系统维护成本** | 旧 `ApiTestCase`/`ApiTestResult` 与新 `ApiAutoTestSuite`/`ApiAutoTestCase`/`ApiAutoTestResult` 并行，序列化器和视图需同时维护 |
| **四重写入** | 旧单例执行同时写入 `ApiTestResult` + `TestRun` + `TestRunCaseResult` + `TestResult` |
| **执行器不统一** | 4 条执行路径使用不同 HTTP 客户端（Django Test Client / requests / requests.Session），行为不一致 |
| **Cookie 会话仅 RunPlan** | 只有 `run_plan_executor.py` 使用共享 `requests.Session`，`api_auto_executor.py` 每次新建连接 |

### 13.3 近期已完成的修复

- ✅ WebSocket 项目范围校验（`ws/qa/dashboard/{project_id}/` —— commit `7b322d4`）
- ✅ 录制器 WebSocket 项目范围限定（commit `2f70f1a`）
- ✅ DRF 认证默认要求（commit `0554658`）
- ✅ Bug 分配目标项目访问校验（commit `7d117b7`）
- ✅ 性能状态标准化（`passed/failed/error/running/pending` 替代 `completed/stopped`）
- ✅ 旧数据格式兼容警告（`TestResultDetail.vue`）

---

## 附录

### A. 完整文件路径索引

**后端核心** (`backend/qa_center/`):

| 文件 | 行数 | 说明 |
|------|------|------|
| `models.py` | 1059 | 21 个模型定义 |
| `serializers.py` | 981 | DRF 序列化器（含 Token 掩码、嵌套序列化、分页） |
| `urls.py` | 92 | Router 注册 + 显式路径 |
| `views_api_test.py` | 852 | 旧 API 测试 ViewSet + 批量执行 |
| `views_api_auto_test.py` | 391 | 新 API 自动测试 ViewSet |
| `views_devops.py` | 1134 | DevOps 平台 ViewSet（统计、CI/CD、任务、质量报告） |
| `views_performance.py` | 231 | 性能测试 ViewSet |
| `views_run_plan.py` | 139 | 执行计划 ViewSet |
| `views_environment.py` | 137 | 环境变量 ViewSet |
| `views_test_run.py` | 328 | TestRun ViewSet（取消/重跑） |
| `api_auto_executor.py` | 429 | 新 API 自动执行器 + AssertionExecutor + JsonPathExtractor |
| `run_plan_executor.py` | 459 | 执行计划引擎（Session 复用 + 并行/serial + WS 广播） |
| `test_executor.py` | 491 | 旧 API 执行器（requests.Session + evaluate_assertion） |
| `template_engine.py` | 152 | `{{var}}` 模板引擎（三级变量优先级） |
| `unified_assertions.py` | 690 | 11 种断言类型统一引擎 |
| `assertion_engine.py` | 254 | 旧断言引擎（仍被 test_executor 使用） |
| `extractors.py` | 110 | 5 种数据源运行时提取器 |
| `request_builder.py` | 152 | Query params 归一化 + 文件上传构建 |
| `pipeline/__init__.py` | 197 | CiClient ABC + CiTriggerResult + _MockCiClient + get_client 工厂 |
| `pipeline/jenkins.py` | 328 | JenkinsClient（Blue Ocean + classic API 回退） |
| `pipeline/gitlab.py` | 239 | GitLabClient（API v4，分页 jobs） |
| `pipeline/state_mapping.py` | 77 | 平台状态到统一状态的映射 + TERMINAL_STATUSES |
| `semaphore.py` | 197 | Redis ZSET 信号量（3 个 Lua 脚本）+ get_available_port |
| `throttling.py` | 35 | 4 个 UserRateThrottle 子类 |
| `webhooks.py` | 162 | HMAC 签名验证 + 去重 + 限流 |
| `metrics.py` | 141 | trace_id 生成 + task_tracker 上下文管理器 |
| `ssrf.py` | 214 | 7 层 SSRF 防御 + SSRFProtectedSession |
| `bug_utils.py` | 130 | 从测试失败自动创建 Bug |
| `locust_runner.py` | 505 | Locust 子进程管理 + TestMetrics + 实时监控 |
| `consumers.py` | 365 | 5 个 WebSocket Consumer |
| `routing.py` | 28 | 7 个 WebSocket URL |
| `tasks.py` | 191 | run_performance_test Celery 任务 |
| `tasks_test_exec.py` | 245 | run_batch_api_tests + execute_test_task + poll_pipeline_status |

**测试文件** (`backend/qa_center/tests/`):

| 文件 | 行数 |
|------|------|
| `conftest.py` | 71 |
| `test_api_auto_executor.py` | 80 |
| `test_extractors.py` | 86 |
| `test_locust_runner.py` | 21 |
| `test_performance_persistence.py` | 250 |
| `test_run_plan_executor.py` | 43 |
| `test_template_engine.py` | 73 |
| `test_unified_assertions.py` | 77 |

**前端核心** (`frontend/src/`):

| 文件 | 说明 |
|------|------|
| `views/QA.vue` | 质量中心入口 |
| `views/qa/ApiCaseList.vue` | API 用例列表 |
| `views/qa/ApiCaseDetail.vue` | API 用例编辑（旧版） |
| `views/qa/ApiCaseRunDetail.vue` | 单次执行详情（新版） |
| `views/qa/AutoResultDetail.vue` | 批量执行结果 |
| `views/qa/UiCaseList.vue` | UI 用例列表 |
| `views/qa/UiCaseDetail.vue` | UI 用例编辑 + 录制 |
| `views/qa/PerformanceTestResult.vue` | 性能测试仪表板 |
| `views/qa/TestResultList.vue` | 结果列表 |
| `views/qa/TestResultDetail.vue` | 结果详情 |
| `views/qa/TestRunList.vue` | 批量执行列表 |
| `views/qa/TestRunDetail.vue` | 批量执行详情 |
| `views/qa/DevOpsPlatform.vue` | DevOps 仪表板 |
| `views/qa/TestTaskDetail.vue` | 测试任务详情 |
| `api/autoresult.ts` | 自动测试结果 API |
| `api/devops.ts` | DevOps API |
| `api/runplan.ts` | 执行计划 API |
| `api/testrun.ts` | TestRun API |
| `composables/useRecorderSocket.ts` | 录制器 WS 状态机 |

**E2E 测试** (`e2e/`):

| 文件 | 说明 |
|------|------|
| `conftest.py` | 浏览器 + 登录 fixtures |
| `helpers.py` | login / ensure_project 工具函数 |
| `test_api_test_flow.py` | API 测试 E2E |
| `test_api_batch_flow.py` | 批量 API E2E |
| `test_devops_flow.py` | DevOps E2E |
| `test_performance_flow.py` | 性能测试 E2E |
| `test_ui_test_flow.py` | UI 测试 E2E |
| `test_bug_flow.py` | Bug 流程 E2E |

### B. 关键配置项

```python
# backend/backend/settings.py - QA 相关配置段

# Celery 队列定义
CELERY_TASK_QUEUES = {
    'qa_long': {'exchange': 'qa_long', 'routing_key': 'qa_long'},
    'qa_pipeline': {'exchange': 'qa_pipeline', 'routing_key': 'qa_pipeline'},
}

# 功能开关（默认全部关闭，渐进式灰度上线）
USE_CELERY_TASKS = False   # Celery 任务迁移开关
USE_REAL_CI = False        # 真实 CI 集成开关
USE_SEMAPHORE = False      # 性能测试信号量开关

# 性能测试并发限制
PERF_MAX_CONCURRENT = 5

# Redis 用于: cache + channel layers + Celery broker/result backend
```

### C. Python 依赖

| 包 | 用途 | 版本要求 |
|----|------|---------|
| `djangorestframework` | REST API 框架 | — |
| `channels` | WebSocket 支持 | — |
| `channels-redis` | WebSocket Redis 后端 | — |
| `celery[redis]` | 异步任务队列 | >=5.3, <6.0 |
| `redis` | 缓存/队列后端 | — |
| `jsonpath-ng` | JSONPath 断言/提取 | — |
| `jsonschema` | JSON Schema 断言 | >=4.0 |
| `locust` | 性能/负载测试 | — |
| `requests` | HTTP 客户端（新执行器） | — |
| `django-fernet-fields` | CiCdConfig token 加密 | 计划引入 |

### D. 设计文档索引

| 文件 | 说明 |
|------|------|
| `docs/superpowers/specs/2026-06-29-qa-center-production-upgrade-design.md` | 生产升级设计 v4（21 项 P0 验收标准） |
| `docs/superpowers/plans/2026-06-29-qa-center-production-upgrade.md` | 生产升级 16 任务执行计划 |
| `docs/superpowers/specs/2026-06-11-qa-center-api-test-optimize-design.md` | API 测试优化：统一断言 + TestRun 模型 |
| `docs/superpowers/specs/2026-06-15-ui-test-module-deep-fix-design.md` | UI 测试子进程重设计 |
| `docs/superpowers/specs/2026-06-28-qa-functional-p1-fixes-design.md` | P1 功能修复设计 |
| `docs/LEARNING_ROADMAP.md` | 学习路线图（8 模块依赖顺序 + 5 个已知代码文档差异） |
| `docs/MODULES_QA.md` | QA 模块问答指南（L1/L2/L3 分级，12 个模块） |

---

> **此文档由代码探索自动生成，反映 2026-06-30 dev 分支的实际代码状态。所有文件路径均为绝对路径，行数来源于实际文件统计。**
