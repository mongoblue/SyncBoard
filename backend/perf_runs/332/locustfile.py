# -*- coding: utf-8 -*-
"""SyncBoard 自动生成的 Locust 压测脚本。

产物目录: D:/Projects/SyncBoard/backend/perf_runs/332
步骤: ['main']
"""
from locust import HttpUser, task, between, events, LoadTestShape
import json
import os
import threading
import time
import re

# ── 指标配置 ──────────────────────────────────────────────────
METRICS_FILE = r"C:\\Users\\MONGOB~1\\AppData\\Local\\Temp\\syncboard-locust\\locust_metrics_prepare_332.json"
METRICS_TMP = r"C:\Users\MONGOB~1\AppData\Local\Temp\syncboard-locust\locust_metrics_prepare_332.json.tmp"
_STEP_NAMES = ['main']
_RPS_LIMIT = None



# ── 全局指标数据 ──────────────────────────────────────────────
_metrics_lock = threading.Lock()
_metrics_data = {
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
    'per_endpoint': {},
    'step_stats': {s: {'total':0,'success':0,'failed':0,'times':[]} for s in _STEP_NAMES},
    'last_sample_time': 0.0,
    'last_total_requests': 0,
    'last_failed_requests': 0,
}


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
            data['throughput_series'].append({'t': round(now - data['start_time'], 1), 'rps': round(instant_rps, 2)})
            data['response_time_series'].append({'t': round(now - data['start_time'], 1), 'avg': round(avg_time, 2), 'p95': round(p95, 2)})
            data['error_rate_series'].append({'t': round(now - data['start_time'], 1), 'error_rate': round(instant_error_rate, 2)})
            for key in ('throughput_series', 'response_time_series', 'error_rate_series'):
                if len(data[key]) > 600:
                    data[key] = data[key][-600:]
            data['last_sample_time'] = now
            data['last_total_requests'] = total
            data['last_failed_requests'] = failed

        distribution = {}
        if times:
            for rt in times:
                bucket = min(int(rt // 50), 39)
                key = f"{bucket * 50}-{(bucket + 1) * 50}ms"
                distribution[key] = distribution.get(key, 0) + 1

        per_endpoint = {}
        for ep, ep_data in data['per_endpoint'].items():
            ep_times = sorted(ep_data.get('times', []))
            et = ep_data.get('total', 0)
            ef = ep_data.get('failed', 0)
            per_endpoint[ep] = {
                'total_requests': et, 'successful_requests': ep_data.get('success', 0),
                'failed_requests': ef, 'avg_response_time': round(sum(ep_times)/len(ep_times),2) if ep_times else 0,
                'p95_response_time': round(ep_times[int(len(ep_times)*0.95)],2) if ep_times else 0,
                'error_rate': round((ef/et*100),2) if et > 0 else 0,
            }

        step_stats = {}
        for sn, ss in data['step_stats'].items():
            ss_times = sorted(ss.get('times', []))
            st = ss.get('total', 0)
            sf = ss.get('failed', 0)
            step_stats[sn] = {
                'total_requests': st, 'successful_requests': ss.get('success', 0),
                'failed_requests': sf, 'p95_response_time': round(ss_times[int(len(ss_times)*0.95)],2) if ss_times else 0,
                'avg_response_time': round(sum(ss_times)/len(ss_times),2) if ss_times else 0,
                'error_details': ss.get('errors', [])[-10:],
            }

        output = {
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
        }

        tmp_content = json.dumps(output, ensure_ascii=False)
        with open(METRICS_TMP, 'w', encoding='utf-8') as f:
            f.write(tmp_content); f.flush(); os.fsync(f.fileno())
        os.replace(METRICS_TMP, METRICS_FILE)
    except Exception as e:
        print(f"[Locust] 写入指标失败: {e}")


# ── 辅助函数 ──────────────────────────────────────────────────

def _resolve_vars(template, ctx):
    """替换模板中的 {{var}} 变量。"""
    if not isinstance(template, str):
        return template
    def _repl(m):
        key = m.group(1).strip()
        return str(ctx.get(key, m.group(0)))
    return re.sub(r'{{(.+?)}}', _repl, template)

def _resolve_headers(headers, ctx):
    return {k: _resolve_vars(v, ctx) for k, v in (headers or {}).items()}

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
            cur = cur.get(key, {}) if key else cur
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
    kw = dict(kwargs) if kwargs else {}
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
                {'message': error_msg, 'time': time.time()}
            )
        if name not in _metrics_data['per_endpoint']:
            _metrics_data['per_endpoint'][name] = {'total':0,'success':0,'failed':0,'times':[]}
        _metrics_data['per_endpoint'][name]['total'] += 1
        _metrics_data['per_endpoint'][name]['failed'] += 1
        _metrics_data['per_endpoint'][name]['times'].append(elapsed)

def _record_step(name, ok, elapsed, status_code):
    """记录步骤完成。"""
    with _metrics_lock:
        ep = _metrics_data['per_endpoint'].setdefault(name, {'total':0,'success':0,'failed':0,'times':[]})
        ss = _metrics_data['step_stats'].setdefault(name, {'total':0,'success':0,'failed':0,'times':[]})
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



# ── 步骤断言函数 ──────────────────────────────────────────────

def _assert_status_in(resp, codes, step_name):
    if resp is None or resp.status_code not in codes:
        _record_failure(step_name, f'status_code not in {codes}', 0)

def _assert_status_eq(resp, code, step_name):
    if resp is None or resp.status_code != code:
        _record_failure(step_name, f'status_code != {code}', 0)

def _assert_response_time(elapsed, max_ms, step_name):
    if elapsed > max_ms:
        _record_failure(step_name, f'response_time {elapsed:.0f}ms > {max_ms}ms', elapsed)

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
        _record_failure(step_name, f'jsonpath {path} assertion failed', 0)


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
        if run_time > 10:
            return (0.1, 0.5)
        current = int(self.get_current_user_count())
        target = max(1, int(run_time / 10 * 100))
        if current < target:
            return (target - current, 0.5)
        return None


# ── 用户类 ────────────────────────────────────────────────────

class PerformanceTestUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.ctx = {}  # 变量上下文（跨步骤共享）
        pass

    @task(1)
    def test_scenario(self):
        ctx = self.ctx

    # ── Step 1: main ────────────────────────────────
    _url_0 = _resolve_vars('http://localhost:8000/api/auth/login', ctx)
    _headers_0 = _resolve_headers({"Content-Type": "application/json"}, ctx)
    _body_0 = _resolve_body(json.dumps({"username": "mongoblue", "password": "13579mnb"}, ensure_ascii=False).encode('utf-8'), ctx)

    _params_0 = None

    _start = time.perf_counter()
    try:
        _resp = _request(
            method='POST',
            url=_url_0,
            headers=_headers_0,
            data=_body_0,
            params=_params_0,
            name='main',
            kwargs={"timeout":30},
        )
        _elapsed = (time.perf_counter() - _start) * 1000
        _ok = True
    except Exception as _exc:
        _elapsed = (time.perf_counter() - _start) * 1000
        _ok = False
        _resp = None
        _error_msg = str(_exc)[:200]
        _record_failure('main', _error_msg, _elapsed)


    _record_step('main', _ok, _elapsed, _resp.status_code if _resp else 0)

    _write_metrics_atomic()
