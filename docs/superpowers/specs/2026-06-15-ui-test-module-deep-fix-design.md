# UI 测试模块深度修复与二次开发设计

- 日期：2026-06-15
- 范围：`backend/qa_center/`（runner、recorder、views_ui_test、consumers）+ `frontend/src/views/qa/`（UiCaseList、UiCaseDetail 及相关组件）
- 状态：待评审

## 1. 背景与问题

UI 测试模块（基于 Playwright 的 E2E 自动化）当前不可用：

- **运行用例失败**：前端 toast 显示「Playwright 运行错误：」（错误信息为空字符串）。
- **录制启动失败**：前端显示「启动失败：」（错误信息为空字符串）。
- 后端日志侧（用户提供）：`[Recorder] Recording loop failed: `、`on_ready callback called with: {'success': False, 'message': '启动失败: '}` —— 异常被捕获但 `str(e) == ''`，根因被吞掉。

### 1.1 现状分析

| 项 | 当前实现 | 问题 |
|---|---|---|
| 运行入口 | `backend/qa_center/views_ui_test.py:42-90` `UiTestCaseViewSet.run` 直接同步调 `PlaywrightRunner.run_ui_case` | 在 ASGI Django 进程的请求线程里跑 `sync_playwright`，与主事件循环、其他线程的 Playwright 调用相互干扰 |
| 运行实现 | `backend/qa_center/utils/runner.py:18` `PlaywrightRunner` | 同步阻塞；异常处理仅 `str(e)`，无 traceback；`_setup_temp_dir` 在 L37-38 **进程级**修改 `os.environ['TEMP']`/`TMP`；`finally` 阶段 `shutil.rmtree` 在 Windows 上易被浏览器/driver 文件锁打断 |
| 录制入口 | `backend/qa_center/consumers.py:42` `RecorderConsumer` 通过 `threading.Thread` 起 `recorder.run_recording_loop` | 同上；与 Django ASGI 主事件循环的 asyncio 在同进程内交错，`sync_playwright().start()` 在不同 Python/Playwright 版本上偶发抛 message 为空的 `Error` |
| 录制实现 | `backend/qa_center/utils/recorder.py:36` `PlaywrightRecorder` 自研 JS 注入 + `expose_binding` 推事件 | 异常处理同样只 `str(e)`；模块级 `_setup_playwright_env()` 也污染 `TEMP/TMP`；与 runner 的临时目录策略不一致（runner 改 TEMP/TMP，recorder 只改 PLAYWRIGHT_TEMP_DIR） |
| 临时目录 | `backend/.playwright-temp/{run\|recorder}_xxx/` | 进程级环境变量污染；多并发请求互相覆盖；rmtree 与浏览器关闭顺序不严格保证；残留目录无清理机制 |
| 错误反馈 | runner/recorder 都用 `str(e)`，丢失 traceback；HTTP 仍返回 200 包错误体 | 用户看到空错误，无法自助排查 |
| 前端运行反馈 | `POST /run/` 同步阻塞，结果异步落库；前端轮询/跳转结果页 | 长任务期间无任何进度可见 |
| 前端录制 | `UiCaseDetail.vue`（约 1300 行单文件）订阅 `ws://.../ws/qa/recorder/`，`start_recording`/`stop_recording` 命令 | 单文件耦合；启动失败信息空；缺暂停/恢复、断言录制 UX、试运行单步 |

### 1.2 根因总结

错误吞噬（`str(e) == ''`）让用户看不到根因。背后的实际故障源自三类问题：

1. 同进程同步 Playwright 与 ASGI 事件循环、并发请求线程互相干扰；
2. 进程级 `TEMP/TMP` 环境变量污染，并发请求互相覆盖、上一次失败污染下一次；
3. Windows 上 `shutil.rmtree` 在 driver/浏览器子进程仍持文件句柄时失败。

## 2. 目标与非目标

### 2.1 目标

- 彻底修好运行与录制两条路径的稳定性，消除"空错误"。
- 把 Playwright 的所有调用搬出 Django 主进程，杜绝同进程事件循环冲突与环境变量污染。
- 失败时前端能看到结构化错误（`error_code`、`message`、`traceback`、失败步骤截图）。
- 运行过程实时可见（步骤进度、日志、截图、可中止）。
- 录制 UX 二次开发：暂停/恢复、断言录制、单步试运行、导出/合入策略。

### 2.2 非目标

- 不引入 Celery / RQ。
- 不切换到 `playwright codegen` CLI（与现有断言交互不兼容，二次开发反而更难）。
- 不做分布式 / 多机 worker。
- 不集成 Playwright Trace Viewer（作为下一期增量，仅留位）。
- 不替换 Channels 的 InMemoryChannelLayer（属于平台级议题，独立处理）。

