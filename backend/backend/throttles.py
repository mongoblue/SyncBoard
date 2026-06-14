from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """登录接口限流: 每分钟 5 次"""
    rate = '5/minute'


class AIRateThrottle(UserRateThrottle):
    """AI 接口限流: 每分钟 20 次"""
    rate = '20/minute'


class WebSocketConnectThrottle(AnonRateThrottle):
    """WebSocket 连接限流: 每分钟 30 次"""
    rate = '30/minute'
