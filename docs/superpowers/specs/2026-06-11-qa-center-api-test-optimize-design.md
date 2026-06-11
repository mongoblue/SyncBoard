# SyncBoard 质量中心优化 — 子项目 1: API 测试

> 日期: 2026-06-11
> 范围: API 测试断言修复 + 批量执行数据模型 + 结果展示专业化(单条 Postman-like + 批量层次化 + cURL + 趋势仪表板)
> 不在范围: UI 测试修复、压测 IPC 重构、套件变量流转、Bug 联动、国际化(均另有 spec)

---

## 一、背景与目标

### 1.1 现状问题
- `ApiTestCase` / `ApiAutoTestSuite` 两套 API 测试模型并行;断言引擎 `unified_assertions.py` 已统一 11 种 kind,但 `eq/ne` 严格相等导致"30" 与 30 永远失败
- 高级断言(regex / schema / 变量提取)未完整接入 `views_api_test.py` 单接口执行路径
- 批量执行结果在 `TestResult.test_log`(TextField)JSON-dump,无法分页/按用例展开/趋势统计
- 前端 `TestResultList.vue` 是平铺列表,看不到断言 diff、复制 cURL、趋势图表

### 1.2 本里程碑目标
1. 修复断言类型容错(eq/ne)、补齐高级断言(变量提取)
2. 引入 `TestRun` + `TestRunCaseResult` 两张新表作为批量/层次化结果的标准载体
3. 新增批量执行 endpoint(4 并发可配置)+ 实时 WebSocket 进度 + 可取消
4. 新增 cURL 一键复制、断言 expected/actual diff 展示
5. 趋势仪表板 4 图表(通过率/类型分布/失败原因/响应时间)
6. 历史 `TestResult.test_log` 数据可一键 backfill 到新模型

### 1.3 非目标
- **不**改 `ApiTestCase` / `ApiTestResult` / `TestResult` 任何字段;老接口/老页面 100% 兼容
- **不**修复 UI 测试(子项目 2)
- **不**重写压测(子项目 3)
- **不**改 `ApiAutoTestSuite` 套件内的变量流转(单独 spec)

---

## 二、子项目拆分(本 spec 仅覆盖子项目 1)

| 子项目 | 范围 | spec |
|--------|------|------|
| **1. API 测试** | 断言修复 + 批量数据模型 + cURL + 趋势 | **本文件** |
| 2. UI 测试 | Playwright 启动与守护线程修复、断言补齐 | `2026-06-XX-qa-ui-test-repair-design.md` |
| 3. DevOps 压测 | IPC 重构 + 多业务场景 + 指标落库 | `2026-06-XX-qa-devops-stress-design.md` |
| 4. 结果展示 | 已有子项目 1/2/3 的结果模型基础上重写 `TestResultList.vue` | `2026-06-XX-qa-result-display-design.md` |

> 注:子项目 4 的前端重写会复用本 spec 产出的 `TestRun` / `TestRunCaseResult` API。

---

## 三、数据模型

### 3.1 新增 `TestRun`(`qa_center/models.py`)

