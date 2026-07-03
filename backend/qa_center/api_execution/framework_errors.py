"""Framework error recognizers for the unified API runner.

Pure module: no Django model imports, no I/O. Reads the redacted response
snapshot produced by the runner and returns a structured diagnosis when the
response body matches a known framework error page (Django DisallowedHost,
Flask Werkzeug, Spring Whitelabel, Node stack traces, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class FrameworkDiagnosis:
    framework: str
    title: str
    root_cause: str
    suggested_fixes: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework": self.framework,
            "title": self.title,
            "root_cause": self.root_cause,
            "suggested_fixes": list(self.suggested_fixes),
            "message": self.message,
        }


_DISALLOWED_HOST_FIXES = [
    "为环境配置正确的 base_url，例如 http://127.0.0.1:8000，不要只请求相对路径",
    "测试环境 ALLOWED_HOSTS 加入 testserver / localhost / 127.0.0.1",
    "生产环境不要使用 ALLOWED_HOSTS = ['*']，必须列出显式主机名",
    "确保用例绑定了 environment，使 {{base_url}} 能解析为完整 URL",
]

_IMPROPERLY_CONFIGURED_FIXES = [
    "检查 Django settings 模块配置是否正确",
    "确认 DJANGO_SETTINGS_MODULE 环境变量指向正确的 settings",
    "查看 traceback 中提到的缺失配置项",
]

_TEMPLATE_DOES_NOT_EXIST_FIXES = [
    "确认模板路径在 TEMPLATES['DIRS'] 中",
    "检查模板文件是否存在于应用 templates 目录",
    "确认相关 app 已加入 INSTALLED_APPS",
]

_DB_OPERATIONAL_FIXES = [
    "检查数据库连接配置 DB_HOST / DB_NAME / DB_USER / DB_PASSWORD",
    "确认数据库服务已启动且网络可达",
    "运行 python manage.py migrate 应用迁移",
]

_DB_PROGRAMMING_FIXES = [
    "运行 python manage.py makemigrations 和 migrate 同步表结构",
    "检查 SQL 语法或 model 字段定义是否与表结构一致",
    "查看 traceback 中的具体 SQL 错误",
]

_CSRF_FIXES = [
    "对不安全方法（POST/PUT/DELETE）在请求头加 X-CSRFToken",
    "携带会话 cookie 以复用 CSRF token",
    "确认前端已从 csrftoken cookie 读取并回传 token",
]

_FLASK_WERKZEUG_FIXES = [
    "查看 Werkzeug traceback 定位失败视图",
    "生产环境关闭 FLASK_DEBUG，避免暴露调试页",
    "为该路由添加异常处理或修复底层错误",
]

_SPRING_WHITELABEL_FIXES = [
    "添加全局 @ExceptionHandler 捕获异常",
    "查看服务端日志定位底层异常",
    "为该端点添加显式错误响应处理",
]

_NODE_STACK_FIXES = [
    "查看 stack trace 定位失败模块",
    "在失败 handler 周围加 try/catch",
    "确认异步错误已被 Promise.catch 或全局 unhandledRejection 捕获",
]


_NODE_FRAME_RE = re.compile(r"at .+\(.+:\d+:\d+\)")


def _body_preview(response_snapshot: Dict[str, Any]) -> str:
    body = response_snapshot.get("body") or {}
    if isinstance(body, dict):
        preview = body.get("preview") or body.get("text") or ""
        if isinstance(preview, (bytes, bytearray)):
            try:
                return preview.decode("utf-8", "ignore")
            except Exception:
                return ""
        return str(preview) if preview else ""
    if isinstance(body, str):
        return body
    return ""


def _status(response_snapshot: Dict[str, Any]) -> int:
    try:
        return int(response_snapshot.get("status_code") or 0)
    except (TypeError, ValueError):
        return 0


def _diagnosis(
    framework: str,
    title: str,
    root_cause: str,
    fixes: list[str],
    message: str,
) -> FrameworkDiagnosis:
    snippet = message
    if len(snippet) > 400:
        snippet = snippet[:400] + "…"
    return FrameworkDiagnosis(
        framework=framework,
        title=title,
        root_cause=root_cause,
        suggested_fixes=fixes,
        message=snippet,
    )


def classify_framework_error(
    response_snapshot: Dict[str, Any],
    transport_response: Any = None,
) -> Optional[FrameworkDiagnosis]:
    """Classify a response as a known framework error page.

    Returns the first matching FrameworkDiagnosis, or None if the response
    does not look like a framework error page.
    """
    if not response_snapshot:
        return None

    body = _body_preview(response_snapshot)
    if not body:
        return None

    status = _status(response_snapshot)
    headers = response_snapshot.get("headers") or {}
    content_type = ""
    for k, v in headers.items():
        if str(k).lower() == "content-type":
            content_type = str(v).lower()
            break

    low = body

    if "DisallowedHost" in body and "ALLOWED_HOSTS" in body:
        msg = _extract_message(body, "Invalid HTTP_HOST header")
        return _diagnosis(
            "django",
            "Django DisallowedHost",
            "请求的 Host 头（如 testserver）不在 Django ALLOWED_HOSTS 中，Django 拒绝处理该请求。",
            _DISALLOWED_HOST_FIXES,
            msg or "DisallowedHost: Invalid HTTP_HOST header",
        )

    if "ImproperlyConfigured" in body:
        msg = _extract_message(body, "ImproperlyConfigured")
        return _diagnosis(
            "django",
            "Django ImproperlyConfigured",
            "Django 配置缺失或错误，应用启动或运行时缺少必要配置项。",
            _IMPROPERLY_CONFIGURED_FIXES,
            msg or "ImproperlyConfigured",
        )

    if "TemplateDoesNotExist" in body:
        msg = _extract_message(body, "TemplateDoesNotExist")
        return _diagnosis(
            "django",
            "Django Template Does Not Exist",
            "Django 找不到请求的模板文件。",
            _TEMPLATE_DOES_NOT_EXIST_FIXES,
            msg or "TemplateDoesNotExist",
        )

    if "OperationalError" in body:
        msg = _extract_message(body, "OperationalError")
        return _diagnosis(
            "django",
            "Django Database OperationalError",
            "数据库连接或查询出现操作错误（连接失败、表不存在、锁等待等）。",
            _DB_OPERATIONAL_FIXES,
            msg or "OperationalError",
        )

    if "ProgrammingError" in body:
        msg = _extract_message(body, "ProgrammingError")
        return _diagnosis(
            "django",
            "Django Database ProgrammingError",
            "数据库查询编程错误（SQL 语法、列不存在、表结构与 model 不一致等）。",
            _DB_PROGRAMMING_FIXES,
            msg or "ProgrammingError",
        )

    if status == 403 and "CSRF" in body and ("Forbidden" in body or "csrf" in low.lower()):
        msg = _extract_message(body, "CSRF")
        return _diagnosis(
            "django",
            "Django CSRF Verification Failed",
            "Django CSRF 校验失败，请求缺少有效 CSRF token。",
            _CSRF_FIXES,
            msg or "CSRF verification failed",
        )

    if "Werkzeug" in body and "Traceback" in body:
        msg = _extract_message(body, "Traceback")
        return _diagnosis(
            "flask",
            "Flask Werkzeug Error",
            "Flask/Werkzeug 调试器捕获到未处理异常并返回调试错误页。",
            _FLASK_WERKZEUG_FIXES,
            msg or "Werkzeug debugger traceback",
        )

    if "Whitelabel Error Page" in body or ("Spring Boot" in body and "message" in low.lower()):
        msg = _extract_message(body, "message")
        return _diagnosis(
            "spring",
            "Spring Boot Whitelabel Error",
            "Spring Boot 未为该异常提供专门处理，返回默认 Whitelabel 错误页。",
            _SPRING_WHITELABEL_FIXES,
            msg or "Whitelabel Error Page",
        )

    frames = _NODE_FRAME_RE.findall(body)
    if len(frames) >= 3 and ("Error" in body or "at " in body):
        msg = frames[0] if frames else "Node.js stack trace"
        return _diagnosis(
            "node",
            "Node.js Unhandled Exception",
            "Node.js 应用抛出未捕获异常，返回包含 stack trace 的错误响应。",
            _NODE_STACK_FIXES,
            msg,
        )

    return None


def _extract_message(body: str, marker: str) -> str:
    """Best-effort extraction of a human-readable message line near the marker."""
    idx = body.find(marker)
    if idx < 0:
        return ""
    end = body.find("\n", idx)
    if end < 0:
        end = min(len(body), idx + 300)
    snippet = body[idx:end].strip()
    snippet = re.sub(r"<[^>]+>", "", snippet)
    snippet = snippet.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return snippet[:300]
