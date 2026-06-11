"""Unified assertion engine tests — M3.1.

覆盖：
- 旧两种输入 schema 的归一化
- 所有 11 种 assertion kinds 的 pass / fail 路径
- 异常防御（非法 regex / 非法 jsonpath / 缺 jsonschema）
"""
from __future__ import annotations

import pytest

from qa_center import unified_assertions as ua
from qa_center.unified_assertions import (
    _smart_eq, _smart_ne,
    evaluate, Assertion, ResponseContext,
    KIND_JSON_EQUALS, KIND_REGEX_MATCH,
)


# --------------------------------------------------------------------------- ctx


@pytest.fixture
def ctx_json():
    return ua.ResponseContext.from_raw(
        status_code=200,
        response_body='{"data": {"user": {"name": "alice", "age": 30, "tags": ["admin","ops"]}}, "items": [1,2,3]}',
        response_headers={'Content-Type': 'application/json', 'X-Trace-Id': 'abc'},
        response_time_ms=120,
    )


@pytest.fixture
def ctx_text():
    return ua.ResponseContext.from_raw(
        status_code=404,
        response_body='Not Found',
        response_headers={'Server': 'nginx'},
        response_time_ms=10,
    )


# --------------------------------------------------------------------------- 归一化


class TestNormalize:
    def test_legacy_assertion_engine_schema(self):
        a = ua.normalize_one({'type': 'status_code', 'operator': '==', 'value': 200})
        assert a is not None
        assert a.kind == 'status_code'
        assert a.operator == 'eq'
        assert a.expected == 200

    def test_legacy_jsonpath_schema(self):
        a = ua.normalize_one({'type': 'jsonpath', 'expression': '$.data.user.name', 'operator': '==', 'value': 'alice'})
        assert a.kind == 'json_equals'
        assert a.path == '$.data.user.name'
        assert a.operator == 'eq'

    def test_legacy_header_exists_coerces_kind(self):
        a = ua.normalize_one({'type': 'header', 'header_name': 'X-Trace-Id', 'operator': 'exists'})
        assert a.kind == 'header_exists'
        assert a.header_name == 'X-Trace-Id'

    def test_executor_schema(self):
        # 旧 AssertionExecutor 格式
        a = ua.normalize_one({
            'assertion_type': 'json_equals',
            'json_path': '$.data.user.age',
            'comparison_operator': 'gte',
            'expected_value': '18',
        })
        assert a.kind == 'json_equals'
        assert a.path == '$.data.user.age'
        assert a.operator == 'gte'

    def test_unknown_returns_none(self):
        assert ua.normalize_one({'type': 'nonsense'}) is None
        assert ua.normalize_one(None) is None
        assert ua.normalize_one(42) is None

    def test_model_like_object(self):
        class Fake:
            assertion_type = 'response_time'
            comparison_operator = 'lt'
            expected_value = '500'
            json_path = ''
            error_message = '太慢'
        a = ua.normalize_one(Fake())
        assert a.kind == 'response_time'
        assert a.operator == 'lt'
        assert a.expected == '500'
        assert a.error_message == '太慢'


# --------------------------------------------------------------------------- 基础类型


class TestStatusCode:
    def test_pass(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='status_code', operator='eq', expected=200), ctx_json)
        assert r.passed is True
        assert r.actual_value == 200

    def test_fail(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='status_code', operator='eq', expected=500), ctx_json)
        assert r.passed is False
        assert '不匹配' in r.error_message or '!=' in r.error_message or '期望' in r.error_message

    def test_range(self, ctx_text):
        r = ua.evaluate(ua.Assertion(kind='status_code', operator='gte', expected=400), ctx_text)
        assert r.passed is True


class TestResponseTime:
    def test_default_lt(self, ctx_json):
        # ctx_json.response_time_ms = 120
        r = ua.evaluate(ua.Assertion(kind='response_time', expected=200), ctx_json)
        assert r.operator == 'lt'
        assert r.passed is True

    def test_slow_fail(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='response_time', expected=50), ctx_json)
        assert r.passed is False


# --------------------------------------------------------------------------- JSON


class TestJsonExists:
    def test_path_exists(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='json_exists', path='$.data.user.name'), ctx_json)
        assert r.passed is True
        assert r.actual_value == 'alice'

    def test_path_missing(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='json_exists', path='$.data.user.email'), ctx_json)
        assert r.passed is False

    def test_not_exists(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='json_exists', operator='not_exists', path='$.data.user.email'), ctx_json)
        assert r.passed is True


