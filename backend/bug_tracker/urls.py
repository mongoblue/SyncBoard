from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BugStatsView, BugViewSet, BugSeedDemoView

router = DefaultRouter()
router.register(r'bugs', BugViewSet, basename='bug')

urlpatterns = [
    path('bugs/stats/', BugStatsView.as_view(), name='bug_stats'),
    path('bugs/seed-demo/', BugSeedDemoView.as_view(), name='bug_seed_demo'),
    path('', include(router.urls)),
]
