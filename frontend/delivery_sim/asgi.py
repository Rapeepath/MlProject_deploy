"""ASGI entry point (สำรองไว้เผื่อ deploy ด้วย uvicorn/daphne)"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "delivery_sim.settings")

application = get_asgi_application()