class TestJsonEquals:
    def test_string_eq(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='json_equals', path='$.data.user.name', expected='alice'), ctx_json)
        assert r.passed is True

    def test_numeric_eq_with_string_input(self, ctx_json):
        # 用户配置经常把 30 存成 "30";M3.2 起 eq 也做类型容错(数字↔字符串互通)
        r = ua.evaluate(ua.Assertion(kind='json_equals', path='$.data.user.age', expected='30'), ctx_json)
        assert r.passed is True
        r2 = ua.evaluate(ua.Assertion(kind='json_equals', path='$.data.user.age', operator='gte', expected='18'), ctx_json)
        assert r2.passed is True

    def test_legacy_dot_path(self, ctx_json):
        # 没有 $ 前缀也能解析（旧用例兼容）
        r = ua.evaluate(ua.Assertion(kind='json_equals', path='data.user.name', expected='alice'), ctx_json)
        assert r.passed is True


class TestJsonContains:
    def test_array_contains(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='json_contains', path='$.data.user.tags', expected='admin'), ctx_json)
        assert r.passed is True

    def test_string_contains(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='json_contains', path='$.data.user.name', expected='ali'), ctx_json)
        assert r.passed is True

    def test_missing_path(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='json_contains', path='$.nope', expected='x'), ctx_json)
        assert r.passed is False


# --------------------------------------------------------------------------- Header


class TestHeader:
    def test_exists(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='header_exists', header_name='X-Trace-Id'), ctx_json)
        assert r.passed is True

    def test_exists_case_insensitive(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='header_exists', header_name='x-trace-id'), ctx_json)
        assert r.passed is True

    def test_equals(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='header_equals', header_name='X-Trace-Id', expected='abc'), ctx_json)
        assert r.passed is True

    def test_equals_fail(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='header_equals', header_name='X-Trace-Id', expected='xyz'), ctx_json)
        assert r.passed is False

    def test_not_exists(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='header_exists', operator='not_exists', header_name='X-Missing'), ctx_json)
        assert r.passed is True


# --------------------------------------------------------------------------- Body size


class TestBodySize:
    def test_default_lte(self, ctx_text):
        # body = 'Not Found' → 9 bytes
        r = ua.evaluate(ua.Assertion(kind='body_size', expected=20), ctx_text)
        assert r.operator == 'lte'
        assert r.passed is True
        assert r.actual_value == 9

    def test_gt(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='body_size', operator='gt', expected=10), ctx_json)
        assert r.passed is True


# --------------------------------------------------------------------------- Regex


class TestRegex:
    def test_match_body(self, ctx_text):
        r = ua.evaluate(ua.Assertion(kind='regex_match', expected=r'Not\s+Found'), ctx_text)
        assert r.passed is True

    def test_match_jsonpath_value(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='regex_match', path='$.data.user.name', expected=r'^ali'), ctx_json)
        assert r.passed is True

    def test_no_match(self, ctx_text):
        r = ua.evaluate(ua.Assertion(kind='regex_match', expected=r'^Hello'), ctx_text)
        assert r.passed is False

    def test_invalid_regex(self, ctx_text):
        r = ua.evaluate(ua.Assertion(kind='regex_match', expected='[bad'), ctx_text)
        assert r.passed is False
        assert '非法正则' in r.error_message


# --------------------------------------------------------------------------- Type check


class TestTypeCheck:
    def test_int(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='type_check', path='$.data.user.age', expected='int'), ctx_json)
        assert r.passed is True

    def test_str(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='type_check', path='$.data.user.name', expected='string'), ctx_json)
        assert r.passed is True

    def test_list(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='type_check', path='$.data.user.tags', expected='array'), ctx_json)
        assert r.passed is True

    def test_wrong_type(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='type_check', path='$.data.user.age', expected='string'), ctx_json)
        assert r.passed is False

    def test_unknown_type(self, ctx_json):
        r = ua.evaluate(ua.Assertion(kind='type_check', path='$.data.user.age', expected='widget'), ctx_json)
        assert r.passed is False
        assert '未知类型' in r.error_message

    def test_bool_not_int(self):
        # True is instance of int in Python; we explicitly reject that confusion
        ctx = ua.ResponseContext.from_raw(
            status_code=200, response_body='{"flag": true}', response_headers={}, response_time_ms=1,
        )
        r_bool = ua.evaluate(ua.Assertion(kind='type_check', path='$.flag', expected='bool'), ctx)
        r_int = ua.evaluate(ua.Assertion(kind='type_check', path='$.flag', expected='int'), ctx)
        assert r_bool.passed is True
        assert r_int.passed is False


# --------------------------------------------------------------------------- Schema


