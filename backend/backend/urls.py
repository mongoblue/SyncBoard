"""
顶层 URL 装配。

路由前缀 → App：
  /api/        → room（看板/项目/AI/通知）
  /api/qa/     → qa_center（测试中心）
  /api/system/ → system（RBAC）
  /api/        → bug_tracker（缺陷）
  /admin/      → Django Admin
  /media/      → 静态文件服务（解决 uvicorn 下图片加载问题）

注意：/api/ 同时指向 room 和 bug_tracker，所以两者路由路径不能冲突。
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({'status': 'ok'})

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('admin/', admin.site.urls),
    path('api/', include('room.urls')),
    path('api/qa/', include('qa_center.urls')),
    path('api/system/', include('system.urls')),
    path('api/', include('bug_tracker.urls')),
    # 强制开启 media 文件服务，解决 uvicorn 下图片无法加载的问题
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
