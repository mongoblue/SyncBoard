from __future__ import annotations

import pytest

from qa_center.assertion_core import (
    AssertionIR,
    AssertionResultIR,
    evaluate_operator,
    normalize_operator,
)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("eq", "eq"),
        ("==", "eq"),
        ("=", "eq"),
        ("neq", "neq"),
        ("ne", "neq"),
        ("!=", "neq"),
        ("<>", "neq"),
        ("gt", "gt"),
        (">", "gt"),
        ("lt", "lt"),
        ("<", "lt"),
        ("gte", "gte"),
        (">=", "gte"),
        ("lte", "lte"),
        ("<=", "lte"),
        ("contains", "contains"),
        ("exists", "exists"),
        ("regex", "regex"),
        ("regex_match", "regex"),
        ("in", "in"),
        ("not in", "not_in"),
        ("not_in", "not_in"),
    ],
)
def test_normalize_operator_supports_current_and_legacy_aliases(raw, normalized):
    assert normalize_operator(raw) == normalized


@pytest.mark.parametrize(
    ("actual", "operator", "expected", "passed"),
    [
        (3, "eq", "3", True),
        (3, "neq", 4, True),
        (5, "gt", 4, True),
        (3, "lt", 4, True),
        ("service-ready", "contains", "ready", True),
        ("grpc", "in", ["http", "grpc"], True),
        ("grpc", "not_in", ["http", "ws"], True),
        ("ready", "regex", r"^rea", True),
        (None, "exists", None, False),
    ],
)
def test_evaluate_operator_supports_protocol_agnostic_operators(
    actual,
    operator,
    expected,
    passed,
):
    assert evaluate_operator(actual, operator, expected) is passed


def test_assertion_ir_and_result_ir_are_protocol_agnostic():
    assertion = AssertionIR(
        type="field_compare",
        scope="queue.state",
        operator="eq",
        expected="ready",
        metadata={"protocol": "grpc"},
    )
    result = AssertionResultIR(
        type=assertion.type,
        scope=assertion.scope,
        operator=assertion.operator,
        expected=assertion.expected,
        actual="draining",
        passed=False,
        metadata={"protocol": "grpc"},
    )

    assert assertion.metadata["protocol"] == "grpc"
    assert result.metadata["protocol"] == "grpc"
    assert not hasattr(assertion, "status_code")
    assert not hasattr(assertion, "header_name")
    assert not hasattr(result, "http_status")
    assert result.passed is False
