"""请求构造辅助 —— M3.4。

把用例上的 ``query_params`` / ``form_files`` 规范化成 ``requests`` 库能直接吃的格式，
同时支持 ``{{var}}`` 模板渲染。

公开 API：
- ``normalize_query_params(raw, variables)`` -> ``list[tuple[str, str]]`` 或 ``None``
- ``build_file_tuples(raw, variables)`` -> ``list[tuple[str, tuple[str, bytes, str]]]`` 或 ``None``

设计要点：
- query_params 接受 ``{"k": "v"}`` 或 ``[["k", "v"], ["k", "v2"]]``，输出 list-of-pairs 保留重复键
- form_files 单条形如 ``{"name": "file", "filename": "a.txt", "content": "...", "content_type": "..."}``
  - ``encoding`` 字段：``base64`` 表示 content 是 base64 字符串；其它（含缺省）当作普通文本
- 渲染失败、字段缺失时尽量不抛异常，回填空值或跳过该条，把"健壮性"留给执行器决定是否报错
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Iterable, List, Optional, Tuple

from . import template_engine as te

logger = logging.getLogger(__name__)


def _stringify(v: Any) -> str:
    if v is None:
        return ''
    if isinstance(v, bool):
        # requests 会把 True/False 序列化成 "True"/"False"，统一成小写以贴近常见 API 习惯
        return 'true' if v else 'false'
    return str(v)


def normalize_query_params(
    raw: Any,
    variables: Optional[dict] = None,
) -> Optional[List[Tuple[str, str]]]:
    """把任意形态的 query_params 规范化成 ``[(k, v), ...]``。

    - ``None`` / 空容器 -> ``None``（调用方据此决定是否传 ``params=``）
    - dict 形态：``{"k": "v"}`` 或 ``{"k": ["v1", "v2"]}``，后者会拆成多条
    - list 形态：``[["k", "v"], ["k", "v2"]]`` 直接保留顺序与重复键
    - 任何键值都会先经过模板渲染（若提供 ``variables``）
    """
    if raw is None:
        return None
    variables = variables or {}

    pairs: List[Tuple[str, str]] = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, (list, tuple)):
                for sub in v:
                    pairs.append((str(k), _stringify(sub)))
            else:
                pairs.append((str(k), _stringify(v)))
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                pairs.append((str(item[0]), _stringify(item[1])))
            elif isinstance(item, dict) and 'name' in item:
                # 兼容 [{"name": "k", "value": "v"}] 形态
                pairs.append((str(item.get('name')), _stringify(item.get('value'))))
            else:
                logger.debug('[QueryParams] skip unparseable item: %r', item)
    else:
        logger.debug('[QueryParams] unsupported type: %r', type(raw))
        return None

    if not pairs:
        return None

    rendered: List[Tuple[str, str]] = []
    for k, v in pairs:
        rk = te.render_string(k, variables) if variables else k
        rv = te.render_string(v, variables) if variables else v
        rendered.append((rk, rv))
    return rendered


def _decode_content(spec: dict) -> bytes:
    """把 form_files 里单条的 content 字段还原成 bytes。"""
    encoding = (spec.get('encoding') or '').lower()
    content = spec.get('content', '')
    if content is None:
        return b''
    if encoding == 'base64':
        try:
            return base64.b64decode(content)
        except Exception as e:
            logger.warning('[FormFiles] base64 decode failed for %r: %s', spec.get('filename'), e)
            return b''
    if isinstance(content, bytes):
        return content
    return str(content).encode('utf-8')


def build_file_tuples(
    raw: Any,
    variables: Optional[dict] = None,
) -> Optional[List[Tuple[str, Tuple[str, bytes, str]]]]:
    """把 form_files spec 转换为 ``requests`` 的 ``files=`` 参数格式。

    requests 接受 ``[(field_name, (filename, content_bytes, content_type)), ...]``。
    渲染 filename / content 中的 ``{{var}}``。

    - 缺少 ``name`` 的条目直接跳过并记日志
    - filename 缺省退化为 name
    - content_type 缺省 ``application/octet-stream``
    """
    if raw is None:
        return None
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, dict)):
        # dict 不是合法形态（应该是 list of dict）
        logger.debug('[FormFiles] unsupported top-level type: %r', type(raw))
        return None
    variables = variables or {}

    tuples: List[Tuple[str, Tuple[str, bytes, str]]] = []
    for spec in raw:
        if not isinstance(spec, dict):
            logger.debug('[FormFiles] skip non-dict item: %r', spec)
            continue
        name = spec.get('name') or spec.get('field')
        if not name:
            logger.debug('[FormFiles] skip item without name: %r', spec)
            continue
        filename = spec.get('filename') or name
        content_type = spec.get('content_type') or 'application/octet-stream'

        # 渲染文件名 / 文本内容（base64 内容不渲染，避免破坏编码）
        if variables:
            name = te.render_string(str(name), variables)
            filename = te.render_string(str(filename), variables)

        encoding = (spec.get('encoding') or '').lower()
        if encoding != 'base64' and variables:
            # 文本内容支持模板
            rendered_spec = dict(spec)
            content = spec.get('content', '')
            if isinstance(content, str):
                rendered_spec['content'] = te.render_string(content, variables)
            content_bytes = _decode_content(rendered_spec)
        else:
            content_bytes = _decode_content(spec)

        tuples.append((str(name), (str(filename), content_bytes, str(content_type))))

    return tuples or None
