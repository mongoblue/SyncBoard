"""
WebSocket 路由汇总中心。

所有 WS 路由汇总在此文件：
  ws/board/<project_id>/    BoardConsumer        看板实时同步
  ws/global/               GlobalConsumer        全局通知
  ws/chat/<project_id>/    ChatConsumer          聊天室

另有 qa_center 的 5 条 WS 路由（通过 qa_center.routing 引用），目录：
  ws/qa/dashboard/、ws/qa/recorder/、ws/qa/performance/<id>/
  ws/qa/test-run/<id>/、ws/qa/run/<id>/

单条 WS 的协议定义见各自 Consumer 文件。
"""
from django.urls import re_path
from . import consumers, consumers_chat
from . import consumers_global # 导入新文件
from qa_center.routing import websocket_urlpatterns as qa_ws_patterns

websocket_urlpatterns = [
    re_path(r'ws/board/(?P<project_id>[\w-]+)/$', consumers.BoardConsumer.as_asgi()),

    re_path(r'ws/global/$', consumers_global.GlobalConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<project_id>[\w-]+)/$', consumers_chat.ChatConsumer.as_asgi()),

]+qa_ws_patterns