```python
class TestRun(models.Model):
    """一次批量执行(父任务)——'10 条接口一次跑完' 的那一次"""
    STATUS = [
        ('pending', '待执行'),
        ('running', '执行中'),
        ('passed',  '全部通过'),
        ('failed',  '有失败'),
        ('error',   '执行异常'),
        ('cancelled','已取消'),
    ]
    TRIGGER = [
        ('manual',    '手动'),
        ('scheduled', '定时'),
        ('cicd',      'CI/CD'),
        ('regression','回归'),
    ]
    TEST_TYPE = [
        ('api',         'API'),
        ('ui',          'UI'),
        ('performance', '性能'),
        ('mixed',       '混合'),
    ]

    project       = FK(Project, related_name='test_runs')
    name          = CharField(max_length=200)            # "订单回归-2026-06-11"
    trigger       = CharField(choices=TRIGGER,    default='manual')
    test_type     = CharField(choices=TEST_TYPE,  default='api')
    status        = CharField(choices=STATUS,     default='pending')

    # 统计(执行过程中增量更新,执行结束后冻结)
    total_count   = IntegerField(default=0)
    passed_count  = IntegerField(default=0)
    failed_count  = IntegerField(default=0)
    error_count   = IntegerField(default=0)
    pass_rate     = DecimalField(max_digits=5, decimal_places=2, default=0)
    duration_ms   = IntegerField(null=True)

    # 入口配置(便于复现)
    config_snapshot = JSONField(default=dict)          # 环境、suite_ids、override 等
    curl_template   = TextField(blank=True)            # 整体运行的"模板"或备注

    triggered_by = FK(User, null=True, on_delete=SET_NULL,
                      related_name='triggered_test_runs')
    started_at   = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
    created_at   = DateTimeField(auto_now_add=True)
    summary      = JSONField(default=dict)             # {"slowest_case":..., "top_error":...}

    class Meta:
        db_table = 'qa_test_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['status']),
        ]
```

### 3.2 新增 `TestRunCaseResult`(`qa_center/models.py`)

```python
class TestRunCaseResult(models.Model):
    """批量执行里单条用例的结果——10 条里第 N 条"""
    STATUS = [
        ('pending', '待执行'),
        ('running', '执行中'),
        ('passed',  '通过'),
        ('failed',  '失败'),
        ('error',   '异常'),
        ('skipped', '跳过'),
    ]
    CASE_TYPE = [
        ('api',         'API'),
        ('ui',          'UI'),
        ('performance', '性能'),
    ]

    test_run    = FK(TestRun, on_delete=CASCADE, related_name='case_results')
    case_type   = CharField(choices=CASE_TYPE, default='api')
    sequence    = IntegerField()                       # 1..N,执行顺序

    # 多态关联(本轮只填 api_test_case)
    api_test_case = FK('ApiTestCase', null=True, on_delete=SET_NULL,
                       related_name='run_case_results')
    ui_test_case  = FK('UiTestCase',  null=True, on_delete=SET_NULL,
                       related_name='run_case_results')

    status         = CharField(choices=STATUS, default='pending')
    duration_ms    = IntegerField(null=True)
    status_code    = IntegerField(null=True)
    response_body  = TextField(blank=True)
    response_headers = JSONField(default=dict)
    assertion_results = JSONField(default=list)        # List[AssertionResult.to_dict()]
    request_snapshot  = JSONField(default=dict)        # 实际发送的 method/url/headers/body
    curl          = TextField(blank=True)              # 一键复制的 cURL
    error_message = TextField(blank=True)

    # 反向追溯到原模型的双写记录
    legacy_api_result_id   = IntegerField(null=True)   # ApiTestResult.id
    legacy_test_result_id  = IntegerField(null=True)   # TestResult.id

    started_at   = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)

    class Meta:
        db_table = 'qa_test_run_case_results'
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(fields=['test_run', 'sequence'],
                                    name='uniq_test_run_sequence'),
        ]
        indexes = [
            models.Index(fields=['test_run', 'status']),
            models.Index(fields=['api_test_case', '-completed_at']),
        ]
```

### 3.3 `ApiTestCase` 追加字段(无破坏性)

```python
response_extractions = JSONField(default=list, blank=True)
# Schema: [{'json_path': '$.token', 'var_name': 'auth_token', 'default': None}]
```

### 3.4 数据迁移

- **Schema migration**: `0015_add_test_run.py` 建表 + 索引
- **Data migration**(`backfill_test_runs`): 解析 `TestResult.test_log`(JSON),按 `summary.total > 1` 判定批量,生成 `TestRun` + `TestRunCaseResult`
  - 命令: `python manage.py backfill_test_runs --days 90 --batch 100`
  - `--days 90` 默认;`--dry-run` 输出预估不写
  - 不删老数据,只追加新数据
  - backfill 失败的记录写日志,不抛错