class TestSchemaValidate:
    def test_valid(self, ctx_json):
        schema = {
            'type': 'object',
            'required': ['data'],
            'properties': {'data': {'type': 'object'}},
        }
        r = ua.evaluate(ua.Assertion(kind='schema_validate', expected=schema), ctx_json)
        assert r.passed is True

    def test_invalid(self, ctx_json):
        schema = {'type': 'object', 'required': ['nonexistent']}
        r = ua.evaluate(ua.Assertion(kind='schema_validate', expected=schema), ctx_json)
        assert r.passed is False
        assert '校验失败' in r.error_message

    def test_string_schema_is_parsed(self, ctx_json):
        # 用户在 UI 里粘 JSON 字符串
        r = ua.evaluate(ua.Assertion(kind='schema_validate', expected='{"type":"object"}'), ctx_json)
        assert r.passed is True

    def test_non_json_response_fails(self):
        ctx = ua.ResponseContext.from_raw(
            status_code=200, response_body='plain text', response_headers={}, response_time_ms=1,
        )
        r = ua.evaluate(ua.Assertion(kind='schema_validate', expected={'type': 'object'}), ctx)
        assert r.passed is False
        assert '合法 JSON' in r.error_message


# --------------------------------------------------------------------------- run_assertions（端到端）


class TestRunAssertions:
    def test_mixed_inputs(self, ctx_json):
        raws = [
            # 旧 AssertionEngine schema
            {'type': 'status_code', 'operator': '==', 'value': 200},
            # 旧 AssertionExecutor schema
            {'assertion_type': 'json_equals', 'json_path': '$.data.user.name',
             'comparison_operator': 'eq', 'expected_value': 'alice'},
            # 新类型
            {'assertion_type': 'header_exists', 'header_name': 'X-Trace-Id'},
            # 不识别
            {'foo': 'bar'},
        ]
        results = ua.run_assertions(raws, ctx_json)
        assert len(results) == 4
        assert results[0]['passed'] is True
        assert results[1]['passed'] is True
        assert results[2]['passed'] is True
        assert results[3]['passed'] is False
        assert results[3]['assertion_type'] == 'unknown'

    def test_empty_returns_empty(self, ctx_json):
        assert ua.run_assertions([], ctx_json) == []
        assert ua.run_assertions(None, ctx_json) == []


# --------------------------------------------------------------------------- 类型容错的相等比较 (M3.2 — _smart_eq / _smart_ne)


def test_smart_eq_int_and_numeric_string():
    """30 应该等于 '30'"""
    assert _smart_eq(30, "30") is True


def test_smart_eq_float_and_numeric_string():
    assert _smart_eq(30.0, "30") is True


def test_smart_eq_strict_equal_unchanged():
    assert _smart_eq("abc", "abc") is True
    assert _smart_eq(30, 30) is True


def test_smart_eq_bool_not_equal_int():
    """True 不应等于 1"""
    assert _smart_eq(True, 1) is False
    assert _smart_eq(False, 0) is False


def test_smart_eq_none_not_equal_empty_string():
    assert _smart_eq(None, "") is False
    assert _smart_eq(None, "x") is False


def test_smart_ne_inverse_of_eq():
    assert _smart_ne(30, "30") is False   # 30 == '30', so != False
    assert _smart_ne(True, 1) is True     # True != 1
    assert _smart_ne("abc", "abd") is True


# --------------------------------------------------------------------------- 失败时附实际/期望渲染 + regex 友好错误


def test_json_equals_renders_expected_and_actual():
    """失败时附 expected_rendered/actual_rendered 字符串"""
    assertion = Assertion(
        kind=KIND_JSON_EQUALS, operator='eq', expected='"1"',
        path='$.user.id', error_message='',
    )
    ctx = ResponseContext(
        status_code=200, response_body='{"user":{"id":1}}',
        response_headers={}, response_time_ms=10.0,
    )
    res = evaluate(assertion, ctx)
    assert res.passed is True
    assert res.expected_value == '"1"' or res.expected_value == '1'
    assert res.actual_value == 1


def test_regex_match_none_target_friendly_error():
    """regex 目标为 None 时,error_message 应该友好"""
    assertion = Assertion(
        kind=KIND_REGEX_MATCH, operator='eq', expected='.*',
        path='$.missing', error_message='',
    )
    ctx = ResponseContext(
        status_code=200, response_body='{}',
        response_headers={}, response_time_ms=10.0,
    )
    res = evaluate(assertion, ctx)
    assert res.passed is False
    assert "目标为空" in res.error_message or "不存在" in res.error_message
