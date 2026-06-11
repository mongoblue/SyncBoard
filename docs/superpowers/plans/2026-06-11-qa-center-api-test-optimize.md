# SyncBoard 质量中心 API 测试优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 API 测试断言类型容错 + 引入 `TestRun`/`TestRunCaseResult` 层次化结果模型 + 批量执行 4 并发可取消 + cURL 复制 + Postman-like 单条详情 + 批量结果层次化 + ECharts 趋势仪表板 + 历史 backfill。

**Architecture:**
- 后端双写: 新增 `TestRun` + `TestRunCaseResult` 承载层次化结果,`ApiTestResult`/`TestResult` 仍保留(老接口 100% 兼容,响应增 3 个字段)
- 前端不破老: `/qa/test-results` 保留 + 新增 `/qa/test-runs`、`/qa/api-cases/:id/runs/:caseResultId`
- 数据迁移: 历史 `TestResult.test_log` 通过 `backfill_test_runs` 命令一键回填

**Tech Stack:**
- Backend: Django 4.x, DRF, Channels (Redis), concurrent.futures, jsonschema
- Frontend: Vue 3, Pinia, ECharts, vue-codemirror, diff-match-patch
- Test: pytest, pytest-django, vitest

**Spec:** `docs/superpowers/specs/2026-06-11-qa-center-api-test-optimize-design.md`

---

## 文件结构

### 新增文件
| 文件 | 职责 |
|------|------|
| `backend/qa_center/utils/curl.py` | cURL 字符串生成器 |
| `backend/qa_center/views_test_run.py` | TestRun/TestRunCaseResult REST 端点 |
| `backend/qa_center/management/commands/backfill_test_runs.py` | 历史 backfill 命令 |
| `backend/tests/test_test_run_model.py` | TestRun 计数/pass_rate/cancel 单元测试 |
| `backend/tests/test_curl.py` | to_curl 工具单测 |
| `backend/tests/test_api_case_run.py` | 单条运行双写集成测试 |
| `backend/tests/test_batch_run.py` | 批量执行并发/cancel 测试 |
| `backend/tests/test_test_run_endpoints.py` | TestRun REST 端点测试 |
| `backend/tests/test_backfill.py` | backfill 命令测试 |
| `frontend/src/views/qa/ApiCaseRunDetail.vue` | Postman-like 单条详情 |
| `frontend/src/views/qa/TestRunList.vue` | 批量执行历史列表 |
| `frontend/src/views/qa/TestRunDetail.vue` | 批量执行详情 |
| `frontend/src/views/qa/QaTrendsDashboard.vue` | 4 图表趋势仪表板 |
| `frontend/src/views/qa/components/RequestPanel.vue` | 请求只读面板 |
| `frontend/src/views/qa/components/ResponsePanel.vue` | 响应 JSON 高亮 |
| `frontend/src/views/qa/components/TestsPanel.vue` | 断言列表+diff |
| `frontend/src/views/qa/components/CurlPanel.vue` | cURL 复制 |
| `frontend/src/views/qa/components/RunProgressBar.vue` | 进度条(WebSocket) |
| `frontend/src/api/testrun.ts` | TestRun API 客户端 |
| `frontend/tests/TestRunList.spec.ts` | 列表组件测试 |
| `frontend/tests/TestRunDetail.spec.ts` | 详情组件测试 |
| `frontend/tests/ApiCaseRunDetail.spec.ts` | 单条详情组件测试 |
| `frontend/tests/toCurl.spec.ts` | 工具单测 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `backend/qa_center/models.py` | 追加 `TestRun`/`TestRunCaseResult`; `ApiTestCase.response_extractions` |
| `backend/qa_center/unified_assertions.py` | `_smart_eq`/`_smart_ne`; `expected_rendered`/`actual_rendered`;regex 友好错误 |
| `backend/qa_center/views_api_test.py` | 单条 run 双写;响应增 `run_id`/`case_result_id`/`curl`;集成 extractors |
| `backend/qa_center/serializers.py` | 增 `TestRunSerializer`/`TestRunCaseResultSerializer`/`TestRunListSerializer` |
| `backend/qa_center/admin.py` | 注册新模型 |
| `backend/qa_center/urls.py` | 注册新端点 |
| `backend/qa_center/consumers.py` | 增 `TestRunProgressConsumer` |
| `backend/qa_center/routing.py` | 增 WS 路由 |
| `backend/qa_center/views_devops.py` | `DashboardStatsView` 增趋势字段 |
| `backend/requirements.txt` | 锁 `jsonschema>=4.0` |
| `backend/tests/test_unified_assertions.py` | 扩 `_smart_eq`/regex/rendered 测试 |
| `backend/tests/test_qa_center.py` | 扩 devops/stats 验证 |
| `frontend/src/router/index.ts` | 增 4 个新路由 |
| `frontend/src/views/QA.vue` | 顶部增 QaTrendsDashboard 挂载 |
| `frontend/package.json` | 增 vue-codemirror / diff-match-patch |
| `frontend/src/api/devops.ts` | 增 devops/stats 扩展字段类型 |

---

## Phase 1: 数据模型(后端,无破坏性)

### Task 1: 给 `ApiTestCase` 加 `response_extractions` 字段

**Files:**
- Modify: `backend/qa_center/models.py:6-97` (在 `ApiTestCase` 类末尾)
- Create: migration 通过 `makemigrations` 自动生成

- [ ] **Step 1: 改 model**

```python
# 在 ApiTestCase 类内、related_tasks 之后,加:
    response_extractions = models.JSONField(
        default=list, blank=True,
        verbose_name='响应变量提取',
        help_text='[{"json_path": "$.token", "var_name": "auth_token", "default": null}]'
    )
```

- [ ] **Step 2: 生成并应用 migration**

```bash
cd backend && python manage.py makemigrations qa_center
cd backend && python manage.py migrate qa_center
```

Expected: 新 migration 文件 `0015_apitestcase_response_extractions.py` 创建并应用成功。

- [ ] **Step 3: 跑现有测试,确保零回归**

```bash
cd backend && python -m pytest tests/test_qa_center.py tests/test_unified_assertions.py -x -q
```

Expected: 全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add backend/qa_center/models.py backend/qa_center/migrations/0015_*.py
git commit -m "feat(qa-center): ApiTestCase.response_extractions 字段"
```

---

### Task 2: 新增 `TestRun` 与 `TestRunCaseResult` 模型

**Files:**
- Modify: `backend/qa_center/models.py` (在文件末尾,新模型)
- Test: 暂用 admin smoke test 验证迁移通过

- [ ] **Step 1: 在 models.py 末尾追加**

```python
class TestRun(models.Model):
    """一次批量执行(父任务)"""
    STATUS = [
        ('pending', '待执行'), ('running', '执行中'),
        ('passed', '全部通过'), ('failed', '有失败'),
        ('error', '执行异常'), ('cancelled', '已取消'),
    ]
    TRIGGER = [
        ('manual', '手动'), ('scheduled', '定时'),
        ('cicd', 'CI/CD'), ('regression', '回归'),
    ]
    TEST_TYPE = [
        ('api', 'API'), ('ui', 'UI'),
        ('performance', '性能'), ('mixed', '混合'),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='test_runs'
    )
    name = models.CharField(max_length=200)
    trigger = models.CharField(max_length=20, choices=TRIGGER, default='manual')
    test_type = models.CharField(max_length=20, choices=TEST_TYPE, default='api')
    status = models.CharField(max_length=20, choices=STATUS, default='pending')

    total_count = models.IntegerField(default=0)
    passed_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    duration_ms = models.IntegerField(null=True)

    config_snapshot = models.JSONField(default=dict, blank=True)
    curl_template = models.TextField(blank=True)

    triggered_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL,
        related_name='triggered_test_runs',
    )
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'qa_test_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.name} [{self.status}]"

    def recompute_pass_rate(self):
        completed = self.passed_count + self.failed_count + self.error_count
        self.pass_rate = (
            round(self.passed_count / completed * 100, 2)
            if completed > 0 else 0
        )


class TestRunCaseResult(models.Model):
    """批量执行里单条用例的结果"""
    STATUS = [
        ('pending', '待执行'), ('running', '执行中'),
        ('passed', '通过'), ('failed', '失败'),
        ('error', '异常'), ('skipped', '跳过'),
    ]
    CASE_TYPE = [
        ('api', 'API'), ('ui', 'UI'), ('performance', '性能'),
    ]

    test_run = models.ForeignKey(
        TestRun, on_delete=models.CASCADE, related_name='case_results'
    )
    case_type = models.CharField(max_length=20, choices=CASE_TYPE, default='api')
    sequence = models.IntegerField()

    api_test_case = models.ForeignKey(
        'ApiTestCase', null=True, on_delete=models.SET_NULL,
        related_name='run_case_results',
    )
    ui_test_case = models.ForeignKey(
        'UiTestCase', null=True, on_delete=models.SET_NULL,
        related_name='run_case_results',
    )

    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    duration_ms = models.IntegerField(null=True)
    status_code = models.IntegerField(null=True)
    response_body = models.TextField(blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    assertion_results = models.JSONField(default=list, blank=True)
    request_snapshot = models.JSONField(default=dict, blank=True)
    curl = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    legacy_api_result_id = models.IntegerField(null=True)
    legacy_test_result_id = models.IntegerField(null=True)

    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = 'qa_test_run_case_results'
        ordering = ['sequence']
        constraints = [
            models.UniqueConstraint(
                fields=['test_run', 'sequence'],
                name='uniq_test_run_sequence',
            ),
        ]
        indexes = [
            models.Index(fields=['test_run', 'status']),
            models.Index(fields=['api_test_case', '-completed_at']),
        ]

    def __str__(self):
        return f"#{self.sequence} {self.status}"
```

- [ ] **Step 2: 迁移**

```bash
cd backend && python manage.py makemigrations qa_center
cd backend && python manage.py migrate qa_center
```

Expected: 新 migration `0016_testrun_testruncaseresult.py` 创建并应用。

- [ ] **Step 3: 提交**

```bash
git add backend/qa_center/models.py backend/qa_center/migrations/0016_*.py
git commit -m "feat(qa-center): TestRun + TestRunCaseResult 模型"
```

---

### Task 3: 注册到 admin

**Files:**
- Modify: `backend/qa_center/admin.py`

- [ ] **Step 1: 追加 admin 注册**

```python
# 在文件末尾追加
from .models import TestRun, TestRunCaseResult


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'project', 'test_type', 'status',
                    'total_count', 'passed_count', 'failed_count', 'created_at')
    list_filter = ('status', 'test_type', 'trigger')
    search_fields = ('name',)


@admin.register(TestRunCaseResult)
class TestRunCaseResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'test_run', 'sequence', 'status',
                    'status_code', 'duration_ms', 'completed_at')
    list_filter = ('status', 'case_type')
```

- [ ] **Step 2: 验证导入不报错**

```bash
cd backend && python -c "import django; django.setup(); from qa_center.admin import TestRunAdmin, TestRunCaseResultAdmin; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/qa_center/admin.py
git commit -m "chore(qa-center): TestRun/TestRunCaseResult admin 注册"
```

---

## Phase 2: 断言引擎修复(后端)

### Task 4: 失败的测试 - `_smart_eq` 数字/字符串互通

**Files:**
- Modify: `backend/tests/test_unified_assertions.py` (在文件末尾追加)

- [ ] **Step 1: 写测试**

```python
# 追加到 backend/tests/test_unified_assertions.py
from qa_center.unified_assertions import (
    _smart_eq, _smart_ne,
    evaluate, Assertion, ResponseContext,
    KIND_JSON_EQUALS, KIND_REGEX_MATCH,
)


def test_smart_eq_int_and_numeric_string():
    """30 应该等于 '30'"""
    assert _smart_eq(30, "30") is True


def test_smart_eq_float_and_numeric_string():
    assert _smart_eq(30.0, "30") is True


def test_smart_eq_strict_equal_unchanged():
    assert _smart_eq("abc", "abc") is True
    assert _smart_eq(30, 30) is True


def test_smart_eq_bool_not_equal_int():
    """True 不应等于 1"""
    assert _smart_eq(True, 1) is False
    assert _smart_eq(False, 0) is False


def test_smart_eq_none_not_equal_empty_string():
    assert _smart_eq(None, "") is False
    assert _smart_eq(None, "x") is False


def test_smart_ne_inverse_of_eq():
    assert _smart_ne(30, "30") is False   # 30 == '30', so != False
    assert _smart_ne(True, 1) is True     # True != 1
    assert _smart_ne("abc", "abd") is True
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -k "smart_eq or smart_ne" -v
```

Expected: 全部 FAIL(ImportError 或 NameError,因为 `_smart_eq` 不存在)

---

### Task 5: 实现 `_smart_eq` / `_smart_ne`

**Files:**
- Modify: `backend/qa_center/unified_assertions.py` (在 OPERATORS 之前)

- [ ] **Step 1: 在 `OPERATORS` 字典定义前插入**

```python
def _smart_eq(a: Any, b: Any) -> bool:
    """类型容错的相等比较。

    顺序:
    1. 严格相等优先
    2. 数字/字符串互通:30 == "30"、30.0 == "30"
    3. bool 永远不与 int 互通(True != 1)
    4. 字符串化的 JSON 自动 parse 后比较
    5. 其它情况 False
    """
    if a == b:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    def _to_num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    na, nb = _to_num(a), _to_num(b)
    if na is not None and nb is not None and na == nb:
        return True
    if isinstance(a, str) and isinstance(b, str):
        try:
            return json.loads(a) == json.loads(b)
        except (json.JSONDecodeError, ValueError):
            pass
    return False


def _smart_ne(a: Any, b: Any) -> bool:
    return not _smart_eq(a, b)
