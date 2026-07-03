"""Webhook security utilities — signature verification, deduplication, rate limiting.

All webhook endpoints are publicly exposed (no session auth), so security
must be enforced at the application layer:

1. verify_webhook_signature — HMAC-SHA256 validation (GitHub/GitLab style)
2. check_webhook_dedup — prevent duplicate processing via cache key
3. compute_webhook_payload_hash — stable hash for dedup when external_run_id absent
4. check_webhook_rate_limit — sliding-window rate limit per config
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Dedup TTL: how long to remember a webhook payload before accepting again
_DEDUP_TTL_SEC = 300  # 5 minutes

# Rate limit: max requests per config per window
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW_SEC = 60


# ---------------------------------------------------------------------------
# Audit logger for webhook security events
# ---------------------------------------------------------------------------

_audit_logger = logging.getLogger("qa_center.webhooks.audit")


def log_webhook_audit(event: str, config_id, **extra):
    """Write a structured audit log for webhook security events.

    NEVER logs tokens, secrets, Authorization headers, or cookies.
    """
    safe_extra = {
        k: (v if k not in ("token", "secret", "signature", "authorization", "cookie")
            else "[redacted]")
        for k, v in extra.items()
    }
    _audit_logger.info(
        "webhook_audit event=%s config_id=%s %s",
        event, config_id,
        " ".join(f"{k}={v}" for k, v in safe_extra.items()),
    )


# ---------------------------------------------------------------------------
# Payload hash for dedup (when external_run_id is missing)
# ---------------------------------------------------------------------------

def compute_webhook_payload_hash(body: bytes, config_id: int) -> str:
    """Compute a stable SHA-256 hash of (canonical body + config_id).

    Used when the external CI platform does not provide an external_run_id
    in the webhook payload.  The hash is stable for identical payloads so
    duplicate deliveries can still be detected.

    Parameters
    ----------
    body : bytes
        Raw request body bytes.
    config_id : int
        The CiCdConfig primary key — scopes the hash to a single config.

    Returns
    -------
    str
        Hex-encoded SHA-256 digest.
    """
    # Canonicalise: sort keys so re-ordered JSON produces the same hash
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        canonical = body.decode("utf-8", errors="replace")

    seed = f"{config_id}:{canonical}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_webhook_signature(
    payload_body: bytes,
    signature_header: Optional[str],
    secret: str,
    *,
    header_prefix: str = "sha256=",
) -> bool:
    """Verify an HMAC-SHA256 webhook signature (GitHub / GitLab style).

    Parameters
    ----------
    payload_body : bytes
        Raw request body bytes.
    signature_header : str or None
        Value of the X-Hub-Signature-256 / X-Gitlab-Token header.
    secret : str
        Shared secret configured in the CI platform.
    header_prefix : str
        Prefix to strip from the header value before comparing (e.g. "sha256=").

    Returns
    -------
    bool
        True if signature matches, False otherwise.
    """
    if not secret or not signature_header:
        return False

    if not signature_header.startswith(header_prefix):
        return False

    expected_sig = signature_header[len(header_prefix):]
    computed_sig = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_sig, expected_sig)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup_key(ci_config_id: int, external_run_id: str) -> str:
    return f"webhook:dedup:{ci_config_id}:{external_run_id}"


def check_webhook_dedup(ci_config_id: int, external_run_id: str,
                        *, payload_body: bytes = b"") -> bool:
    """Return True if this webhook has already been processed (duplicate).

    Uses cache with a TTL to remember recently-seen webhook payloads.
    The first call for a given (config_id, run_id) returns False and sets
    the key; subsequent calls within the TTL return True.

    When *external_run_id* is empty (which some CI platforms omit), a
    stable SHA-256 hash of (canonical body + config_id) is used instead
    so that duplicate deliveries are still detected.

    Parameters
    ----------
    ci_config_id : int
        The CiCdConfig primary key.
    external_run_id : str
        The external pipeline/build ID from the CI platform.  May be empty.
    payload_body : bytes
        Raw request body bytes — used only when external_run_id is empty.

    Returns
    -------
    bool
        True = duplicate (should be ignored), False = new (proceed).
    """
    if external_run_id:
        dedup_key = external_run_id
    elif payload_body:
        dedup_key = compute_webhook_payload_hash(payload_body, ci_config_id)
    else:
        # No external ID and no body — cannot reliably dedup; allow through
        # but log a warning so operators can investigate.
        logger.warning(
            "Webhook dedup: no external_run_id and no body for config=%d; "
            "allowing through but dedup is unreliable.",
            ci_config_id,
        )
        log_webhook_audit("dedup_skipped_no_id", ci_config_id, reason="no_run_id_or_body")
        return False

    key = _dedup_key(ci_config_id, dedup_key)
    # cache.add returns True if the key was NOT already present
    is_new = cache.add(key, int(time.time()), timeout=_DEDUP_TTL_SEC)
    if not is_new:
        logger.warning(
            "Webhook dedup: duplicate webhook for config=%d run=%s",
            ci_config_id, dedup_key[:40],
        )
        log_webhook_audit("dedup_blocked", ci_config_id, dedup_key=dedup_key[:40])
    return not is_new


# ---------------------------------------------------------------------------
# Rate limiting (sliding window via cache)
# ---------------------------------------------------------------------------

def _rate_limit_key(ci_config_id: int, window: int) -> str:
    return f"webhook:ratelimit:{ci_config_id}:{window}"


def check_webhook_rate_limit(ci_config_id: int) -> Tuple[bool, int]:
    """Sliding-window rate limit: max 5 webhooks per config per 60 seconds.

    Uses a simple counter with expiration.  Not perfectly precise under
    high concurrency but sufficient for webhook protection.

    Parameters
    ----------
    ci_config_id : int
        The CiCdConfig primary key.

    Returns
    -------
    (blocked, current_count)
        blocked : True if the rate limit has been exceeded.
        current_count : Number of requests in the current window.
    """
    now = int(time.time())
    window = now // _RATE_LIMIT_WINDOW_SEC
    key = _rate_limit_key(ci_config_id, window)

    try:
        count = cache.incr(key)
    except ValueError:
        # Key doesn't exist yet — initialise with TTL slightly longer than window
        cache.set(key, 1, timeout=_RATE_LIMIT_WINDOW_SEC + 10)
        count = 1

    blocked = count > _RATE_LIMIT_MAX
    if blocked:
        logger.warning(
            "Webhook rate limit exceeded: config=%d count=%d/%d",
            ci_config_id, count, _RATE_LIMIT_MAX,
        )

    return blocked, count
