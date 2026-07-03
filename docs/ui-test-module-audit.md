# UI 测试模块开发审计文档

> **项目**: SyncBoard  
> **审计范围**: `backend/qa_center/views_ui_test.py` + `workers/` + `consumers.py` + 前端 + E2E  
> **审计日期**: 2026-07-03  
> **审计人**: ZCode (代码级审核)  
> **模块总行数**: 后端 ~2,600 行 Python + 前端 ~2,200 行 Vue/TS + E2E ~176 行

---

## 目录

1. [模块概述](#1-模块概述)
2. [架构总览](#2-架构总览)
3. [文件清单与代码量](#3-文件清单与代码量)
4. [数据模型审计](#4-数据模型审计)
5. [API 接口审计](#5-api-接口审计)
6. [安全审计](#6-安全审计)
7. [代码质量问题](#7-代码质量问题)
8. [性能与可靠性](#8-性能与可靠性)
9. [测试覆盖审计](#9-测试覆盖审计)
10. [改进建议（按优先级）](#10-改进建议按优先级)

---

## 1. 模块概述

UI 测试模块是 SyncBoard 质量保障中心基于 **Playwright** 的端到端自动化测试子系统，提供录制、回放、批量执行三大核心能力：

| 能力 | 状态 | 说明 |
|------|------|------|
| **交互式录制** | ✅ 已实现 | Playwright 非 headless 模式 + 注入 JS 脚本捕获 DOM 事件 |
| **用例回放** | ✅ 已实现 | 子进程执行，支持 17 种动作类型 + 7 种断言 |
| **截图管理** | ✅ 已实现 | 每步自动截图，持久化到 TestScreenshot 模型 |
| **实时 WebSocket** | ✅ 已实现 | 录制/执行进度通过 Django Channels 实时推送 |
| **批量执行** | ✅ 已实现 | 通过 `execute_ui_test_cases()` 被 DevOps 和 RunPlan 调用 |
| **中止运行** | ✅ 已实现 | 通过 `abort_runner()` 终止子进程 |
| **事件回放** | ✅ 已实现 | 支持晚连接客户端通过 HTTP 拉取历史事件 |
| **临时运行** | ✅ 已实现 | `/run_temp/` 端点支持无保存用例的临时执行 |

---

## 2. 架构总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                               │
│  UiCaseList.vue  UiCaseDetail.vue  RecorderPanel.vue                 │
│  useRecorderSocket.ts  (WebSocket 状态机)                             │
├──────────────────────────────────────────────────────────────────────┤
│  REST API                         WebSocket                          │
│  POST /ui-cases/{id}/run/         ws/qa/recorder/<project_id>/       │
│  POST /ui-cases/run_temp/         ws/qa/run/<task_id>/               │
│  POST /ui-cases/runs/{id}/abort/  ws/qa/dashboard/<project_id>/      │
│  GET  /ui-run/screenshot/                                            │
├──────────────────────────────────────────────────────────────────────┤
│               Django 进程内 Supervisor                                │
│  ┌────────────────────┐    ┌─────────────────────────┐               │
│  │ runner_supervisor  │    │ recorder_supervisor     │               │
│  │  · execute_ui_case │    │  · RecorderSession      │               │
│  │  · abort_runner    │    │  · start/send/stop      │               │
│  │  · record_event    │    │  · stdout → on_event    │               │
│  └───────┬────────────┘    └───────────┬─────────────┘               │
│          │ stdin/stdout                │ stdin/stdout                 │
│  ┌───────┴────────────┐    ┌───────────┴─────────────┐               │
│  │  runner_worker.py  │    │  recorder_worker.py     │               │
│  │  (Playwright exec) │    │  (Playwright record)    │               │
│  │  headless=true     │    │  headless=false         │               │
│  └────────────────────┘    └─────────────────────────┘               │
├──────────────────────────────────────────────────────────────────────┤
│                         Data Layer                                    │
│  UiTestCase → TestResult → TestScreenshot → TestRun (mirror)         │
│  workers/ → .playwright-temp/ → MEDIA_ROOT/test_screenshots/         │
└──────────────────────────────────────────────────────────────────────┘
```

**核心设计模式**:

- **子进程隔离**: 执行和录制均通过 `subprocess.Popen` 在独立 Python 进程中运行，提供崩溃隔离和资源清理
- **JSON-Lines 协议**: 父子进程通过 stdin/stdout 以 JSON 行协议通信（事件溯源模式）
- **临时目录双写**: Worker 输出到 `.playwright-temp/` → 父进程读取后复制到 `MEDIA_ROOT/test_screenshots/` → 清理临时目录

---

## 3. 文件清单与代码量

### 3.1 后端文件

| 文件 | 行数 | 复杂度 | 职责 |
|------|------|--------|------|
| `views_ui_test.py` | 471 | 🔴 高 | REST API（ViewSet + 4 个静态端点）+ 持久化逻辑 |
| `workers/runner_worker.py` | 283 | 🟡 中 | Playwright 子进程：步骤执行、截图、错误分类 |
| `workers/runner_supervisor.py` | 259 | 🔴 高 | 子进程生命周期管理：启动、超时、崩溃、事件路由 |
| `workers/recorder_worker.py` | 770 | 🔴 极高 | Playwright 录制引擎 + ~640 行内联 JS 录制脚本 |
| `workers/recorder_supervisor.py` | 116 | 🟢 低 | RecorderSession 包装：stdin 命令、stdout 事件 |
| `consumers.py` | 380 | 🟡 中 | 4 个 WebSocket Consumer（Recorder + UiRun + QA + TestRun） |
| `result_sink.py` (sync_ui_run) | 65 | 🟢 低 | TestResult → TestRun/TestRunCaseResult 镜像 |
| `models.py` (UI 相关) | ~100 | 🟢 低 | UiTestCase (32行) + TestScreenshot (18行) + TestResult.ui_test_case |
| `serializers.py` (UI 相关) | ~60 | 🟢 低 | UiTestCaseSerializer + UiTestCaseListSerializer + UiTestCaseRunSerializer |
| `urls.py` (UI 路由) | ~10 | 🟢 低 | Router + 3 个静态路径 |
| **总计** | **~2,600** | | |

### 3.2 前端文件

| 文件 | 行数 | 复杂度 | 职责 |
|------|------|--------|------|
| `views/qa/UiCaseDetail.vue` | 1,050 | 🔴 极高 | 录制+回放+步骤编辑+结果展示的单页应用 |
| `views/qa/UiCaseList.vue` | 278 | 🟡 中 | 用例列表：筛选、删除、跳转 |
| `views/qa/components/RecorderPanel.vue` | 167 | 🟡 中 | 录制面板：状态、事件列表、断言对话框 |
| `composables/useRecorderSocket.ts` | 88 | 🟢 低 | WebSocket 状态机 |
| `views/qa/TestResultDetail.vue` | 1,256 | 🔴 极高 | 统一结果详情（UI 部分渲染步骤时间线和截图） |
| **总计** | **~2,839** | | |

### 3.3 测试文件

| 文件 | 行数 | 类型 |
|------|------|------|
| `e2e/test_ui_test_flow.py` | 63 | E2E |
| `e2e/helpers.py` | 92 | E2E 辅助 |
| `e2e/test_login_flow.py` | 21 | E2E 辅助 |
| **总计** | **176** | **无单元测试** |

---

## 4. 数据模型审计

### 4.1 UiTestCase

| 字段 | 类型 | 审计意见 |
|------|------|---------|
| `name` | CharField(200) | ✅ 合理 |
| `url` | CharField(1000) | ✅ 足够容纳长 URL |
| `steps` | JSONField(default=list) | ⚠️ **无 schema 校验**：后端不会验证 steps 中每个对象的字段结构。错误格式的 step 会在运行时在子进程中以 `UNSUPPORTED_ACTION` 失败 |
| `created_by` | FK→User (SET_NULL) | ✅ 软删除友好 |
| `project` | FK→Project (CASCADE) | ✅ 级联删除合理 |
| `related_tasks` | M2M→Task | ✅ 与看板任务关联 |

**⚠️ steps JSON 无校验**: 当前 steps 完全由前端验证，后端接收任意 JSON。恶意或格式错误的 steps 数组会在 Playwright 子进程中抛出异常。建议在 serializer 层添加 minimal schema 校验。

### 4.2 TestScreenshot

| 字段 | 类型 | 审计意见 |
|------|------|---------|
| `image` | ImageField | ✅ 路径: `test_screenshots/%Y/%m/%d/` |
| `step_index` | IntegerField(null=True) | ⚠️ 允许 null，但 `ui_run_screenshot_by_index` 按 index 查询时，null 的行不会被命中 |
| `test_result` | FK→TestResult (CASCADE) | ✅ |

### 4.3 TestResult（UI 特有字段）

| 字段 | 审计意见 |
|------|---------|
| `ui_test_case` FK | ✅ 关联到 UiTestCase (SET_NULL) |
| `task_id` | ⚠️ 用于 abort 路由和事件回放，但无唯一约束。同一 task_id 可能对应多条 TestResult |
| `lifecycle_state` (13 状态) | ⚠️ 大部分状态（preparing/probing/ramping 等）是为性能测试设计的，UI 测试只用了 pending→running→passed/failed |
| `temp_dir_path` | ⚠️ 存储 worker 的临时目录路径，用于事后读取截图。存在跨部署环境路径泄漏风险 |
| `worker_pid` | ⚠️ 可能已过期（worker 退出后 PID 被回收） |

---

## 5. API 接口审计

### 5.1 REST 端点总览

| 方法 | 端点 | 认证 | 项目隔离 | 审计发现 |
|------|------|------|---------|---------|
| GET | `/ui-cases/` | ✅ | ✅ `project_access_q` | 正常 |
| POST | `/ui-cases/` | ✅ | ✅ `ensure_project_id_access` | 正常 |
| GET | `/ui-cases/{id}/` | ✅ | ✅ `get_object()` 显式校验 | 正常 |
| PUT | `/ui-cases/{id}/` | ✅ | ✅ | 正常 |
| DELETE | `/ui-cases/{id}/` | ✅ | ✅ | 正常 |
| POST | `/ui-cases/{id}/run/` | ✅ | ✅ | ⚠️ 见下方 |
| GET | `/ui-cases/{id}/linked-tasks/` | ✅ | ✅ | 正常 |
| POST | `/ui-cases/runs/{id}/abort/` | ✅ | ✅ `_get_authorized_ui_result_for_task` | ⚠️ 见下方 |
| GET | `/ui-cases/runs/{id}/events/` | ✅ | ✅ | ⚠️ 见下方 |
| POST | `/ui-cases/run_temp/` | ✅ | ✅ | 正常 |
| GET | `/ui-run/screenshot/` | ✅ | ✅ `_path_is_under` | 🔴 见安全审计 |
| GET | `/ui-run/{task_id}/screenshot/{index}/` | ✅ | ✅ | 同上 |
| GET | `/media/test_screenshots/{path}` | ✅ | ✅ | ⚠️ 见安全审计 |

### 5.2 `POST /ui-cases/{id}/run/` — 单用例执行

**问题 1: 同步阻塞 HTTP 请求**

```python
# views_ui_test.py:220-235
@action(detail=True, methods=["post"])
def run(self, request, pk=None):
    test_case = self.get_object()
    events: list = []
    result = execute_ui_case(case_data, on_event=events.append)  # 阻塞 300s
    payload = self._events_to_payload(events, result)
    ...
```

`execute_ui_case` 是**同步阻塞调用**，默认超时 300 秒。在 WSGI 同步 worker 模型下会占用一个请求线程长达 5 分钟。如果使用 Gunicorn/uWSGI 的默认超时（通常 30-60 秒），请求会在 Playwright 执行完成前被 kill。

**影响**: 生产环境中此端点可能在执行长步骤时返回 502/504。

**建议**: 改为异步模式（返回 task_id，通过 WebSocket 或轮询获取结果），类似 DevOps 的 `TestTaskExecuteView` 设计。

**问题 2: 内存中 base64 编码所有截图**

```python
# views_ui_test.py:247-252
with open(ev["path"], "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
step_screenshots.append({
    "step": ev.get("index", 0) + 1,
    "screenshot": f"data:image/png;base64,{b64}",
})
```

所有步骤截图以 base64 编码后嵌入 HTTP 响应 JSON。对于 5 个步骤的全屏截图（每张 ~1-2MB PNG），响应体可能 **> 10MB**，极度浪费带宽和内存。

**建议**: 返回截图 URL 而非 base64 数据，让前端按需加载。

### 5.3 `POST /ui-cases/runs/{id}/abort/` — 中止运行

```python
# views_ui_test.py:288-318
@action(detail=False, methods=["post"], url_path=r"runs/(?P<task_id>[^/]+)/abort")
def abort_run(self, request, task_id=None):
    tr = _get_authorized_ui_result_for_task(request.user, task_id)
    alive = runner_supervisor.is_runner_alive(task_id)
    if not alive:
        return Response({"aborted": False, "message": "运行已结束或不存在"}, 404)
    ok = runner_supervisor.abort_runner(task_id)
    if tr.status not in ("passed", "failed"):
        tr.aborted = True
        tr.save(update_fields=["aborted"])
```

**问题**: abort 使用 `proc.terminate()` (SIGTERM)，但 supervisor 的 `execute_ui_case` 在终止后会检测到 `proc.returncode not in (0, None)`（退出码为 -15），从而发出虚假的 `WORKER_CRASHED` 错误事件。`timed_out["flag"]` 区分了超时终止和崩溃，但没有区分**主动 abort**。

**影响**: abort 后的执行会被记录为 "WORKER_CRASHED"，污染错误日志。

### 5.4 `GET /ui-cases/runs/{id}/events/` — 事件回放

```python
# views_ui_test.py:320-331
evs = runner_supervisor.get_events(task_id)
```

`get_events()` 调用 `_EVENTS.pop(task_id)`，一次性消费事件缓存。

**问题**: 如果前端重试或因网络问题调用了两次此端点，第二次调用会返回空数组（事件已被第一次消费）。
**问题**: `runner_supervisor` 的 `execute_ui_case` **没有调用** `record_event()`。查看代码，`_EVENTS` 注册表只被 `register_runner`/`unregister_runner` 管理，而 `record_event` 虽然在代码中定义，但从未在 `execute_ui_case` 的主循环中被调用。这意味着 `get_events()` **始终返回空数组**。

**影响**: 🔴 **事件回放功能可能已损坏**，除非有其他调用方填充 `_EVENTS`。

### 5.5 WebSocket 端点

| URL | Consumer | 审计发现 |
|-----|----------|---------|
| `ws/qa/recorder/<project_id>/` | `RecorderConsumer` | ✅ 认证 + 项目隔离 |
| `ws/qa/run/<task_id>/` | `UiRunConsumer` | ⚠️ 依赖 `_get_ui_result_project` 从 TestResult 反查 project（竞态） |
| `ws/qa/dashboard/<project_id>/` | `QAConsumer` | ✅ |

---

## 6. 安全审计

### 6.1 🔴 路径遍历 (Path Traversal)

**受影响端点**: `ui_run_screenshot`, `ui_run_screenshot_by_index`, `test_screenshot_media`

三层防护：

```python
def _path_is_under(path, root):
    abs_path = os.path.abspath(path)
    abs_root = os.path.abspath(root)
    try:
        return os.path.commonpath([abs_path, abs_root]) == abs_root
    except ValueError:
        return False
```

**发现**: 
1. `_path_is_under` 使用 `os.path.abspath` 而非 `os.path.realpath`。符号链接可以绕过 `commonpath` 检查。
2. `ui_run_screenshot` 端点接受用户提供的 `?path=` 参数，虽然先校验了 `_path_is_under(abs_path, safe_root)` 和 `_path_is_under(abs_path, temp_dir)`，但 `temp_dir` 来自 `tr.temp_dir_path`（数据库字段），如果数据库被污染，攻击者可读取任意文件。
3. `test_screenshot_media` 使用 `os.path.normpath` + 手动 `../` 检测，不如 `_path_is_under` 严格。

**CVSS 评估**: 中危 (Medium) — 需要认证 + 需要已知 Task ID，但在多租户环境下可造成跨项目文件访问。

**建议**: 
- 统一使用 `os.path.realpath` 替代 `os.path.abspath`
- `test_screenshot_media` 改用 `_path_is_under` 校验
- 对 `temp_dir_path` 数据库字段添加额外的格式校验

### 6.2 🟡 截图端点无速率限制

`ui_run_screenshot` 和 `ui_run_screenshot_by_index` 没有速率限制。攻击者可以用不同 task_id 遍历请求大量 PNG 文件。

### 6.3 🟡 Step 注入风险

```python
# runner_worker.py:104
elif action == "fill":
    _wait(selector).fill(value or "")
```

用户提供的 `selector` 和 `value` 直接传给 Playwright API。虽然 Playwright 的 `locator()` 使用 CSS selector 引擎（不支持 XSS），但 `page.evaluate()` 调用（如 `scroll` 动作）会执行 JavaScript：

```python
# runner_worker.py:125
elif action == "scroll":
    page.evaluate(f"window.scrollTo(0, {value or 0})")
```

如果 `value` 包含恶意 JS（如 `0); alert(1); (0`），会导致代码注入。⚠️ **`value` 未经过滤**。

**CVSS 评估**: 低危 (Low) — 仅在受信任用户创建用例的前提下；但如果用例被共享或通过 API 批量导入，风险增加。

### 6.4 ✅ 做得好的地方

- HMAC `compare_digest` 未直接在此模块使用，但模块的认证链路完整
- 所有 API 端点强制 `IsAuthenticated`
- 项目隔离在所有读/写操作中一致地应用
- `_get_authorized_ui_result_for_task` 作为截图访问的网关

---

## 7. 代码质量问题

### 7.1 🔴 严重

#### 7.1.1 全局可变状态 + 竞态条件

```python
# runner_supervisor.py:20-25
_RUNNERS: dict[str, "subprocess.Popen"] = {}
_RUNNERS_LOCK = threading.Lock()
_EVENTS: dict[str, list[dict]] = {}
_EVENTS_LOCK = threading.Lock()
```

两个全局字典在**多线程 Django 环境**下是共享可变状态。虽然加了锁，但：
- `_RUNNERS` 的 `register_runner` 只在 supervisor 线程中调用，而 `abort_runner` 由 HTTP 请求线程调用 → 锁是必要的，当前实现正确
- **但** `cleanup_expired_events()` 遍历 `_EVENTS` 时使用 `_ts` 键作为时间戳。`record_event()` **从未被调用**（见上方 5.4），意味着 `_EVENTS` 始终为空，该函数无实际作用
- 如果多个 worker 同时运行且 task_id 冲突（理论上 UUID 不会，但若显式传入相同 task_id），`_RUNNERS` 会被覆盖

#### 7.1.2 脆弱的文件路径解析

```python
# runner_supervisor.py:115-117
backend_dir = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."
))
```

`runner_supervisor.py` 位于 `qa_center/workers/`，通过 `"..", ".."` 回到项目根目录。如果文件被移动到不同深度的目录，路径就会出错。

**建议**: 使用 `settings.BASE_DIR`（已在 Django settings 中定义）。

#### 7.1.3 UiCaseDetail.vue — 巨型组件

`UiCaseDetail.vue` 共 **1,050 行**，混合了录制、回放、步骤编辑、任务关联、结果展示五种职责。违反单一职责原则。

**建议**: 拆分为：
- `UiCaseEditor.vue` (步骤编辑)
- `UiCaseRunner.vue` (执行 + 结果)
- `UiCaseRecorderWrapper.vue` (录制集成)

### 7.2 🟡 中等

#### 7.2.1 内联 JS 录制脚本难以维护

```python
# recorder_worker.py:63
RECORDING_SCRIPT = r"""
    (function() {
        if (window.__recorderInjected) return;
        ...
```

~640 行 JavaScript 以 Python 原始字符串嵌入。无语法高亮、无 lint、无单元测试、无版本管理。

**建议**: 将录制脚本提取为独立 `.js` 文件，通过构建步骤注入。

#### 7.2.2 错误分类逻辑脆弱

```python
# runner_worker.py:147-162
def _classify_error(exc: Exception) -> str:
    msg = str(exc)
    cls = exc.__class__.__name__
    lower = msg.lower()
    if "executable" in lower and "doesn" in lower:
        return "BROWSER_NOT_INSTALLED"
    if cls == "TimeoutError" or "Timeout" in cls:
        if "locator" in lower or "waiting for" in lower:
            return "SELECTOR_NOT_FOUND"
        return "STEP_TIMEOUT"
    ...
```

错误分类依赖字符串匹配（`"executable" in lower and "doesn" in lower`），对 Playwright 错误消息的格式变化极度脆弱。

#### 7.2.3 超时时间硬编码

| 位置 | 硬编码值 | 影响 |
|------|---------|------|
| `execute_ui_case(timeout_seconds=300)` | 300s | 所有用例统一 5 分钟超时 |
| `page.goto(timeout=30000)` | 30s | 页面导航 |
| `_wait(timeout=10000)` | 10s | 元素等待 |
| `_execute_single_step` 各操作 | 5s-15s | 分散在各处 |

没有提供用例级别的超时覆盖配置。

#### 7.2.4 `started_at` 和 `completed_at` 同时赋值

```python
# views_ui_test.py:130-131
started_at=timezone.now(),
completed_at=timezone.now(),
```

`_persist_ui_test_result` 在用例执行**完成后**被调用，此时 `started_at` 已不是实际开始时间。`duration_ms` 始终为空或接近 0，因为 `started_at ≈ completed_at`。

**影响**: 无法从 TestResult 中获取准确的执行时长。

#### 7.2.5 recorder_worker 使用非 headless 模式

```python
# recorder_worker.py (main() 调用 _do_start 时)
# headless=False 用于录制交互
```

录制默认使用非 headless 浏览器。在无 GUI 的服务器环境（Docker/CI）中会崩溃。

**建议**: 通过环境变量 `RECORDER_HEADLESS` 控制，默认在检测到无 DISPLAY 时回退。

### 7.3 🟢 轻微

- `consumers.py` 中 `RecorderConsumer._map_event()` 的逻辑分支较多，可改为 dispatch table
- `runner_supervisor.py` 的 `execute_ui_case` 函数 ~150 行，可拆分为 `_spawn_worker` + `_read_events` + `_handle_cleanup`
- 前端 `RecorderPanel.vue` 的事件列表没有虚拟滚动（长录制会话时性能下降）
- `e2e/helpers.py` 的 `BASE_URL` 默认 `http://localhost` —— 应该抛出异常如果环境变量未设置

---

## 8. 性能与可靠性

### 8.1 内存使用

| 操作 | 内存开销 | 风险 |
|------|---------|------|
| 单用例执行 (5 步骤) | ~200MB (Chromium) + 每步截图 ~1-2MB | 并发 5 个执行 = 1GB+ |
| `run` 端点 base64 编码 | 额外 1.33x 内存（base64 inflate） | 大截图下显著 |
| `_events_to_payload` 全量读取 | 所有截图同时存在于内存 | O(n × screenshot_size) |

### 8.2 并发安全

- 🔴 **子进程无并发限制**: 没有机制限制同时运行的 worker 数量。如果有 50 个用户同时点击"执行"，会启动 50 个 Chromium 实例。
- 🟡 **全局字典的锁粒度**: `_RUNNERS_LOCK` 在访问单个 key 时锁全表，高并发下可能成为瓶颈。

### 8.3 临时文件清理

清理链条：`worker cleanup_temp_dir` → `_persist_ui_test_result shutil.rmtree` → 兜底定时任务

**问题**:
1. `cleanup_temp_dir` 只在 `UI_TEST_DEBUG` 为 false 时执行（第 57-63 行），但 `_persist_ui_test_result` 也会清理（第 161-166 行）。两者存在竞态：如果 worker 的 `cleanup_temp_dir` 先执行，父进程读取截图时文件已不存在。
2. `_persist_ui_test_result` 删除后，`ui_run_screenshot_by_index` 的临时目录回退逻辑将找不到文件。
3. 兜底定时任务（`apps.py ready()`）**未被审计确认存在**。

### 8.4 可靠性问题

| 场景 | 行为 | 风险 |
|------|------|------|
| Worker 崩溃 | supervisor 捕获 `WORKER_CRASHED` 事件 | ✅ 正确处理 |
| Supervisor 崩溃 | Worker 成为孤儿进程，直至超时被 OS 清理 | 🟡 有 watchdog timer，但没有进程组管理 |
| Django 进程重启 | 所有 `_RUNNERS` 丢失，无法 abort | 🟡 重启后旧 worker 仍在运行但无法控制 |
| Playwright 浏览器崩溃 | 外层 `try/except` 捕获，`_classify_error` 可能匹配不到 | 🟡 可能返回模糊的 `INTERNAL` 错误 |

---

## 9. 测试覆盖审计

### 9.1 当前测试覆盖

| 测试级别 | 测试数量 | 覆盖内容 |
|---------|---------|---------|
| **单元测试** | **0** | 无 |
| **集成测试** | **0** | 无 |
| **E2E 测试** | 2 个函数 | 录制+保存、回放+截图验证 |

### 9.2 E2E 测试质量

`test_ui_test_flow.py` 的两个测试：

```python
def test_ui_record_and_save(logged_in_page: Page):
    """录制 UI 步骤并保存"""
    # ✅ 覆盖了录制→停止→保存的基本流程
    # ⚠️ 步数太少（仅 1 个 click），未验证复杂场景
    # ⚠️ 未验证保存的步骤是否正确
```

```python
def test_ui_replay_screenshots(logged_in_page: Page):
    """回放并验证截图"""
    # ✅ 验证回放后截图出现
    # ⚠️ 依赖 test_ui_record_and_save 创建的测试数据
    # ⚠️ 未验证截图内容正确性（仅检查 img 元素存在）
```

### 9.3 🔴 严重缺失的测试

| 缺失测试 | 风险 |
|---------|------|
| `runner_worker._execute_single_step` 的单元测试 | 17 种动作类型的正确性未经隔离测试 |
| `runner_worker._classify_error` 的单元测试 | 错误分类逻辑脆弱 |
| `runner_supervisor.execute_ui_case` 的超时测试 | 超时行为未验证 |
| `abort_runner` 的中止行为测试 | 中止后 worker 是否正确清理 |
| `_persist_ui_test_result` 的持久化测试 | 截图保存 + 统一镜像 |
| `_path_is_under` 的安全测试 | 路径遍历攻击向量未验证 |
| `useRecorderSocket` 的单元测试 | WebSocket 重连、状态迁移 |
| RecorderWorker `RECORDING_SCRIPT` 的浏览器测试 | ~640 行 JS 未在任何浏览器中被测试 |

---

## 10. 改进建议（按优先级）

### P0 — 紧急修复

| # | 问题 | 建议 | 文件 |
|---|------|------|------|
| 1 | **事件回放功能损坏** | 在 `execute_ui_case` 中添加 `record_event(task_id, event)` 调用 | `runner_supervisor.py` |
| 2 | **同步阻塞 HTTP 执行** | 将 `/run/` 改为异步（返回 task_id，通过 WS/轮询获取结果） | `views_ui_test.py` |
| 3 | **abort 导致虚假 WORKER_CRASHED** | 在 abort 后设置标志位，检查 false crash | `runner_supervisor.py` |
| 4 | **subprocess 无并发限制** | 添加信号量或最大 worker 数限制 | `runner_supervisor.py` |

### P1 — 高优先级

| # | 问题 | 建议 | 文件 |
|---|------|------|------|
| 5 | **base64 截图导致巨大响应** | 返回截图 URL 列表，前端 `<img>` 按需加载 | `views_ui_test.py` |
| 6 | **`started_at` 不正确** | 在 worker `started` 事件中获取实际时间戳 | `views_ui_test.py` |
| 7 | **路径遍历使用 `realpath`** | `_path_is_under` 改用 `os.path.realpath` | `views_ui_test.py` |
| 8 | **Scroll 步骤代码注入** | 将 `value` 转为 `int` 后再插入 evaluate | `runner_worker.py` |
| 9 | **脆弱的路径解析** | 使用 `settings.BASE_DIR` | `runner_supervisor.py` |
| 10 | **添加 steps schema 校验** | Serializer 级别验证 steps 结构 | `serializers.py` |

### P2 — 中优先级

| # | 问题 | 建议 |
|---|------|------|
| 11 | 提取 RECORDING_SCRIPT 为独立 JS 文件 | 构建步骤注入 |
| 12 | 拆分 UiCaseDetail.vue (1050行) | 3 个子组件 |
| 13 | 添加 worker 进程组管理 | `start_new_session=True` |
| 14 | 添加录制 headless 回退 | 检测 DISPLAY 环境变量 |
| 15 | 添加 TestResult.duration_ms 正确计算 | 在 `_persist_ui_test_result` 中设置 |
| 16 | `_classify_error` 重构为异常类型匹配 | 替代字符串匹配 |

### P3 — 低优先级

| # | 问题 | 建议 |
|---|------|------|
| 17 | 添加单元测试 | 优先覆盖 worker 和 supervisor |
| 18 | RecorderPanel 虚拟滚动 | 大量录制事件时 |
| 19 | 添加速率限制到截图端点 | Django throttle |
| 20 | 统一 `temp_dir_path` 清理逻辑 | 单一清理入口 |

---

## 附录 A: 依赖关系

```
views_ui_test.py
  ├── workers/runner_supervisor.py
  │   └── workers/runner_worker.py (子进程)
  │       └── playwright (sync API)
  ├── workers/recorder_supervisor.py
  │   └── workers/recorder_worker.py (子进程)
  │       └── playwright (sync API)
  ├── result_sink.py (sync_ui_run_from_test_result)
  ├── consumers.py (RecorderConsumer, UiRunConsumer)
  └── models.py (UiTestCase, TestResult, TestScreenshot)
```

## 附录 B: WebSocket 事件类型清单

| 事件类型 | 方向 | 用途 |
|---------|------|------|
| `connected` | S→C | WebSocket 连接成功 |
| `recording_started` | S→C | 录制已启动 |
| `recording_paused` | S→C | 录制已暂停 |
| `recording_resumed` | S→C | 录制已恢复 |
| `recording_stopped` | S→C | 录制已停止 |
| `record_event` | S→C | DOM 事件捕获 |
| `record_assert_event` | S→C | 断言事件捕获 |
| `step_run_done` | S→C | 单步试运行完成 |
| `run_event` | S→C | 执行进度事件 |
| `error` | S→C | 错误事件 |
| `start_recording` | C→S | 启动录制 |
| `stop_recording` | C→S | 停止录制 |
| `pause_recording` | C→S | 暂停录制 |
| `resume_recording` | C→S | 恢复录制 |
| `run_step` | C→S | 试运行单步 |

---

> **审计结论**: 模块架构设计合理（子进程隔离 + 事件溯源），但存在 **4 个 P0 级问题**需要立即修复（事件回放损坏、同步阻塞执行、虚假崩溃告警、无并发限制）。测试覆盖严重不足（0 单元测试），代码质量存在多处硬编码和技术债务（内联 640 行 JS、巨型组件）。安全方面整体可接受，但需修复路径遍历的 TOCTOU 风险和 scroll 步骤的代码注入。