## 3. 总体架构

```
┌─────────────── Django ASGI 进程 ───────────────┐
│ HTTP / WS                                      │
│ ├ UiTestCaseViewSet.run  ─────────► RunnerSupervisor ──┐
│ ├ RecorderConsumer       ─────────► RecorderSupervisor ┤
│ └ ws/qa/run/{task_id}/   ◄──── 事件流 ◄───────────────┘
│                                                       │ subprocess.Popen + JSON Lines (stdin/stdout)
└───────────────────────────────────────────────────────┼──────────┐
                                                       ▼          ▼
                                               runner_worker.py  recorder_worker.py
                                                  (一次性)         (会话期常驻)
                                               · 自有 temp_dir   · 自有 temp_dir
                                               · 自有 TEMP/TMP   · 自有 TEMP/TMP
                                               · sync_playwright 全部在子进程内
                                               · 退出时 rmtree
```

核心思想：Django 进程不再直接调 `sync_playwright`，全部下沉到独立子进程。每个 worker 拥有自己的工作目录与环境变量，互不干扰；崩溃也只崩自己。

## 4. 进程模型与目录约定

### 4.1 Worker 类型

| Worker | 职责 | 生命周期 |
|---|---|---|
| `runner_worker.py` | 执行单次用例所有步骤，流式回报进度 / 截图 / 错误 | 一次用例运行 |
| `recorder_worker.py` | 启动有头浏览器、注入录制脚本、流式回报录制事件 | 录制会话期间，stop 后退出 |

### 4.2 Supervisor

| Supervisor | 职责 |
|---|---|
| `runner_supervisor.execute_ui_case(case, on_event)` | `Popen` 拉起 worker，喂入参，从 stdout 读 JSON 行回调 `on_event`；返回最终结果 dict |
| `recorder_supervisor.RecorderSession` | `start(url, on_event)` / `stop()` / `is_alive()`；维护与 worker 的双向 stdin/stdout 通道 |

### 4.3 临时目录约定

- **彻底移除** `runner.py:37-38` 与 `recorder.py:_setup_playwright_env()` 对进程级 `os.environ['TEMP']/['TMP']` 的修改。
- 每个 worker 子进程内部 `tempfile.mkdtemp(prefix='run_'|'rec_', dir=BASE_DIR/.playwright-temp)`，并在**子进程环境**里设置 `TEMP`/`TMP`/`PLAYWRIGHT_TEMP_DIR` 指向该目录。
- worker 退出前按 `browser.close()` → `playwright.stop()` → 等 driver 子进程回收 → `shutil.rmtree(ignore_errors=True)`。
- Django `apps.py ready()` 添加启动钩子：扫描 `.playwright-temp/` 删除超过 24h 的残留目录；同时维护一份运行中 PID 表，发现 PID 不存在即清理对应目录。

## 5. JSON 行协议

stdout 每行一个 JSON 对象。stdin 同样按行读 JSON 命令。stderr 直通 Django logger 输出（`[worker:{pid}] ...`）。

### 5.1 Runner worker

启动后从 stdin 读一行入参：
```json
{"case_id": 10, "steps": [...], "base_url": "...", "viewport": {"width":1920,"height":1080}, "timeout_ms": 30000}
```
stdout 事件：
```jsonl
{"type":"started","temp_dir":"D:\\...\\run_abc"}
{"type":"step_start","index":0,"action":"goto","desc":"打开首页"}
{"type":"step_log","index":0,"message":"已导航到 ..."}
{"type":"step_screenshot","index":0,"path":"D:\\...\\run_abc\\step_0.png"}
{"type":"step_done","index":0,"success":true,"duration_ms":420}
{"type":"step_done","index":1,"success":false,"code":"SELECTOR_NOT_FOUND","message":"找不到元素 ...","traceback":"..."}
{"type":"finished","success":false,"summary":{"passed":3,"failed":1,"total":4}}
```
stdin 命令（运行期间）：
```jsonl
{"cmd":"abort"}
```

### 5.2 Recorder worker

stdin 命令：
```jsonl
{"cmd":"start","url":"https://...","viewport":{"width":1920,"height":1080}}
{"cmd":"pause"}
{"cmd":"resume"}
{"cmd":"run_step","step":{...}}
{"cmd":"stop"}
```
stdout 事件：
```jsonl
{"type":"ready","success":true}
{"type":"record_event","data":{...}}
{"type":"record_assert_event","data":{...}}
{"type":"step_run_done","success":true|false,"code":"...","message":"..."}
{"type":"paused"}
{"type":"resumed"}
{"type":"stopped","success":true}
{"type":"error","code":"LAUNCH_FAILED","message":"...","traceback":"..."}
```

