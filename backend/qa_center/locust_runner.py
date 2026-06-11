"""
Locust 压力测试运行器 - 使用事件系统实时收集指标
通过 JSON 文件实现进程间通信
"""

import os
import sys
import json
import time
import tempfile
import subprocess
import threading
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import deque


@dataclass
class TestMetrics:
    """测试指标数据"""
    state: str = 'initializing'
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    min_response_time: float = 0.0
    max_response_time: float = 0.0
    p50_response_time: float = 0.0
    p90_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    throughput: float = 0.0
    error_rate: float = 0.0
    current_users: int = 0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    errors: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


class LocustRunner:
    """Locust 测试运行器 - 使用事件系统和文件通信"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.metrics = TestMetrics()
        self._callbacks: list[Callable[[TestMetrics], None]] = []
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self.locustfile_path: Optional[str] = None
        self.metrics_file_path: Optional[str] = None
        self._start_timestamp: Optional[float] = None
        self._response_times: deque = deque(maxlen=10000)
        self._last_request_count: int = 0

    def register_callback(self, callback: Callable[[TestMetrics], None]):
        """注册回调函数，用于接收实时数据"""
        self._callbacks.append(callback)

    def _notify_callbacks(self):
        """通知所有回调函数"""
        for callback in self._callbacks:
            try:
                callback(self.metrics)
            except Exception as e:
                print(f"[LocustRunner] 回调函数调用失败: {e}")

    def generate_locustfile(self, test_case, metrics_file: str) -> str:
        """生成 Locust 测试文件（使用固定路径，每次覆盖）"""
        base_temp = os.path.join(tempfile.gettempdir(), 'syncboard-locust')
        os.makedirs(base_temp, exist_ok=True)

        headers_dict = test_case.headers if isinstance(test_case.headers, dict) else {}
        headers_str = json.dumps(headers_dict, ensure_ascii=False)

        body_str = test_case.body if isinstance(test_case.body, str) else ''
        body_code = "data = None"
        if body_str:
            try:
                json.loads(body_str)
                body_code = f"data = json.dumps({body_str}, ensure_ascii=False).encode('utf-8')"
            except:
                body_code = f"data = {repr(body_str)}.encode('utf-8')"

        from urllib.parse import urlparse
        parsed = urlparse(test_case.url)
        url_path = parsed.path
        if parsed.query:
            url_path += '?' + parsed.query
        if not url_path:
            url_path = '/'
        if not url_path.endswith('/'):
            url_path += '/'

        metrics_file_escaped = metrics_file.replace('\\', '\\\\')

        locust_code = f'''# -*- coding: utf-8 -*-
from locust import HttpUser, task, between, events
import json
import time
import os
import threading

METRICS_FILE = r"{metrics_file_escaped}"
_metrics_lock = threading.Lock()
_metrics_data = {{
    'total_requests': 0,
    'successful_requests': 0,
    'failed_requests': 0,
    'response_times': [],
    'errors': [],
    'state': 'running',
    'start_time': time.time()
}}

def write_metrics():
    """写入指标到文件"""
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
            else:
                avg_time = p50 = p90 = p95 = p99 = 0

            elapsed = time.time() - data['start_time']
            throughput = data['total_requests'] / elapsed if elapsed > 0 else 0
            error_rate = (data['failed_requests'] / data['total_requests'] * 100) if data['total_requests'] > 0 else 0

            output = {{
                'state': data['state'],
                'total_requests': data['total_requests'],
                'successful_requests': data['successful_requests'],
                'failed_requests': data['failed_requests'],
                'avg_response_time': round(avg_time, 2),
                'min_response_time': round(times[0], 2) if times else 0,
                'max_response_time': round(times[-1], 2) if times else 0,
                'p50_response_time': round(p50, 2),
                'p90_response_time': round(p90, 2),
                'p95_response_time': round(p95, 2),
                'p99_response_time': round(p99, 2),
                'throughput': round(throughput, 2),
                'error_rate': round(error_rate, 2),
                'errors': data['errors'][-10:],
                'timestamp': time.time()
            }}

        with open(METRICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False)
    except Exception as e:
        print(f"[Locust] 写入指标失败: {{e}}")

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始事件"""
    print("[Locust] 测试开始")
    with _metrics_lock:
        _metrics_data['state'] = 'running'
        _metrics_data['start_time'] = time.time()
    write_metrics()

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束事件"""
    print("[Locust] 测试结束")
    with _metrics_lock:
        _metrics_data['state'] = 'completed'
    write_metrics()

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response,
               context, exception, start_time, url, **kwargs):
    """请求完成事件 - 实时收集指标"""
    with _metrics_lock:
        _metrics_data['total_requests'] += 1

        if exception:
            _metrics_data['failed_requests'] += 1
            error_msg = str(exception)[:200]
            existing = next((e for e in _metrics_data['errors'] if e['message'] == error_msg), None)
            if existing:
                existing['count'] += 1
            else:
                _metrics_data['errors'].append({{'message': error_msg, 'count': 1}})
        else:
            _metrics_data['successful_requests'] += 1

        _metrics_data['response_times'].append(response_time)
        if len(_metrics_data['response_times']) > 10000:
            _metrics_data['response_times'] = _metrics_data['response_times'][-5000:]

    write_metrics()

class PerformanceTestUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.headers = {headers_str}

    @task(1)
    def test_endpoint(self):
        url = "{url_path}"
        method = "{test_case.method}"
        {body_code}

        try:
            if method == "GET":
                self.client.get(url, headers=self.headers, name=url)
            elif method == "POST":
                self.client.post(url, headers=self.headers, data=data, name=url)
            elif method == "PUT":
                self.client.put(url, headers=self.headers, data=data, name=url)
            elif method == "PATCH":
                self.client.patch(url, headers=self.headers, data=data, name=url)
            elif method == "DELETE":
                self.client.delete(url, headers=self.headers, name=url)
        except Exception as e:
            print(f"Request failed: {{e}}")
'''
        # 使用固定文件名，每次覆盖
        path = os.path.join(base_temp, 'locustfile_current.py')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(locust_code)

        self.locustfile_path = path
        return path

    def _monitor_process(self):
        """监控 Locust 进程的后台线程 - 从文件读取指标"""
        print(f"[LocustRunner] 监控线程启动")
        
        while not self._stop_event.is_set() and self.process:
            if self.process.poll() is not None:
                self.metrics.state = 'stopped'
                self.metrics.end_time = datetime.now().isoformat()
                self._notify_callbacks()
                break
            
            try:
                if self.metrics_file_path and os.path.exists(self.metrics_file_path):
                    with open(self.metrics_file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    self.metrics.state = data.get('state', 'running')
                    self.metrics.total_requests = data.get('total_requests', 0)
                    self.metrics.successful_requests = data.get('successful_requests', 0)
                    self.metrics.failed_requests = data.get('failed_requests', 0)
                    self.metrics.avg_response_time = data.get('avg_response_time', 0)
                    self.metrics.min_response_time = data.get('min_response_time', 0)
                    self.metrics.max_response_time = data.get('max_response_time', 0)
                    self.metrics.p50_response_time = data.get('p50_response_time', 0)
                    self.metrics.p90_response_time = data.get('p90_response_time', 0)
                    self.metrics.p95_response_time = data.get('p95_response_time', 0)
                    self.metrics.p99_response_time = data.get('p99_response_time', 0)
                    self.metrics.throughput = data.get('throughput', 0)
                    self.metrics.error_rate = data.get('error_rate', 0)
                    self.metrics.errors = data.get('errors', [])
                    
                    self._notify_callbacks()
                    
            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"[LocustRunner] 读取指标失败: {e}")
            
            time.sleep(0.5)

    def start_test(self, test_case, host: str, users: int = 10, 
                   spawn_rate: int = 1, run_time: str = "60s") -> bool:
        """启动测试"""
        try:
            base_temp = os.path.join(tempfile.gettempdir(), 'syncboard-locust')
            os.makedirs(base_temp, exist_ok=True)

            # 使用固定文件名，每次覆盖
            self.metrics_file_path = os.path.join(base_temp, 'locust_metrics_current.json')
            with open(self.metrics_file_path, 'w', encoding='utf-8') as f:
                json.dump({'state': 'initializing'}, f)
            
            locustfile_path = self.generate_locustfile(test_case, self.metrics_file_path)
            
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
                    except:
                        pass
            
            cmd = [
                sys.executable, '-m', 'locust',
                '-f', locustfile_path,
                '--host', host,
                '--users', str(users),
                '--spawn-rate', str(spawn_rate),
                '--run-time', f"{run_time_seconds}s",
                '--headless',
                '--only-summary',
            ]
            
            print(f"[Locust] 启动命令: {' '.join(cmd)}")
            print(f"[Locust] 指标文件: {self.metrics_file_path}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=base_temp,  # 输出文件写入临时目录
            )
            
            self._start_timestamp = time.time()
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_process)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()
            
            self.metrics.state = 'running'
            self.metrics.start_time = datetime.now().isoformat()
            self.metrics.current_users = users
            
            return True
            
        except Exception as e:
            print(f"[Locust] 启动测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_test(self):
        """停止测试"""
        try:
            self._stop_event.set()
            
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except:
                    self.process.kill()
                    self.process.wait()
            
            if self.locustfile_path and os.path.exists(self.locustfile_path):
                try:
                    os.remove(self.locustfile_path)
                except:
                    pass
            
            if self.metrics_file_path and os.path.exists(self.metrics_file_path):
                try:
                    os.remove(self.metrics_file_path)
                except:
                    pass
            
            self.process = None
            self.metrics.state = 'stopped'
            self.metrics.end_time = datetime.now().isoformat()
            self._notify_callbacks()
            
            print("[Locust] 测试已停止")
            return True
            
        except Exception as e:
            print(f"[Locust] 停止测试失败: {e}")
            return False

    def get_current_stats(self) -> Dict[str, Any]:
        """获取当前统计信息"""
        duration = 0
        if self.metrics.start_time:
            start = datetime.fromisoformat(self.metrics.start_time)
            duration = (datetime.now() - start).seconds
        
        return {
            'state': self.metrics.state,
            'current_users': self.metrics.current_users,
            'total_requests': self.metrics.total_requests,
            'successful_requests': self.metrics.successful_requests,
            'failed_requests': self.metrics.failed_requests,
            'avg_response_time': round(self.metrics.avg_response_time, 2),
            'min_response_time': round(self.metrics.min_response_time, 2),
            'max_response_time': round(self.metrics.max_response_time, 2),
            'p50_response_time': round(self.metrics.p50_response_time, 2),
            'p90_response_time': round(self.metrics.p90_response_time, 2),
            'p95_response_time': round(self.metrics.p95_response_time, 2),
            'p99_response_time': round(self.metrics.p99_response_time, 2),
            'throughput': round(self.metrics.throughput, 2),
            'error_rate': round(self.metrics.error_rate, 2),
            'errors': self.metrics.errors[-10:],
            'start_time': self.metrics.start_time,
            'duration': duration,
        }

    def is_running(self) -> bool:
        """检查测试是否正在运行"""
        return self.process is not None and self.process.poll() is None
