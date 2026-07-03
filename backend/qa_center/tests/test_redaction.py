from __future__ import annotations

import json

from qa_center.api_execution.redaction import REDACTED, SecretRedactor


def test_secret_redactor_does_not_value_redact_short_secret_values():
    redactor = SecretRedactor(secret_values={"abc", "long-secret-token"})

    rendered = redactor.redact_text("abc long-secret-token").value

    assert rendered == f"abc {REDACTED}"


def test_secret_redactor_redacts_nested_keys_and_values_recursively():
    redactor = SecretRedactor(secret_values={"top-secret-value"})

    result = redactor.redact_value(
        {
            "headers": {"Authorization": "Bearer top-secret-value"},
            "nested": [{"token": "top-secret-value"}],
            "plain": "top-secret-value",
        }
    )

    dumped = json.dumps(result.value, ensure_ascii=False)
    assert "top-secret-value" not in dumped
    assert REDACTED in dumped
    assert result.redacted is True
