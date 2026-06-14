import os
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """登录接口限流。CI 用 LOGIN_THROTTLE_RATE=10000/minute 关闭。"""
    rate = os.environ.get('LOGIN_THROTTLE_RATE', '5/minute')


class AIRateThrottle(UserRateThrottle):
    """AI 接口限流"""
    rate = os.environ.get('AI_THROTTLE_RATE', '20/minute')


class WebSocketConnectThrottle(AnonRateThrottle):
    """WebSocket 连接限流"""
    rate = os.environ.get('WS_THROTTLE_RATE', '30/minute')
