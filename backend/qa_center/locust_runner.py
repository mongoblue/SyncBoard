"""
LocustRunner — 纯 Locust 子进程适配器（生产级 metrics pipeline）。

职责边界：
    - 动态生成 locustfile（Python 源码写入 perf_runs/{execution_id}/）
    - 管理 Locust 子进程生命周期（Popen / terminate / kill）
    - 提供被动指标读取接口（从 JSON 文件读取，原子写保证）
    - 管理执行产物目录（metrics.json / report.html / stats.csv / failures.csv / metadata.json）

不包含：
    - 业务判定（pass/fail）           → ExecutionEngine
    - 回调 / 事件通知                 → ExecutionWorker
    - 并发控制（semaphore）           → ExecutionEngine
    - 结果持久化                      → ExecutionEngine

设计目标：可替换的执行器，为后续 Kubernetes Job / Docker 容器执行器预留接口。
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from .semaphore import get_available_port
from .execution.runner import BaseRunner
from .execution.constants import (
    LOCUST_NOT_STARTED,
    METRICS_NOT_CREATED,
    METRICS_EMPTY,
    METRICS_PARSE_ERROR,
    LOCUST_PROCESS_EXITED,
    LOCUST_RUNNING_NO_REQUESTS,
    LOCUST_RUNNING_WITH_REQUESTS,
    METRICS_FILE_CREATION_TIMEOUT,
)

if TYPE_CHECKING:
    from .execution.process_manager import HardTimeoutWatchdog

logger = logging.getLogger(__name__)

# ── 敏感字段脱敏 ─────────────────────────────────────────────────

_SENSITIVE_HEADERS = frozenset({
    'authorization', 'cookie', 'set-cookie', 'x-api-key',
    'x-auth-token', 'proxy-authorization',
})

_SENSITIVE_KEYS = frozenset({
    'token', 'password', 'secret', 'api_key', 'apikey',
    'access_token', 'refresh_token', 'private_key',
})


def _mask_sensitive(data: Any, depth: int = 0) -> Any:
    """递归脱敏 dict/list 中的敏感字段。"""
    if depth > 10:
        return data
    if isinstance(data, dict):
        return {
            k: '***' if _is_sensitive_key(k) else _mask_sensitive(v, depth + 1)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_sensitive(item, depth + 1) for item in data]
    if isinstance(data, str) and len(data) > 64:
        # 长字符串可能是 token，截断 + 掩码
        for kw in _SENSITIVE_KEYS:
            if kw in data.lower():
                return data[:8] + '***' + data[-4:] if len(data) > 16 else '***'
    return data


def _is_sensitive_key(key: str) -> bool:
    """判断 key 是否为敏感字段名。"""
    # 标准化：去连字符、下划线、空格统一为下划线，小写
    norm = key.lower().replace('-', '_').replace(' ', '_')
    # 同时检查原始敏感集合（已标准化为下划线形式）
    for s in _SENSITIVE_HEADERS:
        if s.replace('-', '_') == norm:
            return True
    for s in _SENSITIVE_KEYS:
        if s.replace('-', '_') == norm:
            return True
    return False

# ── 产物目录基础路径 ──────────────────────────────────────────────


def _get_artifact_base_dir() -> str:
    """获取产物目录基础路径。"""
    return os.path.join(os.getcwd(), 'perf_runs')


class LocustRunner(BaseRunner):
    """Locust 子进程适配器 —— 可替换执行器 (v1 LocalRunner)。

    产物目录结构::

        perf_runs/{execution_id}/
            locustfile.py
            metrics.json
            stdout.log
            stderr.log
            report.html          (Locust --html)
            stats.csv            (Locust --csv)
            failures.csv         (Locust --csv)
            metadata.json

    使用方式::

        runner = LocustRunner(execution_id=42)
        locustfile = runner.generate_locustfile(test_case, runner.metrics_file_path)
        ok = runner.start_test(test_case, 'https://api.example.com', users=10, spawn_rate=2, run_time='60s')
        while runner.is_running():
            stats = runner.read_stats()
            push_to_frontend(stats)
            time.sleep(0.5)
        final = runner.read_full_payload()
        runner.stop_test()
    """

    def __init__(self, execution_id: Optional[int] = None, port_offset: int = 0):
        self.execution_id = execution_id
        self.port_offset = port_offset

        # 子进程状态
        self.process: Optional[subprocess.Popen] = None
        self.locustfile_path: Optional[str] = None
        self.metrics_file_path: Optional[str] = None

        # ── 产物目录 ──────────────────────────────────────────
        suffix = self.execution_id if self.execution_id is not None else os.getpid()
        self._artifact_dir = os.path.join(_get_artifact_base_dir(), str(suffix))

        # ── 诊断信息（start_test 后填充） ──────────────────────
        self._diagnostic: Dict[str, Any] = {}
        self._stdout_log_path: Optional[str] = None
        self._stderr_log_path: Optional[str] = None
        self._start_time: Optional[float] = None
        self._last_read_error: Optional[str] = None

        # ── 进程管理 ──────────────────────────────────────────
        self._watchdog: Optional[HardTimeoutWatchdog] = None
        self._resource_snapshot: Dict[str, Any] = {}

    # ── 产物目录管理 ──────────────────────────────────────────────

    @property
    def artifact_dir(self) -> str:
        return self._artifact_dir

    def ensure_artifact_dir(self) -> str:
        """创建产物目录并返回路径。"""
        os.makedirs(self._artifact_dir, exist_ok=True)
        return self._artifact_dir

    # ── locustfile 生成 ────────────────────────────────────────────

    def generate_locustfile(self, test_case, metrics_file: str) -> str:
        """生成 Locust 测试文件（支持单接口/多步骤场景）。

        新增能力：
        - 多步骤场景 + 变量提取与引用 ({{var}})
        - 认证配置 (Bearer / Basic / Cookie)
        - 请求体类型 (json / form / raw)
        - 负载模型 (ramp-up / rate-limit / think-time)
        - 断言 (status_code / response_time / body / JSONPath / p95 / throughput)
        - 步骤级指标
        """
        self.ensure_artifact_dir()

        metrics_file_escaped = metrics_file.replace('\\', '\\\\')
        metrics_tmp = metrics_file + '.tmp'

        # ── 判断场景类型 ──────────────────────────────────────
        steps_raw = getattr(test_case, 'steps', None) or []
        has_steps = bool(steps_raw and len(steps_raw) > 0)

        # ── 构建步骤代码 ──────────────────────────────────────
        if has_steps:
            steps_code, step_names, extractors = self._build_steps_code(steps_raw)
        else:
            steps_code, step_names, extractors = self._build_single_step_code(test_case)

        # ── 认证代码 ──────────────────────────────────────────
        auth_code = self._build_auth_code(test_case)

        # ── 断言代码 ──────────────────────────────────────────
        assertions_code = self._build_assertions_code(test_case)

        # ── 负载参数 ──────────────────────────────────────────
        ramp_up = getattr(test_case, 'ramp_up_seconds', None) or 10
        rps_limit = getattr(test_case, 'requests_per_second', None)
        think_min = getattr(test_case, 'think_time_min', None) or 0.1
        think_max = getattr(test_case, 'think_time_max', None) or 0.5

        # ── 组装 Locust 脚本 ──────────────────────────────────
        locust_code = self._render_locustfile(
            metrics_file_escaped=metrics_file_escaped,
            metrics_tmp=metrics_tmp,
            steps_code=steps_code,
            step_names=step_names,
            auth_code=auth_code,
            assertions_code=assertions_code,
            ramp_up=ramp_up,
            rps_limit=rps_limit,
            think_min=think_min,
            think_max=think_max,
            concurrent_users=getattr(test_case, 'concurrent_users', 10),
        )

        path = os.path.join(self._artifact_dir, 'locustfile.py')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(locust_code)

        self.locustfile_path = path
        logger.info("locustfile 已生成: %s (steps=%d)", path, len(step_names))
        return path

    # ── 步骤构建 ────────────────────────────────────────────────

    def _build_single_step_code(self, test_case) -> tuple:
        """构建单步骤场景的代码。"""
        url = getattr(test_case, 'url', '/')
        method = getattr(test_case, 'method', 'GET') or 'GET'
        headers = getattr(test_case, 'headers', {}) or {}
        body = getattr(test_case, 'body', '') or ''
        body_type = getattr(test_case, 'body_type', 'json') or 'json'
        query_params = getattr(test_case, 'query_params', {}) or {}
        timeout = getattr(test_case, 'request_timeout', 30) or 30
        follow_redirects = getattr(test_case, 'follow_redirects', True)
        verify_ssl = getattr(test_case, 'verify_ssl', True)

        step = {
            'name': 'main',
            'url': url,
            'method': method,
            'headers': headers,
            'body': body,
            'body_type': body_type,
            'query_params': query_params,
            'timeout': timeout,
            'follow_redirects': follow_redirects,
            'verify_ssl': verify_ssl,
        }
        return self._build_steps_code([step])

    def _build_steps_code(self, steps: list) -> tuple:
        """构建多步骤场景 Python 代码。

        Returns:
            (code_str, step_names, extractor_map)
        """
        import json as _json

        lines = []
        step_names = []
        extractors = {}

        for i, step in enumerate(steps):
            name = step.get('name', f'step_{i+1}')
            url = step.get('url', '/')
            method = (step.get('method') or 'GET').upper()
            headers = step.get('headers', {}) or {}
            body = step.get('body', '') or ''
            body_type = step.get('body_type', 'json') or 'json'
            query_params = step.get('query_params', {}) or {}
            timeout = step.get('timeout', 30) or 30
            follow_redirects = step.get('follow_redirects', True)
            verify_ssl = step.get('verify_ssl', True)
            extract = step.get('extract', {}) or {}
            step_assertions = step.get('assertions', []) or []

            step_names.append(name)
            for var_name, jsonpath in extract.items():
                extractors[var_name] = jsonpath

            # 构建请求参数
            headers_code = self._render_headers(headers)
            body_code = self._render_body(body, body_type)
            query_code = self._render_query_params(query_params)
            req_kwargs = self._render_request_kwargs(timeout, follow_redirects, verify_ssl)

            url_var = self._render_url(url)
            name_var = repr(name)

            lines.append(f'''
    # ── Step {i+1}: {name} ────────────────────────────────
    _url_{i} = _resolve_vars({url_var}, ctx)
    _headers_{i} = _resolve_headers({headers_code}, ctx)
    _body_{i} = _resolve_body({body_code}, ctx)
''')

            if query_code != 'None':
                lines.append(f'    _params_{i} = _resolve_vars({query_code}, ctx)')
            else:
                lines.append(f'    _params_{i} = None')

            # 请求调用
            lines.append(f'''
    _start = time.perf_counter()
    try:
        _resp = _request(
            method={repr(method)},
            url=_url_{i},
            headers=_headers_{i},
            data=_body_{i},
            params=_params_{i},
            name={name_var},
            kwargs={{{req_kwargs}}},
        )
        _elapsed = (time.perf_counter() - _start) * 1000
        _ok = True
    except Exception as _exc:
        _elapsed = (time.perf_counter() - _start) * 1000
        _ok = False
        _resp = None
        _error_msg = str(_exc)[:200]
        _record_failure({name_var}, _error_msg, _elapsed)
''')

            # 成功后提取变量
            if extract:
                lines.append(f'    if _ok and _resp is not None:')
                lines.append(f'        _body_text = _resp.text')
                for var_name, jsonpath in extract.items():
                    lines.append(f'        ctx[{repr(var_name)}] = _extract_jsonpath(_body_text, {repr(jsonpath)})')

            # 步骤级断言
            if step_assertions:
                for ass in step_assertions:
                    ass_code = self._render_single_assertion(ass, name_var)
                    if ass_code:
                        lines.append(f'    {ass_code}')

            # 步骤关闭
            lines.append(f'''
    _record_step({name_var}, _ok, _elapsed, _resp.status_code if _resp else 0)
''')

        return '\n'.join(lines), step_names, extractors

    # ── 认证代码 ────────────────────────────────────────────────

    def _build_auth_code(self, test_case) -> str:
        """生成认证相关代码。"""
        auth = getattr(test_case, 'auth_config', None) or {}
        if not auth or not auth.get('type'):
            return ''

        auth_type = auth.get('type', '')

        if auth_type == 'bearer':
            token = auth.get('token', '')
            # 支持环境变量引用
            if token.startswith('{{') and token.endswith('}}'):
                env_var = token[2:-2].strip()
                return f'''
# ── Bearer Token 认证 ──────────────────────────────────
_AUTH_TOKEN = os.environ.get({repr(env_var)}, "")
_AUTH_HEADER = {{"Authorization": f"Bearer {{_AUTH_TOKEN}}"}}
'''
            else:
                # 安全：使用 repr() 转义 token 中的特殊字符
                safe_token = repr(token)
                return f'''
# ── Bearer Token 认证 ──────────────────────────────────
_AUTH_HEADER = {{"Authorization": "Bearer {safe_token}"}}
'''

        elif auth_type == 'basic':
            username = auth.get('username', '')
            password = auth.get('password', '')
            import base64
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            return f'''
# ── Basic Auth 认证 ────────────────────────────────────
_AUTH_HEADER = {{"Authorization": "Basic {encoded}"}}
'''

        return ''

    # ── 断言代码 ────────────────────────────────────────────────

    def _build_assertions_code(self, test_case) -> str:
        """生成场景级断言代码。"""
        assertions = getattr(test_case, 'assertions', None) or []
        if not assertions:
            return ''

        lines = ['def _check_assertions(metrics):', '    """场景级断言检查。"""', '    results = []']
        for ass in assertions:
            code = self._render_assertion_check(ass)
            if code:
                lines.append(f'    {code}')
        lines.append('    return results')
        return '\n'.join(lines)

    def _render_single_assertion(self, ass: dict, step_name: str) -> str:
        """渲染单个步骤断言。"""
        typ = ass.get('type', '')
        op = ass.get('op', 'eq')
        expect = ass.get('expect')

        if typ == 'status_code':
            if op in ('in', 'contains'):
                return f'_assert_status_in(_resp, {expect}, {step_name})'
            else:
                return f'_assert_status_eq(_resp, {expect}, {step_name})'
        elif typ == 'response_time':
            return f'_assert_response_time(_elapsed, {expect}, {step_name})'
        elif typ == 'body_contains':
            return f'_assert_body_contains(_resp, {repr(expect)}, {step_name})'
        elif typ == 'jsonpath':
            path = ass.get('path', '$')
            return f'_assert_jsonpath(_resp, {repr(path)}, {repr(op)}, {repr(expect)}, {step_name})'
        return ''

    def _render_assertion_check(self, ass: dict) -> str:
        """渲染场景级断言检查。"""
        typ = ass.get('type', '')
        op = ass.get('op', 'lt')
        expect = ass.get('expect')

        if typ == 'p95' and op == 'lt':
            return f'results.append({{"type":"p95","op":"lt","expect":{expect},"actual":metrics.get("p95_response_time",0),"passed":metrics.get("p95_response_time",9999) < {expect}}})'
        elif typ == 'throughput' and op == 'gt':
            return f'results.append({{"type":"throughput","op":"gt","expect":{expect},"actual":metrics.get("current_rps",0),"passed":metrics.get("current_rps",0) > {expect}}})'
        elif typ == 'error_rate' and op == 'lt':
            return f'results.append({{"type":"error_rate","op":"lt","expect":{expect},"actual":metrics.get("error_rate",0),"passed":metrics.get("error_rate",100) < {expect}}})'
        return ''

    # ── 渲染辅助 ────────────────────────────────────────────────

    def _render_url(self, url: str) -> str:
        """处理 URL 中的变量引用。"""
        if '{{' in url:
            return repr(url)
        return repr(url)

    def _render_headers(self, headers: dict) -> str:
        """渲染请求头为 Python dict。"""
        if not headers:
            return '{}'
        import json as _json
        return _json.dumps(headers, ensure_ascii=False)

    def _render_body(self, body: str, body_type: str) -> str:
        """安全渲染请求体 — 所有用户输入通过序列化处理，禁止直接拼接。

        json.dumps(parsed) 生成的 JSON 字符串即是合法的 Python 字面量
        （对于 list/dict/str/int），null/true/false 由 repr() 转换为 None/True/False。
        """
        if not body:
            return 'None'
        import json as _json
        try:
            parsed = _json.loads(body)
        except (_json.JSONDecodeError, ValueError):
            parsed = body
        # null/true/false → None/True/False
        if parsed is None:
            safe_value = 'None'
        elif isinstance(parsed, bool):
            safe_value = repr(parsed)
        else:
            safe_value = _json.dumps(parsed, ensure_ascii=False)
        if body_type == 'json':
            return f"json.dumps({safe_value}, ensure_ascii=False).encode('utf-8')"
        elif body_type == 'form':
            return f"{safe_value}.encode('utf-8')"
        else:
            return f"{safe_value}.encode('utf-8')"

    def _render_query_params(self, params: dict) -> str:
        """渲染 query 参数。"""
        if not params:
            return 'None'
        import json as _json
        return _json.dumps(params, ensure_ascii=False)

    def _render_request_kwargs(self, timeout: int, follow_redirects: bool, verify_ssl: bool) -> str:
        """渲染 requests 额外参数。"""
        parts = [f'"timeout":{timeout}']
        if not follow_redirects:
            parts.append('"allow_redirects":False')
        if not verify_ssl:
            parts.append('"verify":False')
        return ', '.join(parts)

    def _render_locustfile(
        self, metrics_file_escaped, metrics_tmp, steps_code, step_names,
        auth_code, assertions_code, ramp_up, rps_limit, think_min, think_max,
        concurrent_users,
    ) -> str:
        """渲染完整的 Locust 脚本。"""
        step_names_list = repr(step_names)
        rps_limit_code = f'_RPS_LIMIT = {rps_limit}' if rps_limit else '_RPS_LIMIT = None'

        artifact_dir_safe = self._artifact_dir.replace('\\', '/')

        return f'''# -*- coding: utf-8 -*-
"""SyncBoard 自动生成的 Locust 压测脚本。

