# QA 测试中心生产级可靠性升级 — 设计规格（v4）

> **创建日期**: 2026-06-29 | **修订**: 2026-06-29（审阅 v3 → v4：7 处精修 + 6 条验收标准）
> **路线**: 渐进式加固（路线 A）
> **目标**: 将 QA 测试中心从功能完备提升到生产级可靠

---

## 一、背景与现状

### 当前评分：6.5/10

| 问题 | 影响 |
|------|------|
| qa_center 核心模块零测试覆盖 | 迭代中容易引入回归 bug |
| DevOps Pipeline 是 mock | 质量报告「部署成功率」不可信 |
| 后台任务用 threading.Thread | Django 重启即丢任务 |
| 性能测试单进程 | 多用户并发排队 |
| 无 SSRF 防护 | 可攻击内网 |
| 无可观测性 | 故障不可感知 |
| Webhook 无安全校验 | 可伪造结果 |

---

## 二、优先级总览

```
P0（阻塞上线）：
  P0-1  核心模块测试覆盖
  P0-2  Celery 任务迁移 + 幂等 + 状态机 + 超时 + 失败恢复
  P0-3  Pipeline 真实 CI 对接（含状态映射 + 短轮询调度）
  P0-4  Pipeline Webhook 安全与幂等
  P0-5  性能测试并发控制（ZSET semaphore + Lua）
  P0-6  安全与权限加固（SSRF + DNS rebinding / token / 审计）
  P0-7  基础可观测性
  P0-8  发布迁移与回滚

P1（质量基线）：
  P1-1  E2E 测试 10+ 场景
  P1-2  前端集成测试增强
  P1-3  请求限流 + 资源配额
  P1-4  五维报告去 mock
  P1-5  失败归因与报告可信度增强

P2（后续迭代）：多租户配额、排队优先级、历史趋势、flaky test 识别、CI/CD 门禁、Locust 分布式
```

---

## 三、数据模型

### PipelineRun

```
PipelineRun:
  - id / project_id / ci_config_id
  - ci_type / ci_url / ci_project / ci_job_name
  - external_queue_id / external_queue_url
  - external_run_id / external_build_number / external_url
  - ref / commit_sha
  - status: pending / queued / running / success / failed / canceled / timeout / waiting
  - result: {passed, failed, skipped, total}
  - duration_ms / triggered_by / trigger_source
  - error_message
  - raw_status_payload (JSON, 最大 256KB, 超出截断且标记 truncated=true)

唯一约束: (ci_config_id, external_run_id) UNIQUE WHERE external_run_id IS NOT NULL
```

### PipelineWebhookEvent

```
PipelineWebhookEvent:
  - id / ci_type / ci_config_id / external_run_id
  - event_type / delivery_id
  - status
  - payload_hash: SHA256(raw_payload)
  - raw_payload (JSON, 最大 256KB, 超出截断且标记 truncated=true)
  - received_at / processed_at
  - process_status: pending / processed / duplicate / rejected / error
  - error_message
```

### TestExecution

```
TestExecution:
  - id / project_id
  - execution_id (UUID, UNIQUE)
  - trace_id (UUID)
  - batch_id → BatchExecution
  - retry_of_execution_id (NULL=首次)
  - suite_id / case_id
  - status: pending / queued / running / success / failed / canceled / timeout
  - status_reason
  - total_assertions / passed_assertions / failed_assertions
  - extracted_variables (JSON)
  - request_snapshot (JSON)
  - response_snapshot (JSON, 最大 128KB, 超出截断且标记 truncated=true)
  - error_type / error_message / traceback_summary (最大 4KB)
  - retry_count / celery_task_id
  - triggered_by / trigger_source
  - started_at / finished_at
```

### BatchExecution