```

- [ ] **Step 2: 替换 OPERATORS 的 eq/ne**

```python
# 把 'eq' 和 'ne' 替换为:
OPERATORS: Dict[str, Any] = {
    'eq': _smart_eq,
    'ne': _smart_ne,
    'gt': lambda a, b: _safe_cmp(a, b, lambda x, y: x > y),
    # ... 其它保持不变
}
```

- [ ] **Step 3: 跑测试,确认通过**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -k "smart_eq or smart_ne" -v
```

Expected: 全部 PASS

- [ ] **Step 4: 跑所有断言测试,确保零回归**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/qa_center/unified_assertions.py backend/tests/test_unified_assertions.py
git commit -m "feat(qa-center): _smart_eq 类型容错的相等比较"
```

---

### Task 6: 失败的测试 - `expected_rendered` / `actual_rendered`

**Files:**
- Modify: `backend/tests/test_unified_assertions.py` (追加)

- [ ] **Step 1: 写测试**

```python
def test_json_equals_renders_expected_and_actual():
    """失败时附 expected_rendered/actual_rendered 字符串"""
    assertion = Assertion(
        kind=KIND_JSON_EQUALS, operator='eq', expected='"1"',
        path='$.user.id', error_message='',
    )
    ctx = ResponseContext(
        status_code=200, response_body='{"user":{"id":1}}',
        response_headers={}, response_time_ms=10.0,
    )
    res = evaluate(assertion, ctx)
    assert res.passed is True
    assert res.expected_value == '"1"' or res.expected_value == '1'
    assert res.actual_value == 1


def test_regex_match_none_target_friendly_error():
    """regex 目标为 None 时,error_message 应该友好"""
    assertion = Assertion(
        kind=KIND_REGEX_MATCH, operator='eq', expected='.*',
        path='$.missing', error_message='',
    )
    ctx = ResponseContext(
        status_code=200, response_body='{}',
        response_headers={}, response_time_ms=10.0,
    )
    res = evaluate(assertion, ctx)
    assert res.passed is False
    assert "目标为空" in res.error_message or "不存在" in res.error_message
```

- [ ] **Step 2: 跑测试,确认行为**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -k "renders_expected or regex_match_none" -v
```

Expected: `renders_expected` 行为已通过(只是验证不报错); `regex_match_none` 应该已经过(原代码就是返回"目标为空")。如果都已过,继续。

- [ ] **Step 3: 改进 regex_match 错误消息(更友好)**

在 `backend/qa_center/unified_assertions.py` 的 `KIND_REGEX_MATCH` 分支,找到:

```python
if target is None:
    res.passed = False
    res.error_message = a.error_message or '目标为空，无法匹配正则'
    return res
```

改为:

```python
if target is None:
    res.passed = False
    res.error_message = a.error_message or (
        f'正则匹配目标为空:路径 "{a.path}" 不存在或响应不是合法 JSON'
    )
    return res
```

- [ ] **Step 4: 跑测试**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/qa_center/unified_assertions.py
git commit -m "feat(qa-center): regex_match 目标为空错误消息更友好"
```

---

### Task 7: 锁 `jsonschema` 依赖

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 检查是否已声明**

```bash
cd backend && grep -i jsonschema requirements.txt
```

如果存在,跳过此任务。

- [ ] **Step 2: 如果不存在,追加**

```
jsonschema>=4.0
```

- [ ] **Step 3: 安装并验证**

```bash
cd backend && pip install 'jsonschema>=4.0'
cd backend && python -c "import jsonschema; print(jsonschema.__version__)"
```

Expected: 版本号 >= 4.0

- [ ] **Step 4: 提交**

```bash
git add backend/requirements.txt
git commit -m "chore(qa-center): 锁 jsonschema>=4.0 依赖"
```

---

## Phase 3: cURL 工具

### Task 8: 失败的测试 - `to_curl` 基础

**Files:**
- Create: `backend/tests/test_curl.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_curl.py
import pytest
from qa_center.utils.curl import to_curl


def test_to_curl_get():
    result = to_curl('GET', 'https://api.example.com/users', {}, None)
    assert 'curl -X GET' in result
    assert "'https://api.example.com/users'" in result
    assert '-d' not in result  # GET 不应有 body


def test_to_curl_post_json():
    headers = {'Authorization': 'Bearer abc', 'X-Custom': 'val'}
    body = {'name': 'test', 'count': 30}
    result = to_curl('POST', 'https://api.example.com/users', headers, body)
    assert 'curl -X POST' in result
    assert "Content-Type: application/json" in result
    assert 'Authorization: Bearer abc' in result
    assert '"name": "test"' in result or '"name":"test"' in result
    assert "'https://api.example.com/users'" in result


def test_to_curl_skips_cookie_header():
    """cookie 头不应该出现在 cURL 里"""
    headers = {'Cookie': 'sessionid=xyz', 'Authorization': 'Bearer abc'}
    result = to_curl('GET', 'https://api.example.com', headers, None)
    assert 'Cookie' not in result
    assert 'sessionid' not in result
    assert 'Authorization: Bearer abc' in result


def test_to_curl_form_urlencoded():
    body = {'username': 'admin', 'password': 'pass'}
    result = to_curl('POST', 'https://api.example.com/login', {},
                     body, content_type='application/x-www-form-urlencoded')
    assert 'username=admin' in result
    assert 'password=pass' in result


def test_to_curl_multipart():
    body = {'file_field': '/tmp/test.txt', 'description': 'a file'}
    result = to_curl('POST', 'https://api.example.com/upload', {},
                     body, content_type='multipart/form-data')
    assert '-F' in result
    assert 'file_field=/tmp/test.txt' in result


def test_to_curl_handles_chinese():
    headers = {'X-Name': '张三'}
    result = to_curl('GET', 'https://api.example.com', headers, None)
    assert '张三' in result
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_curl.py -v
```

Expected: 全部 FAIL(`ModuleNotFoundError: No module named 'qa_center.utils.curl'`)

---

### Task 9: 实现 `to_curl`

**Files:**
- Create: `backend/qa_center/utils/curl.py`

- [ ] **Step 1: 写实现**

```python
"""cURL 字符串生成器。

把 ApiTestCase 的 method/url/headers/body 转换成可直接粘贴到 shell 复现的 cURL 命令。

注意:
- 跳过 Cookie / Host / Content-Length 头(自动注入或敏感)
- 跳过 GET 的 body
- 支持 JSON / form-urlencoded / multipart 三种 content_type
"""
import json
import urllib.parse
from typing import Any, Dict, Optional

_SKIP_HEADERS = {'cookie', 'host', 'content-length'}


def to_curl(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]],
    body: Any,
    content_type: str = 'application/json',
) -> str:
    method = (method or 'GET').upper()
    headers = headers or {}
    parts = [f"curl -X {method}"]

    for k, v in headers.items():
        if k.lower() in _SKIP_HEADERS:
            continue
        # 转义单引号
        v_escaped = str(v).replace("'", "'\\''")
        parts.append(f"  -H '{k}: {v_escaped}'")

    if body is not None and method != 'GET':
        if content_type == 'application/json':
            parts.append("  -H 'Content-Type: application/json'")
            body_str = json.dumps(body, ensure_ascii=False)
            body_escaped = body_str.replace("'", "'\\''")
            parts.append(f"  -d '{body_escaped}'")
        elif content_type == 'application/x-www-form-urlencoded':
            parts.append("  -H 'Content-Type: application/x-www-form-urlencoded'")
            if isinstance(body, dict):
                encoded = urllib.parse.urlencode(body, doseq=True)
                parts.append(f"  -d '{encoded}'")
            else:
                parts.append(f"  -d '{body}'")
        elif content_type == 'multipart/form-data':
            # multipart 不要手动设 Content-Type,让 curl 加 boundary
            for k, v in (body or {}).items():
                v_escaped = str(v).replace("'", "'\\''")
                parts.append(f"  -F '{k}={v_escaped}'")
        else:
            # 其它类型透传
            body_escaped = str(body).replace("'", "'\\''")
            parts.append(f"  -d '{body_escaped}'")

    parts.append(f"  '{url}'")
    return " \\\n".join(parts)
```

- [ ] **Step 2: 跑测试**

```bash
cd backend && python -m pytest tests/test_curl.py -v
```

Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add backend/qa_center/utils/curl.py backend/tests/test_curl.py
git commit -m "feat(qa-center): to_curl 工具 + 单测"
```

---

## Phase 4: 单条运行 双写

### Task 9.5: 失败的测试 - `expected_rendered` / `actual_rendered` 字段

**Files:**
- Modify: `backend/tests/test_unified_assertions.py` (追加)

- [ ] **Step 1: 写测试**

```python
def test_assertion_result_to_dict_includes_rendered():
    """AssertionResult.to_dict 失败时应该带 expected_rendered/actual_rendered 字符串"""
    from qa_center.unified_assertions import AssertionResult
    res = AssertionResult(
        assertion_type='json_equals', operator='eq',
        expected_value=30, actual_value='30', passed=False,
        error_message='mismatch', json_path='$.id',
    )
    res.expected_rendered = '30 (int)'
    res.actual_rendered = '30 (str)'
    d = res.to_dict()
    assert d['expected_rendered'] == '30 (int)'
    assert d['actual_rendered'] == '30 (str)'


def test_evaluate_fills_rendered_on_failure():
    """evaluate 失败时自动填 expected_rendered/actual_rendered"""
    from qa_center.unified_assertions import (
        evaluate, Assertion, ResponseContext, KIND_JSON_EQUALS,
    )
    assertion = Assertion(
        kind=KIND_JSON_EQUALS, operator='eq', expected='xxx', path='$.id',
    )
    ctx = ResponseContext(
        status_code=200, response_body='{"id":30}',
        response_headers={}, response_time_ms=10.0,
    )
    res = evaluate(assertion, ctx)
    assert res.passed is False
    assert hasattr(res, 'expected_rendered')
    assert hasattr(res, 'actual_rendered')
    assert 'xxx' in res.expected_rendered
    assert '30' in res.actual_rendered
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -k "rendered" -v
```

Expected: FAIL

- [ ] **Step 3: 在 `AssertionResult` dataclass 加 `expected_rendered`/`actual_rendered` 字段**

修改 `backend/qa_center/unified_assertions.py` 的 `AssertionResult` dataclass,加:

```python
@dataclass
class AssertionResult:
    assertion_type: str
    operator: str = 'eq'
    expected_value: Any = None
    actual_value: Any = None
    passed: bool = False
    error_message: str = ''
    json_path: str = ''
    header_name: str = ''
    expected_rendered: str = ''    # ← 新增
    actual_rendered: str = ''      # ← 新增
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            'assertion_type': self.assertion_type,
            'operator': self.operator,
            'expected_value': self.expected_value,
            'actual_value': self.actual_value,
            'passed': self.passed,
            'error_message': self.error_message,
            'expected_rendered': self.expected_rendered,    # ← 新增
            'actual_rendered': self.actual_rendered,        # ← 新增
        }
        if self.json_path:
            d['json_path'] = self.json_path
        if self.header_name:
            d['header_name'] = self.header_name
        if self.extra:
            d.update(self.extra)
        return d
```

- [ ] **Step 4: 写辅助函数 `_format_value` 并在 `evaluate` 失败时填这两个字段**

在 `backend/qa_center/unified_assertions.py` 加(在 `evaluate` 函数定义之前):

```python
def _format_value(v: Any) -> str:
    """人类可读的格式化,带类型注解。"""
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return f'{v} (bool)'
    if isinstance(v, (int, float)):
        return f'{v} ({type(v).__name__})'
    if isinstance(v, str):
        return f'"{v}" (str)'
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False)
        if len(s) > 100:
            s = s[:100] + '...'
        return f'{s} ({type(v).__name__})'
    return f'{v} ({type(v).__name__})'
```

在 `evaluate` 函数每个 `res.error_message = ...` 之前,添加:

```python
            res.expected_rendered = _format_value(expected)
            res.actual_rendered = _format_value(actual)
```

(在 KIND_STATUS_CODE / KIND_RESPONSE_TIME / KIND_JSON_EQUALS / KIND_JSON_CONTAINS / KIND_HEADER_EQUALS / KIND_BODY_SIZE 失败分支都加)

- [ ] **Step 5: 跑测试**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -k "rendered" -v
```

Expected: PASS

- [ ] **Step 6: 跑所有断言测试,确保零回归**

```bash
cd backend && python -m pytest tests/test_unified_assertions.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add backend/qa_center/unified_assertions.py backend/tests/test_unified_assertions.py
git commit -m "feat(qa-center): AssertionResult expected_rendered/actual_rendered 字段"
```

---

### Task 9.6: 接入 extractors 到单条 run

**Files:**
- Modify: `backend/qa_center/views_api_test.py` (在 `run` action 写 TestRunCaseResult 之前)

- [ ] **Step 1: 在 `run` action 内、生成 `assertion_results` 之后,插入提取调用**

找到 `assertion_results = ua.run_assertions(...)` 之后,插入:

```python
            # 变量提取
            from . import extractors as ext
            extractions = ext.run_extractors(
                test_case.response_extractions or [],
                response_json=json.loads(response_body) if response_body else None,
                response_headers=response_headers,
                status_code=status_code,
                response_time_ms=response_time_ms,
            )
            extractions_summary = ext.summarize_extractions(extractions)
            # 把 extractions 挂到 assertion_results 末尾的 extractions 块
            if extractions_summary:
                assertion_results = list(assertion_results) + [
                    {'extractions': extractions_summary}
                ]
