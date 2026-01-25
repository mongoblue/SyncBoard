from django.urls import re_path
from . import consumers, consumers_chat
from . import consumers_global # 导入新文件

websocket_urlpatterns = [
    re_path(r'ws/board/(?P<project_id>[\w-]+)/$', consumers.BoardConsumer.as_asgi()),
    # ✅ 新增全局通知路由
    re_path(r'ws/global/$', consumers_global.GlobalConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<project_id>[\w-]+)/$', consumers_chat.ChatConsumer.as_asgi()),
]