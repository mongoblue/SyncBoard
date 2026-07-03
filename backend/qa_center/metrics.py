"""Observability utilities — structured task tracking and execution metrics.

Provides:
- task_tracker: context manager that logs task lifecycle (start/finish/fail)
  with duration_ms, trace_id, and execution_id.
- log_execution: helper for structured logging in Celery tasks.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_trace_id() -> str:
    """Generate a unique trace ID for full-chain observability."""
    return str(uuid.uuid4())


@dataclass
class TaskMetrics:
    """Structured metrics for a task execution."""
    trace_id: str = ""
    task_name: str = ""
    execution_id: str = ""
    status: str = "unknown"  # started / finished / failed
    duration_ms: Optional[int] = None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

@contextmanager
def task_tracker(
    task_name: str,
    execution_id: str = "",
    *,
    trace_id: Optional[str] = None,
    **extra,
):
    """Context manager that logs task lifecycle with duration.

    Usage::

        with task_tracker("execute_test_task", task_id, trace_id=tid):
            ... do work ...

    Logs:
    - On enter:  task_started  with trace_id, execution_id
    - On exit:   task_finished with duration_ms
    - On exception: task_failed with duration_ms + error
    """
    tid = trace_id or generate_trace_id()
    start = time.monotonic()

    logger.info(
        "task_started",
        extra={
            "task_name": task_name,
            "trace_id": tid,
            "execution_id": execution_id,
            **extra,
        },
    )

    try:
        yield tid
    except Exception:
        duration = int((time.monotonic() - start) * 1000)
        logger.exception(
            "task_failed",
            extra={
                "task_name": task_name,
                "trace_id": tid,
                "execution_id": execution_id,
                "duration_ms": duration,
                **extra,
            },
        )
        raise
    else:
        duration = int((time.monotonic() - start) * 1000)
        logger.info(
            "task_finished",
            extra={
                "task_name": task_name,
                "trace_id": tid,
                "execution_id": execution_id,
                "duration_ms": duration,
                **extra,
            },
        )


# ---------------------------------------------------------------------------
# Structured execution log
# ---------------------------------------------------------------------------

def log_execution(
    event: str,
    trace_id: str,
    execution_id: str = "",
    *,
    level: str = "info",
    **extra,
):
    """Log a structured execution event with trace_id and execution_id.

    Parameters
    ----------
    event : str
        Event name (e.g. "batch_started", "case_completed").
    trace_id : str
        Trace ID for full-chain correlation.
    execution_id : str
        Execution/batch ID for grouping.
    level : str
        Log level: "debug", "info", "warning", "error".
    """
    log_fn = getattr(logger, level, logger.info)
    log_fn(
        event,
        extra={
            "trace_id": trace_id,
            "execution_id": execution_id,
            **extra,
        },
    )
