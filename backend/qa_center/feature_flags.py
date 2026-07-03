from __future__ import annotations

from django.conf import settings


def use_unified_runner_for_api_auto_case() -> bool:
    return bool(
        getattr(settings, "USE_UNIFIED_API_RUNNER", False)
        and (
            getattr(settings, "USE_UNIFIED_RUNNER_FOR_API_AUTO", False)
            or getattr(settings, "USE_UNIFIED_RUNNER_FOR_API_AUTO_CASE", False)
        )
    )


def use_unified_runner_for_api_auto_suite() -> bool:
    return bool(
        getattr(settings, "USE_UNIFIED_API_RUNNER", False)
        and (
            getattr(settings, "USE_UNIFIED_RUNNER_FOR_API_AUTO", False)
            or getattr(settings, "USE_UNIFIED_RUNNER_FOR_API_AUTO_SUITE", False)
        )
    )


def use_unified_runner_for_runplan_serial() -> bool:
    return bool(
        getattr(settings, "USE_UNIFIED_API_RUNNER", False)
        and (
            getattr(settings, "USE_UNIFIED_RUNNER_FOR_RUNPLAN", False)
            or getattr(settings, "USE_UNIFIED_RUNNER_FOR_RUNPLAN_SERIAL", False)
        )
    )


def use_unified_runner_for_runplan_parallel() -> bool:
    return bool(
        getattr(settings, "USE_UNIFIED_API_RUNNER", False)
        and (
            getattr(settings, "USE_UNIFIED_RUNNER_FOR_RUNPLAN", False)
            or getattr(settings, "USE_UNIFIED_RUNNER_FOR_RUNPLAN_PARALLEL", False)
        )
    )


def use_unified_runner_for_async_triggers() -> bool:
    return bool(
        getattr(settings, "USE_UNIFIED_API_RUNNER", False)
        and getattr(settings, "USE_UNIFIED_RUNNER_FOR_ASYNC_TRIGGERS", False)
    )


def use_unified_runner_for_legacy() -> bool:
    return bool(
        getattr(settings, "USE_UNIFIED_API_RUNNER", False)
        and getattr(settings, "USE_UNIFIED_RUNNER_FOR_LEGACY", False)
    )
