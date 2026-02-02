from django.urls import path
from .views import DataFactoryView, RunTestView

urlpatterns = [
    # 路由地址: /api/qa/data-factory/
    path('data-factory/', DataFactoryView.as_view(), name='data_factory'),
    path('run-test/', RunTestView.as_view(), name='run_test'),
]