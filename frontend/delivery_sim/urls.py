"""URL หลักของโปรเจกต์ — มอบทุกเส้นทางให้ app simulator จัดการ"""

from django.urls import include, path

urlpatterns = [
    path("", include("simulator.urls")),
]