### 3.5 关键不变量
- `TestRun.status` 与 `passed/failed/error_count` 由执行器在每条 case 完成时通过 `F()` 表达式原子更新
- 取消时:`pending → skipped`、`running → 跑完后 TestRun 状态变 cancelled`
- `(test_run, sequence)` 联合唯一:同一批量内 sequence 不可重复
- 断言结果 schema 遵循 `AssertionResult.to_dict()` 统一形状

---

## 四、断言引擎修复(`qa_center/unified_assertions.py`)

### 4.1 类型容错的 `eq`/`ne`

`OPERATORS['eq']` 替换为 `_smart_eq(a, b)`,顺序:

1. `a == b` 严格相等优先
2. 数字/字符串互通:`30 == "30"`、`30.0 == "30"`(两侧 `float()` 后相等)
3. **bool 永远不与 int 互通**:`True != 1`(避免 isTrue 错配)
4. 字符串化的 JSON 自动 parse 后比较
5. 其它情况返回 False

`_smart_ne(a, b)` = `not _smart_eq(a, b)`。其它操作符(`gt/lt/gte/lte/contains/...`)保持原 `_safe_cmp` 行为。

### 4.2 断言评估器增强

- `regex_match`:`target` 为 None 时返回 `passed=False` + 文案 `"目标为空,无法匹配正则"`,不再只说"目标为空"
- `schema_validate`:
  - `requirements.txt` 显式锁 `jsonschema>=4.0`
  - 缺失依赖时返回清晰提示:`"未安装 jsonschema 依赖, 请运行: pip install jsonschema>=4.0"`
- 所有 kind 失败时附 `expected_rendered` / `actual_rendered` 字符串字段,JSON 序列化时人类可读

### 4.3 变量提取接入单接口

- `ApiTestCase.response_extractions` 字段
- `views_api_test.py::run` 写 `TestRunCaseResult` 前调用 `extractors.extract(response_json, response_extractions)`
- 提取结果存进 `TestRunCaseResult.assertion_results` 末尾的 `extractions` 块:
  ```json
  {"extractions": [{"var_name": "auth_token", "value": "abc123", "source": "$.token"}]}
  ```
- 套件(`ApiAutoTestCase.extract_response`)路径同步对齐(下个里程碑本轮不实现完整流转,先支持结构)

### 4.4 兼容性
- 字段全部追加,老数据兼容
- **行为变化**:`eq/ne` 更宽容 → 已有的"明明相等却失败"用例会从 failed 变 passed → release notes 标注

---

## 五、视图层(`qa_center/views_api_test.py` + `views_test_run.py` 新增)

### 5.1 现有入口处理

#### `POST /api/qa/api-cases/{id}/run/` (单条)
- 逻辑保持(读用例 → 解析环境 → Client 调 → 断言 → 写 `ApiTestResult`)
- **新增**: 同步创建 `TestRun`(单条也算"一次运行",`source='single'`)+ `TestRunCaseResult`
- 响应体增加 `run_id` / `case_result_id` / `curl` 字段(前端不取无害)

#### `POST /api/qa/api-cases/run-batch/` (新增)
- Request: `{case_ids: [..], name?, environment_id?, max_workers?}`
- 默认 `max_workers=4`,可通过请求覆盖
- 立刻创建 `TestRun(status='running', total_count=len(case_ids))`,返回 `{run_id}`
- 内部 `concurrent.futures.ThreadPoolExecutor(max_workers=4)` 并发执行
- 每条完成后:写 `ApiTestResult` + `TestRunCaseResult` + 用 `F()` 原子更新 `TestRun` 计数
- 全部完成:`status=passed|failed|error`、`completed_at=now()`、`duration_ms=...`
- WebSocket 推 `test_run_{run_id}` 群:`{type: 'case_done', sequence, status, passed_count, failed_count}`

#### `POST /api/qa/api-cases/run-suite/{suite_id}/` (新增)
- 读 `ApiAutoTestSuite` 内的 cases 列表,转调 batch
- 套件自身的 extracts 流转留到下个 spec(本轮 stub)

### 5.2 新增端点(`qa_center/views_test_run.py`)