```
BatchExecution:
  - id / project_id
  - batch_id (UUID, UNIQUE)
  - suite_id / plan_id
  - status: pending / queued / running / success / partial_failed / failed / canceled / timeout
  - total_cases / passed_cases / failed_cases / skipped_cases
  - progress: 0.0 ~ 1.0
  - triggered_by / trigger_source / celery_task_id / trace_id
  - started_at / finished_at

状态推导规则（由下属 TestExecution 汇总）:
  - 全部 success → success
  - 部分 failed/timeout → partial_failed
  - 全部 failed/timeout → failed
  - 任一 running → running
  - 用户取消 batch → 未开始任务 canceled，运行中任务尝试 cancel
```

### PerformanceExecution

```
PerformanceExecution:
  - id / project_id
  - execution_id (UNIQUE)
  - status: pending / running / success / failed / canceled / timeout
  - locust_pid / web_port
  - users / spawn_rate / duration / host
  - rps_avg / failure_count / p50 / p90 / p95 / p99
  - report_path / error_message
  - heartbeat_at / semaphore_slot
  - started_at / finished_at
```

---

## 四、P0 详细设计

### P0-1：核心模块测试覆盖

目标：qa_center 总覆盖率 > 60%，核心执行链路 > 80%。

6 个新测试文件 + conftest（test_template_engine / test_unified_assertions / test_extractors / test_api_auto_executor / test_run_plan_executor / test_locust_runner）。

---

### P0-2：Celery 任务迁移 + 幂等 + 状态机 + 超时

#### 2.1 迁移映射

| 现有位置 | 当前方式 | 替换 |
|----------|---------|------|
| `views_api_test.py` 批量执行 | `threading.Thread` | `tasks_test_exec.run_batch_api_tests.delay(batch_id)` |
| `views_devops.py` TestTask | `threading.Thread` | `tasks_test_exec.execute_test_task.delay(task_id)` |
| `views_devops.py` Pipeline 轮询 | 无 | `tasks_test_exec.poll_pipeline_status.delay(run_id)`（短轮询自调度，见 P0-3） |
| `views_ui_test.py` UI 执行 | `runner_supervisor` 子进程 | **不变** |
| `views_performance.py` 性能执行 | 已是 Celery | **不变** |

#### 2.2 状态转移表

| 当前状态 | 可转移至 | 触发条件 |
|----------|---------|---------|
| pending | queued | Celery 成功入队 |
| pending | failed | 入队失败 / 校验失败 |
| pending | canceled | 用户取消 |
| queued | running | Worker 领取 |
| queued | failed | 执行前校验失败 |
| queued | canceled | 用户取消 |
| queued | timeout | 排队超时 |
| running | success | 执行成功 |
| running | failed | 执行异常 |
| running | canceled | 用户取消 |
| running | timeout | 超过 soft_time_limit |
| success | **不可变** | — |
| failed | 生成新 execution (retry_of_execution_id) | 手动/自动重试 |
| canceled | **不可变** | — |
| timeout | 生成新 execution (retry_of_execution_id) | 手动/自动重试 |

**BatchExecution 状态推导**（由下属 TestExecution 汇总）：
- 全部 success → success
- 部分 failed/timeout → partial_failed
- 全部 failed/timeout → failed
- 任一 running → running
- 用户取消 batch → 未开始任务 canceled，运行中任务尝试 cancel

#### 2.3 幂等

- `execution_id`（UUID）唯一键，任务入口按转移表判断
- 终态时重复任务直接返回
- `BatchExecution.batch_id` 唯一，重复触发返回已有记录

#### 2.4 Celery 配置

**全局保守默认值：**
```python
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {'visibility_timeout': 7200}
```

**按任务类型分 Queue：**

| Queue | 任务类型 | time_limit | soft_time_limit |
|-------|---------|-----------|----------------|
| `qa_short` | API 单用例 | 180s | 150s |
| `qa_long` | API 批量执行 | 1800s | 1500s |
| `qa_pipeline` | Pipeline 轮询（单次短任务） | 120s | 90s |
| `qa_perf` | 性能测试 | duration + 300s | duration + 240s |
| `qa_watchdog` | Zombie 检测 | 120s | 90s |

