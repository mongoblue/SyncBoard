from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable


REDACTED = "[REDACTED]"


@dataclass
class RedactionResult:
    value: Any
    redacted: bool


class SecretRedactor:
    """Redacts secret-like keys and values recursively."""

    DEFAULT_SECRET_NAMES = {
        "authorization",
        "token",
        "password",
        "secret",
        "api_key",
        "cookie",
        "set-cookie",
    }

    def __init__(
        self,
        *,
        secret_names: Iterable[str] | None = None,
        secret_values: Iterable[str] | None = None,
        min_secret_length: int = 6,
    ) -> None:
        provided_names = {str(name).lower() for name in (secret_names or set())}
        self.secret_names = self.DEFAULT_SECRET_NAMES | provided_names
        self.secret_values = {
            str(value)
            for value in (secret_values or set())
            if value not in (None, "") and len(str(value)) >= min_secret_length
        }

    def is_sensitive_key(self, key: Any) -> bool:
        return str(key).lower() in self.secret_names

    def redact_text(self, text: str) -> RedactionResult:
        if text is None:
            return RedactionResult("", False)

        redacted = False
        rendered = str(text)
        for secret in sorted(self.secret_values, key=len, reverse=True):
            if secret and secret in rendered:
                rendered = rendered.replace(secret, REDACTED)
                redacted = True
        return RedactionResult(rendered, redacted)

    def redact_value(self, value: Any, *, parent_key: str | None = None) -> RedactionResult:
        if parent_key and self.is_sensitive_key(parent_key):
            return RedactionResult(REDACTED, True)

        if isinstance(value, dict):
            changed = False
            rendered = {}
            for key, inner in value.items():
                result = self.redact_value(inner, parent_key=str(key))
                rendered[key] = result.value
                changed = changed or result.redacted
            return RedactionResult(rendered, changed)

        if isinstance(value, list):
            changed = False
            rendered = []
            for item in value:
                result = self.redact_value(item, parent_key=parent_key)
                rendered.append(result.value)
                changed = changed or result.redacted
            return RedactionResult(rendered, changed)

        if isinstance(value, tuple):
            changed = False
            rendered = []
            for item in value:
                result = self.redact_value(item, parent_key=parent_key)
                rendered.append(result.value)
                changed = changed or result.redacted
            return RedactionResult(tuple(rendered), changed)

        if isinstance(value, bytes):
            decoded = value.decode("utf-8", errors="ignore")
            return self.redact_text(decoded)

        if isinstance(value, str):
            return self.redact_text(value)

        return RedactionResult(value, False)

    @staticmethod
    def _truncate_utf8_bytes(text: str, limit_bytes: int) -> tuple[str, int, bool]:
        encoded = text.encode("utf-8")
        original_size = len(encoded)
        if original_size <= limit_bytes:
            return text, original_size, False
        preview = encoded[:limit_bytes].decode("utf-8", errors="ignore")
        return preview, original_size, True

    def make_text_envelope(
        self,
        value: Any,
        *,
        limit_bytes: int,
        content_type: str = "text/plain",
        encoding: str = "utf-8",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        redacted_value = self.redact_value(value)
        if isinstance(redacted_value.value, (dict, list, tuple)):
            serialized = json.dumps(redacted_value.value, ensure_ascii=False)
        elif redacted_value.value is None:
            serialized = ""
        else:
            serialized = str(redacted_value.value)

        preview, original_size, truncated = self._truncate_utf8_bytes(serialized, limit_bytes)
        preview_size = len(preview.encode("utf-8"))
        return {
            "preview": preview,
            "preview_size": preview_size,
            "truncated": truncated,
            "original_size": original_size,
            "limit_bytes": limit_bytes,
            "content_type": content_type,
            "encoding": encoding,
            "is_binary": False,
            "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest() if serialized else "",
            "redacted": redacted_value.redacted,
            "meta": meta or {},
        }

    @staticmethod
    def make_binary_envelope(
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "preview": None,
            "preview_size": 0,
            "truncated": True,
            "original_size": len(payload),
            "limit_bytes": 0,
            "content_type": content_type,
            "encoding": None,
            "is_binary": True,
            "sha256": hashlib.sha256(payload).hexdigest() if payload else "",
            "redacted": False,
            "meta": meta or {},
        }