```
GET  /api/qa/runs/                       分页列表
                                       filter: project, status, test_type, days
GET  /api/qa/runs/{id}/                  详情(含 summary、进度)
GET  /api/qa/runs/{id}/cases/            逐条结果
                                       filter: status, sequence
                                       支持 ?page=&page_size=
GET  /api/qa/runs/{id}/cases/{cid}/      单条详情
                                       (完整断言列表 + curl + diff)
POST /api/qa/runs/{id}/cancel/           running → cancelled
                                       (仅 pending → skipped,running 跑完)
POST /api/qa/runs/{id}/rerun/            用 config_snapshot 重新执行
```

权限: `IsAuthenticated` + 项目成员校验(沿用 `qa:api:list` 权限)

### 5.3 cURL 工具(`qa_center/utils/curl.py` 新增)

```python
def to_curl(method: str, url: str, headers: dict, body, content_type: str = 'application/json') -> str:
    """生成可粘贴到 shell 的 cURL 命令"""
    parts = [f"curl -X {method.upper()}"]
    for k, v in (headers or {}).items():
        if k.lower() in ('cookie', 'host', 'content-length'):
            continue
        parts.append(f"  -H '{k}: {v}'")
    if body is not None and method.upper() != 'GET':
        if content_type == 'application/json':
            parts.append("  -H 'Content-Type: application/json'")
            parts.append(f"  -d '{json.dumps(body, ensure_ascii=False)}'")
        elif content_type == 'application/x-www-form-urlencoded':
            parts.append(f"  -d '{urllib.parse.urlencode(body)}'")
        elif content_type == 'multipart/form-data':
            for k, v in (body or {}).items():
                parts.append(f"  -F '{k}={v}'")
    parts.append(f"  '{url}'")
    return " \\\n".join(parts)
```

- 写入 `TestRunCaseResult.curl`(执行结束时填一次)
- 跳过的 `cookie` 头(每次执行由 Django Test Client 注入)
- `Content-Length` 由 curl 自动算

### 5.4 WebSocket(`qa_center/consumers.py` 扩展)

- 群名 `test_run_{run_id}`
- 消息 schema:
  ```json
  {"type": "case_done", "sequence": 3, "status": "passed",
   "passed_count": 5, "failed_count": 1, "error_count": 0, "total": 10}
  {"type": "run_finished", "status": "failed", "duration_ms": 1240}
  ```
- 复用现有 `QAConsumer` 风格

### 5.5 取消语义
- `cancel` 后 `pending` 立即变 `skipped`
- `running` 继续跑完(Django Test Client 同步调用,中断代价高)
- 跑完所有 in-flight 后,`TestRun.status='cancelled'`

---

## 六、前端(`frontend/src/views/qa/`)

### 6.1 新增页面

| 文件 | 路径 | 说明 |
|------|------|------|
| `ApiCaseRunDetail.vue` | `/qa/api-cases/:id/runs/:caseResultId` | 单条执行详情(Postman-like) |
| `TestRunList.vue`       | `/qa/test-runs` | 批量执行历史 |
| `TestRunDetail.vue`     | `/qa/test-runs/:id` | 批量执行详情 + 进度 |
| `QaTrendsDashboard.vue` | `/qa` 入口(挂到 QA.vue 顶部) | 4 图表 |

### 6.2 单条详情页布局

```
┌─────────────────────────────────────────────────────────┐
│ ← 返回   登录接口测试  POST /api/auth/login    [▶ 重跑] │
├─────────────────────────────────────────────────────────┤
│ [Request]  [Response]  [Tests(3)]  [cURL]               │
├─────────────────────────────────────────────────────────┤
│  Request                    │  Response                │
│  Method  POST               │  Status  200  ✓          │
│  URL    /api/auth/login     │  Time    124ms           │
│  Headers [+]                │  Size    1.2KB           │
│  Body (JSON editor)         │  Headers [展开 ▾]        │
│                             │  Body (高亮 JSON viewer) │
├─────────────────────────────────────────────────────────┤
│  Tests (3/3 passed)                                    │
│  ✓ status_code == 200                                   │
│  ✓ $.token exists                                       │
│  ✗ $.user.id == "1"   expected 1(str) got 1(int)       │
└─────────────────────────────────────────────────────────┘
```