每个 task 用 `@shared_task(time_limit=..., soft_time_limit=..., queue=...)` 单独声明。

#### 2.5 失败记录 & 依赖

每个执行记录携带 `error_type`、`error_message`、`traceback_summary`（最大 4KB）、`retry_count`、`started_at`、`finished_at`、`status_reason`。

`requirements.txt` 添加 `celery[redis]>=5.3,<6.0`。

---

### P0-3：Pipeline 真实 CI 对接

#### 3.1 CiClient 接口（同 v3）

`CiTriggerResult` / `CiRunStatus` / `CiJobResult` + `trigger/get_status/get_jobs/get_logs/cancel/verify_webhook`

#### 3.2 统一状态映射

**Jenkins：**
| Jenkins | 内部 |
|---------|------|
| QUEUED | **queued** |
| BUILDING | running |
| SUCCESS | success |
| FAILURE / UNSTABLE | failed |
| ABORTED | canceled |

**GitLab：**
| GitLab | 内部 |
|--------|------|
| created / pending | queued |
| running | running |
| success | success |
| failed | failed |
| canceled | canceled |
| skipped | skipped |
| manual / scheduled | waiting |

#### 3.3 短轮询自调度（关键：不长期占用 worker）

```
poll_pipeline_status(run_id):
  1. 查询一次 CI 状态 (get_status)
  2. 更新 PipelineRun.status
  3. 如果未终态:
     - countdown = 30s (默认, 可按失败次数退避: 30→60→120)
     - poll_pipeline_status.apply_async(args=[run_id], countdown=30, queue='qa_pipeline')
  4. 如果到达终态:
     - get_jobs() → 写入 PipelineRun.result
     - 结束
```

**好处**：不长期占用 worker、worker 重启影响小、每次 poll 独立、退避灵活。

#### 3.4 修改点

- `views_devops.py:746 _simulate_run` → 真实 CI 触发 + 短轮询
- `CiCdConfig` 新增：`ci_type`、`ci_url`、`ci_token`（加密）、`ci_project`、`ci_job_name`、`verify_ssl`

---

### P0-4：Pipeline Webhook 安全与幂等

**处理流程：**
```
POST /api/qa/pipeline/webhook/
  → 写入 PipelineWebhookEvent (process_status=pending)
  → 校验 secret (verify_webhook)
     → 失败: process_status=rejected, 401, 安全日志
  → 幂等检查: delivery_id 或 payload_hash 查重
     → 重复: process_status=duplicate, 200 (不处理)
  → 按 (ci_config_id, external_run_id) 查找 PipelineRun
  → 状态机检查: 终态不可逆
  → 更新, process_status=processed
```

`raw_payload` 最大 256KB，超出截断标记 `truncated=true`。与 polling 并存时以先到达终态的结果为准。

---

### P0-5：性能测试并发控制（ZSET semaphore + Lua）

#### 5.1 数据结构

```
perf:slots = ZSET (member=execution_id, score=acquired_at)
```

#### 5.2 Lua 原子脚本

**acquire.lua：**
```lua
-- KEYS[1] = "perf:slots"
-- ARGV[1] = execution_id
-- ARGV[2] = limit
-- ARGV[3] = now (timestamp)
-- ARGV[4] = heartbeat_timeout

local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local timeout = tonumber(ARGV[4])

-- 1. 清理过期 slot
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - timeout)

-- 2. 幂等：已持有直接返回
local existing = redis.call('ZSCORE', KEYS[1], ARGV[1])
if existing then
    return 1
end

-- 3. 超限检查
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
    return 0
end

-- 4. 获取
redis.call('ZADD', KEYS[1], now, ARGV[1])
return 1
```

**release.lua：**
```lua
-- KEYS[1] = "perf:slots"
-- ARGV[1] = execution_id
return redis.call('ZREM', KEYS[1], ARGV[1])
```

