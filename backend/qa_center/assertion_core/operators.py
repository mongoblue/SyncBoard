from __future__ import annotations

import json
from typing import Any, Callable, Dict


OPERATOR_ALIASES = {
    "==": "eq",
    "=": "eq",
    "!=": "neq",
    "<>": "neq",
    "ne": "neq",
    "neq": "neq",
    ">": "gt",
    "<": "lt",
    ">=": "gte",
    "<=": "lte",
    "regex_match": "regex",
    "matches": "regex",
    "has": "contains",
    "member_of": "in",
    "not-member-of": "not_in",
    "not in": "not_in",
    "not_contains": "not_contains",
    "exists": "exists",
    "not_exists": "not_exists",
}


def _to_num(x: Any):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _safe_cmp(a: Any, b: Any, fn: Callable[[Any, Any], bool]) -> bool:
    try:
        if isinstance(a, str):
            a = float(a)
        if isinstance(b, str):
            b = float(b)
        return fn(a, b)
    except (TypeError, ValueError):
        return False


def _smart_eq(a: Any, b: Any) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if a == b:
        return True
    if a is None or b is None:
        return False
    na, nb = _to_num(a), _to_num(b)
    if na is not None and nb is not None and na == nb:
        return True
    if isinstance(a, str) and isinstance(b, str):
        try:
            return json.loads(a) == json.loads(b)
        except (json.JSONDecodeError, ValueError):
            return False
    return False


def _smart_neq(a: Any, b: Any) -> bool:
    return not _smart_eq(a, b)


def _contains(a: Any, b: Any) -> bool:
    if isinstance(a, (str, list, dict, tuple)):
        return b in a
    return str(b) in str(a) if a is not None else False


def _regex(a: Any, b: Any) -> bool:
    import re

    try:
        return re.search(str(b), "" if a is None else str(a)) is not None
    except re.error:
        return False


def _in(a: Any, b: Any) -> bool:
    if isinstance(b, range):
        return a in b
    if isinstance(b, (list, tuple, set)):
        return a in b
    if isinstance(a, (list, tuple, set)):
        return b in a
    if isinstance(b, str):
        s = b.strip().lower()
        if s == "2xx":
            try:
                ai = int(a)
            except (TypeError, ValueError):
                return False
            return 200 <= ai < 300
        if s == "3xx":
            try:
                ai = int(a)
            except (TypeError, ValueError):
                return False
            return 300 <= ai < 400
        if s == "4xx":
            try:
                ai = int(a)
            except (TypeError, ValueError):
                return False
            return 400 <= ai < 500
        if s == "5xx":
            try:
                ai = int(a)
            except (TypeError, ValueError):
                return False
            return 500 <= ai < 600
        return str(a) in b
    return False


def _not_in(a: Any, b: Any) -> bool:
    return not _in(a, b)


OPERATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "eq": _smart_eq,
    "neq": _smart_neq,
    "gt": lambda a, b: _safe_cmp(a, b, lambda x, y: x > y),
    "gte": lambda a, b: _safe_cmp(a, b, lambda x, y: x >= y),
    "lt": lambda a, b: _safe_cmp(a, b, lambda x, y: x < y),
    "lte": lambda a, b: _safe_cmp(a, b, lambda x, y: x <= y),
    "contains": _contains,
    "not_contains": lambda a, b: not _contains(a, b),
    "exists": lambda a, _b: a is not None,
    "not_exists": lambda a, _b: a is None,
    "regex": _regex,
    "in": _in,
    "not_in": _not_in,
}


def normalize_operator(op: str | None) -> str:
    if not op:
        return "eq"
    normalized = OPERATOR_ALIASES.get(op.strip(), op.strip())
    if normalized == "ne":
        return "neq"
    return normalized


def evaluate_operator(actual: Any, operator: str, expected: Any) -> bool:
    """协议无关的操作符求值入口：按名查找操作符并执行。

    未知操作符返回 False（不抛异常），与断言引擎的容错约定一致。
    """
    try:
        fn = OPERATORS[normalize_operator(operator)]
    except KeyError:
        return False
    return bool(fn(actual, expected))