### 6.3 关键组件

| 组件 | 说明 |
|------|------|
| `RequestPanel.vue`  | 复用现有请求编辑控件(只读模式) |
| `ResponsePanel.vue` | JSON 语法高亮(vue-codemirror) |
| `TestsPanel.vue`    | 断言列表,每条带 ✓/✗ + 折叠式 expected/actual diff(diff-match-patch) |
| `CurlPanel.vue`     | 黑色等宽字体 + `[复制] [下载 .sh]` |
| `RunProgressBar.vue`| 进度条 + 实时统计,WebSocket 订阅 |

### 6.4 批量执行列表页

| 状态:全部▾  类型:API▾  时间:近7天▾ |
| ☑ 订单回归-2026-06-11   ✓ 25/25 通过   API · 手动 · 1240ms · 5分钟前 |
| ☑ 登录全套验证          ✗ 2/10 失败    API · CI/CD · 850ms · 2小时前 |

### 6.5 批量执行详情页

```
┌─────────────────────────────────────────────────────────┐
│ ← 订单回归-2026-06-11          [⏸ 取消] [↻ 重跑]      │
├─────────────────────────────────────────────────────────┤
│ 进度 25/25   ✓ 23 passed   ✗ 2 failed   ⏱ 1240ms      │
│ ████████████████████████████████ 100%                  │
├─────────────────────────────────────────────────────────┤
│ 状态:全部▾  耗时↑↓  名称🔍                              │
│ #  状态   名称              状态码  耗时    操作        │
│ 1  ✓     登录获取token     200    124ms   [详情][cURL] │
│ 3  ✗     创建订单          500    320ms   [详情][cURL] │
└─────────────────────────────────────────────────────────┘
```

点击 [详情] → 复用 `ApiCaseRunDetail.vue`

### 6.6 趋势仪表板 4 图表(ECharts)

1. **通过率趋势**(折线)— 最近 30 天 daily pass_rate
2. **用例类型分布**(饼图)— api/ui/performance 占比
3. **失败原因 Top10**(横向柱状)— 按 `assertion_results[].assertion_type` 聚合
4. **平均响应时间趋势**(折线 + 阈值线)— p50/p95

数据走 `DashboardStatsView`,扩展字段不破坏老调用。

### 6.7 路由共存策略

- `/qa/test-results` 保留(老 `TestResultList.vue`,只显示 `source='single'`)
- `/qa/test-runs` 新增(批量执行历史)
- 老路径前端不重定向,只是导航栏增加"批量执行"入口

### 6.8 依赖(`frontend/package.json`)

```json
{
  "dependencies": {
    "vue-codemirror": "^6.0.0",
    "@codemirror/lang-json": "^6.0.0",
    "diff-match-patch": "^1.0.5"
  }
}
```

---

## 七、API 端点汇总

### 7.1 已有(改写,响应增加 3 个字段)

| Method | URL | 变化 |
|--------|-----|------|
| POST | `/api/qa/api-cases/{id}/run/` | 响应增 `run_id` / `case_result_id` / `curl` |

### 7.2 新增

| Method | URL | 说明 |
|--------|-----|------|
| POST | `/api/qa/api-cases/run-batch/` | 批量执行(同步返回 run_id) |
| POST | `/api/qa/api-cases/run-suite/{suite_id}/` | 套件执行 |
| GET  | `/api/qa/runs/` | 列表 |
| GET  | `/api/qa/runs/{id}/` | 详情 |
| GET  | `/api/qa/runs/{id}/cases/` | 逐条 |
| GET  | `/api/qa/runs/{id}/cases/{cid}/` | 单条 |
| POST | `/api/qa/runs/{id}/cancel/` | 取消 |
| POST | `/api/qa/runs/{id}/rerun/` | 重跑 |
| WS   | `/ws/qa/test-run/{run_id}/` | 实时进度 |