### 5.3 编码 / 缓冲

- worker 启动时：`sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)`、`sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)`。
- supervisor：`Popen(..., encoding='utf-8', errors='replace', bufsize=1)`。
- 每条事件单行，避免 stdout 缓冲合并。
- 截图不入 JSON：worker 落盘到 temp_dir，事件中仅传 `path`，supervisor 读取转成 DataURL 后再转发给前端。

## 6. 错误模型

worker 内部把所有异常归类为结构化错误码：

| code | 触发场景 | 前端建议动作 |
|---|---|---|
| `BROWSER_NOT_INSTALLED` | `executable does not exist` / 找不到 chromium | 提示 `playwright install chromium` |
| `LAUNCH_FAILED` | `browser.launch()` 抛异常 | 展示 traceback + temp_dir，建议查 AV/防火墙 |
| `NAVIGATION_FAILED` | `page.goto` 超时或网络错误 | 展示 url + 上游错误 |
| `SELECTOR_NOT_FOUND` | locator 找不到 / count==0 | 展示选择器 + 当前截图 |
| `ASSERTION_FAILED` | 断言不通过 | 展示期望 vs 实际 |
| `STEP_TIMEOUT` | `PlaywrightTimeoutError` | 展示超时阈值 + 截图 |
| `UNSUPPORTED_ACTION` | 步骤 schema 中包含 worker 未识别的 action | 标记失败但不崩溃 |
| `WORKER_CRASHED` | worker 进程非 0 退出 | supervisor 兜底，附 stderr 尾部 |
| `INTERNAL` | 兜底其它 | 完整 traceback |

序列化字段统一：
```json
{"type":"error","code":"...","message":"...","traceback":"...","step_index":null,"screenshot_path":"..."}
```

### 6.1 Supervisor 兜底

- worker 非 0 退出：读 stderr 全部内容，构造 `WORKER_CRASHED` 事件回调；保证前端不会无限转圈。
- stdout 解析失败：原样写 `logger.warning`，不中断。
- 运行总超时（默认 5 分钟，可配置）：超时则发 `abort`，等 5 秒未退则 `terminate()`。

## 7. 数据模型增量

修改 `UiTestResult`（或当前承载结果的模型）。新增字段（全部允许 null，additive migration）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | CharField(64), indexed | 与 worker 进程关联，前端订阅 WS 频道用 |
| `error_code` | CharField(64), nullable | 见第 6 节 |
| `error_traceback` | TextField, nullable | 完整 traceback |
| `worker_pid` | IntegerField, nullable | 调试用 |
| `temp_dir_path` | CharField(512), nullable | 调试用，DEBUG 模式不会被自动清 |
| `aborted` | BooleanField, default False | 是否人工中止 |

## 8. 前端联动

### 8.1 运行实时事件流

- `POST /qa/ui-cases/{id}/run/` 立即返回 `{"task_id":"...","result_id":253}`。
- 新 WS 频道 `ws://.../ws/qa/run/{task_id}/`。supervisor 把 worker 事件双写到 DB 与 WS。
- 新增前端组件 `RunDrawer.vue`：步骤列表 + 进度条 + 实时日志 + 实时截图缩略图 + 失败详情（code/message/traceback）+「中止」按钮。
- `composables/useUiRunSocket.ts` 封装 WS 客户端。

### 8.2 录制 UX

| 功能 | 说明 |
|---|---|
| 录制状态指示 | worker pid / 浏览器就绪 / 已录制 N 步 / 当前 URL；启动失败显示 `[code] message` |
| 事件实时显示 | 右侧抽屉逐条显示，可即时编辑描述、删除、上移下移 |
| 断言录制 | Alt+点击元素弹断言类型选择（存在/可见/文本等于/包含/属性等于），插入断言步骤；复用 `onRecordAssertEvent` |
| 暂停/恢复 | `pause`/`resume` 命令；pause 期间不回传事件，浏览器保持 |
| 重启录制 | 一键 stop+start 换 URL |
| 导出/合入 | 「替换当前用例步骤」/「追加到当前用例」 |
| 单步试运行 | 录制器空闲时调 `run_step` 命令在当前页面执行单步骤 |

### 8.3 前端代码改造

| 文件 | 改造 |
|---|---|
| `UiCaseList.vue` | 运行按钮改为打开 `RunDrawer`；不再依赖 toast 通知最终结果 |
| `UiCaseDetail.vue` | 拆分为：录制控制器、步骤编辑器、运行抽屉、录制事件流面板 |
| 新增 `RunDrawer.vue` | 实时步骤进度 + 日志 + 截图 + 中止 |
| 新增 `RecorderPanel.vue` | 录制控制 + 事件列表 + 暂停/恢复 + 断言模式 |
| 新增 `composables/useUiRunSocket.ts` | 运行 WS 客户端 |
| 新增 `composables/useRecorderSocket.ts` | 录制 WS 客户端（替换现有内联实现） |

