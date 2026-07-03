from __future__ import annotations

import os

from django.conf import settings
from django.core.cache import CacheKeyWarning


class RuntimeGuard:
    """Centralized runtime environment decisions."""

    def get_app_env(self) -> str:
        return (os.environ.get("APP_ENV") or "local").strip().lower()

    def is_production(self) -> bool:
        return self.get_app_env() == "production"

    def is_strict(self) -> bool:
        return self.get_app_env() in {"staging", "production"}

    def require_celery_for_runtime_entrypoint(self) -> bool:
        return self.is_strict()

    def require_semaphore_for_performance(self) -> bool:
        return self.is_production()

    def require_shared_cache_for_webhooks(self) -> bool:
        """Return True if webhook rate limiting requires a shared cache.

        In staging/production, rate limiting with a local-memory cache
        (LocMemCache / DummyCache) is ineffective across multiple processes.
        This method returns True for strict environments to signal that
        the caller should verify a shared cache is configured.
        """
        return self.is_strict()

    def cache_is_shared(self) -> bool:
        """Best-effort check whether the default cache backend is shared.

        Returns False for LocMemCache / DummyCache (process-local).
        Returns True for Redis, Memcached, database-backed, or unknown backends.
        """
        try:
            from django.core.cache import caches
            backend = caches['default']
            backend_class = type(backend).__name__
            # These are process-local — not suitable for multi-process rate limiting
            if backend_class in ("LocMemCache", "DummyCache"):
                return False
            return True
        except Exception:
            # Conservative: if we can't determine, assume it's not shared
            return False

    def choose_default_transport(self) -> str:
        env = self.get_app_env()
        if env == "test":
            return "mock_transport"
        if env in {"staging", "production"}:
            return "ssrf_protected_requests_transport"
        return "requests_transport"

    def assert_mock_result_not_in_quality_report(self) -> bool:
        return self.get_app_env() in {"staging", "production"}

    def build_runtime_mode(
        self,
        *,
        guarded_rejected: bool = False,
        thread_fallback: bool = False,
        celery_eager: bool = False,
        is_mock: bool = False,
    ) -> str:
        if guarded_rejected:
            return "guarded_rejected"
        if thread_fallback:
            return "thread_fallback"
        if celery_eager:
            return "celery_eager"
        if is_mock:
            return "mock"
        return "real"

    def get_runtime_summary(self) -> dict:
        """Return a read-only summary of runtime configuration.

        Does NOT expose tokens, secrets, or sensitive settings.
        """
        return {
            "app_env": self.get_app_env(),
            "is_strict": self.is_strict(),
            "is_production": self.is_production(),
            "mock_allowed": not self.is_strict(),
            "celery_required": self.require_celery_for_runtime_entrypoint(),
            "use_real_ci": bool(getattr(settings, "USE_REAL_CI", False)),
            "use_celery_tasks": bool(getattr(settings, "USE_CELERY_TASKS", False)),
            "cache_is_shared": self.cache_is_shared(),
        }
