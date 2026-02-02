from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/qa/dashboard/$', consumers.QAConsumer.as_asgi()),
]