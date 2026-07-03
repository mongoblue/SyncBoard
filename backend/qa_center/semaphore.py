"""Performance test concurrency control — Redis-backed semaphore + port allocation.

Prevents resource exhaustion when multiple Locust performance tests run
simultaneously.  Uses a Redis Lua script for atomic acquire/release so
that worker crashes do not permanently leak slots.

When Redis is unavailable the semaphore degrades gracefully (no limit).
"""

from __future__ import annotations

import logging
import socket
import time
from contextlib import contextmanager
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Semaphore TTL: if a worker crashes, the slot auto-expires after this
_SEMAPHORE_TTL_SEC = 600  # 10 minutes

# Port range for Locust web UIs
_PORT_RANGE_START = 8090
_PORT_RANGE_END = 8099

# Redis key prefix to avoid collisions
_KEY_PREFIX = "perf:semaphore"


# ---------------------------------------------------------------------------
# Redis connection helper
# ---------------------------------------------------------------------------

def _get_redis():
    """Return a Redis client or None if unavailable."""
    try:
        import redis
        host = getattr(settings, "REDIS_HOST", "127.0.0.1")
        return redis.Redis(host=host, port=6379, db=0, socket_timeout=2)
    except Exception:
        logger.warning("Redis unavailable — semaphore disabled (no concurrency limit)")
        return None


# ---------------------------------------------------------------------------
# Lua-backed semaphore
# ---------------------------------------------------------------------------

# Atomic acquire: adds member to sorted set only if under limit, sets TTL.
_ACQUIRE_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local member = ARGV[2]
local ttl = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

-- Clean expired members
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - ttl)

local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl + 10)
return 1
"""

# Atomic release
_RELEASE_LUA = """
local key = KEYS[1]
local member = ARGV[1]
redis.call('ZREM', key, member)
return 1
"""


class PerfSemaphore:
    """Redis-backed semaphore for performance test concurrency.

    Usage::

        sem = PerfSemaphore()
        if not sem.acquire(execution_id):
            raise RuntimeError("Too many concurrent performance tests")
        try:
            ... run locust ...
        finally:
            sem.release(execution_id)
    """

    def __init__(self):
        self._redis = _get_redis()
        self._max_concurrent = getattr(settings, "PERF_MAX_CONCURRENT", 5)
        self._acquire_script = None
        self._release_script = None
        if self._redis:
            try:
                self._acquire_script = self._redis.register_script(_ACQUIRE_LUA)
                self._release_script = self._redis.register_script(_RELEASE_LUA)
            except Exception as exc:
                logger.warning("Failed to register Lua scripts: %s", exc)
                self._redis = None

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    def acquire(self, execution_id) -> bool:
        """Try to acquire a concurrency slot.  Returns True on success.

        Redis 不可用时：
        - DEBUG=True (开发): fail-open（放行，不限并发）
        - DEBUG=False (生产): fail-closed（拒绝，返回 False）
        """
        if not self._redis or not self._acquire_script:
            debug = getattr(settings, 'DEBUG', True)
            if debug:
                logger.warning("Redis unavailable — semaphore disabled (fail-open in DEBUG mode)")
                return True
            else:
                logger.error("Redis unavailable — semaphore rejecting (fail-closed in production)")
                return False

        key = f"{_KEY_PREFIX}:slots"
        now = time.time()
        try:
            result = self._acquire_script(
                keys=[key],
                args=[self._max_concurrent, str(execution_id), _SEMAPHORE_TTL_SEC, now],
            )
            acquired = bool(result)
            if not acquired:
                logger.warning(
                    "Perf semaphore: denied execution_id=%s (limit=%d)",
                    execution_id, self._max_concurrent,
                )
            return acquired
        except Exception as exc:
            logger.error("Perf semaphore acquire error: %s", exc)
            debug = getattr(settings, 'DEBUG', True)
            return debug  # Fail open in dev, fail closed in prod

    def release(self, execution_id) -> None:
        """Release a concurrency slot."""
        if not self._redis or not self._release_script:
            return
        key = f"{_KEY_PREFIX}:slots"
        try:
            self._release_script(keys=[key], args=[str(execution_id)])
        except Exception as exc:
            logger.error("Perf semaphore release error: %s", exc)

    def active_count(self) -> int:
        """Return current number of active slots."""
        if not self._redis:
            return 0
        key = f"{_KEY_PREFIX}:slots"
        try:
            # Clean expired first
            self._redis.zremrangebyscore(key, "-inf", time.time() - _SEMAPHORE_TTL_SEC)
            return self._redis.zcard(key)
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Port allocation
# ---------------------------------------------------------------------------

def get_available_port(start: int = _PORT_RANGE_START, end: int = _PORT_RANGE_END) -> Optional[int]:
    """Find an available TCP port in [start, end].

    Returns the first free port, or None if all are occupied.
    """
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    logger.warning("No available port in range %d-%d", start, end)
    return None


# ---------------------------------------------------------------------------
# Convenience: semaphore context manager
# ---------------------------------------------------------------------------

@contextmanager
def perf_semaphore_context(execution_id):
    """Context manager that acquires the semaphore and releases on exit."""
    sem = PerfSemaphore()
    if not sem.acquire(execution_id):
        raise RuntimeError(
            f"Too many concurrent performance tests (limit: {sem.max_concurrent})"
        )
    try:
        yield sem
    finally:
        sem.release(execution_id)
