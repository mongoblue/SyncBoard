from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('room.urls')),
    path('api/qa/', include('qa_center.urls'))
]