## 9. 日志与可观测性

### 9.1 Logger 划分

- `qa_center.runner`：运行事件（INFO），错误（ERROR + traceback）。
- `qa_center.recorder`：录制启动/停止/事件计数。
- worker stderr：`logging.basicConfig(level=DEBUG)`，supervisor 转发为 `[worker:{pid}] ...` 写入对应 logger。

替换现有 `logger = logging.getLogger('django')`，避免淹没在通用日志中。

### 9.2 调试模式

`UI_TEST_DEBUG=true` 时：
- supervisor 把 worker 完整 stdin/stdout/stderr 流落盘到 `.playwright-temp/{run|rec}_xxx/io.log`。
- worker 退出时**不删** temp_dir，方便人工排查。

## 10. 实施分阶段

每个 milestone 独立 commit，可单独回滚。

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **M1：worker 骨架** | `qa_center/workers/{__init__,protocol,runner_worker,recorder_worker}.py`；定义协议；最小 echo 流程 | 命令行手动喂 JSON，能拿到结构化事件 |
| **M2：runner 子进程化** | runner 逻辑搬入 `runner_worker.py`；新增 `runner_supervisor.py`；ViewSet 切换；移除 TEMP/TMP 进程级污染 | 用例能跑通；故意失败步骤前端能看到 code+traceback；并发 5 个运行不串扰 |
| **M3：错误模型 + DB migration** | 增加 `error_code`/`error_traceback`/`worker_pid`/`temp_dir_path`/`aborted`/`task_id` 字段；supervisor 写库；详情页展示 | 失败用例详情页能看到 code + traceback + 截图 |
| **M4：运行实时事件流** | WS 频道 `ws/qa/run/{task_id}/`；supervisor 双写 DB+WS；前端 `RunDrawer.vue` + `useUiRunSocket` | 点击运行立即出抽屉，步骤进度实时；中止按钮工作 |
| **M5：recorder 子进程化** | `recorder_worker.py` + `recorder_supervisor.py`；`RecorderConsumer` 通过 supervisor 中转；删 `_setup_playwright_env` 与 sync_playwright 直调 | 录制能稳定启停；连开 3 次启停不残留目录 |
| **M6：录制 UX 增强** | 拆分 `UiCaseDetail.vue` → `RecorderPanel.vue`；暂停/恢复、断言模式、单步试运行、替换/追加 | 录制全流程演示通过 |
| **M7：清理与日志** | 划分 logger；`apps.py ready()` 启动清理 24h 前残留 + 僵尸 PID；`UI_TEST_DEBUG`；删除老路径死代码 | 后端日志干净；`.playwright-temp` 不再无限膨胀 |

M1–M3 完成 = "修好"；M4–M7 = "二次开发"。

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Windows 子进程 stdout/stderr 编码乱码 | worker `sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)`；supervisor `Popen(..., encoding='utf-8', errors='replace')` |
| 截图 base64 撑爆 stdout 缓冲 | worker 落盘，事件传 path；supervisor 读取转 DataURL |
| 大量步骤事件挤爆 WS | supervisor 端做 100ms 节流合批 |
| Channels InMemoryChannelLayer 跨进程问题 | 新 WS 频道仍在同一 Django 进程内，supervisor 跑在 Django 进程；多 worker 部署需切 Redis channel layer，超出本次范围，文档标注 |
| 无 GUI 服务器跑录制 | worker 启动前检测 `DISPLAY`/`WAYLAND_DISPLAY`/Windows 桌面，缺失返回 `LAUNCH_FAILED` 明确提示 |
| 旧用例 schema 与新执行器兼容 | 未识别 action 返回 `UNSUPPORTED_ACTION` 不崩溃；M2 完成后回归现有所有用例 |
| 大改 `UiCaseDetail.vue` 引入回归 | 仅"抽出组件"式拆分，不改交互；M6 单独 PR；前后跑现有冒烟 |

## 12. 回滚策略

- 每个 milestone 独立 commit。
- M2 引入临时 feature flag `settings.UI_TEST_USE_SUBPROCESS`（默认 True，False 走旧路径）；稳定后下个 PR 直接删旧代码，不长期维护两套。
- DB migration 仅 add column，回滚不需要 down migration。
- `.playwright-temp/` 是一次性目录，回滚不影响数据。

## 13. 范围之外（明确不做）

- Celery / RQ。
- `playwright codegen` CLI 集成。
- 分布式 worker。
- Trace Viewer 集成（下一期增量，留位）。
- Redis channel layer 切换（独立议题）。