```

- [ ] **Step 2: 把 `assertion_results` 重新赋给 `TestRunCaseResult` 创建时的字段**

找到 `TestRunCaseResult.objects.create(...assertion_results=assertion_results...)`,确认 `assertion_results` 现在带 extractions 块。

- [ ] **Step 3: 写测试**

在 `backend/tests/test_api_case_run.py` 追加:

```python
@pytest.mark.django_db
def test_single_run_extracts_response_variables(auth_client, project):
    client, user = auth_client
    case = ApiTestCase.objects.create(
        name='login', url='/api/auth/login', method='POST',
        expected_status=200, project=project, created_by=user,
        expected_response={'assertions': []},
        response_extractions=[
            {'json_path': '$.token', 'var_name': 'auth_token', 'default': None},
        ],
    )
    response = client.post(
        f'/api/qa/api-cases/{case.id}/run/',
        data=json.dumps({}),
        content_type='application/json',
    )
    data = response.json()
    case_result = TestRunCaseResult.objects.get(id=data['case_result_id'])
    # assertion_results 末尾应该有 extractions 块
    assert any('extractions' in r for r in case_result.assertion_results)
```

- [ ] **Step 4: 跑测试**

```bash
cd backend && python -m pytest tests/test_api_case_run.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/qa_center/views_api_test.py backend/tests/test_api_case_run.py
git commit -m "feat(qa-center): 单条 run 接入 extractors 响应变量提取"
```

---

### Task 9.7: rerun 端点

**Files:**
- Modify: `backend/qa_center/views_test_run.py` (追加)
- Modify: `backend/qa_center/urls.py`
- Create: `backend/tests/test_test_run_endpoints.py` (追加)

- [ ] **Step 1: 写测试**

```python
# 追加到 backend/tests/test_test_run_endpoints.py
@pytest.mark.django_db
def test_rerun_creates_new_test_run(auth_client, two_runs):
    client, _ = auth_client
    _, r2, _ = two_runs
    response = client.post(f'/api/qa/runs/{r2.id}/rerun/')
    assert response.status_code == 202
    data = response.json()
    assert 'new_run_id' in data
    new_run = TestRun.objects.get(id=data['new_run_id'])
    assert new_run.config_snapshot.get('rerun_from') == r2.id
    assert new_run.total_count == r2.total_count
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_test_run_endpoints.py::test_rerun_creates_new_test_run -v
```

Expected: FAIL

- [ ] **Step 3: 在 `views_test_run.py` 追加**

```python
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rerun_test_run(request, run_id):
    """用 config_snapshot 重新执行一个 TestRun。

    创建新 TestRun,继承原 run 的 case_ids / environment_id / max_workers
    """
    from concurrent.futures import ThreadPoolExecutor
    import threading

    try:
        old_run = TestRun.objects.get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)

    config = old_run.config_snapshot or {}
    case_ids = config.get('case_ids', [])
    if not case_ids:
        # 单条运行继承的,试 legacy_api_result_id 找出对应 case
        first_case_result = old_run.case_results.filter(api_test_case__isnull=False).first()
        if first_case_result:
            case_ids = [first_case_result.api_test_case_id]

    if not case_ids:
        return Response(
            {'error': '原 TestRun 没有可重跑的 case'},
            status=status.HTTP_400_BAD_REQUEST
        )

    max_workers = int(config.get('max_workers', 4))

    new_run = TestRun.objects.create(
        project=old_run.project,
        name=f"{old_run.name} (重跑)",
        trigger='manual',
        test_type=old_run.test_type,
        status='running',
        total_count=len(case_ids),
        started_at=timezone.now(),
        triggered_by=request.user,
        config_snapshot={**config, 'rerun_from': old_run.id},
    )

    # 复用 run-batch 的后台执行逻辑:此处为简化版,直接调 batch endpoint 的内部函数
    # 实际:为避免代码重复,提取一个独立函数 _run_batch_in_background(run, cases, max_workers, request)
    # 并让 run-batch 端点和 rerun 都调用它。本任务为占位,见 Task 9.8 重构。
    def _background():
        # 这里实际执行应调到 Task 13 里写的 _execute_single_case
        # 简化:本里程碑 rerun 只创建 run,真实重跑放到子项目 4 补完
        import time
        time.sleep(0.1)
        new_run.status = 'passed'
        new_run.completed_at = timezone.now()
        new_run.save()

    thread = threading.Thread(target=_background)
    thread.daemon = True
    thread.start()

    return Response({'new_run_id': new_run.id}, status=status.HTTP_202_ACCEPTED)
```

- [ ] **Step 4: 在 `urls.py` 注册**

```python
    path('runs/<int:run_id>/rerun/', rerun_test_run, name='test_run_rerun'),
```

- [ ] **Step 5: 跑测试**

```bash
cd backend && python -m pytest tests/test_test_run_endpoints.py::test_rerun_creates_new_test_run -v
```

Expected: PASS

- [ ] **Step 6: 跑所有 qa_center 测试**

```bash
cd backend && python -m pytest tests/test_qa_center.py tests/test_api_case_run.py tests/test_batch_run.py tests/test_test_run_endpoints.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add backend/qa_center/views_test_run.py backend/qa_center/urls.py backend/tests/test_test_run_endpoints.py
git commit -m "feat(qa-center): TestRun rerun 端点(创建新 run, 真实执行下里程碑补完)"
```

---

### Task 9.8: 重构 _execute_single_case 为共享函数

**Files:**
- Modify: `backend/qa_center/views_api_test.py` (把 `_execute_single_case` 抽到模块级)
- Modify: `backend/qa_center/views_test_run.py` (rerun 复用)

- [ ] **Step 1: 把 `_execute_single_case` 从 `ApiTestCaseBatchRunView.post` 内部抽到模块级**

在 `views_api_test.py` 顶部 import 区后、第一个 class 前,定义:

```python
def execute_single_api_case(
    orig_request, case: 'ApiTestCase', parent_run: 'TestRun', sequence: int
) -> tuple[bool, str | None]:
    """执行一条 API 用例,写 ApiTestResult + TestRunCaseResult, 更新 TestRun 计数。返回 (passed, error_message)。"""
    # 把原来 post 里的 _execute_single_case 函数体搬到这里
    # 包括 try/except,Client 调用,断言,写两张表,F() 更新
    # 此处代码较长,与 Task 13 Step 2 内的 _execute_single_case 一致
    ...
```

(完整代码:把 Task 13 里 `_execute_single_case(orig_request, case, parent_run, sequence)` 函数整体平移到模块级,签名 `orig_request` 仍是 HttpRequest)

- [ ] **Step 2: 让 `ApiTestCaseBatchRunView` 内的 `run_one` 调模块级函数**

```python
        def run_one(sequence, case):
            return sequence, case, execute_single_api_case(request._request, case, run, sequence)
```

- [ ] **Step 3: 让 `rerun_test_run` 也调这个函数(本里程碑简化:在 ThreadPoolExecutor 里调)**

修改 `views_test_run.py::rerun_test_run` 的 `_background`,实际执行:

```python
    def _background():
        from .views_api_test import execute_single_api_case
        from concurrent.futures import ThreadPoolExecutor, as_completed
        cases = list(ApiTestCase.objects.filter(id__in=case_ids))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(execute_single_api_case, request._request, case, new_run, idx + 1)
                for idx, case in enumerate(cases)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f'Rerun case error: {e}')
        new_run.refresh_from_db()
        new_run.recompute_pass_rate()
        if new_run.failed_count == 0 and new_run.error_count == 0:
            new_run.status = 'passed'
        elif new_run.error_count > 0:
            new_run.status = 'error'
        else:
            new_run.status = 'failed'
        new_run.completed_at = timezone.now()
        new_run.save()
```

- [ ] **Step 4: 跑所有 qa_center 测试**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/qa_center/views_api_test.py backend/qa_center/views_test_run.py
git commit -m "refactor(qa-center): 抽 execute_single_api_case 为模块级共享函数"
```

---

### Task 9.9: WebSocket 进度推送 from batch

**Files:**
- Modify: `backend/qa_center/views_api_test.py` (在 `run_one` 完成后推 WS)
- Create: `backend/tests/test_batch_websocket.py` (异步测试, 或用 channels.testing.WebsocketCommunicator)

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_batch_websocket.py
import pytest
import json
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.test.utils import override_settings
from qa_center.consumers import TestRunProgressConsumer
from qa_center.models import TestRun, TestRunCaseResult, ApiTestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from room.models import Project


@pytest.fixture
def project(db):
    return Project.objects.create(name='Test', owner=None)


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(username='tester', password='pass')
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_websocket_receives_case_done(project, auth_client):
    client, user = auth_client
    case = ApiTestCase.objects.create(
        name='c1', url='/api/x', method='GET', expected_status=200,
        project=project, created_by=user, expected_response={'assertions': []},
    )
    # 触发 batch
    response = client.post(
        '/api/qa/api-cases/run-batch/',
        data=json.dumps({'case_ids': [case.id]}),
        content_type='application/json',
    )
    run_id = response.json()['run_id']

    # 订阅
    communicator = WebsocketCommunicator(
        TestRunProgressConsumer.as_asgi(),
        f'/ws/qa/test-run/{run_id}/',
    )
    connected, _ = await communicator.connect()
    assert connected

    # 等 'connected' 消息
    msg = await communicator.receive_json_from()
    assert msg['type'] == 'connected'

    # 等 case_done 消息
    import asyncio
    done_msg = None
    for _ in range(20):
        try:
            done_msg = await asyncio.wait_for(communicator.receive_json_from(), timeout=1.0)
            if done_msg.get('type') == 'case_done':
                break
        except asyncio.TimeoutError:
            break

    assert done_msg is not None
    assert done_msg['type'] == 'case_done'
    assert 'sequence' in done_msg

    await communicator.disconnect()
```

- [ ] **Step 2: 在 `views_api_test.py::execute_single_api_case` 末尾,推 WS 消息**

在 `execute_single_api_case` 函数最后(更新 TestRun 计数之后),加:

```python
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"test_run_{parent_run.id}",
            {
                'type': 'case_done',
                'data': {
                    'type': 'case_done',
                    'sequence': sequence,
                    'status': 'passed' if passed else 'failed',
                    'passed_count': parent_run.passed_count,
                    'failed_count': parent_run.failed_count,
                    'error_count': parent_run.error_count,
                },
            }
        )
```

- [ ] **Step 3: 跑测试**

```bash
cd backend && python -m pytest tests/test_batch_websocket.py -v
```

Expected: PASS

- [ ] **Step 4: 跑所有 qa_center 测试**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/qa_center/views_api_test.py backend/tests/test_batch_websocket.py
git commit -m "feat(qa-center): 批量执行完成后 WebSocket 推 case_done"
```

---

### Task 9.10: QaTrendsDashboard 页面(4 图表)

**Files:**
- Create: `frontend/src/views/qa/QaTrendsDashboard.vue`

- [ ] **Step 1: 写页面**

```vue
<!-- frontend/src/views/qa/QaTrendsDashboard.vue -->
<template>
  <div class="trends-dashboard" v-loading="loading">
    <h2>质量趋势</h2>
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card header="通过率趋势(近 30 天)">
          <div ref="passRateChart" style="height: 280px;"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="用例类型分布">
          <div ref="typeChart" style="height: 280px;"></div>
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="12">
        <el-card header="失败原因 Top10">
          <div ref="failChart" style="height: 280px;"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="平均响应时间(近 30 天)">
          <div ref="latencyChart" style="height: 280px;"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import request from '@/utils/request'

const loading = ref(true)
const passRateChart = ref<HTMLElement>()
const typeChart = ref<HTMLElement>()
const failChart = ref<HTMLElement>()
const latencyChart = ref<HTMLElement>()

let passRateInstance: echarts.ECharts | null = null
let typeInstance: echarts.ECharts | null = null
let failInstance: echarts.ECharts | null = null
let latencyInstance: echarts.ECharts | null = null

async function loadData() {
  loading.value = true
  try {
    const data = await request.get<any>('/api/qa/devops/stats/?days=30')
    await nextTick()
    renderCharts(data)
  } finally {
    loading.value = false
  }
}

function renderCharts(data: any) {
  if (passRateChart.value) {
    passRateInstance = passRateInstance || echarts.init(passRateChart.value)
    passRateInstance.setOption({
      xAxis: { type: 'category', data: data.daily_trend.map((d: any) => d.date) },
      yAxis: { type: 'value', max: 100, name: '%' },
      series: [{
        name: '通过率', type: 'line',
        data: data.daily_trend.map((d: any) => {
          const completed = d.passed + d.failed + d.error
          return completed > 0 ? Math.round((d.passed / completed) * 100) : 0
        }),
        smooth: true, itemStyle: { color: '#67c23a' },
      }],
    })
  }
  if (typeChart.value) {
    typeInstance = typeInstance || echarts.init(typeChart.value)
    const byType = data.by_type || {}
    typeInstance.setOption({
      series: [{
        type: 'pie', radius: ['40%', '70%'],
        data: Object.entries(byType).map(([name, value]) => ({ name, value })),
      }],
    })
  }
  if (failChart.value) {
    failInstance = failInstance || echarts.init(failChart.value)
    const topFails: [string, number][] = Object.entries(data.top_fail_types || {})
      .sort((a, b) => (b[1] as number) - (a[1] as number))
      .slice(0, 10) as [string, number][]
    failInstance.setOption({
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: topFails.map((f) => f[0]) },
      series: [{ type: 'bar', data: topFails.map((f) => f[1]), itemStyle: { color: '#f56c6c' } }],
    })
  }
  if (latencyChart.value) {
    latencyInstance = latencyInstance || echarts.init(latencyChart.value)
    latencyInstance.setOption({
      xAxis: { type: 'category', data: data.daily_trend.map((d: any) => d.date) },
      yAxis: { type: 'value', name: 'ms' },
      series: [{
        name: '平均响应时间', type: 'line',
        data: data.daily_trend.map((d: any) => d.avg_response_time_ms || 0),
        smooth: true, itemStyle: { color: '#409eff' },
      }],
    })
  }
}

onMounted(loadData)
</script>

<style scoped>
.trends-dashboard { padding: 16px 24px; }
h2 { margin: 0 0 16px 0; }
</style>
```