---

## 八、测试覆盖

### 8.1 后端(`backend/tests/`)

| 文件 | 覆盖点 |
|------|--------|
| `test_test_run_model.py` (新)   | `TestRun` 计数原子更新、`pass_rate` 计算、cancel 语义 |
| `test_unified_assertions.py` (扩)| `_smart_eq` 数字/字符串互通、bool 不互通、None 容错;regex_match None target;schema_validate 缺依赖提示 |
| `test_api_case_run.py` (新)     | 单条运行双写 `TestRun` + `TestRunCaseResult`;curl 正确;curl 不含 cookie |
| `test_batch_run.py` (新)        | 批量 4 并发、`F()` 计数正确、cancel 后 pending→skipped |
| `test_test_run_endpoints.py` (新)| 列表分页/筛选、详情摘要、单条结果 |
| `test_curl.py` (新)             | GET/POST/PUT/PATCH/DELETE、JSON/form/multipart、headers 转义 |
| `test_backfill.py` (新)         | 从老 `TestResult.test_log` 解析批量记录 |
| `test_qa_center.py` (扩)        | 现有 9 个用例继续过;扩展 devops/stats 验证新字段 |

### 8.2 前端(`frontend/tests/`)

| 文件 | 覆盖点 |
|------|--------|
| `TestRunList.spec.ts`       | 列表渲染、筛选、跳详情 |
| `TestRunDetail.spec.ts`     | 进度条、状态过滤、复制 curl |
| `ApiCaseRunDetail.spec.ts`  | 4 个 Tab 切换、断言 ✓/✗ 渲染、复制 curl |
| `toCurl.spec.ts`            | 工具函数单测 |

### 8.3 端到端冒烟

- `e2e/test_api_batch_flow.py`(可选用 playwright,新 spec 再开)

---

## 九、迁移命令

```bash
# 1. 装新依赖
pip install jsonschema>=4.0

# 2. 迁移
python manage.py migrate qa_center

# 3. 历史回填(可选)
python manage.py backfill_test_runs --days 90 --batch 100 --dry-run   # 预览
python manage.py backfill_test_runs --days 90 --batch 100             # 实际跑

# 4. 前端装包
cd frontend && npm install vue-codemirror @codemirror/lang-json diff-match-patch
```

---

## 十、验收清单

- [ ] 创建一个 5 条接口的批量任务,4 并发,看到实时进度
- [ ] 中途点取消,pending 用例变 skipped,running 跑完后 TestRun 状态变 cancelled
- [ ] 点进任一失败用例详情,看到 ✓/✗ 列表、expected/actual diff、curl 一键复制可粘贴到 shell 复现
- [ ] 老 `/api/qa/api-cases/{id}/run/` 响应多了 `run_id` / `case_result_id` / `curl` 三个字段,前端不取不报错
- [ ] 老 `/qa/test-results` 路径不变,新数据不再写入(只有 `source='single'` 的还在)
- [ ] `python manage.py backfill_test_runs --days 30` 跑完后,`/qa/test-runs` 出现历史批量任务的镜像
- [ ] 断言类型容错验证:对响应字段 `30` 与断言 `eq "30"` 的用例,以前 failed 现在 passed
- [ ] 仪表板 `/qa` 显示 4 个图表;通过率/类型分布/失败原因 Top10/响应时间
- [ ] 所有后端测试通过,前端 smoke 测试通过
- [ ] 老 `test_qa_center.py` 9 个用例零回归

---

## 十一、不在本 spec 范围(子项目 2/3/4 后续 spec)

- 子项目 2:UI 测试 Playwright 启动与守护线程修复
- 子项目 3:压测 IPC 重构 + 多业务场景 + 指标落库
- 子项目 4:结果展示最终重写(本 spec 已铺好数据模型,子项目 4 主要做 UI 收敛)
- `ApiAutoTestSuite` 套件内的变量流转(独立 spec)
- Bug 联动(独立 spec)
- 国际化(独立 spec)
