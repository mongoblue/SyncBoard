"""变量抽取器 —— M3.3。

从响应里抽出值，喂给 template_engine 的变量池。

抽取规则：
  - source='body'    : JSONPath 取响应 JSON 字段
  - source='header'  : 取响应头（不区分大小写）
  - source='status'  : 响应状态码
  - source='cookie'  : 从响应 cookie 里取
  - source='response_time' : 响应耗时(ms)

任何失败都返回 default_value（字符串），不抛异常 —— 测试链不应该因单条抽取失败崩溃。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from .unified_assertions import _extract_by_jsonpath, _get_header_ci

logger = logging.getLogger(__name__)


def extract_value(
    *,
    source: str,
    expression: str,
    response_json: Any,
    response_headers: Dict[str, str],
    status_code: int,
    cookies: Optional[Dict[str, str]] = None,
    response_time_ms: float = 0.0,
    default: Any = None,
) -> Any:
    """根据 source/expression 抽出一个值。失败返回 default。"""
    try:
        if source == 'status':
            return status_code
        if source == 'response_time':
            return response_time_ms
        if source == 'header':
            v = _get_header_ci(response_headers or {}, expression or '')
            return v if v is not None else default
        if source == 'cookie':
            if not cookies:
                return default
            return cookies.get(expression or '', default)
        if source == 'body':
            if response_json is None or not expression:
                return default
            v = _extract_by_jsonpath(response_json, expression)
            return v if v is not None else default
        # 未知 source 直接 fallback
        return default
    except Exception as e:  # pragma: no cover
        logger.debug('[Extractor] failed source=%s expr=%s err=%s', source, expression, e)
        return default


def run_extractors(
    extractors: Iterable,
    *,
    response_json: Any,
    response_headers: Dict[str, str],
    status_code: int,
    cookies: Optional[Dict[str, str]] = None,
    response_time_ms: float = 0.0,
) -> Dict[str, Any]:
    """对一组 ApiAutoTestExtractor（已 prefetch / list 化）批量抽取，返回 ``{name: value}``。

    会跳过 is_active=False 和 name 为空的条目。
    """
    out: Dict[str, Any] = {}
    for ex in extractors or []:
        if not getattr(ex, 'is_active', True):
            continue
        name = (getattr(ex, 'name', '') or '').strip()
        if not name:
            continue
        value = extract_value(
            source=getattr(ex, 'source', 'body'),
            expression=getattr(ex, 'expression', '') or '',
            response_json=response_json,
            response_headers=response_headers,
            status_code=status_code,
            cookies=cookies,
            response_time_ms=response_time_ms,
            default=getattr(ex, 'default_value', None) or None,
        )
        out[name] = value
    return out


def summarize_extractions(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把抽取结果转成前端友好的列表（用于结果详情展示 / 日志）。

    值如果太长会截断，避免污染日志和数据库。
    """
    items: List[Dict[str, Any]] = []
    for name, value in extracted.items():
        text = '' if value is None else str(value)
        items.append({
            'name': name,
            'value_preview': text[:200] + ('…' if len(text) > 200 else ''),
            'is_none': value is None,
        })
    return items