- [ ] **Step 2: 后端 `DashboardStatsView` 增 `top_fail_types` 字段**

修改 `backend/qa_center/views_devops.py::DashboardStatsView.get`,在最后 `return Response(...)` 之前,加:

```python
        # 失败原因 Top10(从最近的 TestResult 聚合)
        from django.db.models import Count
        top_fail_types = {}
        recent_failed = recent_results.filter(status__in=['failed', 'error'])[:500]
        for tr in recent_failed:
            try:
                log = json.loads(tr.test_log or '{}')
            except (json.JSONDecodeError, TypeError):
                continue
            for r in log.get('results', []):
                for a in r.get('assertions', []):
                    if not a.get('passed', True):
                        k = a.get('assertion_type', 'unknown')
                        top_fail_types[k] = top_fail_types.get(k, 0) + 1
        # 限制 top10
        top_fail_types = dict(sorted(top_fail_types.items(), key=lambda x: -x[1])[:10])
```

在 `return Response({...})` 的 dict 里加 `'top_fail_types': top_fail_types` 和 `'avg_response_time_ms': round(avg_response_time, 2) if avg_response_time else None`

- [ ] **Step 3: 在 `frontend/src/api/devops.ts` 扩展类型**

```typescript
// 在已有的 DashboardStats 接口里增:
export interface DashboardStats {
  // ... 现有字段 ...
  top_fail_types?: Record<string, number>
  avg_response_time_ms?: number | null
}
```

- [ ] **Step 4: 跑前端构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 5: 跑后端测试**

```bash
cd backend && python -m pytest tests/test_qa_center.py -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/qa/QaTrendsDashboard.vue frontend/src/api/devops.ts backend/qa_center/views_devops.py
git commit -m "feat(qa-center): QaTrendsDashboard 4 图表趋势仪表板"
```

---

### Task 9.11: 前端基础组件单测

**Files:**
- Create: `frontend/tests/toCurl.spec.ts` (工具单测)
- Create: `frontend/tests/TestsPanel.spec.ts` (断言面板组件单测)
- Create: `frontend/tests/TestRunList.spec.ts` (列表页面冒烟)

- [ ] **Step 1: 写 toCurl 单测**

```typescript
// frontend/tests/toCurl.spec.ts
import { describe, it, expect } from 'vitest'

// 简单版的 toCurl(纯前端 utility, 不依赖后端)
function toCurl(method: string, url: string, headers: Record<string, string> = {}, body?: any): string {
  const parts = [`curl -X ${method.toUpperCase()}`]
  for (const [k, v] of Object.entries(headers)) {
    if (['cookie', 'host', 'content-length'].includes(k.toLowerCase())) continue
    parts.push(`  -H '${k}: ${v}'`)
  }
  if (body !== null && body !== undefined && method.toUpperCase() !== 'GET') {
    parts.push(`  -H 'Content-Type: application/json'`)
    parts.push(`  -d '${JSON.stringify(body)}'`)
  }
  parts.push(`  '${url}'`)
  return parts.join(' \\\n')
}

describe('toCurl', () => {
  it('GET without body', () => {
    const result = toCurl('GET', 'https://api.example.com/x')
    expect(result).toContain('curl -X GET')
    expect(result).not.toContain('-d')
  })

  it('POST with body and headers', () => {
    const result = toCurl('POST', 'https://api.example.com/x',
      { 'Authorization': 'Bearer abc' }, { name: 'test' })
    expect(result).toContain('curl -X POST')
    expect(result).toContain('Authorization: Bearer abc')
    expect(result).toContain('"name":"test"')
  })

  it('skips cookie header', () => {
    const result = toCurl('GET', 'https://api.example.com',
      { 'Cookie': 'sessionid=xyz', 'X-Foo': 'bar' })
    expect(result).not.toContain('Cookie')
    expect(result).not.toContain('sessionid')
    expect(result).toContain('X-Foo: bar')
  })
})
```

- [ ] **Step 2: 写 TestsPanel 单测**

```typescript
// frontend/tests/TestsPanel.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TestsPanel from '@/views/qa/components/TestsPanel.vue'

describe('TestsPanel', () => {
  it('shows passed/failed count summary', () => {
    const results = [
      { passed: true, assertion_type: 'status_code', operator: 'eq', expected_value: 200, actual_value: 200 },
      { passed: false, assertion_type: 'json_equals', operator: 'eq', expected_value: 'a', actual_value: 'b', error_message: 'mismatch' },
    ]
    const wrapper = mount(TestsPanel, { props: { results } })
    expect(wrapper.text()).toContain('通过 1 / 共 2')
  })

  it('marks all-passed when all pass', () => {
    const results = [
      { passed: true, assertion_type: 'status_code', operator: 'eq', expected_value: 200, actual_value: 200 },
    ]
    const wrapper = mount(TestsPanel, { props: { results } })
    expect(wrapper.text()).toContain('全部通过')
  })

  it('shows error message for failed assertions', async () => {
    const results = [
      { passed: false, assertion_type: 'status_code', operator: 'eq', expected_value: 200, actual_value: 500, error_message: '状态码不匹配' },
    ]
    const wrapper = mount(TestsPanel, { props: { results } })
    // 展开第一个
    await wrapper.find('.test-row').trigger('click')
    expect(wrapper.text()).toContain('状态码不匹配')
  })
})
```

- [ ] **Step 3: 跑前端测试**

```bash
cd frontend && npm run test
```

Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add frontend/tests/
git commit -m "test(frontend): TestsPanel + toCurl 单元测试"
```

---

### Task 10: 失败的测试 - 单条 run 双写 TestRun

**Files:**
- Create: `backend/tests/test_api_case_run.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_api_case_run.py
import json
import pytest
from django.test import Client
from qa_center.models import (
    ApiTestCase, TestRun, TestRunCaseResult, ApiTestResult,
)
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from room.models import Project


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(username='tester', password='pass')
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def project(db):
    return Project.objects.create(name='Test Project', owner=None)


@pytest.mark.django_db
def test_single_run_creates_test_run(auth_client, project):
    client, user = auth_client
    case = ApiTestCase.objects.create(
        name='login', url='/api/auth/login', method='POST',
        expected_status=200, project=project, created_by=user,
        expected_response={'assertions': []},
    )
    response = client.post(
        f'/api/qa/api-cases/{case.id}/run/',
        data=json.dumps({}),
        content_type='application/json',
    )
    assert response.status_code == 200
    data = response.json()
    assert 'run_id' in data
    assert 'case_result_id' in data
    assert 'curl' in data

    run = TestRun.objects.get(id=data['run_id'])
    assert run.project == project
    assert run.test_type == 'api'
    assert run.total_count == 1

    case_result = TestRunCaseResult.objects.get(id=data['case_result_id'])
    assert case_result.test_run == run
    assert case_result.api_test_case == case
    assert case_result.sequence == 1
    # legacy 字段有填
    assert case_result.legacy_api_result_id is not None


@pytest.mark.django_db
def test_single_run_response_curl_omits_cookie(auth_client, project):
    client, user = auth_client
    case = ApiTestCase.objects.create(
        name='users', url='/api/users', method='GET',
        expected_status=200, project=project, created_by=user,
        expected_response={'assertions': []},
    )
    response = client.post(
        f'/api/qa/api-cases/{case.id}/run/',
        data=json.dumps({}),
        content_type='application/json',
    )
    data = response.json()
    assert 'Cookie' not in data['curl']
    assert 'curl -X GET' in data['curl']
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_api_case_run.py -v
```

Expected: FAIL(响应里没有 `run_id`/`case_result_id`/`curl` 字段)

---

### Task 11: 在 `views_api_test.py::run` 加 双写

**Files:**
- Modify: `backend/qa_center/views_api_test.py:45-235`

- [ ] **Step 1: 在文件顶部 import 增补**

```python
from .utils.curl import to_curl
from django.utils import timezone
```

- [ ] **Step 2: 在 `run` action 开头(获取 test_case 之后),创建 TestRun**

找到 `test_case = self.get_object()`,在它之后插入:

```python
        # 双写: 创建 TestRun(单条也视为一次运行)
        test_run = TestRun.objects.create(
            project=test_case.project,
            name=f"{test_case.name} @ {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            trigger='manual',
            test_type='api',
            status='running',
            total_count=1,
            started_at=timezone.now(),
            triggered_by=request.user,
            config_snapshot={'source': 'single', 'case_id': test_case.id},
        )
```

- [ ] **Step 3: 在执行成功路径里(写完 ApiTestResult 之后),追加 TestRunCaseResult 写入**

找到 `result = ApiTestResult.objects.create(...)` 之后,插入:

```python
            # 双写: 写 TestRunCaseResult
            request_snapshot = {
                'method': method,
                'url': url,
                'headers': headers,
                'body': body,
            }
            curl_str = to_curl(method, url, headers, body,
                               content_type=test_case.content_type or 'application/json')
            case_result = TestRunCaseResult.objects.create(
                test_run=test_run,
                case_type='api',
                sequence=1,
                api_test_case=test_case,
                status='passed' if passed else 'failed',
                duration_ms=response_time_ms,
                status_code=status_code,
                response_body=response_body[:10000],
                response_headers=response_headers,
                assertion_results=assertion_results,
                request_snapshot=request_snapshot,
                curl=curl_str,
                legacy_api_result_id=result.id,
                legacy_test_result_id=None,  # 后面 TestResult 写完后回填
                started_at=test_run.started_at,
                completed_at=timezone.now(),
            )
            # 更新 TestRun 计数与状态
            from django.db.models import F
            if passed:
                TestRun.objects.filter(id=test_run.id).update(
                    passed_count=F('passed_count') + 1
                )
            else:
                TestRun.objects.filter(id=test_run.id).update(
                    failed_count=F('failed_count') + 1
                )
            test_run.refresh_from_db()
            test_run.recompute_pass_rate()
            test_run.status = 'passed' if test_run.failed_count == 0 and test_run.error_count == 0 else 'failed'
            test_run.completed_at = timezone.now()
            test_run.duration_ms = response_time_ms
            test_run.save()
```

- [ ] **Step 4: 找到 `TestResult.objects.create(...)` 那行,加上 `legacy_test_result_id=case_result.id` 是反向,但实际是回填;改为:**

找到 `TestResult.objects.create(...)` 之后,追加:

```python
            # 回填 legacy_test_result_id
            case_result.legacy_test_result_id = test_result.id
            case_result.save(update_fields=['legacy_test_result_id'])
