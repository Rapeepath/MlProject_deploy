"""
เส้นทางของหน้าบ้าน

  /                     หน้า Dashboard
  /api/random/          สุ่มออเดอร์ (generate ในฝั่ง Django ไม่ต้องยิง backend)
  /api/predict/         ส่งออเดอร์ไปให้ Backend ทำนาย (proxy)
  /api/simulate/        สุ่มหลายออเดอร์ + ทำนายรวดเดียว
  /api/health/          เช็คสถานะ Backend
  /api/test-sample/     ดึงออเดอร์จริงจาก text.csv + เปรียบเทียบ 2 โมเดล
  /api/compare/         เปรียบเทียบ 2 โมเดลจากออเดอร์ที่ส่งมาเอง
  /api/evaluate-batch/  รัน benchmark ทั้ง 1,000 แถว
  /api/testset-stats/   ข้อมูลสรุปของชุดทดสอบ

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

    # โหมดเปรียบเทียบ 2 โมเดลกับเฉลยจริงจาก text.csv
    path("api/test-sample/", views.api_test_sample, name="api_test_sample"),
    path("api/compare/", views.api_compare, name="api_compare"),
    path("api/evaluate-batch/", views.api_evaluate_batch, name="api_evaluate_batch"),
    path("api/testset-stats/", views.api_testset_stats, name="api_testset_stats"),
]
