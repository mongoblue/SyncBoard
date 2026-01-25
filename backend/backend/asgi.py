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
import room.routing

application = ProtocolTypeRouter({
    # HTTP 请求走 Django 原生 ASGI 处理
    "http": django_asgi_app,

    # WebSocket 请求走 Channels 处理
    "websocket": AuthMiddlewareStack(
        URLRouter(
            room.routing.websocket_urlpatterns
        )
    ),
})