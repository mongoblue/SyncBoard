"""
ASGI 入口 —— 协议分流（HTTP ↔ WebSocket）。

拓扑：
  ProtocolTypeRouter {
    "http"     → Django ASGI（DRF 等所有 HTTP 请求）
    "websocket" → AuthMiddlewareStack → URLRouter → room.routing（含 qa_center WS）
  }

初始化顺序有严格要求：先在 clean env 下调 get_asgi_application()，再 import 路由。
如果把这改成懒加载（例如放到 ProtocolTypeRouter 内部 import），某些 ASGI server 会报 AppRegistryNotReady。
"""
import os
from django.core.asgi import get_asgi_application

# 1. 先设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# 2. 【关键】先初始化 Django ASGI 应用
# 这步必须在导入 room.routing 之前！因为它会加载 Django 的模型和配置
django_asgi_app = get_asgi_application()

# 3. 然后再导入你的路由 (因为 routing 需要用到加载好的环境)
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import room.routing

application = ProtocolTypeRouter({
    # HTTP 请求走 Django 原生 ASGI 处理
    "http": django_asgi_app,

    # WebSocket 请求走 Channels 处理
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                room.routing.websocket_urlpatterns
            )
        )
    ),
})
