from __future__ import annotations

from qa_center import api_execution


def test_snapshot_limits_are_bytes_not_characters():
    redactor = api_execution.SecretRedactor()
    envelope = redactor.make_text_envelope("你好世界", limit_bytes=5)

    assert envelope["truncated"] is True
    assert envelope["original_size"] == len("你好世界".encode("utf-8"))
    assert envelope["preview_size"] <= 5


def test_redaction_happens_before_truncation():
    secret = "super-secret-token"
    redactor = api_execution.SecretRedactor(secret_values={secret})
    envelope = redactor.make_text_envelope(
        f"prefix-{secret}-suffix",
        limit_bytes=10,
    )

    assert secret not in envelope["preview"]
    assert envelope["redacted"] is True
    assert envelope["truncated"] is True


def test_response_snapshot_binary_body_stores_metadata_only():
    runner = api_execution.UnifiedApiRunner(transport=api_execution.MockTransport())
    redactor = api_execution.SecretRedactor()
    response = api_execution.TransportResponse(
        status_code=200,
        headers={"Content-Type": "application/octet-stream"},
        cookies={},
        body_bytes=b"\x00\x01\x02binary-data",
        text="",
        elapsed_ms=3,
        final_url="https://api.example.test/file.bin",
        redirect_chain=[],
    )

    snapshot = runner._build_response_snapshot(response, redactor)

    assert snapshot["body"]["is_binary"] is True
    assert snapshot["body"]["preview"] is None
    assert snapshot["body"]["original_size"] == len(b"\x00\x01\x02binary-data")

