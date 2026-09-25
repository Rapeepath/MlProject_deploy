"""
เส้นทางของหน้าบ้าน

  /                     หน้า Dashboard
  /api/random/          สุ่มออเดอร์ (generate ในฝั่ง Django ไม่ต้องยิง backend)
  /api/predict/         ส่งออเดอร์ไปให้ Backend ทำนาย (proxy)
  /api/simulate/        สุ่มหลายออเดอร์ + ทำนายรวดเดียว
  /api/health/          เช็คสถานะ Backend

เหตุผลที่ proxy ผ่าน Django แทนที่จะให้เบราว์เซอร์ยิงหา Render ตรง ๆ:
  1. ไม่ต้องเปิด CORS กว้าง ๆ ที่ฝั่ง Backend
  2. URL ของ Backend ไม่หลุดไปอยู่ใน JavaScript ฝั่ง client
"""

from django.urls import path

from . import views

app_name = "simulator"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/random/", views.api_random_order, name="api_random"),
    path("api/predict/", views.api_predict, name="api_predict"),
    path("api/simulate/", views.api_simulate, name="api_simulate"),
    path("api/health/", views.api_health, name="api_health"),
]
