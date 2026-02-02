from django.urls import re_path
from . import consumers, consumers_chat
from . import consumers_global # 导入新文件
from qa_center.routing import websocket_urlpatterns as qa_ws_patterns

websocket_urlpatterns = [
    re_path(r'ws/board/(?P<project_id>[\w-]+)/$', consumers.BoardConsumer.as_asgi()),

    re_path(r'ws/global/$', consumers_global.GlobalConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<project_id>[\w-]+)/$', consumers_chat.ChatConsumer.as_asgi()),

]+qa_ws_patterns