**heartbeat.lua：**
```lua
-- KEYS[1] = "perf:slots"
-- ARGV[1] = execution_id
-- ARGV[2] = now (timestamp)

local now = tonumber(ARGV[2])
local existing = redis.call('ZSCORE', KEYS[1], ARGV[1])
if existing then
    redis.call('ZADD', KEYS[1], now, ARGV[1])
    return 1
end
return 0
```

#### 5.3 使用 + Zombie 恢复（同 v3）

---

### P0-6：安全与权限加固

#### 6.1 执行权限

所有 QA 执行接口校验用户是否属于项目 + `can_execute_tests` 权限。

#### 6.2 Token 安全

- `ci_token` 加密存储（`django-fernet-fields`）
- Serializer 返回 `****`
- 日志自动脱敏
- Token 轮换：默认立即替换；如需灰度可配置旧 token 过渡期（最长 24h），旧 token 使用记录写入审计日志

#### 6.3 SSRF 防护（含 DNS rebinding）

**完整策略：**

1. **Allowlist 优先**：项目级配置允许域名列表；hostname 统一 lowercase、去末尾点、IDNA/punycode 规范化后再比较
2. **DNS 解析校验**：对目标 hostname 做 DNS 解析，获取所有 A/AAAA 记录
3. **IP 分类拦截**：禁止 loopback / private / link-local / multicast / reserved 网段
4. **Metadata 地址拦截**：`169.254.169.254`、`metadata.google.internal`、`100.100.100.200`
5. **Scheme 白名单**：只允许 `http` / `https`
6. **DNS rebinding 防护**：
   - 每次发起 HTTP 请求前重新解析 DNS 并校验（不复用校验阶段的解析缓存）
   - 每次 HTTP redirect 后对新 URL 重新解析并校验
   - 若校验时解析为公网 IP、请求时解析出内网 IP → 拒绝
7. **URL 防绕过**：禁止 `@` 用户名密码形式、十进制/八进制/十六进制 IP
8. **请求执行**：自定义 HTTP client，禁止自动跟随重定向

#### 6.4 操作审计（同 v3）

---

### P0-7：基础可观测性

`trace_id` + `execution_id` 贯穿全链路（前端→Django→DB→Celery→HTTP→断言→WS→报告）。结构化日志、6 个关键指标、5 条告警规则、管理面板。

---

### P0-8：发布迁移与回滚

#### 8.1 灰度策略

- 新 Celery 任务与旧 threading 并存一个版本
- `USE_CELERY_TASKS` feature flag 控制切换
- `USE_REAL_CI` 控制 Pipeline 真实对接

#### 8.2 回滚方案

| 场景 | 操作 |
|------|------|
| Celery 任务异常（灰度期） | `USE_CELERY_TASKS=False` → 切回 threading |
| Celery 任务异常（全量后） | 暂停任务触发、修复 worker、重新入队未完成任务 |
| Pipeline 异常 | `USE_REAL_CI=False` → 切回 mock |
| Migration 失败 | `migrate qa_center <previous>` |
| Semaphore 异常 | `USE_SEMAPHORE=False` → 切回 count 检查 |

> **注意**：旧 threading 路径仅作为灰度期短期兜底。全量稳定后**删除旧路径**，回滚方式改为暂停触发 + 修复 worker + 重新入队。

#### 8.3 数据迁移

- Migration 可重复执行（`RunPython` 中 `if not exists`）
- 新字段 `null=True`，旧数据兼容
- Pipeline mock 历史数据标记 `is_mock=True`，不参与新质量报告
- 数据修复脚本：旧 PipelineRun status 映射、旧性能结果迁移

---

## 五、P1 详细设计（摘要）

