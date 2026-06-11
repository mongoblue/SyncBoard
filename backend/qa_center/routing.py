from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/qa/dashboard/$', consumers.QAConsumer.as_asgi()),
    re_path(r'ws/qa/recorder/$', consumers.RecorderConsumer.as_asgi()),
    re_path(r'ws/qa/performance/(?P<execution_id>\d+)/$', consumers.PerformanceTestConsumer.as_asgi()),
    re_path(r'ws/qa/test-run/(?P<run_id>\w+)/$', consumers.TestRunProgressConsumer.as_asgi()),
]