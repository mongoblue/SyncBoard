"""
Request Util - HTTP 请求封装工具
基于 requests.Session 封装 GET/POST/PUT/DELETE 方法
支持请求/响应日志记录、自动处理 JSON
"""
import json
import time
from typing import Optional, Dict, Any, Union
import requests
from requests import Response


class RequestUtil:
    """统一 HTTP 请求工具类"""

    def __init__(self, base_url: str = "", timeout: int = 30):
        """
        初始化请求工具

        Args:
            base_url: API 基础 URL，拼接在 path 前
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout = timeout
        self.session = requests.Session()
        self._default_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.last_response: Optional[Response] = None

    def _build_url(self, path: str) -> str:
        """
        构建完整的请求 URL

        Args:
            path: API 路径，支持绝对路径和相对路径

        Returns:
            完整的 URL 字符串
        """
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _merge_headers(self, headers: Optional[Dict] = None) -> Dict:
        """合并请求头"""
        merged = self._default_headers.copy()
        if headers:
            merged.update(headers)
        return merged

    def _log_request(self, method: str, url: str,
                     headers: Dict, params: Optional[Dict] = None,
                     json_data: Any = None, data: Any = None):
        """打印请求日志"""
        print(f"\n{'='*60}")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📤 REQUEST")
        print(f"{'='*60}")
        print(f"Method:     {method}")
        print(f"URL:        {url}")
        print(f"Headers:    {json.dumps(headers, ensure_ascii=False, indent=2)}")
        if params:
            print(f"Params:     {json.dumps(params, ensure_ascii=False, indent=2)}")
        if json_data:
            print(f"Body(JSON): {json.dumps(json_data, ensure_ascii=False, indent=2)}")
        if data:
            print(f"Body(Text): {data}")
        print(f"{'='*60}")

    def _log_response(self, response: Response, elapsed_ms: float):
        """打印响应日志"""
        print(f"\n{'='*60}")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📥 RESPONSE ({elapsed_ms:.0f}ms)")
        print(f"{'='*60}")
        print(f"Status:     {response.status_code} {response.reason}")
        print(f"Headers:    {json.dumps(dict(response.headers), ensure_ascii=False, indent=2)}")

        try:
            body = response.json()
            print(f"Body(JSON): {json.dumps(body, ensure_ascii=False, indent=2)}")
        except (json.JSONDecodeError, ValueError):
            text = response.text[:1000] if response.text else "(empty)"
            print(f"Body(Text): {text}")

        print(f"{'='*60}\n")

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        data: Optional[Any] = None,
        **kwargs
    ) -> Response:
        """
        通用请求方法

        Args:
            method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS)
            path: API 路径
            params: URL 查询参数
            headers: 请求头
            json_data: JSON 请求体
            data: 文本请求体
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response 对象
        """
        url = self._build_url(path)
        merged_headers = self._merge_headers(headers)

        self._log_request(method, url, merged_headers, params, json_data, data)

        start_time = time.time()
        response = self.session.request(
            method=method.upper(),
            url=url,
            params=params,
            headers=merged_headers,
            json=json_data,
            data=data,
            timeout=self.timeout,
            **kwargs
        )
        elapsed_ms = (time.time() - start_time) * 1000

        self._log_response(response, elapsed_ms)

        self.last_response = response

        return response

    def get(
        self,
        path: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        **kwargs
    ) -> Response:
        """
        GET 请求

        Args:
            path: API 路径
            params: URL 查询参数
            headers: 请求头
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response 对象
        """
        return self.request("GET", path, params=params, headers=headers, **kwargs)

    def post(
        self,
        path: str,
        json_data: Optional[Dict] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict] = None,
        **kwargs
    ) -> Response:
        """
        POST 请求

        Args:
            path: API 路径
            json_data: JSON 请求体
            data: 文本请求体
            headers: 请求头
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response 对象
        """
        return self.request("POST", path, json_data=json_data, data=data, headers=headers, **kwargs)

    def put(
        self,
        path: str,
        json_data: Optional[Dict] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict] = None,
        **kwargs
    ) -> Response:
        """
        PUT 请求

        Args:
            path: API 路径
            json_data: JSON 请求体
            data: 文本请求体
            headers: 请求头
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response 对象
        """
        return self.request("PUT", path, json_data=json_data, data=data, headers=headers, **kwargs)

    def patch(
        self,
        path: str,
        json_data: Optional[Dict] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict] = None,
        **kwargs
    ) -> Response:
        """
        PATCH 请求

        Args:
            path: API 路径
            json_data: JSON 请求体
            data: 文本请求体
            headers: 请求头
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response 对象
        """
        return self.request("PATCH", path, json_data=json_data, data=data, headers=headers, **kwargs)

    def delete(
        self,
        path: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        **kwargs
    ) -> Response:
        """
        DELETE 请求

        Args:
            path: API 路径
            params: URL 查询参数
            headers: 请求头
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response 对象
        """
        return self.request("DELETE", path, params=params, headers=headers, **kwargs)

    def set_header(self, key: str, value: str):
        """动态设置默认请求头"""
        self._default_headers[key] = value

    def set_auth_token(self, token: str, token_type: str = "Bearer"):
        """设置认证 Token"""
        self.set_header("Authorization", f"{token_type} {token}")

    def close(self):
        """关闭会话，释放连接"""
        self.session.close()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


if __name__ == "__main__":
    print("=" * 60)
    print("RequestUtil 使用示例")
    print("=" * 60)

    with RequestUtil(base_url="http://httpbin.org") as req:
        response = req.get("/get", params={"name": "test", "age": 25})
        print(f"Status: {response.status_code}")

        response = req.post("/post", json_data={"username": "admin", "password": "123456"})
        print(f"Status: {response.status_code}")
