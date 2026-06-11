"""统一的 API 断言引擎 —— M3.1。

历史上 SyncBoard 存在两套断言实现，schema 不一致：

  1. ``assertion_engine.AssertionEngine`` (legacy)
     存于 ``ApiTestCase.expected_response.assertions`` JSON。
     单条形如::

         {"type": "status_code|jsonpath|header",
          "operator": "==|!=|>|<|>=|<=|contains|exists",
          "value": ..., "expression": "$.foo", "header_name": "X-Foo"}

  2. ``api_auto_executor.AssertionExecutor``
     来自 ``ApiAutoTestAssertion`` 模型。单条形如::

         {"assertion_type": "status_code|json_equals|json_exists|json_contains|response_time",
          "comparison_operator": "eq|ne|gt|gte|lt|lte|contains|not_contains",
          "json_path": "$.foo", "expected_value": "..."}

本模块统一这两路输入到一个 ``Assertion`` dataclass，并扩展支持：

  * ``status_code`` / ``response_time``
  * ``json_equals`` / ``json_exists`` / ``json_contains``
  * ``header_equals`` / ``header_exists``
  * ``body_size``      —— 响应体字节数
  * ``regex_match``    —— 正则匹配字段值或整个响应体
  * ``type_check``     —— 字段类型断言 (int/str/list/dict/bool/null/number)
  * ``schema_validate``—— jsonschema 校验整个响应

迁移策略：不强制改库——执行器在拿到断言列表时调用 ``normalize_one`` 把
任意 schema 收敛到内部 ``Assertion``，再交给 ``run_assertions`` 评估。
执行结果使用与现有 ``AssertionExecutor`` 一致的字段，最大限度兼容前端。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - 软依赖
    from jsonpath_ng import parse as jsonpath_parse
    from jsonpath_ng.exceptions import JsonPathParserError
except Exception:  # pragma: no cover
    jsonpath_parse = None
    JsonPathParserError = Exception

try:  # pragma: no cover
    import jsonschema
except Exception:  # pragma: no cover
    jsonschema = None


# -------------------------------------------------------------------- 操作符表

# 旧 AssertionEngine 用 ==/!=/>... 这种符号，
# 旧 AssertionExecutor 用 eq/ne/gt... 这种缩写。
# 统一以下表为权威，符号会先映射成缩写。
_SYMBOL_TO_OP = {
    '==': 'eq', '=': 'eq',
    '!=': 'ne', '<>': 'ne',
    '>': 'gt', '<': 'lt',
    '>=': 'gte', '<=': 'lte',
}

OPERATORS: Dict[str, Any] = {
    'eq': lambda a, b: a == b,
    'ne': lambda a, b: a != b,
    'gt': lambda a, b: _safe_cmp(a, b, lambda x, y: x > y),
    'gte': lambda a, b: _safe_cmp(a, b, lambda x, y: x >= y),
    'lt': lambda a, b: _safe_cmp(a, b, lambda x, y: x < y),
    'lte': lambda a, b: _safe_cmp(a, b, lambda x, y: x <= y),
    'contains': lambda a, b: (b in a) if isinstance(a, (str, list, dict, tuple)) else (str(b) in str(a) if a is not None else False),
    'not_contains': lambda a, b: not OPERATORS['contains'](a, b),
    'exists': lambda a, _b: a is not None,
    'not_exists': lambda a, _b: a is None,
}


def _safe_cmp(a: Any, b: Any, fn) -> bool:
    """数字比较前尝试转 float，类型不匹配返回 False，避免抛 TypeError。"""
    try:
        if isinstance(a, str):
            a = float(a)
        if isinstance(b, str):
            b = float(b)
        return fn(a, b)
    except (TypeError, ValueError):
        return False


# -------------------------------------------------------------------- 数据结构


# 内部统一的断言种类
KIND_STATUS_CODE = 'status_code'
KIND_RESPONSE_TIME = 'response_time'
KIND_JSON_EQUALS = 'json_equals'
KIND_JSON_EXISTS = 'json_exists'
KIND_JSON_CONTAINS = 'json_contains'
KIND_HEADER_EQUALS = 'header_equals'
KIND_HEADER_EXISTS = 'header_exists'
KIND_BODY_SIZE = 'body_size'
KIND_REGEX_MATCH = 'regex_match'
KIND_TYPE_CHECK = 'type_check'
KIND_SCHEMA_VALIDATE = 'schema_validate'

ALL_KINDS = {
    KIND_STATUS_CODE, KIND_RESPONSE_TIME,
    KIND_JSON_EQUALS, KIND_JSON_EXISTS, KIND_JSON_CONTAINS,
    KIND_HEADER_EQUALS, KIND_HEADER_EXISTS,
    KIND_BODY_SIZE, KIND_REGEX_MATCH, KIND_TYPE_CHECK,
    KIND_SCHEMA_VALIDATE,
}


@dataclass
class Assertion:
    """内部归一化的断言定义。所有评估函数都吃这个结构。"""

    kind: str
    operator: str = 'eq'
    expected: Any = None
    # 通用定位字段：
    path: str = ''           # jsonpath / 字段路径
    header_name: str = ''    # response header 名
    error_message: str = ''  # 自定义失败文案


@dataclass
class AssertionResult:
    """评估结果。与 AssertionExecutor 的输出兼容，前端不用改。"""

    assertion_type: str
    operator: str = 'eq'
    expected_value: Any = None
    actual_value: Any = None
    passed: bool = False
    error_message: str = ''
    json_path: str = ''
    header_name: str = ''
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            'assertion_type': self.assertion_type,
            'operator': self.operator,
            'expected_value': self.expected_value,
            'actual_value': self.actual_value,
            'passed': self.passed,
            'error_message': self.error_message,
        }
        if self.json_path:
            d['json_path'] = self.json_path
        if self.header_name:
            d['header_name'] = self.header_name
        if self.extra:
            d.update(self.extra)
        return d


# -------------------------------------------------------------------- 归一化


def _norm_operator(op: Optional[str]) -> str:
    if not op:
        return 'eq'
    op = op.strip()
    return _SYMBOL_TO_OP.get(op, op)


def _coerce_legacy_type(t: str) -> str:
    """旧 AssertionEngine 的 type 字符串到内部 kind 的映射。"""
    if t == 'jsonpath':
        return KIND_JSON_EQUALS
    if t == 'header':
        # 旧的 header 类型在 operator=exists 时是存在断言，其它情况是值断言
        return KIND_HEADER_EQUALS
    return t  # status_code / 其它直接透传


def normalize_one(raw: Any) -> Optional[Assertion]:
    """把任意已知 schema（dict 或带属性的对象）转为 ``Assertion``。

    不能识别时返回 None，调用方应在结果里加一条 ``error_message`` 占位。
    """
    if raw is None:
        return None

    if hasattr(raw, 'assertion_type'):
        # 模型实例（ApiAutoTestAssertion）
        kind = raw.assertion_type
        op = _norm_operator(getattr(raw, 'comparison_operator', None))
        expected = getattr(raw, 'expected_value', None)
        path = getattr(raw, 'json_path', '') or ''
        err = getattr(raw, 'error_message', '') or ''
        header_name = ''
    elif isinstance(raw, dict):
        kind = raw.get('assertion_type') or _coerce_legacy_type(raw.get('type', '') or '')
        op = _norm_operator(raw.get('comparison_operator') or raw.get('operator'))
        expected = (
            raw['expected_value'] if 'expected_value' in raw
            else raw.get('value')
            if 'value' in raw
            else raw.get('expected')
        )
        path = raw.get('json_path') or raw.get('path') or raw.get('expression') or ''
        header_name = raw.get('header_name', '') or ''
        err = raw.get('error_message', '') or ''
    else:
        return None

    if kind not in ALL_KINDS:
        return None

    # exists 操作符下 header_equals 应该退化为 header_exists；
    # 旧 json_exists 也是 exists 语义。
    if kind == KIND_HEADER_EQUALS and op in ('exists', 'not_exists'):
        kind = KIND_HEADER_EXISTS
    if kind == KIND_JSON_EQUALS and op in ('exists', 'not_exists'):
        kind = KIND_JSON_EXISTS

    return Assertion(
        kind=kind,
        operator=op,
        expected=expected,
        path=str(path),
        header_name=str(header_name or raw.get('header_name', '') if isinstance(raw, dict) else header_name),
        error_message=err,
    )


# -------------------------------------------------------------------- 上下文


@dataclass
class ResponseContext:
    """评估时需要的响应快照。"""
    status_code: int
    response_body: str
    response_headers: Dict[str, str]
    response_time_ms: float
    # 解析后的 JSON（None 表示响应体不是合法 JSON）
    response_json: Optional[Any] = None

    @classmethod
    def from_raw(
        cls,
        *,
        status_code: int,
        response_body: str,
        response_headers: Optional[Dict[str, str]],
        response_time_ms: float,
    ) -> 'ResponseContext':
        rj = None
        if response_body:
            try:
                rj = json.loads(response_body)
            except (json.JSONDecodeError, TypeError):
                rj = None
        return cls(
            status_code=status_code,
            response_body=response_body or '',
            response_headers=dict(response_headers or {}),
            response_time_ms=float(response_time_ms or 0),
            response_json=rj,
        )


# -------------------------------------------------------------------- 字段抽取


def _extract_by_jsonpath(data: Any, path: str) -> Any:
    """尽力解析 jsonpath。空 path 返回整个 data；非法 path 返回 None。

    优先用 jsonpath-ng；失败时退化到简易点号/中括号解析（兼容旧用例里
    诸如 ``data.user.name`` / ``items[0].id`` 这种"非 $."的写法）。
    """
    if not path:
        return data
    if data is None:
        return None

    # 尝试 jsonpath-ng
    if jsonpath_parse is not None:
        norm = path if path.startswith('$') else f'$.{path}'
        try:
            matches = jsonpath_parse(norm).find(data)
            if not matches:
                # 退化到手工解析（兼容简单情形）
                return _manual_extract(data, path)
            if len(matches) == 1:
                return matches[0].value
            return [m.value for m in matches]
        except (JsonPathParserError, Exception):
            return _manual_extract(data, path)
    return _manual_extract(data, path)


def _manual_extract(data: Any, path: str) -> Any:
    if not path or data is None:
        return data
    # 把 a.b[0].c 这种规范化为 ['a','b','[0]','c']
    tokens: List[str] = []
    for seg in path.lstrip('$').lstrip('.').split('.'):
        if not seg:
            continue
        # 把 items[0] 拆成 items + [0]
        m = re.match(r'^([^\[]+)((?:\[\d+\])*)$', seg)
        if not m:
            tokens.append(seg)
            continue
        name, rest = m.group(1), m.group(2)
        if name:
            tokens.append(name)
        for idx in re.findall(r'\[(\d+)\]', rest or ''):
            tokens.append(f'[{idx}]')

    cur = data
    for tok in tokens:
        if cur is None:
            return None
        if tok.startswith('[') and tok.endswith(']'):
            try:
                i = int(tok[1:-1])
                if isinstance(cur, list) and 0 <= i < len(cur):
                    cur = cur[i]
                else:
                    return None
            except ValueError:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(tok)
        else:
            return None
    return cur


def _get_header_ci(headers: Dict[str, str], name: str) -> Optional[str]:
    """大小写不敏感的 header 取值。"""
    if not name:
        return None
    low = name.lower()
    for k, v in headers.items():
        if str(k).lower() == low:
            return v
    return None


# -------------------------------------------------------------------- 评估


_TYPE_TO_PY = {
    'int': int, 'integer': int,
    'str': str, 'string': str,
    'list': list, 'array': list,
    'dict': dict, 'object': dict,
    'bool': bool, 'boolean': bool,
    'float': float, 'number': (int, float),
    'null': type(None), 'none': type(None),
}


def evaluate(a: Assertion, ctx: ResponseContext) -> AssertionResult:
    """对单条断言做评估，必定返回 ``AssertionResult``（含错误描述）。"""

    res = AssertionResult(
        assertion_type=a.kind,
        operator=a.operator,
        expected_value=a.expected,
        json_path=a.path,
        header_name=a.header_name,
    )

    try:
        if a.kind == KIND_STATUS_CODE:
            actual = ctx.status_code
            expected = _try_int(a.expected, default=actual)
            res.actual_value = actual
            res.passed = OPERATORS.get(a.operator, OPERATORS['eq'])(actual, expected)
            if not res.passed:
                res.error_message = a.error_message or (
                    f'状态码不匹配：实际 {actual}，期望 {a.operator} {expected}'
                )
            return res

        if a.kind == KIND_RESPONSE_TIME:
            actual = ctx.response_time_ms
            expected = _try_float(a.expected, default=0.0)
            res.actual_value = actual
            # response_time 默认操作符为 lt（更友好）；eq 几乎没意义，统一改成 lt
            op = a.operator if a.operator in ('gt', 'gte', 'lt', 'lte', 'ne') else 'lt'
            res.passed = OPERATORS[op](actual, expected)
            res.operator = op
            if not res.passed:
                res.error_message = a.error_message or (
                    f'响应时间不达标：实际 {actual:.0f}ms，期望 {op} {expected}ms'
                )
            return res

        if a.kind == KIND_JSON_EXISTS:
            actual = _extract_by_jsonpath(ctx.response_json, a.path)
            res.actual_value = actual
            negated = a.operator == 'not_exists'
            exists = actual is not None
            res.passed = (not exists) if negated else exists
            if not res.passed:
                res.error_message = a.error_message or (
                    f'JSON 路径 "{a.path}" {"不应存在但存在" if negated else "不存在"}'
                )
            return res

        if a.kind == KIND_JSON_EQUALS:
            actual = _extract_by_jsonpath(ctx.response_json, a.path)
            res.actual_value = actual
            # 对 eq/ne 走严格相等（不强制把 "30" 解析成 30）；其余比较走 _safe_cmp 自动处理。
            if a.operator in ('eq', 'ne'):
                expected = _maybe_loads_structured(a.expected)
            else:
                expected = _maybe_loads_json(a.expected)
            res.passed = OPERATORS.get(a.operator, OPERATORS['eq'])(actual, expected)
            if not res.passed:
                res.error_message = a.error_message or (
                    f'路径 "{a.path}" 实际 {actual!r}, 期望 {a.operator} {expected!r}'
                )
            return res

        if a.kind == KIND_JSON_CONTAINS:
            actual = _extract_by_jsonpath(ctx.response_json, a.path)
            res.actual_value = actual
            if actual is None:
                res.passed = False
                res.error_message = a.error_message or f'路径 "{a.path}" 不存在'
                return res
            res.passed = OPERATORS['contains'](actual, a.expected)
            if not res.passed:
                res.error_message = a.error_message or (
                    f'路径 "{a.path}" 的值 {actual!r} 不包含 {a.expected!r}'
                )
            return res

        if a.kind == KIND_HEADER_EXISTS:
            v = _get_header_ci(ctx.response_headers, a.header_name)
            res.actual_value = v
            negated = a.operator == 'not_exists'
            exists = v is not None
            res.passed = (not exists) if negated else exists
            if not res.passed:
                res.error_message = a.error_message or (
                    f'响应头 "{a.header_name}" {"不应存在但存在" if negated else "不存在"}'
                )
            return res

        if a.kind == KIND_HEADER_EQUALS:
            v = _get_header_ci(ctx.response_headers, a.header_name)
            res.actual_value = v
            res.passed = OPERATORS.get(a.operator, OPERATORS['eq'])(v, a.expected)
            if not res.passed:
                res.error_message = a.error_message or (
                    f'响应头 "{a.header_name}" 实际 {v!r}, 期望 {a.operator} {a.expected!r}'
                )
            return res

        if a.kind == KIND_BODY_SIZE:
            actual = len((ctx.response_body or '').encode('utf-8'))
            expected = _try_int(a.expected, default=0)
            res.actual_value = actual
            # body_size 默认 lte（不超过）；精确字节相等几乎不会用到，统一退化到 lte。
            op = a.operator if a.operator in ('gt', 'gte', 'lt', 'lte', 'ne') else 'lte'
            res.passed = OPERATORS[op](actual, expected)
            res.operator = op
            if not res.passed:
                res.error_message = a.error_message or (
                    f'响应体大小不符：实际 {actual} 字节，期望 {op} {expected}'
                )
            return res

        if a.kind == KIND_REGEX_MATCH:
            # 有 path 时对提取值做正则，没有时对整个 body
            target = (
                _extract_by_jsonpath(ctx.response_json, a.path) if a.path else ctx.response_body
            )
            res.actual_value = target
            if target is None:
                res.passed = False
                res.error_message = a.error_message or '目标为空，无法匹配正则'
                return res
            pat = a.expected if isinstance(a.expected, str) else str(a.expected)
            try:
                ok = re.search(pat, str(target)) is not None
            except re.error as e:
                res.passed = False
                res.error_message = f'非法正则表达式: {e}'
                return res
            res.passed = ok
            if not ok:
                res.error_message = a.error_message or f'正则 /{pat}/ 未匹配'
            return res

        if a.kind == KIND_TYPE_CHECK:
            actual = _extract_by_jsonpath(ctx.response_json, a.path) if a.path else ctx.response_json
            res.actual_value = type(actual).__name__
            expected = (a.expected or '').strip().lower() if isinstance(a.expected, str) else ''
            py_type = _TYPE_TO_PY.get(expected)
            if py_type is None:
                res.passed = False
                res.error_message = f'未知类型: {a.expected!r}（支持: {", ".join(sorted(_TYPE_TO_PY))}）'
                return res
            # bool 是 int 的子类，单独判断避免 True/False 被认成 number
            if py_type is bool:
                res.passed = isinstance(actual, bool)
            elif py_type is int:
                res.passed = isinstance(actual, int) and not isinstance(actual, bool)
            else:
                res.passed = isinstance(actual, py_type)
            if not res.passed:
                res.error_message = a.error_message or (
                    f'路径 "{a.path}" 类型不符：实际 {res.actual_value}，期望 {expected}'
                )
            return res

        if a.kind == KIND_SCHEMA_VALIDATE:
            if jsonschema is None:
                res.passed = False
                res.error_message = '未安装 jsonschema 依赖'
                return res
            schema = _maybe_loads_json(a.expected)
            if not isinstance(schema, dict):
                res.passed = False
                res.error_message = 'schema 必须是 JSON 对象'
                return res
            if ctx.response_json is None:
                res.passed = False
                res.error_message = '响应体不是合法 JSON，无法 schema 校验'
                return res
            try:
                jsonschema.validate(instance=ctx.response_json, schema=schema)
                res.passed = True
            except jsonschema.ValidationError as ve:
                res.passed = False
                res.error_message = a.error_message or f'schema 校验失败: {ve.message}'
                res.extra['schema_path'] = list(ve.absolute_path)
            return res

        # 走到这里说明 ALL_KINDS 覆盖漏了一个 kind
        res.error_message = f'未实现的断言类型: {a.kind}'  # pragma: no cover
        return res

    except Exception as e:  # 防御：单条出错不应连累其它断言
        res.passed = False
        res.error_message = f'断言执行异常: {e}'
        return res


def run_assertions(
    assertions: List[Any],
    ctx: ResponseContext,
) -> List[Dict[str, Any]]:
    """对一组断言（任意输入 schema）做评估，返回前端友好的 dict 列表。"""

    results: List[Dict[str, Any]] = []
    for raw in assertions or []:
        norm = normalize_one(raw)
        if norm is None:
            # 保留一条占位结果便于排错
            results.append(AssertionResult(
                assertion_type='unknown',
                passed=False,
                error_message=f'无法识别的断言: {raw!r}',
            ).to_dict())
            continue
        results.append(evaluate(norm, ctx).to_dict())
    return results


# -------------------------------------------------------------------- helpers


def _try_int(v: Any, default: int) -> int:
    if v is None or v == '':
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def _try_float(v: Any, default: float) -> float:
    if v is None or v == '':
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _maybe_loads_json(v: Any) -> Any:
    """如果是看起来像 JSON 的字符串就尝试解析，否则原样返回。"""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return v
    if s[0] in '{[' or s in ('true', 'false', 'null') or _looks_like_number(s):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return v
    return v


def _maybe_loads_structured(v: Any) -> Any:
    """只解析结构化 JSON（对象/数组/true/false/null），不把数字字符串转成数字。

    用于 eq/ne 这种严格相等场景，避免 "30" == 30 这种类型混淆。
    """
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return v
    if s[0] in '{[' or s in ('true', 'false', 'null'):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return v
    return v


def _looks_like_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False
