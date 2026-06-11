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