产物目录: {artifact_dir_safe}
步骤: {step_names_list}
"""
from locust import HttpUser, task, between, events, LoadTestShape
import json
import os
import threading
import time
import re

# ── 指标配置 ──────────────────────────────────────────────────
METRICS_FILE = r"{metrics_file_escaped}"
METRICS_TMP = r"{metrics_tmp}"
_STEP_NAMES = {step_names_list}
{rps_limit_code}

{auth_code}

# ── 全局指标数据 ──────────────────────────────────────────────
_metrics_lock = threading.Lock()
_metrics_data = {{
    'state': 'running',
    'start_time': time.time(),
    'total_requests': 0,
    'successful_requests': 0,
    'failed_requests': 0,
    'response_times': [],
    'errors': [],
    'throughput_series': [],
    'response_time_series': [],
    'error_rate_series': [],
    'per_endpoint': {{}},
    'step_stats': {{s: {{'total':0,'success':0,'failed':0,'times':[]}} for s in _STEP_NAMES}},
    'last_sample_time': 0.0,
    'last_total_requests': 0,
    'last_failed_requests': 0,
}}


def _write_metrics_atomic():
    """原子写入 metrics.json。"""
    try:
        with _metrics_lock:
            data = _metrics_data.copy()

        times = sorted(data['response_times'])
        if times:
            n = len(times)
            avg_time = sum(times) / n
            p50 = times[int(n * 0.5)] if n > 0 else 0
            p90 = times[int(n * 0.9)] if n > 0 else 0
            p95 = times[int(n * 0.95)] if n > 0 else 0
            p99 = times[int(n * 0.99)] if n > 0 else 0
            min_time, max_time = times[0], times[-1]
        else:
            avg_time = p50 = p90 = p95 = p99 = min_time = max_time = 0

        now = time.time()
        elapsed = now - data['start_time']
        total = data['total_requests']
        failed = data['failed_requests']
        throughput = total / elapsed if elapsed > 0 else 0
        error_rate = (failed / total * 100) if total > 0 else 0

        if now - data['last_sample_time'] >= 1.0:
            delta_reqs = total - data['last_total_requests']
            delta_failed = failed - data['last_failed_requests']
            delta_t = now - data['last_sample_time'] if data['last_sample_time'] else 1.0
            instant_rps = delta_reqs / delta_t if delta_t > 0 else 0
            instant_error_rate = (delta_failed / delta_reqs * 100) if delta_reqs > 0 else 0
            data['throughput_series'].append({{'t': round(now - data['start_time'], 1), 'rps': round(instant_rps, 2)}})
            data['response_time_series'].append({{'t': round(now - data['start_time'], 1), 'avg': round(avg_time, 2), 'p95': round(p95, 2)}})
            data['error_rate_series'].append({{'t': round(now - data['start_time'], 1), 'error_rate': round(instant_error_rate, 2)}})
            for key in ('throughput_series', 'response_time_series', 'error_rate_series'):
                if len(data[key]) > 600:
                    data[key] = data[key][-600:]
            data['last_sample_time'] = now
            data['last_total_requests'] = total
            data['last_failed_requests'] = failed

        distribution = {{}}
        if times:
            for rt in times:
                bucket = min(int(rt // 50), 39)
                key = f"{{bucket * 50}}-{{(bucket + 1) * 50}}ms"
                distribution[key] = distribution.get(key, 0) + 1

        per_endpoint = {{}}
        for ep, ep_data in data['per_endpoint'].items():
            ep_times = sorted(ep_data.get('times', []))
            et = ep_data.get('total', 0)
            ef = ep_data.get('failed', 0)
            per_endpoint[ep] = {{
                'total_requests': et, 'successful_requests': ep_data.get('success', 0),
                'failed_requests': ef, 'avg_response_time': round(sum(ep_times)/len(ep_times),2) if ep_times else 0,
                'p95_response_time': round(ep_times[int(len(ep_times)*0.95)],2) if ep_times else 0,
                'error_rate': round((ef/et*100),2) if et > 0 else 0,
            }}

        step_stats = {{}}
        for sn, ss in data['step_stats'].items():
            ss_times = sorted(ss.get('times', []))
            st = ss.get('total', 0)
            sf = ss.get('failed', 0)
            step_stats[sn] = {{
                'total_requests': st, 'successful_requests': ss.get('success', 0),
                'failed_requests': sf, 'p95_response_time': round(ss_times[int(len(ss_times)*0.95)],2) if ss_times else 0,
                'avg_response_time': round(sum(ss_times)/len(ss_times),2) if ss_times else 0,
                'error_details': ss.get('errors', [])[-10:],
            }}

        output = {{
            'state': data['state'], 'generated_at': now,
            'total_requests': total, 'successful_requests': data['successful_requests'],
            'failed_requests': failed, 'avg_response_time': round(avg_time, 2),
            'min_response_time': round(min_time, 2), 'max_response_time': round(max_time, 2),
            'p50_response_time': round(p50, 2), 'p90_response_time': round(p90, 2),
            'p95_response_time': round(p95, 2), 'p99_response_time': round(p99, 2),
            'current_rps': round(throughput, 2), 'error_rate': round(error_rate, 2),
            'elapsed_seconds': round(elapsed, 1), 'errors': data['errors'][-20:],
            'per_endpoint': per_endpoint, 'step_stats': step_stats,
            'throughput_over_time': list(data['throughput_series']),
            'response_time_over_time': list(data['response_time_series']),
            'error_rate_over_time': list(data['error_rate_series']),
            'response_time_distribution': distribution, 'timestamp': time.time(),
        }}

        tmp_content = json.dumps(output, ensure_ascii=False)
        with open(METRICS_TMP, 'w', encoding='utf-8') as f:
            f.write(tmp_content); f.flush(); os.fsync(f.fileno())
        os.replace(METRICS_TMP, METRICS_FILE)
    except Exception as e:
        print(f"[Locust] 写入指标失败: {{e}}")


# ── 辅助函数 ──────────────────────────────────────────────────

def _resolve_vars(template, ctx):
    """替换模板中的 {{{{var}}}} 变量。"""
    if not isinstance(template, str):
        return template
    def _repl(m):
        key = m.group(1).strip()
        return str(ctx.get(key, m.group(0)))
    return re.sub(r'{{{{(.+?)}}}}', _repl, template)

def _resolve_headers(headers, ctx):
    return {{k: _resolve_vars(v, ctx) for k, v in (headers or {{}}).items()}}

def _resolve_body(body_data, ctx):
    if body_data is None:
        return None
    if isinstance(body_data, str):
        return _resolve_vars(body_data, ctx).encode('utf-8')
    return body_data

def _extract_jsonpath(text, path):
    """从 JSON 文本中提取 JSONPath 值（支持 $.token / $.data.id）。"""
    try:
        obj = json.loads(text)
    except Exception:
        return None
    parts = path.lstrip('$').strip('.').split('.')
    cur = obj
    for p in parts:
        if not p:
            continue
        if p.endswith(']') and '[' in p:
            key, idx = p.split('[', 1)
            idx = idx.rstrip(']')
            cur = cur.get(key, {{}}) if key else cur
            try:
                cur = cur[int(idx)]
            except (ValueError, TypeError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
        if cur is None:
            return None
    return cur

def _request(method, url, headers, data, params, name, kwargs):
    """统一的 HTTP 请求封装。"""
    kw = dict(kwargs) if kwargs else {{}}
    timeout_val = kw.pop('timeout', 30)
    allow_redirects = kw.pop('allow_redirects', True)
    verify = kw.pop('verify', True)
    import requests as _req
    return _req.request(
        method=method, url=url, headers=headers, data=data, params=params,
        timeout=timeout_val, allow_redirects=allow_redirects, verify=verify,
    )

def _record_failure(name, error_msg, elapsed):
    """记录请求失败。"""
    with _metrics_lock:
        _metrics_data['failed_requests'] += 1
        _metrics_data['total_requests'] += 1
        _metrics_data['response_times'].append(elapsed)
        if name in _metrics_data['step_stats']:
            _metrics_data['step_stats'][name]['total'] += 1
            _metrics_data['step_stats'][name]['failed'] += 1
            _metrics_data['step_stats'][name]['times'].append(elapsed)
            _metrics_data['step_stats'][name].setdefault('errors', []).append(
                {{'message': error_msg, 'time': time.time()}}
            )
        if name not in _metrics_data['per_endpoint']:
            _metrics_data['per_endpoint'][name] = {{'total':0,'success':0,'failed':0,'times':[]}}
        _metrics_data['per_endpoint'][name]['total'] += 1
        _metrics_data['per_endpoint'][name]['failed'] += 1
        _metrics_data['per_endpoint'][name]['times'].append(elapsed)

def _record_step(name, ok, elapsed, status_code):
    """记录步骤完成。"""
    with _metrics_lock:
        ep = _metrics_data['per_endpoint'].setdefault(name, {{'total':0,'success':0,'failed':0,'times':[]}})
        ss = _metrics_data['step_stats'].setdefault(name, {{'total':0,'success':0,'failed':0,'times':[]}})
        if ok:
            _metrics_data['total_requests'] += 1
            _metrics_data['successful_requests'] += 1
            ep['total'] += 1; ep['success'] += 1
            ss['total'] += 1; ss['success'] += 1
        _metrics_data['response_times'].append(elapsed)
        ep['times'].append(elapsed)
        ss['times'].append(elapsed)
        if len(_metrics_data['response_times']) > 10000:
            _metrics_data['response_times'] = _metrics_data['response_times'][-5000:]

{assertions_code}

# ── 步骤断言函数 ──────────────────────────────────────────────

def _assert_status_in(resp, codes, step_name):
    if resp is None or resp.status_code not in codes:
        _record_failure(step_name, f'status_code not in {{codes}}', 0)

def _assert_status_eq(resp, code, step_name):
    if resp is None or resp.status_code != code:
        _record_failure(step_name, f'status_code != {{code}}', 0)

def _assert_response_time(elapsed, max_ms, step_name):
    if elapsed > max_ms:
        _record_failure(step_name, f'response_time {{elapsed:.0f}}ms > {{max_ms}}ms', elapsed)

def _assert_body_contains(resp, text, step_name):
    if resp is None or text not in (resp.text or ''):
        _record_failure(step_name, f'body does not contain expected text', 0)

def _assert_jsonpath(resp, path, op, expect, step_name):
    if resp is None:
        _record_failure(step_name, f'no response for jsonpath check', 0)
        return
    val = _extract_jsonpath(resp.text, path)
    passed = False
    if op == 'exists':
        passed = val is not None
    elif op == 'eq':
        passed = str(val) == str(expect)
    if not passed:
        _record_failure(step_name, f'jsonpath {{path}} assertion failed', 0)


# ── Locust 事件 ────────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("[Locust] 测试开始")
    with _metrics_lock:
        _metrics_data['state'] = 'running'
        _metrics_data['start_time'] = time.time()
    _write_metrics_atomic()

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("[Locust] 测试结束")
    with _metrics_lock:
        _metrics_data['state'] = 'completed'
    _write_metrics_atomic()


# ── 负载模型 (Ramp-up + Rate Limit) ──────────────────────────

class PerfTestShape(LoadTestShape):
    """自定义负载模型：支持 ramp-up 和 rate limiting。"""
    def tick(self):
        run_time = self.get_run_time()
        if run_time > {ramp_up}:
            return ({think_min}, {think_max})
        current = int(self.get_current_user_count())
        target = max(1, int(run_time / {ramp_up} * {concurrent_users}))
        if current < target:
            return (target - current, {think_max})
        return None


# ── 用户类 ────────────────────────────────────────────────────

class PerformanceTestUser(HttpUser):
    wait_time = between({think_min}, {think_max})

    def on_start(self):
        self.ctx = {{}}  # 变量上下文（跨步骤共享）
        {self._render_auth_on_start(auth_code)}

    @task(1)
    def test_scenario(self):
        ctx = self.ctx
{steps_code}
    _write_metrics_atomic()
'''

    def _render_auth_on_start(self, auth_code: str) -> str:
        """生成 on_start 中的认证初始化代码。"""
        if not auth_code:
            return 'pass'
        return 'pass  # auth headers are set at module level'

    # ── 兼容旧方法名 ──────────────────────────────────────────
    # start_test, stop_test, is_running 等继承自之前的实现

    # ── 子进程启动 ────────────────────────────────────────────────

    def start_test(self, test_case, host: str, users: int = 10,
                   spawn_rate: int = 1, run_time: str = "60s",
                   use_web_ui: bool = False) -> bool:
        """启动 Locust 子进程。

        stdout/stderr → 产物目录日志文件。
        Locust 原生 CSV/HTML 报告 → 产物目录。
        metadata.json → 产物目录。
        """
        if use_web_ui and self.port_offset == 0:
            port = get_available_port()
            if port is not None:
                self.port_offset = port - 8089

        try:
            self.ensure_artifact_dir()

            # ── 指标文件路径 ──────────────────────────────────
            self.metrics_file_path = os.path.join(
                self._artifact_dir, 'metrics.json'
            )
            # 写入初始状态（原子写）
            initial = {'state': 'initializing', 'runner_status': 'starting'}
            tmp_path = self.metrics_file_path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(initial, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.metrics_file_path)

            locustfile_path = self.generate_locustfile(test_case, self.metrics_file_path)

            # ── 解析 run_time ──────────────────────────────────
            run_time_seconds = 60
            if run_time:
                rt = str(run_time).lower().strip()
                if rt.endswith('s'):
                    run_time_seconds = int(rt[:-1])
                elif rt.endswith('m'):
                    run_time_seconds = int(rt[:-1]) * 60
                elif rt.endswith('h'):
                    run_time_seconds = int(rt[:-1]) * 3600
                else:
                    try:
                        run_time_seconds = int(rt)
                    except (ValueError, TypeError):
                        pass

            # ── 计算 target path ───────────────────────────────
            from urllib.parse import urlparse
            parsed = urlparse(test_case.url)
            target_path = parsed.path or '/'
            if parsed.query:
                target_path += '?' + parsed.query

            # ── 日志文件路径 ────────────────────────────────────
            self._stdout_log_path = os.path.join(self._artifact_dir, 'stdout.log')
            self._stderr_log_path = os.path.join(self._artifact_dir, 'stderr.log')

            # ── CSV / HTML 报告路径 ─────────────────────────────
            csv_prefix = os.path.join(self._artifact_dir, 'stats')

            stdout_f = open(self._stdout_log_path, 'w', encoding='utf-8', buffering=1)
            stderr_f = open(self._stderr_log_path, 'w', encoding='utf-8', buffering=1)

            # 写入启动标记
            header = (
                f"=== Locust log — execution_id={self.execution_id} ===\n"
                f"=== Started at: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n"
            )
            stdout_f.write(header)
            stdout_f.flush()
            stderr_f.write(header)
            stderr_f.flush()

            cmd = [
                sys.executable, '-m', 'locust',
                '-f', locustfile_path,
                '--host', host,
                '--users', str(users),
                '--spawn-rate', str(spawn_rate),
                '--run-time', f"{run_time_seconds}s",
                '--csv', csv_prefix,          # 生成 stats.csv + failures.csv
                '--html', os.path.join(self._artifact_dir, 'report.html'),
            ]
            if use_web_ui:
                cmd.extend(['--web-port', str(self.web_port)])
            else:
                cmd.extend(['--headless', '--only-summary'])

            logger.info("Locust 启动: %s", ' '.join(cmd))

            # ── 启动子进程（独立进程组） ────────────────────────
            from .execution.process_manager import _start_process_group, _get_resource_usage
            self.process = _start_process_group(cmd, self._artifact_dir, stdout_f, stderr_f)
            self._start_time = time.time()

            # ── 采集启动时资源快照 ────────────────────────────
            self._resource_snapshot = _get_resource_usage(self.process.pid)
            if self._resource_snapshot.get('cpu_percent') is not None:
                logger.info(
                    "Locust PID=%s 资源: CPU=%.1f%% MEM=%.1fMB",
                    self.process.pid,
                    self._resource_snapshot.get('cpu_percent', 0),
                    self._resource_snapshot.get('memory_mb', 0),
                )

            # ── 后台线程：进程退出后关闭文件句柄 ────────────────
            def _close_logs_on_exit():
                try:
                    self.process.wait()
                except Exception:
                    pass
                finally:
                    try:
                        stdout_f.close()
                    except Exception:
                        pass
                    try:
                        stderr_f.close()
                    except Exception:
                        pass

            closer = threading.Thread(target=_close_logs_on_exit, daemon=True)
            closer.start()

            # ── 写入 metadata.json ──────────────────────────────
            metadata = {
                'execution_id': self.execution_id,
                'locustfile_path': locustfile_path,
                'metrics_file_path': self.metrics_file_path,
                'command': ' '.join(cmd),
                'cwd': self._artifact_dir,
                'pid': self.process.pid,
                'stdout_log_path': self._stdout_log_path,
                'stderr_log_path': self._stderr_log_path,
                'host': host,
                'target_path': target_path,
                'target_url': test_case.url,
                'method': test_case.method,
                'users': users,
                'spawn_rate': spawn_rate,
                'run_time': f"{run_time_seconds}s",
                'run_time_seconds': run_time_seconds,
                'headless': not use_web_ui,
                'start_time_iso': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'start_timestamp': self._start_time,
            }
            meta_path = os.path.join(self._artifact_dir, 'metadata.json')
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            self._diagnostic = metadata

            logger.info(
                "Locust 子进程已启动: execution_id=%s pid=%s users=%s "
                "spawn_rate=%s run_time=%ss host=%s target=%s artifact_dir=%s",
                self.execution_id, self.process.pid,
                users, spawn_rate, run_time_seconds, host, target_path, self._artifact_dir,
            )

            return True

        except Exception as e:
            logger.exception("Locust 启动失败: execution_id=%s", self.execution_id)
            self._diagnostic = {
                'execution_id': self.execution_id,
                'error': str(e),
                'start_error': True,
            }
            return False

    # ── 子进程管理 ────────────────────────────────────────────────

    def stop_test(self) -> bool:
        """终止 Locust 子进程（graceful terminate → kill process group）。

        产物目录保留不删除（供事后查看/下载）。
        """
        try:
            if self.process:
                # ── 取消看门狗 ────────────────────────────────
                if self._watchdog:
                    self._watchdog.cancel()
                    self._watchdog = None

                # ── 采集最终资源快照 ───────────────────────────
                if self.process.pid:
                    from .execution.process_manager import _get_resource_usage
                    final_usage = _get_resource_usage(self.process.pid)
                    self._resource_snapshot.update(final_usage)

                from .execution.process_manager import _terminate_process_group
                _terminate_process_group(self.process, timeout=5.0)

            if self.locustfile_path and os.path.exists(self.locustfile_path):
                try:
                    os.remove(self.locustfile_path)
                except OSError:
                    pass

            self.process = None
            logger.info("Locust 已停止 (execution_id=%s, artifacts=%s)",
                         self.execution_id, self._artifact_dir)
            return True

        except Exception as e:
            logger.error("Locust 停止失败: %s (execution_id=%s)", e, self.execution_id)
            return False

    def is_running(self) -> bool:
        """检查子进程是否仍在运行。"""
        if self.process is None:
            return False
        return self.process.poll() is None

    def exit_code(self) -> Optional[int]:
        """获取子进程退出码（如果已退出），否则返回 None。"""
        if self.process is None:
            return None
        return self.process.poll()

    # ── 看门狗管理 ──────────────────────────────────────────

    def start_watchdog(self, max_runtime: float, on_timeout: callable = None) -> None:
        """启动硬超时看门狗。"""
        if self.process is None:
            return
        from .execution.process_manager import HardTimeoutWatchdog
        self._watchdog = HardTimeoutWatchdog(
            process=self.process,
            max_runtime=max_runtime,
            execution_id=self.execution_id or 0,
            on_timeout=on_timeout,
        )
        self._watchdog.start()

    def cancel_watchdog(self) -> None:
        """取消看门狗。"""
        if self._watchdog:
            self._watchdog.cancel()
            self._watchdog = None

    @property
    def watchdog_triggered(self) -> bool:
        return self._watchdog.triggered if self._watchdog else False

    def get_resource_usage(self) -> Dict[str, Any]:
        """获取当前资源使用快照。"""
        if self.process and self.process.pid:
            from .execution.process_manager import _get_resource_usage
            current = _get_resource_usage(self.process.pid)
            self._resource_snapshot.update(current)
        return dict(self._resource_snapshot)

    # ── 指标读取（统一 schema） ──────────────────────────────────

    def read_stats(self) -> Dict[str, Any]:
        """读取当前性能指标快照。

        统一返回 schema::

            {
                "ok": true/false,
                "runner_status": "locust_not_started | ...",
                "metrics_status": "ok | not_created | empty | parse_error | ...",
                "stats": { ... },           # 仅 ok=true 时有值
                "diagnostics": { ... }      # 执行上下文
            }
        """
        if self.process is None and self.metrics_file_path is None:
            return self._unified_response(
                ok=False,
                runner_status=LOCUST_NOT_STARTED,
                metrics_status='no_runner',
                diagnostics={'message': 'LocustRunner 尚未调用 start_test()'},
            )

        return self._read_metrics_file()

    def read_full_payload(self) -> Dict[str, Any]:
        """读取完整指标（含时间序列、per-endpoint、错误分类），附加诊断信息。"""
        if self.process is None and self.metrics_file_path is None:
            return self._unified_response(
                ok=False,
                runner_status=LOCUST_NOT_STARTED,
                metrics_status='no_runner',
                diagnostics={
                    'message': 'LocustRunner 尚未调用 start_test()',
                    **self.get_diagnostic_info(),
                },
            )

        result = self._read_metrics_file()
        # 合并完整诊断信息
        result['diagnostics'] = {
            **result.get('diagnostics', {}),
            **self.get_diagnostic_info(),
        }
        return result

    def _unified_response(
        self,
        ok: bool,
        runner_status: str,
        metrics_status: str = '',
        stats: Optional[Dict[str, Any]] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        **extra,
    ) -> Dict[str, Any]:
        """构建统一 schema 的响应。"""
        return {
            'ok': ok,
            'runner_status': runner_status,
            'metrics_status': metrics_status,
            'stats': stats or self._empty_stats(),
            'diagnostics': diagnostics or {},
            'timestamp': time.time(),
            **extra,
        }

    @staticmethod
    def _empty_stats() -> Dict[str, Any]:
        """空指标占位（当 ok=False 时使用）。"""
        return {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'current_rps': 0,
            'avg_response_time': 0,
            'min_response_time': 0,
            'max_response_time': 0,
            'p50_response_time': 0,
            'p90_response_time': 0,
            'p95_response_time': 0,
            'p99_response_time': 0,
            'error_rate': 0,
            'errors': [],
            'per_endpoint': {},
            'throughput_over_time': [],
            'response_time_over_time': [],
            'error_rate_over_time': [],
            'response_time_distribution': {},
        }

    def _read_metrics_file(self) -> Dict[str, Any]:
        """从 JSON 文件读取指标并包装为统一 schema。

        区分以下 metrics_status：
        - ok: 正常读取
        - not_created: 文件不存在（超过 CREATION_TIMEOUT 则确认）
        - empty: 文件为空
        - parse_error: JSON 解析失败
        - process_exited: 子进程已退出但文件无有效数据
        """
        # ── 进程已退出 ────────────────────────────────────────
        exit_code = self.exit_code()
        if self.process is not None and exit_code is not None:
            final_metrics = self._try_read_metrics_json()
            if final_metrics:
                return self._unified_response(
                    ok=True,
                    runner_status=LOCUST_PROCESS_EXITED,
                    metrics_status='ok',
                    stats=final_metrics,
                    diagnostics={
                        'locust_exit_code': exit_code,
                        'artifact_dir': self._artifact_dir,
                        'stderr_log_path': self._stderr_log_path,
                    },
                )
            return self._unified_response(
                ok=False,
                runner_status=LOCUST_PROCESS_EXITED,
                metrics_status='process_exited',
                diagnostics={
                    'locust_exit_code': exit_code,
                    'message': (
                        f'Locust 进程已退出 (exit_code={exit_code})，'
                        f'且无有效指标文件。请检查 stderr 日志: {self._stderr_log_path}'
                    ),
                    'artifact_dir': self._artifact_dir,
                    'stderr_log_path': self._stderr_log_path,
                },
            )

        # ── 文件不存在检测 ────────────────────────────────────
        if not self.metrics_file_path or not os.path.exists(self.metrics_file_path):
            # 检查已运行时间，超过阈值判定为 not_created
            elapsed = (time.time() - self._start_time) if self._start_time else 0
            if elapsed >= METRICS_FILE_CREATION_TIMEOUT:
                msg = (
                    f'指标文件 {self.metrics_file_path} 超过 {METRICS_FILE_CREATION_TIMEOUT}s 未创建。'
                    f'Locust 可能启动失败，请检查 stderr 日志: {self._stderr_log_path}'
                )
            else:
                msg = (
                    f'指标文件尚未创建（已等待 {elapsed:.1f}s），Locust 可能在启动中。'
                )

            return self._unified_response(
                ok=False,
                runner_status=(
                    LOCUST_RUNNING_NO_REQUESTS if self.is_running() else LOCUST_PROCESS_EXITED
                ),
                metrics_status='not_created',
                diagnostics={
                    'message': msg,
                    'elapsed_seconds': round(elapsed, 1),
                    'metrics_file_path': self.metrics_file_path,
                    'artifact_dir': self._artifact_dir,
                    'stderr_log_path': self._stderr_log_path,
                },
            )

        # ── 尝试解析 JSON ─────────────────────────────────────
        metrics = self._try_read_metrics_json()
        if metrics is None:
            self._last_read_error = 'JSON parse error'
            try:
                file_size = os.path.getsize(self.metrics_file_path)
            except OSError:
                file_size = -1

            if file_size == 0:
                return self._unified_response(
                    ok=False,
                    runner_status=(
                        LOCUST_RUNNING_NO_REQUESTS if self.is_running() else LOCUST_PROCESS_EXITED
                    ),
                    metrics_status='empty',
                    diagnostics={
                        'message': '指标文件为空，Locust 可能未能正常写入。',
                        'file_size': 0,
                        'metrics_file_path': self.metrics_file_path,
                        'stderr_log_path': self._stderr_log_path,
                    },
                )

            # 读取原始内容（前 500 字符）用于调试
            raw_preview = ''
            try:
                with open(self.metrics_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    raw_preview = f.read(500)
            except Exception:
                pass

            return self._unified_response(
                ok=False,
                runner_status=(
                    LOCUST_RUNNING_NO_REQUESTS if self.is_running() else LOCUST_PROCESS_EXITED
                ),
                metrics_status='parse_error',
                diagnostics={
                    'message': '指标文件 JSON 解析失败。',
                    'file_size': file_size,
                    'metrics_file_path': self.metrics_file_path,
                    'raw_preview': raw_preview,
                    'stderr_log_path': self._stderr_log_path,
                },
            )

        # ── 正常数据 ──────────────────────────────────────────
        total_requests = metrics.get('total_requests', 0)
        if self.is_running() and total_requests == 0:
            runner_status = LOCUST_RUNNING_NO_REQUESTS
        else:
            runner_status = LOCUST_RUNNING_WITH_REQUESTS

        return self._unified_response(
            ok=True,
            runner_status=runner_status,
            metrics_status='ok',
            stats=metrics,
            diagnostics={
                'last_metrics_at': time.time(),
                'artifact_dir': self._artifact_dir,
            },
        )

    def _try_read_metrics_json(self) -> Optional[Dict[str, Any]]:
        """尝试读取并解析 metrics JSON 文件，失败返回 None。"""
        try:
            with open(self.metrics_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, IOError):
            return None

    # ── 诊断信息 ──────────────────────────────────────────────────

    def get_diagnostic_info(self) -> Dict[str, Any]:
        """返回当前诊断信息快照（敏感字段已脱敏）。"""
        info = dict(self._diagnostic)
        info['is_running'] = self.is_running()
        info['exit_code'] = self.exit_code()
        info['stdout_log_path'] = self._stdout_log_path
        info['stderr_log_path'] = self._stderr_log_path
        info['last_read_error'] = self._last_read_error
        info['artifact_dir'] = self._artifact_dir
        if self._start_time is not None:
            info['elapsed_seconds'] = round(time.time() - self._start_time, 1)
        # 脱敏 headers/auth（如果 diagnostic 中包含）
        if 'headers' in info:
            info['headers'] = _mask_sensitive(info['headers'])
        return info

    def read_stderr_tail(self, lines: int = 50) -> str:
        """读取 stderr 日志的最后 N 行。"""
        if not self._stderr_log_path or not os.path.exists(self._stderr_log_path):
            return ''
        try:
            with open(self._stderr_log_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception:
            return ''

    def read_stdout_tail(self, lines: int = 50) -> str:
        """读取 stdout 日志的最后 N 行。"""
        if not self._stdout_log_path or not os.path.exists(self._stdout_log_path):
            return ''
        try:
            with open(self._stdout_log_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception:
            return ''

    def list_artifacts(self) -> Dict[str, Optional[str]]:
        """列出产物目录中所有文件及其路径。"""
        artifacts: Dict[str, Optional[str]] = {
            'metrics_json': self.metrics_file_path if self.metrics_file_path and os.path.exists(self.metrics_file_path) else None,
            'stdout_log': self._stdout_log_path if self._stdout_log_path and os.path.exists(self._stdout_log_path) else None,
            'stderr_log': self._stderr_log_path if self._stderr_log_path and os.path.exists(self._stderr_log_path) else None,
            'metadata_json': os.path.join(self._artifact_dir, 'metadata.json'),
            'report_html': os.path.join(self._artifact_dir, 'report.html'),
            'stats_csv': os.path.join(self._artifact_dir, 'stats_stats.csv'),
            'failures_csv': os.path.join(self._artifact_dir, 'stats_failures.csv'),
            'artifact_dir': self._artifact_dir,
        }

        # 检查文件是否存在
        for key, path in list(artifacts.items()):
            if key == 'artifact_dir':
                continue
            if path and not os.path.exists(path):
                artifacts[key] = None

        return artifacts

    # ── 属性 ────────────────────────────────────────────────────────

    @property
    def web_port(self) -> int:
        """Locust Web UI 端口号（仅 use_web_ui=True 时有效）。"""
        return 8089 + self.port_offset