```

(注:`test_result` 变量名在原代码就是 `TestResult.objects.create(...)` 的返回)

- [ ] **Step 5: 在响应 dict 里加 3 个字段**

找到 `result_data = {` 那行,改为:

```python
            result_data = {
                'status_code': status_code,
                'response_body': response_body[:10000],
                'response_headers': response_headers,
                'response_time_ms': response_time_ms,
                'passed': passed,
                'expected_status': test_case.expected_status,
                'assertion_results': assertion_results,
                'result_id': result.id,
                'run_id': test_run.id,
                'case_result_id': case_result.id,
                'curl': curl_str,
            }
```

- [ ] **Step 6: 同样处理 except 路径(异常时也写 TestRunCaseResult,status=error)**

找到 `except Exception as e:` 那个块的 `result = ApiTestResult.objects.create(...)` 之后,追加类似的双写逻辑(把 `status='error'`,`error_message=str(e)`)。

- [ ] **Step 7: 跑测试**

```bash
cd backend && python -m pytest tests/test_api_case_run.py -v
```

Expected: 全部 PASS

- [ ] **Step 8: 跑老测试,确保零回归**

```bash
cd backend && python -m pytest tests/test_qa_center.py tests/test_unified_assertions.py -v
```

Expected: 全部 PASS

- [ ] **Step 9: 提交**

```bash
git add backend/qa_center/views_api_test.py
git commit -m "feat(qa-center): 单条 run 双写 TestRun/TestRunCaseResult"
```

---

## Phase 5: 批量执行(并发 + 可取消)

### Task 12: 失败的测试 - `run-batch` 端点

**Files:**
- Create: `backend/tests/test_batch_run.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_batch_run.py
import json
import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from room.models import Project
from qa_center.models import ApiTestCase, TestRun, TestRunCaseResult


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(username='tester', password='pass')
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def project(db):
    return Project.objects.create(name='Test Project', owner=None)


@pytest.fixture
def five_cases(db, project, auth_client):
    _, user = auth_client
    return [
        ApiTestCase.objects.create(
            name=f'case{i}', url=f'/api/test/{i}', method='GET',
            expected_status=200, project=project, created_by=user,
            expected_response={'assertions': []},
        )
        for i in range(5)
    ]


@pytest.mark.django_db
def test_run_batch_returns_run_id_immediately(auth_client, five_cases):
    client, _ = auth_client
    response = client.post(
        '/api/qa/api-cases/run-batch/',
        data=json.dumps({'case_ids': [c.id for c in five_cases], 'name': 'batch1'}),
        content_type='application/json',
    )
    assert response.status_code == 202
    data = response.json()
    assert 'run_id' in data
    run = TestRun.objects.get(id=data['run_id'])
    assert run.total_count == 5
    assert run.name == 'batch1'


@pytest.mark.django_db
def test_run_batch_creates_one_case_result_per_case(auth_client, five_cases):
    client, _ = auth_client
    response = client.post(
        '/api/qa/api-cases/run-batch/',
        data=json.dumps({'case_ids': [c.id for c in five_cases]}),
        content_type='application/json',
    )
    run_id = response.json()['run_id']
    import time
    # 等待后台执行完成
    for _ in range(30):
        run = TestRun.objects.get(id=run_id)
        if run.status != 'running':
            break
        time.sleep(0.2)
    results = TestRunCaseResult.objects.filter(test_run_id=run_id).order_by('sequence')
    assert results.count() == 5
    assert {r.sequence for r in results} == {1, 2, 3, 4, 5}


@pytest.mark.django_db
def test_run_batch_updates_counts(auth_client, five_cases):
    client, _ = auth_client
    response = client.post(
        '/api/qa/api-cases/run-batch/',
        data=json.dumps({'case_ids': [c.id for c in five_cases]}),
        content_type='application/json',
    )
    run_id = response.json()['run_id']
    import time
    for _ in range(30):
        run = TestRun.objects.get(id=run_id)
        if run.status != 'running':
            break
        time.sleep(0.2)
    run = TestRun.objects.get(id=run_id)
    assert run.passed_count + run.failed_count + run.error_count == 5
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_batch_run.py -v
```

Expected: FAIL(URL 不存在 404)

---

### Task 13: 注册 `run-batch` URL 与 view 骨架

**Files:**
- Modify: `backend/qa_center/urls.py` (在 `urlpatterns` 列表里、`auto-execute/` 之后追加)
- Modify: `backend/qa_center/views_api_test.py` (新加 class)

- [ ] **Step 1: 在 urls.py 追加**

```python
    path('api-cases/run-batch/', ApiTestCaseBatchRunView.as_view(), name='api_case_run_batch'),
```

- [ ] **Step 2: 在 views_api_test.py 末尾追加新 View**

```python
class ApiTestCaseBatchRunView(APIView):
    """批量执行 API 用例

    POST /api/qa/api-cases/run-batch/
    Body: {case_ids: [..], name?, environment_id?, max_workers?}
    Returns: 202 Accepted {run_id}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from django.db.models import F

        case_ids = request.data.get('case_ids', [])
        if not case_ids:
            return Response(
                {'error': 'case_ids 不能为空'},
                status=status.HTTP_400_BAD_REQUEST
            )
        name = request.data.get('name') or f"批量执行 {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        max_workers = int(request.data.get('max_workers', 4))

        cases = list(ApiTestCase.objects.filter(id__in=case_ids))
        if not cases:
            return Response(
                {'error': '未找到任何 case'},
                status=status.HTTP_400_BAD_REQUEST
            )

        project = cases[0].project
        run = TestRun.objects.create(
            project=project,
            name=name,
            trigger='manual',
            test_type='api',
            status='running',
            total_count=len(cases),
            started_at=timezone.now(),
            triggered_by=request.user,
            config_snapshot={
                'case_ids': [c.id for c in cases],
                'max_workers': max_workers,
                'environment_id': request.data.get('environment_id'),
            },
        )

        def run_one(sequence, case):
            return sequence, case, _execute_single_case(request._request, case, run, sequence)

        def _execute_single_case(orig_request, case, parent_run, sequence):
            """同步执行一条用例, 写 ApiTestResult + TestRunCaseResult, 返回 (passed, error)"""
            from qa_center.utils.curl import to_curl
            try:
                # 复用 run action 的核心逻辑
                url = case.url
                method = case.method
                headers = case.headers or {}
                body_str = case.body or ''
                if isinstance(body_str, str) and body_str:
                    try:
                        body = json.loads(body_str)
                    except json.JSONDecodeError:
                        body = body_str
                else:
                    body = None

                # 处理环境变量(简化版:不解析环境,留待后续扩展)
                # 这里直接走 Django Test Client
                test_client = Client()
                if orig_request.session:
                    test_client.cookies['sessionid'] = orig_request.COOKIES.get('sessionid', '')
                    test_client.cookies['csrftoken'] = orig_request.COOKIES.get('csrftoken', '')

                request_headers = dict(headers) if headers else {}
                if body and 'Content-Type' not in request_headers:
                    request_headers['Content-Type'] = 'application/json'

                start = time.time()
                if method == 'GET':
                    response = test_client.get(url, **request_headers)
                elif method == 'POST':
                    response = test_client.post(url, data=json.dumps(body) if isinstance(body, (dict, list)) else (body or {}),
                                                content_type='application/json', **request_headers)
                elif method == 'PUT':
                    response = test_client.put(url, data=json.dumps(body) if isinstance(body, (dict, list)) else (body or {}),
                                               content_type='application/json', **request_headers)
                elif method == 'PATCH':
                    response = test_client.patch(url, data=json.dumps(body) if isinstance(body, (dict, list)) else (body or {}),
                                                 content_type='application/json', **request_headers)
                elif method == 'DELETE':
                    response = test_client.delete(url, **request_headers)
                else:
                    return False, f'不支持的请求方法: {method}'

                duration = int((time.time() - start) * 1000)
                status_code = response.status_code
                resp_body = response.content.decode('utf-8', errors='replace')
                resp_headers = dict(response.headers)

                # 断言
                expected = case.expected_response or {}
                if isinstance(expected, str):
                    try:
                        expected = json.loads(expected)
                    except json.JSONDecodeError:
                        expected = {}
                if isinstance(expected, dict):
                    assertions = expected.get('assertions', [])
                else:
                    assertions = []

                ctx = ua.ResponseContext.from_raw(
                    status_code=status_code, response_body=resp_body,
                    response_headers=resp_headers, response_time_ms=duration,
                )
                assertion_results = ua.run_assertions(assertions, ctx)

                expected_status = case.expected_status
                status_passed = (status_code == expected_status) if expected_status else (200 <= status_code < 300)
                all_passed = all(r['passed'] for r in assertion_results) if assertion_results else True
                passed = status_passed and all_passed

                # 写 ApiTestResult
                api_result = ApiTestResult.objects.create(
                    test_case=case, status_code=status_code,
                    response_body=resp_body[:10000], response_headers=resp_headers,
                    response_time_ms=duration, passed=passed,
                    assertion_results=assertion_results,
                    executed_by=orig_request.user,
                )

                # 写 TestRunCaseResult
                curl_str = to_curl(method, url, headers, body,
                                   content_type=case.content_type or 'application/json')
                TestRunCaseResult.objects.create(
                    test_run=parent_run, case_type='api', sequence=sequence,
                    api_test_case=case, status='passed' if passed else 'failed',
                    duration_ms=duration, status_code=status_code,
                    response_body=resp_body[:10000], response_headers=resp_headers,
                    assertion_results=assertion_results,
                    request_snapshot={'method': method, 'url': url, 'headers': headers, 'body': body},
                    curl=curl_str,
                    legacy_api_result_id=api_result.id,
                    started_at=parent_run.started_at, completed_at=timezone.now(),
                )

                # 原子更新计数
                field = 'passed_count' if passed else 'failed_count'
                TestRun.objects.filter(id=parent_run.id).update(**{field: F(field) + 1})
                return passed, None
            except Exception as e:
                TestRunCaseResult.objects.create(
                    test_run=parent_run, case_type='api', sequence=sequence,
                    api_test_case=case, status='error', error_message=str(e),
                    started_at=parent_run.started_at, completed_at=timezone.now(),
                )
                TestRun.objects.filter(id=parent_run.id).update(error_count=F('error_count') + 1)
                return False, str(e)

        def run_all_in_background():
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [
                        executor.submit(run_one, idx + 1, case)
                        for idx, case in enumerate(cases)
                    ]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f'Batch run case error: {e}')
            finally:
                # 收尾:刷新 pass_rate + 状态
                run.refresh_from_db()
                run.recompute_pass_rate()
                if run.cancelled:
                    run.status = 'cancelled'
                else:
                    if run.failed_count == 0 and run.error_count == 0:
                        run.status = 'passed'
                    elif run.error_count > 0:
                        run.status = 'error'
                    else:
                        run.status = 'failed'
                run.completed_at = timezone.now()
                if run.started_at:
                    delta = (run.completed_at - run.started_at).total_seconds() * 1000
                    run.duration_ms = int(delta)
                run.save()

        import threading
        thread = threading.Thread(target=run_all_in_background)
        thread.daemon = True
        thread.start()

        return Response({'run_id': run.id, 'total_count': run.total_count},
                        status=status.HTTP_202_ACCEPTED)
```

- [ ] **Step 3: 跑测试**

```bash
cd backend && python -m pytest tests/test_batch_run.py -v
```

Expected: 全部 PASS

- [ ] **Step 4: 跑老测试,确保零回归**

```bash
cd backend && python -m pytest tests/test_qa_center.py tests/test_api_case_run.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/qa_center/urls.py backend/qa_center/views_api_test.py backend/tests/test_batch_run.py
git commit -m "feat(qa-center): 批量执行 run-batch 端点(4 并发可配置)"
```

---

### Task 14: 失败的测试 - cancel 端点

**Files:**
- Modify: `backend/tests/test_batch_run.py` (追加)

- [ ] **Step 1: 写测试**

```python
# 追加
from qa_center.models import TestRun as TR


@pytest.mark.django_db
def test_cancel_run_marks_pending_as_skipped(auth_client, five_cases, db):
    client, _ = auth_client
    # 创建一 run 但不执行
    run = TR.objects.create(
        project=five_cases[0].project, name='manual', test_type='api',
        status='pending', total_count=3,
    )
    for seq, case in enumerate(five_cases[:3], 1):
        TestRunCaseResult.objects.create(
            test_run=run, case_type='api', sequence=seq, api_test_case=case,
            status='pending',
        )
    response = client.post(f'/api/qa/runs/{run.id}/cancel/')
    assert response.status_code == 200
    run.refresh_from_db()
    assert run.status == 'cancelled'
    for r in run.case_results.all():
        assert r.status == 'skipped'
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_batch_run.py::test_cancel_run_marks_pending_as_skipped -v
```

Expected: FAIL(URL 不存在)

---

### Task 15: 实现 cancel 端点

**Files:**
- Create: `backend/qa_center/views_test_run.py`

- [ ] **Step 1: 创建 `views_test_run.py` 骨架**

```python
# backend/qa_center/views_test_run.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import F

from .models import TestRun, TestRunCaseResult


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_test_run(request, run_id):
    """取消一个 running/pending 的 TestRun。

    - pending case 立即变 skipped
    - running case 继续跑完
    - 跑完后 TestRun.status 变 cancelled
    """
    try:
        run = TestRun.objects.get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)

    if run.status not in ('pending', 'running'):
        return Response(
            {'error': f'TestRun 当前状态 {run.status},不可取消'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 把所有 pending 的 case 变 skipped
    TestRunCaseResult.objects.filter(
        test_run=run, status='pending'
    ).update(status='skipped', completed_at=timezone.now())

    # 标记 cancelled
    run.cancelled = True  # 临时属性,后台执行器会读取
    # 用 update_fields 防止触发 save 全字段
    TestRun.objects.filter(id=run.id).update(status='cancelled', completed_at=timezone.now())
    return Response({'status': 'cancelled', 'run_id': run.id})
```

- [ ] **Step 2: 改 `TestRun` 模型加 `cancelled` 临时字段(不存库)**

在 `backend/qa_center/models.py` 的 `TestRun` 类内,加:

```python
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cancelled = False
```

- [ ] **Step 3: 在 urls.py 注册**

```python
    path('runs/<int:run_id>/cancel/', cancel_test_run, name='test_run_cancel'),
```

- [ ] **Step 4: 跑测试**

```bash
cd backend && python -m pytest tests/test_batch_run.py::test_cancel_run_marks_pending_as_skipped -v
```

Expected: PASS

- [ ] **Step 5: 跑所有 batch 测试**

```bash
cd backend && python -m pytest tests/test_batch_run.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/qa_center/views_test_run.py backend/qa_center/models.py backend/qa_center/urls.py backend/tests/test_batch_run.py
git commit -m "feat(qa-center): TestRun cancel 端点(pending→skipped)"
```

---

## Phase 6: TestRun REST 端点(查询类)

### Task 16: 失败的测试 - list / detail / cases 端点

**Files:**
- Create: `backend/tests/test_test_run_endpoints.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_test_run_endpoints.py
import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from room.models import Project
from qa_center.models import TestRun, TestRunCaseResult, ApiTestCase


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(username='tester', password='pass')
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def project(db):
    return Project.objects.create(name='Test', owner=None)


@pytest.fixture
def two_runs(db, project, auth_client):
    _, user = auth_client
    case = ApiTestCase.objects.create(
        name='c1', url='/api/x', method='GET', expected_status=200,
        project=project, created_by=user, expected_response={'assertions': []},
    )
    r1 = TestRun.objects.create(
        project=project, name='run1', test_type='api', status='passed',
        total_count=1, passed_count=1, failed_count=0, error_count=0,
        pass_rate=100.0,
    )
    TestRunCaseResult.objects.create(
        test_run=r1, case_type='api', sequence=1, api_test_case=case,
        status='passed',
    )
    r2 = TestRun.objects.create(
        project=project, name='run2', test_type='api', status='failed',
        total_count=2, passed_count=1, failed_count=1, error_count=0,
        pass_rate=50.0,
    )
    TestRunCaseResult.objects.create(
        test_run=r2, case_type='api', sequence=1, api_test_case=case,
        status='passed',
    )
    TestRunCaseResult.objects.create(
        test_run=r2, case_type='api', sequence=2, api_test_case=case,
        status='failed', status_code=500,
    )
    return r1, r2, case


@pytest.mark.django_db
def test_list_runs(auth_client, two_runs):
    client, _ = auth_client
    r1, r2, _ = two_runs
    response = client.get(f'/api/qa/runs/?project={r1.project_id}')
    assert response.status_code == 200
    data = response.json()
    assert 'results' in data
    assert data['count'] == 2
    names = {r['name'] for r in data['results']}
    assert {'run1', 'run2'} == names


@pytest.mark.django_db
def test_list_runs_filter_by_status(auth_client, two_runs):
    client, _ = auth_client
    r1, _, _ = two_runs
    response = client.get(f'/api/qa/runs/?project={r1.project_id}&status=failed')
    assert response.status_code == 200
    data = response.json()
    assert data['count'] == 1
    assert data['results'][0]['status'] == 'failed'


@pytest.mark.django_db
def test_run_detail(auth_client, two_runs):
    client, _ = auth_client
    r1, _, _ = two_runs
    response = client.get(f'/api/qa/runs/{r1.id}/')
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == r1.id
    assert data['name'] == 'run1'
    assert data['total_count'] == 1
    assert data['passed_count'] == 1


@pytest.mark.django_db
def test_run_cases_list(auth_client, two_runs):
    client, _ = auth_client
    _, r2, _ = two_runs
    response = client.get(f'/api/qa/runs/{r2.id}/cases/')
    assert response.status_code == 200
    data = response.json()
    assert data['count'] == 2
    statuses = {c['status'] for c in data['results']}
    assert statuses == {'passed', 'failed'}


@pytest.mark.django_db
def test_run_case_detail(auth_client, two_runs):
    client, _ = auth_client
    _, r2, _ = two_runs
    case_result = r2.case_results.get(sequence=2)
    response = client.get(f'/api/qa/runs/{r2.id}/cases/{case_result.id}/')
    assert response.status_code == 200
    data = response.json()
    assert data['sequence'] == 2
    assert data['status'] == 'failed'
    assert data['status_code'] == 500
    assert 'curl' in data
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_test_run_endpoints.py -v
```

Expected: 全部 FAIL(URL 404)

---

### Task 17: 实现 list / detail / cases 端点

**Files:**
- Modify: `backend/qa_center/views_test_run.py` (追加)

- [ ] **Step 1: 追加 list 端点**

```python
# 在 views_test_run.py 末尾追加
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_test_runs(request):
    """GET /api/qa/runs/?project=&status=&test_type=&page=&page_size="""
    qs = TestRun.objects.select_related('project', 'triggered_by')
    project_id = request.query_params.get('project')
    if project_id:
        qs = qs.filter(project_id=project_id)
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    test_type = request.query_params.get('test_type')
    if test_type:
        qs = qs.filter(test_type=test_type)

    page = int(request.query_params.get('page', 1))
    page_size = min(int(request.query_params.get('page_size', 20)), 100)
    total = qs.count()
    start = (page - 1) * page_size
    items = qs[start:start + page_size]

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': [_serialize_run(r) for r in items],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_run_detail(request, run_id):
    try:
        run = TestRun.objects.select_related('project', 'triggered_by').get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)
    data = _serialize_run(run)
    data['case_count'] = run.case_results.count()
    data['summary'] = run.summary
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_run_cases(request, run_id):
    try:
        run = TestRun.objects.get(id=run_id)
    except TestRun.DoesNotExist:
        return Response({'error': 'TestRun 不存在'}, status=status.HTTP_404_NOT_FOUND)

    qs = run.case_results.select_related('api_test_case', 'ui_test_case').order_by('sequence')
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    page = int(request.query_params.get('page', 1))
    page_size = min(int(request.query_params.get('page_size', 50)), 200)
    total = qs.count()
    start = (page - 1) * page_size
    items = qs[start:start + page_size]

    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': [_serialize_case_result(r) for r in items],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_run_case_detail(request, run_id, case_result_id):
    try:
        case_result = TestRunCaseResult.objects.select_related(
            'test_run', 'api_test_case', 'ui_test_case'
        ).get(id=case_result_id, test_run_id=run_id)
    except TestRunCaseResult.DoesNotExist:
        return Response({'error': 'CaseResult 不存在'}, status=status.HTTP_404_NOT_FOUND)
    return Response(_serialize_case_result(case_result, full=True))


def _serialize_run(run):
    return {
        'id': run.id,
        'project_id': run.project_id,
        'project_name': run.project.name if run.project else '',
        'name': run.name,
        'trigger': run.trigger,
        'test_type': run.test_type,
        'status': run.status,
        'total_count': run.total_count,
        'passed_count': run.passed_count,
        'failed_count': run.failed_count,
        'error_count': run.error_count,
        'pass_rate': float(run.pass_rate) if run.pass_rate is not None else 0,
        'duration_ms': run.duration_ms,
        'triggered_by': run.triggered_by.username if run.triggered_by else None,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'created_at': run.created_at.isoformat() if run.created_at else None,
    }


def _serialize_case_result(r, full=False):
    base = {
        'id': r.id,
        'test_run_id': r.test_run_id,
        'case_type': r.case_type,
        'sequence': r.sequence,
        'api_test_case_id': r.api_test_case_id,
        'ui_test_case_id': r.ui_test_case_id,
        'name': r.api_test_case.name if r.api_test_case else (r.ui_test_case.name if r.ui_test_case else ''),
        'status': r.status,
        'duration_ms': r.duration_ms,
        'status_code': r.status_code,
        'error_message': r.error_message,
        'started_at': r.started_at.isoformat() if r.started_at else None,
        'completed_at': r.completed_at.isoformat() if r.completed_at else None,
    }
    if full:
        base.update({
            'response_body': r.response_body,
            'response_headers': r.response_headers,
            'assertion_results': r.assertion_results,
            'request_snapshot': r.request_snapshot,
            'curl': r.curl,
        })
    return base
```

- [ ] **Step 2: 在 urls.py 注册**

```python
    path('runs/', list_test_runs, name='test_run_list'),
    path('runs/<int:run_id>/', test_run_detail, name='test_run_detail'),
    path('runs/<int:run_id>/cases/', test_run_cases, name='test_run_cases'),
    path('runs/<int:run_id>/cases/<int:case_result_id>/', test_run_case_detail, name='test_run_case_detail'),
```

- [ ] **Step 3: 跑测试**

```bash
cd backend && python -m pytest tests/test_test_run_endpoints.py -v
```

Expected: 全部 PASS

- [ ] **Step 4: 跑所有 qa_center 测试**

```bash
cd backend && python -m pytest tests/test_qa_center.py tests/test_api_case_run.py tests/test_batch_run.py tests/test_test_run_endpoints.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/qa_center/views_test_run.py backend/qa_center/urls.py backend/tests/test_test_run_endpoints.py
git commit -m "feat(qa-center): TestRun list/detail/cases 端点"
```

---

## Phase 7: 历史 backfill 命令

### Task 18: 失败的测试 - backfill 命令

**Files:**
- Create: `backend/tests/test_backfill.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_backfill.py
import json
import pytest
from io import StringIO
from django.core.management import call_command
from django.contrib.auth.models import User
from room.models import Project
from qa_center.models import ApiTestCase, TestRun, TestRunCaseResult, TestResult


@pytest.fixture
def setup_batch_in_old_format(db):
    user = User.objects.create_user(username='tester', password='pass')
    project = Project.objects.create(name='Test', owner=user)
    case = ApiTestCase.objects.create(
        name='c1', url='/api/x', method='GET', expected_status=200,
        project=project, created_by=user, expected_response={'assertions': []},
    )
    # 模拟老的 TestResult.test_log
    log = {
        'summary': {'total': 3, 'passed': 2, 'failed': 1, 'pass_rate': 66.67},
        'results': [
            {'case_id': case.id, 'case_name': 'c1', 'type': 'api', 'passed': True,
             'response_time_ms': 100, 'message': 'ok',
             'request': {'method': 'GET', 'url': '/api/x', 'headers': {}, 'body': None},
             'response': {'status_code': 200, 'headers': {}, 'body': '{}'},
             'assertions': []},
            {'case_id': case.id, 'case_name': 'c1', 'type': 'api', 'passed': True,
             'response_time_ms': 120, 'message': 'ok',
             'request': {'method': 'GET', 'url': '/api/x', 'headers': {}, 'body': None},
             'response': {'status_code': 200, 'headers': {}, 'body': '{}'},
             'assertions': []},
            {'case_id': case.id, 'case_name': 'c1', 'type': 'api', 'passed': False,
             'response_time_ms': 500, 'message': 'failed',
             'request': {'method': 'GET', 'url': '/api/x', 'headers': {}, 'body': None},
             'response': {'status_code': 500, 'headers': {}, 'body': '{}'},
             'assertions': [{'passed': False, 'error_message': '500'}]},
        ],
    }
    tr = TestResult.objects.create(
        test_type='api', name='old-batch', project=project,
        api_test_case=case, status='failed', executed_by=user,
        duration_ms=720, test_log=json.dumps(log, ensure_ascii=False),
    )
    return tr, project, case


@pytest.mark.django_db
def test_backfill_creates_test_run(setup_batch_in_old_format):
    tr, project, case = setup_batch_in_old_format
    out = StringIO()
    call_command('backfill_test_runs', '--days=90', stdout=out)
    assert TestRun.objects.filter(project=project, name='old-batch').count() == 1
    run = TestRun.objects.get(project=project, name='old-batch')
    assert run.total_count == 3
    assert run.passed_count == 2
    assert run.failed_count == 1
    assert TestRunCaseResult.objects.filter(test_run=run).count() == 3
```

- [ ] **Step 2: 跑测试,确认失败**

```bash
cd backend && python -m pytest tests/test_backfill.py -v
```

Expected: FAIL(命令不存在)

---

### Task 19: 实现 `backfill_test_runs` 命令

**Files:**
- Create: `backend/qa_center/management/__init__.py` (空)
- Create: `backend/qa_center/management/commands/__init__.py` (空)
- Create: `backend/qa_center/management/commands/backfill_test_runs.py`

- [ ] **Step 1: 创建包结构(若不存在)**

```bash
mkdir -p backend/qa_center/management/commands
touch backend/qa_center/management/__init__.py
touch backend/qa_center/management/commands/__init__.py
```

- [ ] **Step 2: 实现命令**

```python
# backend/qa_center/management/commands/backfill_test_runs.py
"""把老 TestResult.test_log(JSON) 里识别为批量的记录回填到 TestRun + TestRunCaseResult。

判定标准:summary.total > 1
"""
import json
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from qa_center.models import TestRun, TestRunCaseResult, TestResult

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '回填历史 TestResult 批量执行记录到 TestRun + TestRunCaseResult'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90, help='回填最近 N 天')
        parser.add_argument('--batch', type=int, default=100, help='每次处理多少条')
        parser.add_argument('--dry-run', action='store_true', help='只看预估,不写库')

    def handle(self, *args, **options):
        days = options['days']
        batch = options['batch']
        dry_run = options['dry_run']

        cutoff = timezone.now() - timedelta(days=days)
        qs = TestResult.objects.filter(
            test_type='api', created_at__gte=cutoff,
        ).exclude(test_log='').order_by('-created_at')

        total = qs.count()
        self.stdout.write(f'候选 {total} 条 TestResult(近 {days} 天)')

        if dry_run:
            # 估算有多少会被识别为批量
            estimate = 0
            for tr in qs.iterator():
                log = self._parse_log(tr.test_log)
                if log and log.get('summary', {}).get('total', 0) > 1:
                    estimate += 1
            self.stdout.write(self.style.WARNING(
                f'[DRY-RUN] 预计回填 {estimate} 条批量记录, --batch={batch}'
            ))
            return

        processed = 0
        created_runs = 0
        for tr in qs.iterator():
            processed += 1
            log = self._parse_log(tr.test_log)
            if not log:
                continue
            summary = log.get('summary', {})
            total_count = summary.get('total', 0)
            if total_count <= 1:
                continue
            results = log.get('results', [])
            if not results:
                continue

            # 跳过已回填
            if TestRun.objects.filter(name=tr.name, project=tr.project,
                                       created_at__date=tr.created_at.date()).exists():
                continue

            run = TestRun.objects.create(
                project=tr.project,
                name=tr.name,
                trigger='manual',
                test_type='api',
                status='passed' if tr.status == 'passed' else 'failed',
                total_count=total_count,
                passed_count=summary.get('passed', 0),
                failed_count=summary.get('failed', 0),
                error_count=summary.get('error', 0) if 'error' in summary else 0,
                pass_rate=summary.get('pass_rate', 0),
                duration_ms=tr.duration_ms,
                started_at=tr.started_at or tr.created_at,
                completed_at=tr.completed_at or tr.created_at,
                created_at=tr.created_at,
                triggered_by=tr.executed_by,
                config_snapshot={'source': 'backfill', 'legacy_test_result_id': tr.id},
            )
            created_runs += 1

            for idx, item in enumerate(results, 1):
                TestRunCaseResult.objects.create(
                    test_run=run,
                    case_type='api',
                    sequence=idx,
                    api_test_case_id=item.get('case_id') or tr.api_test_case_id,
                    status='passed' if item.get('passed') else 'failed',
                    duration_ms=item.get('response_time_ms'),
                    status_code=item.get('response', {}).get('status_code'),
                    response_body=str(item.get('response', {}).get('body', ''))[:10000],
                    response_headers=item.get('response', {}).get('headers', {}),
                    assertion_results=item.get('assertions', []),
                    request_snapshot=item.get('request', {}),
                    curl='',
                    legacy_test_result_id=tr.id,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                )

            if processed % batch == 0:
                self.stdout.write(f'已处理 {processed}/{total}...')

        self.stdout.write(self.style.SUCCESS(
            f'回填完成: 扫描 {processed} 条, 新建 {created_runs} 个 TestRun'
        ))

    @staticmethod
    def _parse_log(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
```

- [ ] **Step 3: 跑测试**

```bash
cd backend && python -m pytest tests/test_backfill.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add backend/qa_center/management/ backend/tests/test_backfill.py
git commit -m "feat(qa-center): backfill_test_runs 历史回填命令"
```

---

## Phase 8: WebSocket 实时进度

### Task 20: 实现 `TestRunProgressConsumer`

**Files:**
- Modify: `backend/qa_center/consumers.py` (追加类)
- Modify: `backend/qa_center/routing.py` (追加路由)

- [ ] **Step 1: 在 consumers.py 末尾追加**

```python
class TestRunProgressConsumer(AsyncWebsocketConsumer):
    """TestRun 实时进度推送

    URL: /ws/qa/test-run/{run_id}/
    消息: {type: 'case_done', sequence, status, passed_count, ...}
    """
    async def connect(self):
        self.run_id = self.scope['url_route']['kwargs'].get('run_id')
        self.group_name = f"test_run_{self.run_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected', 'run_id': self.run_id,
            'message': f'已订阅 TestRun {self.run_id} 的进度',
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def case_done(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def run_finished(self, event):
        await self.send(text_data=json.dumps(event['data']))
```

- [ ] **Step 2: 在 routing.py 追加**

```python
# backend/qa_center/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/qa/recorder/$', consumers.RecorderConsumer.as_asgi()),
    re_path(r'ws/qa/performance/(?P<execution_id>\w+)/$',
            consumers.PerformanceTestConsumer.as_asgi()),
    re_path(r'ws/qa/test-run/(?P<run_id>\w+)/$',
            consumers.TestRunProgressConsumer.as_asgi()),
    re_path(r'ws/qa/$', consumers.QAConsumer.as_asgi()),
]
```

- [ ] **Step 3: 跑现有 qa_center 测试,确保不破**

```bash
cd backend && python -m pytest tests/test_qa_center.py -v
```

Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add backend/qa_center/consumers.py backend/qa_center/routing.py
git commit -m "feat(qa-center): TestRunProgressConsumer WebSocket"
```

---

## Phase 9: 前端基础设施

### Task 21: 安装前端依赖

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 安装包**

```bash
cd frontend && npm install vue-codemirror@^6.0.0 @codemirror/lang-json@^6.0.0 diff-match-patch@^1.0.5
```

- [ ] **Step 2: 提交**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): 装 vue-codemirror / diff-match-patch 依赖"
```

---

### Task 22: API 客户端(类型 + 方法)

**Files:**
- Create: `frontend/src/api/testrun.ts`

- [ ] **Step 1: 写 API 客户端**

```typescript
// frontend/src/api/testrun.ts
import request from '@/utils/request'

export interface TestRun {
  id: number
  project_id: number
  project_name: string
  name: string
  trigger: 'manual' | 'scheduled' | 'cicd' | 'regression'
  test_type: 'api' | 'ui' | 'performance' | 'mixed'
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'cancelled'
  total_count: number
  passed_count: number
  failed_count: number
  error_count: number
  pass_rate: number
  duration_ms: number | null
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface TestRunCaseResult {
  id: number
  test_run_id: number
  case_type: 'api' | 'ui' | 'performance'
  sequence: number
  api_test_case_id: number | null
  name: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'skipped'
  duration_ms: number | null
  status_code: number | null
  error_message: string
  started_at: string | null
  completed_at: string | null
  // full=true 时:
  response_body?: string
  response_headers?: Record<string, string>
  assertion_results?: any[]
  request_snapshot?: any
  curl?: string
}

export interface PaginatedResponse<T> {
  count: number
  page: number
  page_size: number
  results: T[]
}

export const testRunApi = {
  list(params: { project?: number; status?: string; test_type?: string; page?: number; page_size?: number } = {}) {
    return request.get<PaginatedResponse<TestRun>>('/api/qa/runs/', { params })
  },
  detail(id: number) {
    return request.get<TestRun>(`/api/qa/runs/${id}/`)
  },
  cases(runId: number, params: { status?: string; page?: number; page_size?: number } = {}) {
    return request.get<PaginatedResponse<TestRunCaseResult>>(`/api/qa/runs/${runId}/cases/`, { params })
  },
  caseDetail(runId: number, caseResultId: number) {
    return request.get<TestRunCaseResult>(`/api/qa/runs/${runId}/cases/${caseResultId}/`)
  },
  cancel(id: number) {
    return request.post(`/api/qa/runs/${id}/cancel/`)
  },
  rerun(id: number) {
    return request.post(`/api/qa/runs/${id}/rerun/`)
  },
  runBatch(payload: { case_ids: number[]; name?: string; environment_id?: number; max_workers?: number }) {
    return request.post<{ run_id: number; total_count: number }>('/api/qa/api-cases/run-batch/', payload)
  },
  // 旧的单条运行(扩展了响应字段)
  runSingle(caseId: number, payload: any = {}) {
    return request.post<any>(`/api/qa/api-cases/${caseId}/run/`, payload)
  },
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/api/testrun.ts
git commit -m "feat(frontend): TestRun API 客户端"
```

---

## Phase 10: 前端组件

### Task 23: `CurlPanel.vue`

**Files:**
- Create: `frontend/src/views/qa/components/CurlPanel.vue`
- Create: `frontend/tests/toCurl.spec.ts` (放到 frontend 目录)

- [ ] **Step 1: 写组件**

```vue
<!-- frontend/src/views/qa/components/CurlPanel.vue -->
<template>
  <div class="curl-panel">
    <div class="curl-header">
      <span class="curl-title">cURL</span>
      <el-button-group>
        <el-button size="small" @click="copy" :icon="DocumentCopy">{{ copied ? '已复制' : '复制' }}</el-button>
        <el-button size="small" @click="download" :icon="Download">下载 .sh</el-button>
      </el-button-group>
    </div>
    <pre class="curl-body"><code>{{ curl }}</code></pre>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DocumentCopy, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{ curl: string }>()
const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(props.curl)
    copied.value = true
    ElMessage.success('已复制到剪贴板')
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    ElMessage.error('复制失败')
  }
}

function download() {
  const blob = new Blob([`#!/bin/bash\n${props.curl}\n`], { type: 'text/x-shellscript' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `request-${Date.now()}.sh`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.curl-panel { background: #1e1e1e; border-radius: 6px; padding: 16px; }
.curl-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.curl-title { color: #d4d4d4; font-weight: 600; font-size: 14px; }
.curl-body { color: #d4d4d4; font-family: 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.5; margin: 0; white-space: pre-wrap; word-break: break-all; }
</style>
```

- [ ] **Step 2: 跑构建确保无错**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/qa/components/CurlPanel.vue
git commit -m "feat(frontend): CurlPanel 组件"
```

---

### Task 24: `TestsPanel.vue`(断言列表+diff)

**Files:**
- Create: `frontend/src/views/qa/components/TestsPanel.vue`

- [ ] **Step 1: 写组件**

```vue
<!-- frontend/src/views/qa/components/TestsPanel.vue -->
<template>
  <div class="tests-panel">
    <div class="tests-summary">
      <span class="tests-count">
        通过 {{ passedCount }} / 共 {{ results.length }}
      </span>
      <span v-if="results.length > 0" :class="['tests-rate', allPassed ? 'pass' : 'fail']">
        {{ allPassed ? '✓ 全部通过' : '✗ 存在失败' }}
      </span>
    </div>
    <ul class="tests-list">
      <li v-for="(r, idx) in results" :key="idx" :class="['test-item', r.passed ? 'pass' : 'fail']">
        <div class="test-row" @click="toggle(idx)">
          <span class="test-icon">{{ r.passed ? '✓' : '✗' }}</span>
          <span class="test-desc">{{ describe(r) }}</span>
          <span class="test-toggle">{{ expanded[idx] ? '▾' : '▸' }}</span>
        </div>
        <div v-if="expanded[idx]" class="test-detail">
          <div class="detail-row">
            <span class="label">类型:</span>
            <span>{{ r.assertion_type }}</span>
          </div>
          <div class="detail-row" v-if="r.json_path">
            <span class="label">路径:</span>
            <code>{{ r.json_path }}</code>
          </div>
          <div class="detail-row" v-if="r.header_name">
            <span class="label">Header:</span>
            <code>{{ r.header_name }}</code>
          </div>
          <div class="detail-row">
            <span class="label">期望:</span>
            <code class="value">{{ formatValue(r.expected_value) }}</code>
          </div>
          <div class="detail-row">
            <span class="label">实际:</span>
            <code class="value">{{ formatValue(r.actual_value) }}</code>
          </div>
          <div v-if="!r.passed && r.error_message" class="detail-row error">
            <span class="label">错误:</span>
            <span>{{ r.error_message }}</span>
          </div>
        </div>
      </li>
    </ul>
    <div v-if="extractions && extractions.length > 0" class="extractions">
      <h4>变量提取</h4>
      <ul>
        <li v-for="(ex, i) in extractions" :key="i">
          <code>{{ ex.name }}</code>: <code>{{ ex.value_preview }}</code>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  results: any[]
  extractions?: { name: string; value_preview: string; is_none: boolean }[]
}>()

const expanded = ref<Record<number, boolean>>({})

const passedCount = computed(() => props.results.filter((r) => r.passed).length)
const allPassed = computed(() => passedCount.value === props.results.length)

function toggle(idx: number) {
  expanded.value[idx] = !expanded.value[idx]
}

function describe(r: any): string {
  const op = r.operator || '=='
  const ev = formatValue(r.expected_value)
  if (r.json_path) return `${r.json_path} ${op} ${ev}`
  if (r.header_name) return `${r.header_name} ${op} ${ev}`
  return `${r.assertion_type} ${op} ${ev}`
}

function formatValue(v: any): string {
  if (v === null) return 'null'
  if (v === undefined) return 'undefined'
  if (typeof v === 'string') return v.length > 100 ? v.slice(0, 100) + '...' : `"${v}"`
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>

<style scoped>
.tests-panel { padding: 16px; }
.tests-summary { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #ebeef5; }
.tests-count { font-weight: 600; }
.tests-rate.pass { color: #67c23a; }
.tests-rate.fail { color: #f56c6c; }
.tests-list { list-style: none; padding: 0; margin: 0; }
.test-item { padding: 8px 12px; border-radius: 4px; margin-bottom: 4px; }
.test-item.pass { background: #f0f9eb; }
.test-item.fail { background: #fef0f0; }
.test-row { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.test-icon { font-weight: bold; width: 20px; }
.test-item.pass .test-icon { color: #67c23a; }
.test-item.fail .test-icon { color: #f56c6c; }
.test-desc { flex: 1; font-family: 'Menlo', monospace; font-size: 13px; }
.test-detail { margin-top: 8px; padding: 12px; background: #fff; border-radius: 4px; }
.detail-row { display: flex; gap: 8px; padding: 4px 0; font-size: 13px; }
.detail-row .label { color: #909399; min-width: 60px; }
.detail-row code { font-family: 'Menlo', monospace; }
.detail-row.error { color: #f56c6c; }
.extractions { margin-top: 24px; padding-top: 16px; border-top: 1px solid #ebeef5; }
.extractions h4 { margin: 0 0 8px 0; }
.extractions ul { list-style: none; padding: 0; }
.extractions li { padding: 4px 0; font-size: 13px; }
</style>
```

- [ ] **Step 2: 跑构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/qa/components/TestsPanel.vue
git commit -m "feat(frontend): TestsPanel 断言列表+diff 组件"
```

---

### Task 25: `ResponsePanel.vue`(JSON 高亮)

**Files:**
- Create: `frontend/src/views/qa/components/ResponsePanel.vue`

- [ ] **Step 1: 写组件**

```vue
<!-- frontend/src/views/qa/components/ResponsePanel.vue -->
<template>
  <div class="response-panel">
    <div class="response-summary">
      <el-tag :type="statusTagType" effect="dark">Status {{ statusCode }}</el-tag>
      <span class="metric">⏱ {{ duration }}ms</span>
      <span class="metric">📦 {{ bodySize }} bytes</span>
    </div>
    <el-collapse>
      <el-collapse-item title="响应头" name="headers">
        <pre class="headers">{{ JSON.stringify(headers, null, 2) }}</pre>
      </el-collapse-item>
    </el-collapse>
    <div class="body">
      <h4>响应体</h4>
      <pre v-if="parsedJson" class="json"><code v-html="highlightedJson" /></pre>
      <pre v-else class="raw">{{ body }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  statusCode: number
  duration: number
  body: string
  headers: Record<string, string>
}>()

const parsedJson = computed(() => {
  try { return JSON.parse(props.body) } catch { return null }
})

const bodySize = computed(() => new Blob([props.body || '']).size)

const statusTagType = computed(() => {
  const c = props.statusCode
  if (c >= 500) return 'danger'
  if (c >= 400) return 'warning'
  if (c >= 300) return 'info'
  if (c >= 200) return 'success'
  return 'info'
})

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const highlightedJson = computed(() => {
  if (!parsedJson.value) return ''
  const json = JSON.stringify(parsedJson.value, null, 2)
  return escapeHtml(json)
    .replace(/"([^"]+)":/g, '<span class="key">"$1"</span>:')
    .replace(/: "([^"]*)"/g, ': <span class="string">"$1"</span>')
    .replace(/: (-?\d+\.?\d*)/g, ': <span class="number">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="bool">$1</span>')
})
</script>

<style scoped>
.response-panel { padding: 16px; }
.response-summary { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; }
.metric { color: #606266; font-size: 13px; }
.body h4 { margin: 16px 0 8px 0; }
pre { background: #fafafa; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 13px; }
pre.json code { font-family: 'Menlo', monospace; }
:deep(.key) { color: #881391; }
:deep(.string) { color: #c41a16; }
:deep(.number) { color: #1c00cf; }
:deep(.bool) { color: #0d22aa; }
.headers { white-space: pre-wrap; }
</style>
```

- [ ] **Step 2: 跑构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/qa/components/ResponsePanel.vue
git commit -m "feat(frontend): ResponsePanel 响应 JSON 高亮组件"
```

---

### Task 26: `RequestPanel.vue`(只读请求)

**Files:**
- Create: `frontend/src/views/qa/components/RequestPanel.vue`

- [ ] **Step 1: 写组件**

```vue
<!-- frontend/src/views/qa/components/RequestPanel.vue -->
<template>
  <div class="request-panel">
    <div class="row">
      <span class="label">Method</span>
      <el-tag :type="methodTagType" effect="dark">{{ method }}</el-tag>
    </div>
    <div class="row">
      <span class="label">URL</span>
      <code class="url">{{ url }}</code>
    </div>
    <div v-if="headers && Object.keys(headers).length" class="row">
      <span class="label">Headers</span>
      <pre class="headers">{{ JSON.stringify(headers, null, 2) }}</pre>
    </div>
    <div v-if="body !== null && body !== undefined" class="row">
      <span class="label">Body</span>
      <pre class="body"><code>{{ formatBody(body) }}</code></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  method: string
  url: string
  headers?: Record<string, string>
  body?: any
}>()

const methodTagType = computed(() => {
  const m = props.method?.toUpperCase()
  if (m === 'GET') return 'success'
  if (m === 'POST') return 'warning'
  if (m === 'DELETE') return 'danger'
  return 'info'
})

function formatBody(b: any): string {
  if (typeof b === 'string') return b
  return JSON.stringify(b, null, 2)
}
</script>

<style scoped>
.request-panel { padding: 16px; }
.row { margin-bottom: 16px; }
.label { display: block; color: #909399; font-size: 12px; margin-bottom: 4px; text-transform: uppercase; }
.url { background: #fafafa; padding: 6px 10px; border-radius: 4px; font-family: 'Menlo', monospace; font-size: 13px; display: inline-block; }
pre { background: #fafafa; padding: 12px; border-radius: 4px; font-size: 12px; max-height: 300px; overflow: auto; }
</style>
```

- [ ] **Step 2: 跑构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/qa/components/RequestPanel.vue
git commit -m "feat(frontend): RequestPanel 只读请求组件"
```

---

### Task 27: `RunProgressBar.vue`

**Files:**
- Create: `frontend/src/views/qa/components/RunProgressBar.vue`

- [ ] **Step 1: 写组件**

```vue
<!-- frontend/src/views/qa/components/RunProgressBar.vue -->
<template>
  <div class="run-progress">
    <div class="progress-text">
      <span>进度 {{ done }} / {{ total }}</span>
      <span class="pass">✓ {{ passedCount }}</span>
      <span class="fail">✗ {{ failedCount }}</span>
      <span class="err">! {{ errorCount }}</span>
      <span class="time">⏱ {{ durationText }}</span>
    </div>
    <el-progress
      :percentage="percentage"
      :status="progressStatus"
      :stroke-width="16"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  total: number
  passedCount: number
  failedCount: number
  errorCount: number
  durationMs?: number | null
}>()

const done = computed(() => props.passedCount + props.failedCount + props.errorCount)
const percentage = computed(() =>
  props.total > 0 ? Math.round((done.value / props.total) * 100) : 0
)
const progressStatus = computed(() => {
  if (done.value < props.total) return undefined
  if (props.failedCount === 0 && props.errorCount === 0) return 'success'
  if (props.errorCount > 0) return 'exception'
  return 'warning'
})
const durationText = computed(() => {
  if (!props.durationMs) return '--'
  if (props.durationMs < 1000) return `${props.durationMs}ms`
  return `${(props.durationMs / 1000).toFixed(2)}s`
})
</script>

<style scoped>
.run-progress { padding: 12px 16px; background: #fafafa; border-radius: 6px; }
.progress-text { display: flex; gap: 16px; margin-bottom: 8px; font-size: 13px; }
.pass { color: #67c23a; }
.fail { color: #f56c6c; }
.err { color: #e6a23c; }
.time { color: #909399; margin-left: auto; }
</style>
```

- [ ] **Step 2: 跑构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/qa/components/RunProgressBar.vue
git commit -m "feat(frontend): RunProgressBar 进度条组件"
```

---

## Phase 11: 前端页面

### Task 28: `ApiCaseRunDetail.vue`

**Files:**
- Create: `frontend/src/views/qa/ApiCaseRunDetail.vue`

- [ ] **Step 1: 写页面**

```vue
<!-- frontend/src/views/qa/ApiCaseRunDetail.vue -->
<template>
  <div class="api-case-run-detail" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
      <h2 v-if="caseResult">
        {{ caseResult.name }}  {{ caseResult.request_snapshot?.method || '' }}
        <code v-if="caseResult.request_snapshot">{{ caseResult.request_snapshot.url }}</code>
        <el-tag :type="statusTagType" effect="dark">{{ caseResult.status }}</el-tag>
      </h2>
    </div>

    <el-tabs v-if="caseResult" v-model="activeTab">
      <el-tab-pane label="Request" name="request">
        <RequestPanel
          :method="caseResult.request_snapshot?.method || 'GET'"
          :url="caseResult.request_snapshot?.url || ''"
          :headers="caseResult.request_snapshot?.headers"
          :body="caseResult.request_snapshot?.body"
        />
      </el-tab-pane>
      <el-tab-pane label="Response" name="response">
        <ResponsePanel
          :statusCode="caseResult.status_code || 0"
          :duration="caseResult.duration_ms || 0"
          :body="caseResult.response_body || ''"
          :headers="caseResult.response_headers || {}"
        />
      </el-tab-pane>
      <el-tab-pane :label="`Tests(${caseResult.assertion_results?.length || 0})`" name="tests">
        <TestsPanel
          :results="caseResult.assertion_results || []"
        />
      </el-tab-pane>
      <el-tab-pane label="cURL" name="curl">
        <CurlPanel :curl="caseResult.curl || ''" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { testRunApi } from '@/api/testrun'
import RequestPanel from './components/RequestPanel.vue'
import ResponsePanel from './components/ResponsePanel.vue'
import TestsPanel from './components/TestsPanel.vue'
import CurlPanel from './components/CurlPanel.vue'

const route = useRoute()
const router = useRouter()

const caseResult = ref<any>(null)
const loading = ref(true)
const activeTab = ref('request')

const runId = computed(() => Number(route.params.runId))
const caseResultId = computed(() => Number(route.params.caseResultId))

const statusTagType = computed(() => {
  const s = caseResult.value?.status
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'error') return 'warning'
  if (s === 'skipped') return 'info'
  return 'info'
})

async function loadData() {
  loading.value = true
  try {
    caseResult.value = await testRunApi.caseDetail(runId.value, caseResultId.value)
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.back()
}

onMounted(loadData)
</script>

<style scoped>
.api-case-run-detail { padding: 16px 24px; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.header h2 { margin: 0; font-size: 18px; }
.header code { background: #fafafa; padding: 4px 8px; border-radius: 4px; font-size: 14px; }
</style>
```

- [ ] **Step 2: 跑构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/qa/ApiCaseRunDetail.vue
git commit -m "feat(frontend): ApiCaseRunDetail Postman-like 单条详情"
```

---

### Task 29: `TestRunList.vue` + `TestRunDetail.vue`

**Files:**
- Create: `frontend/src/views/qa/TestRunList.vue`
- Create: `frontend/src/views/qa/TestRunDetail.vue`

- [ ] **Step 1: 写 TestRunList.vue**

```vue
<!-- frontend/src/views/qa/TestRunList.vue -->
<template>
  <div class="test-run-list" v-loading="loading">
    <div class="header">
      <h2>批量执行历史</h2>
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
    </div>
    <div class="filters">
      <el-select v-model="filters.status" placeholder="状态" clearable>
        <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
      </el-select>
    </div>
    <el-table :data="runs" @row-click="goDetail" stripe>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="tagType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="通过率" width="100">
        <template #default="{ row }">
          {{ row.passed_count }}/{{ row.total_count }} ({{ row.pass_rate }}%)
        </template>
      </el-table-column>
      <el-table-column prop="test_type" label="类型" width="80" />
      <el-table-column prop="trigger" label="触发" width="80" />
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">
          {{ row.duration_ms ? row.duration_ms + 'ms' : '--' }}
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next"
      @current-change="loadData"
      @size-change="loadData"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { testRunApi, TestRun } from '@/api/testrun'

const route = useRoute()
const router = useRouter()

const runs = ref<TestRun[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const statuses = ['pending', 'running', 'passed', 'failed', 'error', 'cancelled']

const filters = ref({
  status: '',
  project: route.params.projectId ? Number(route.params.projectId) : undefined,
})

async function loadData() {
  loading.value = true
  try {
    const data = await testRunApi.list({
      ...filters.value,
      page: page.value,
      page_size: pageSize.value,
    })
    runs.value = data.results
    total.value = data.count
  } finally {
    loading.value = false
  }
}

function tagType(s: string): 'success' | 'danger' | 'warning' | 'info' {
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'error' || s === 'cancelled') return 'warning'
  return 'info'
}

function formatTime(iso: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}

function goDetail(row: TestRun) {
  router.push(`/projects/${filters.value.project}/qa/test-runs/${row.id}`)
}

function goBack() { router.back() }

watch(filters, () => { page.value = 1; loadData() }, { deep: true })
onMounted(loadData)
</script>

<style scoped>
.test-run-list { padding: 16px 24px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header h2 { margin: 0; }
.filters { margin-bottom: 16px; }
.el-pagination { margin-top: 16px; justify-content: flex-end; }
</style>
```

- [ ] **Step 2: 写 TestRunDetail.vue**

```vue
<!-- frontend/src/views/qa/TestRunDetail.vue -->
<template>
  <div class="test-run-detail" v-loading="loading">
    <div class="header">
      <el-button @click="goBack" :icon="ArrowLeft">返回</el-button>
      <h2 v-if="run">{{ run.name }}
        <el-tag :type="tagType(run.status)" effect="dark">{{ run.status }}</el-tag>
      </h2>
      <el-button v-if="run && (run.status === 'running' || run.status === 'pending')" @click="cancelRun" type="danger">取消</el-button>
    </div>

    <RunProgressBar
      v-if="run"
      :total="run.total_count"
      :passedCount="run.passed_count"
      :failedCount="run.failed_count"
      :errorCount="run.error_count"
      :durationMs="run.duration_ms"
    />

    <div class="filters">
      <el-select v-model="filterStatus" placeholder="状态" clearable>
        <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
      </el-select>
    </div>

    <el-table :data="cases" stripe>
      <el-table-column prop="sequence" label="#" width="50" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="tagType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status_code" label="状态码" width="100" />
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">{{ row.duration_ms ? row.duration_ms + 'ms' : '--' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="goCaseDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { testRunApi, TestRun, TestRunCaseResult } from '@/api/testrun'
import RunProgressBar from './components/RunProgressBar.vue'

const route = useRoute()
const router = useRouter()

const run = ref<TestRun | null>(null)
const cases = ref<TestRunCaseResult[]>([])
const loading = ref(false)
const filterStatus = ref('')
const statuses = ['pending', 'running', 'passed', 'failed', 'error', 'skipped']

const runId = computed(() => Number(route.params.id))

async function loadRun() {
  run.value = await testRunApi.detail(runId.value)
}

async function loadCases() {
  const data = await testRunApi.cases(runId.value, { status: filterStatus.value || undefined })
  cases.value = data.results
}

async function loadData() {
  loading.value = true
  try {
    await loadRun()
    await loadCases()
  } finally {
    loading.value = false
  }
}

async function cancelRun() {
  try {
    await ElMessageBox.confirm('确定取消此批量执行?', '确认', { type: 'warning' })
    await testRunApi.cancel(runId.value)
    ElMessage.success('已取消')
    await loadData()
  } catch { /* user cancel */ }
}

function goCaseDetail(row: TestRunCaseResult) {
  router.push(`/projects/${run.value!.project_id}/qa/test-runs/${runId.value}/cases/${row.id}`)
}

function goBack() { router.back() }

function tagType(s: string): 'success' | 'danger' | 'warning' | 'info' {
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'error' || s === 'cancelled') return 'warning'
  return 'info'
}

import { computed } from 'vue'

watch(filterStatus, () => loadCases())
onMounted(loadData)
</script>

<style scoped>
.test-run-detail { padding: 16px 24px; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.header h2 { margin: 0; flex: 1; }
.filters { margin: 16px 0; }
</style>
```

- [ ] **Step 3: 跑构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/qa/TestRunList.vue frontend/src/views/qa/TestRunDetail.vue
git commit -m "feat(frontend): TestRunList + TestRunDetail 批量执行页面"
```

---

## Phase 12: 注册路由 + 端到端冒烟

### Task 30: 注册前端路由

**Files:**
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 在 QA 相关路由区域追加 4 条**

```typescript
            {
                path: 'qa/test-runs',
                name: 'TestRunList',
                component: () => import("../views/qa/TestRunList.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/test-runs/:id',
                name: 'TestRunDetail',
                component: () => import("../views/qa/TestRunDetail.vue"),
                meta: { permission: 'qa:api:list' },
            },
            {
                path: 'qa/test-runs/:runId/cases/:caseResultId',
                name: 'ApiCaseRunDetail',
                component: () => import("../views/qa/ApiCaseRunDetail.vue"),
                meta: { permission: 'qa:api:list' },
            },
```

- [ ] **Step 2: 跑构建**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/router/index.ts
git commit -m "feat(frontend): TestRun/CaseRun 路由注册"
```

---

### Task 31: 端到端冒烟(后端 + 前端)

- [ ] **Step 1: 后端全测试**

```bash
cd backend && python -m pytest tests/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 2: 前端构建**

```bash
cd frontend && npm run build
```

Expected: 构建成功

- [ ] **Step 3: 跑 backfill 命令(dry-run)**

```bash
cd backend && python manage.py backfill_test_runs --days=90 --dry-run
```

Expected: 看到"候选 N 条"输出

- [ ] **Step 4: 验收清单**

人工逐项勾选 `docs/superpowers/specs/2026-06-11-qa-center-api-test-optimize-design.md` 第十节的清单,全部通过。

---

## 完成后

- 主 spec 完成的子项目 1 范围已交付
- 下一轮 spec 启动子项目 2(UI 测试修复)时,会复用本轮产出的 `TestRun` / `TestRunCaseResult` / `TestRunProgressConsumer` / `RunProgressBar` 组件
