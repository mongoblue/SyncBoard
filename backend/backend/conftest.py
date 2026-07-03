# backend/conftest.py
import os
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connections


def _dashboard_group_name():
    project_id = os.environ.get("QA_DASHBOARD_PROJECT_ID")
    if not project_id:
        return None
    return f"qa_dashboard_{project_id}"


def pytest_runtest_logreport(report):
    """
    Pytest 内置钩子：每当一个测试用例有结果（Setup/Call/Teardown）时触发。
    """
    group_name = _dashboard_group_name()
    if not group_name:
        return

    if report.when == 'call':
        status = "PASS" if report.passed else "FAIL"
        if report.failed:
            error_msg = str(report.longrepr).split('\n')[-1]
        else:
            error_msg = ""

        message = {
            "type": "test_update",
            "nodeid": report.nodeid,
            "status": status,
            "outcome": report.outcome,
            "duration": round(report.duration, 2),
            "error": error_msg,
            "timestamp": time.strftime("%H:%M:%S"),
        }

        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return
            async_to_sync(channel_layer.group_send)(
                group_name,
                message,
            )
        except Exception:
            return


def pytest_collection_finish(session):
    group_name = _dashboard_group_name()
    if not group_name:
        return

    total = len(session.items)
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "test_meta",
                "total": total,
            },
        )
    except Exception:
        return


def pytest_configure(config):
    """
    Some test plugins and async helpers may touch Django DB wrappers from a
    different thread during full-suite startup/teardown. Allow thread sharing in
    the test process so setup_databases()/teardown_databases() can safely close
    wrappers without tripping Django's thread guard.
    """
    try:
        for connection in connections.all():
            connection.inc_thread_sharing()
    except Exception:
        return
