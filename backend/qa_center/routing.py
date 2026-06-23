"""
QA Center WebSocket 路由 —— 5 条 WS。

路径列表：
  ws/qa/dashboard/              QAConsumer               测试计划执行进度（每用例完成时广播）
  ws/qa/recorder/               RecorderConsumer          UI 录制器（双向通信）
  ws/qa/performance/<id>/       PerformanceTestConsumer   性能测试实时指标
  ws/qa/test-run/<id>/          TestRunProgressConsumer   旧版测试运行进度
  ws/qa/run/<task_id>/          UiRunConsumer             UI 自动化执行进度

其中 QAConsumer 和 TestRunProgressConsumer 主要做进度推送（单向），
RecorderConsumer 为双向（接收录制指令 + 回传步骤），
PerformanceTestConsumer 流式传输性能指标。
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/qa/dashboard/$', consumers.QAConsumer.as_asgi()),
    re_path(r'ws/qa/recorder/$', consumers.RecorderConsumer.as_asgi()),
    re_path(r'ws/qa/performance/(?P<execution_id>\d+)/$', consumers.PerformanceTestConsumer.as_asgi()),
    re_path(r'ws/qa/test-run/(?P<run_id>\w+)/$', consumers.TestRunProgressConsumer.as_asgi()),
    re_path(r'ws/qa/run/(?P<task_id>\w+)/$', consumers.UiRunConsumer.as_asgi()),
]