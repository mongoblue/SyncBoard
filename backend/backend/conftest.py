# backend/conftest.py
import os
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# 获取 channel_layer 用于发送消息。仅在 RunTestView 注入项目作用域时推送。
channel_layer = get_channel_layer()


def _dashboard_group_name():
    project_id = os.environ.get("QA_DASHBOARD_PROJECT_ID")
    if not project_id:
        return None
    return f"qa_dashboard_{project_id}"


def pytest_runtest_logreport(report):
    """
    Pytest 的内置钩子：每当一个测试用例有结果（Setup/Call/Teardown）时触发。
    """
    group_name = _dashboard_group_name()
    if not group_name:
        return

    # 我们只关心 "call" 阶段（即测试真正执行的阶段），并且忽略 skipped 的
    if report.when == 'call':
        status = "✅ PASS" if report.passed else "❌ FAIL"
        if report.failed:
            # 如果失败，带上错误信息
            error_msg = str(report.longrepr).split('\n')[-1]  # 取最后一行错误
        else:
            error_msg = ""

        # 构造消息内容
        message = {
            "type": "test_update",  # 对应 Consumer 里的处理器方法
            "nodeid": report.nodeid,  # 测试用例路径
            "status": status,
            "outcome": report.outcome,
            "duration": round(report.duration, 2),
            "error": error_msg,
            "timestamp": time.strftime("%H:%M:%S")
        }

        # 实时推送到 WebSocket Group
        # 注意：这里是在同步代码里调用异步的 channel_layer，所以要 wrap 一下
        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                message
            )
        except Exception as e:
            print(f"WebSocket Push Error: {e}")


# 可选：收集所有用例数量，用于计算进度条百分比
def pytest_collection_finish(session):
    group_name = _dashboard_group_name()
    if not group_name:
        return

    total = len(session.items)
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "test_meta",
            "total": total
        }
    )
