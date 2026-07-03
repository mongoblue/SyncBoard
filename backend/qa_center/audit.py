"""
压力测试审计日志。

记录每次压测的关键操作：启动、停止、失败原因。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger('qa_center.audit')


def log_test_started(
    execution_id: int,
    user: str,
    project_id: Any,
    case_name: str,
    target_url: str,
    users: int,
    duration: int,
) -> None:
    """记录压测启动。"""
    logger.info(
        "[AUDIT] PERF_START execution_id=%s user=%s project=%s case=%s "
        "target=%s users=%s duration=%ss",
        execution_id, user, project_id, case_name,
        target_url, users, duration,
    )


def log_test_stopped(
    execution_id: int,
    user: str,
    reason: str = 'user_requested',
) -> None:
    """记录压测停止。"""
    logger.info(
        "[AUDIT] PERF_STOP execution_id=%s user=%s reason=%s",
        execution_id, user, reason,
    )


def log_test_failed(
    execution_id: int,
    reason: str,
    error_message: str = '',
    lifecycle_state: str = '',
) -> None:
    """记录压测失败。"""
    logger.error(
        "[AUDIT] PERF_FAIL execution_id=%s reason=%s lifecycle=%s error=%s",
        execution_id, reason, lifecycle_state, error_message[:200] if error_message else '',
    )


def log_test_completed(
    execution_id: int,
    total_requests: int,
    error_rate: float,
    avg_response_time: float,
    status: str,
) -> None:
    """记录压测完成。"""
    logger.info(
        "[AUDIT] PERF_COMPLETE execution_id=%s status=%s "
        "total_requests=%s error_rate=%.2f%% avg_rt=%.0fms",
        execution_id, status, total_requests, error_rate, avg_response_time,
    )
