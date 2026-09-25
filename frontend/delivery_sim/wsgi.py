"""
WSGI entry point

ใช้ได้ทั้งกับ runserver/gunicorn ตอน dev และกับ @vercel/python ตอน deploy
Vercel มองหาตัวแปรชื่อ `app` ในไฟล์ที่ระบุใน vercel.json จึงต้อง alias ไว้ด้วย
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "delivery_sim.settings")

application = get_wsgi_application()

# Vercel Serverless Function handler
app = application
