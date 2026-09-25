"""
Django settings สำหรับหน้าบ้าน Delivery ETA Simulator

ออกแบบให้รันได้ทั้งบนเครื่องและบน Vercel Serverless:
  * ไม่ใช้ฐานข้อมูลเลย (DATABASES ว่าง) — หน้าบ้านเป็น stateless ทั้งหมด
    ข้อมูลออเดอร์ถูก generate ขึ้นมาสด ๆ แล้วส่งต่อให้ Backend API ทำนาย
    ทำให้ deploy บน serverless ได้โดยไม่ต้องต่อ DB และไม่ต้อง migrate
  * ตัด app ที่ต้องพึ่ง DB ออก (admin / auth / sessions) เหลือเท่าที่จำเป็น
  * เสิร์ฟ static ด้วย WhiteNoise โดยเปิด WHITENOISE_USE_FINDERS เพื่อให้
    ทำงานได้แม้ยังไม่ได้รัน collectstatic (สะดวกตอน deploy บน Vercel)
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# โหลด .env ถ้ามี (ตอน dev) — บน Vercel/Render ใช้ environment variables ของแพลตฟอร์มแทน
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # python-dotenv เป็น optional
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# =====================================================================
# Core
# =====================================================================
# บนโปรดักชันต้องตั้ง DJANGO_SECRET_KEY เสมอ ค่า fallback นี้มีไว้ให้รัน dev ได้ทันที
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-key-change-me-in-production-0123456789",
)

DEBUG = _env_bool("DJANGO_DEBUG", False)

# Vercel ให้โดเมน *.vercel.app มา ส่วน dev ใช้ localhost
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.vercel.app").split(",")
    if h.strip()
]

# Django >= 4 ต้องระบุ origin ที่เชื่อถือได้สำหรับ POST ที่มี CSRF token
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "https://*.vercel.app,http://localhost:8001,http://127.0.0.1:8001",
    ).split(",")
    if o.strip()
]

ROOT_URLCONF = "delivery_sim.urls"
WSGI_APPLICATION = "delivery_sim.wsgi.application"

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "simulator",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise ต้องอยู่ถัดจาก SecurityMiddleware ทันที
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

# ไม่ใช้ฐานข้อมูล — หน้าบ้านไม่เก็บ state ใด ๆ
DATABASES: dict = {}

# =====================================================================
# Static files (WhiteNoise)
# =====================================================================
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ใช้ finders เสิร์ฟไฟล์จาก STATICFILES_DIRS ตรง ๆ ทำให้ไม่ต้องรัน collectstatic
# ตอน build บน Vercel (ซึ่งทำได้ยุ่งยากกว่ากับ @vercel/python)
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# =====================================================================
# i18n / tz
# =====================================================================
LANGUAGE_CODE = "th"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =====================================================================
# การเชื่อมต่อ Backend API
# =====================================================================
# URL ของ FastAPI service บน Render (ไม่ต้องมี / ปิดท้าย)
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000").rstrip("/")

# timeout (วินาที) ตั้งเผื่อไว้สูงหน่อยเพราะ Render free tier จะ "หลับ" เมื่อไม่มีทราฟฟิก
# และใช้เวลา cold start ราว 30-60 วินาทีในการปลุก + โหลดโมเดล 129 MB
BACKEND_TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "60"))

# benchmark 1,000 แถว x 2 โมเดล ใช้เวลาราว 4 วินาทีบนเครื่องปกติ
# แต่บน instance เล็ก ๆ อาจนานกว่านั้นมาก จึงเผื่อไว้ยาว
BATCH_TIMEOUT = float(os.getenv("BATCH_TIMEOUT", "180"))

# ถ้าตั้งเป็น True เมื่อ Backend ล่ม หน้าบ้านจะยังสุ่มออเดอร์โชว์ได้ แต่ไม่มีผลทำนาย
ALLOW_BACKEND_DOWN = _env_bool("ALLOW_BACKEND_DOWN", True)

# =====================================================================
# Security (เปิดเฉพาะตอนไม่ใช่ DEBUG)
# =====================================================================
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    # Vercel ปิด TLS ให้ที่ edge แล้ว ส่ง header นี้มาบอก Django
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}
