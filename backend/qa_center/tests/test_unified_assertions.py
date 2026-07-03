import pytest
from qa_center.assertion_core.ir import AssertionIR, AssertionResultIR
from qa_center.unified_assertions import (
    Assertion, ResponseContext, evaluate,
    KIND_STATUS_CODE, KIND_JSON_EQUALS, KIND_JSON_EXISTS, KIND_JSON_CONTAINS,
    KIND_HEADER_EXISTS,
)


def _ctx(status_code=200, body="", headers=None):
    return ResponseContext(
        status_code=status_code,
        response_body=body,
        response_headers=headers or {},
        response_time_ms=0,
    )


class TestAssertionCoreContracts:
    def test_protocol_agnostic_assertion_ir_has_no_http_specific_fields(self):
        ir = AssertionIR(
            type="event",
            scope="message",
            path="payload.status",
            operator="eq",
            expected="ok",
            provider="websocket",
            source="provider_default",
            metadata={"channel": "chat"},
        )

        assert ir.type == "event"
        assert ir.scope == "message"
        assert ir.provider == "websocket"
        assert ir.metadata["channel"] == "chat"
        assert not hasattr(ir, "positive")
        assert not hasattr(ir, "negative")
        assert not hasattr(ir, "success_status_set")

    def test_protocol_agnostic_result_ir_tracks_generic_outcome(self):
        result = AssertionResultIR(
            type="metric",
            scope="latency",
            operator="lte",
            expected=200,
            actual=180,
            passed=True,
            provider="performance",
            source="explicit",
        )

        assert result.passed is True
        assert result.scope == "latency"
        assert result.provider == "performance"
        assert result.actual == 180

    @pytest.mark.parametrize(
        ("raw", "normalized"),
        [
            ("==", "eq"),
            ("=", "eq"),
            ("!=", "neq"),
            ("<>", "neq"),
            ("ne", "neq"),
            ("neq", "neq"),
            ("regex_match", "regex"),
            ("matches", "regex"),
            ("has", "contains"),
            ("member_of", "in"),
            ("not-member-of", "not_in"),
        ],
    )
    def test_operator_aliases_normalize_through_unified_entry(self, raw, normalized):
        ir = Assertion.from_ir(AssertionIR(type="status_code", operator=normalized, expected=200))
        normalized_assertion = ir.normalize_operator(raw)
        assert normalized_assertion == normalized


class TestStatusCodeAssertions:
    def test_eq_pass(self):
        a = Assertion(kind=KIND_STATUS_CODE, operator="eq", expected=200)
        result = evaluate(a, _ctx(200))
        assert result.passed is True

    def test_eq_fail(self):
        a = Assertion(kind=KIND_STATUS_CODE, operator="eq", expected=200)
        result = evaluate(a, _ctx(404))
        assert result.passed is False

    def test_ne_pass(self):
        a = Assertion(kind=KIND_STATUS_CODE, operator="ne", expected=500)
        result = evaluate(a, _ctx(200))
        assert result.passed is True


class TestJSONPathAssertions:
    def test_simple_field_eq(self):
        a = Assertion(kind=KIND_JSON_EQUALS, operator="eq", expected="Alice", path="$.name")
        result = evaluate(a, _ctx(body='{"name":"Alice","age":30}'))
        assert result.passed is True

    def test_simple_field_ne(self):
        a = Assertion(kind=KIND_JSON_EQUALS, operator="ne", expected="Bob", path="$.name")
        result = evaluate(a, _ctx(body='{"name":"Alice"}'))
        assert result.passed is True

    def test_nested_path(self):
        a = Assertion(kind=KIND_JSON_EQUALS, operator="eq", expected="NYC", path="$.user.profile.city")
        result = evaluate(a, _ctx(body='{"user":{"profile":{"city":"NYC"}}}'))
        assert result.passed is True

    def test_array_contains(self):
        a = Assertion(kind=KIND_JSON_CONTAINS, operator="contains", expected="python", path="$.tags")
        result = evaluate(a, _ctx(body='{"tags":["python","django"]}'))
        assert result.passed is True

    def test_array_contains_fail(self):
        a = Assertion(kind=KIND_JSON_CONTAINS, operator="contains", expected="java", path="$.tags")
        result = evaluate(a, _ctx(body='{"tags":["python","django"]}'))
        assert result.passed is False

    def test_exists(self):
        a = Assertion(kind=KIND_JSON_EXISTS, operator="exists", expected=None, path="$.id")
        result = evaluate(a, _ctx(body='{"id":1}'))
        assert result.passed is True

    def test_exists_fail(self):
        a = Assertion(kind=KIND_JSON_EXISTS, operator="exists", expected=None, path="$.nonexistent")
        result = evaluate(a, _ctx(body='{"id":1}'))
        assert result.passed is False


class TestHeaderAssertions:
    def test_header_exists(self):
        a = Assertion(kind=KIND_HEADER_EXISTS, operator="contains", expected="json", header_name="Content-Type")
        result = evaluate(a, _ctx(headers={"Content-Type": "application/json"}))
        assert result.passed is True