- P1-1：E2E 10+ 场景（api_test / api_batch / ui_test / performance / devops / bug）
- P1-2：前端集成测试 5 个新文件
- P1-3：DRF throttle（429）+ 资源配额（Redis 原子计数）
- P1-4：`_calc_deploy_score()` 从 PipelineRun 真实数据计算
- P1-5：失败自动分类 + 样本不足标注

---

## 六、数据大小限制汇总

| 字段 | 最大 | 超出处理 |
|------|------|---------|
| `TestExecution.response_snapshot` | 128KB | 截断，标记 `truncated=true` |
| `TestExecution.traceback_summary` | 4KB | 截断 |
| `PipelineRun.raw_status_payload` | 256KB | 截断，标记 `truncated=true` |
| `PipelineWebhookEvent.raw_payload` | 256KB | 截断，标记 `truncated=true` |

大文件、二进制响应、图片、压缩包不直接入库。

---

## 七、验收标准

### Phase 1（P0）— 21 条

1. `pytest backend/qa_center/tests/ -v --cov=qa_center` 通过，总覆盖率 > 60%，核心链路 > 80%
2. API 批量执行任务在 Django 重启后不丢失
3. 手动 kill Celery worker 后，任务不会永久 running
4. 同一 `batch_id` 重复触发不生成重复执行结果
5. Jenkins/GitLab 可真实触发，状态回写 PipelineRun
6. Pipeline webhook 重复推送不重复统计
7. CI token 不出现在 API 响应、日志、错误堆栈中
8. 同时触发 3 个性能测试，端口/进程/WS 指标互不串
9. 超过 `PERF_MAX_CONCURRENT` 返回明确错误
10. Locust 进程异常退出后，execution 自动标记 failed
11. 无 PipelineRun 数据时，质量报告部署维度显示「暂无数据」
12. SSRF：`http://127.0.0.1/` 被拒绝；`http://evil.com`（解析到 10.0.0.1）被拒绝
13. 非法 webhook 返回 401，记录安全日志 + PipelineWebhookEvent
14. CI 覆盖率下降 > 2% 时 CI 失败
15. Migration 可重复执行；旧数据兼容；回滚方案已演练
16. Pipeline 轮询任务不长期占用 worker；未终态时通过 countdown 重新调度
17. `response_snapshot` 超过 128KB 时截断，DB 不写入大体积响应
18. SSRF：HTTP redirect 到 `127.0.0.1` / `169.254.169.254` 时被拒绝
19. SSRF：域名首次解析为公网、二次解析为内网时被拒绝（DNS rebinding 防护）
20. `BatchExecution` 状态与下属 `TestExecution` 汇总一致
21. 灰度期结束后旧 threading 执行路径有明确删除计划

### Phase 2（P1）— 5 条

22. `pytest e2e/ -v` 全部 10+ 场景通过
23. `npx vitest run frontend/src/__tests__/` 全部通过
24. 超限流阈值返回 429；超资源配额返回明确错误
25. 质量报告「部署成功率」来自真实 PipelineRun 数据
26. 失败任务可归因到请求失败/断言失败/超时/连接失败/CI 失败

### 故障演练

| 场景 | 预期结果 |
|------|---------|
| Django 重启（Celery worker 存活） | 任务继续执行 |
| Celery worker kill -9 | 任务重新入队，幂等保证不重复 |
| Redis 短断（< 30s） | Celery 自动重连 |
| Jenkins/GitLab 不可达 | PipelineRun 标记 failed + error_message |
| Locust 进程 kill -9 | watchdog → timeout → release_slot |
| 同一 webhook 重复推送 3 次 | PipelineWebhookEvent 记录 duplicate |
| SSRF 尝试 169.254.169.254 | 拒绝 + 审计日志 |
| SSRF DNS rebinding（evil.com→127.0.0.1） | 拒绝 |
| SSRF HTTP redirect → 127.0.0.1 | 拒绝 |
| Celery 任务超时 | soft_time_limit 异常 → timeout → 可重试 |
| semaphore 进程 crash | heartbeat 超时 → Lua 自动清理 |
