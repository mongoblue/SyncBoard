"""
Celery 入口。仅用于搜索索引异步更新（backend/tasks.py）。

当前有两项任务：
  - update_search_index: Haystack 模型级联更新
  - remove_from_search_index: 从索引中移除

Broker / Backend：在 settings.py 中通过 CELERY_BROKER_URL 指定（Redis）。
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')