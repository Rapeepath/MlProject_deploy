#!/usr/bin/env python
"""เครื่องมือบรรทัดคำสั่งของ Django (runserver, collectstatic, check ฯลฯ)"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "delivery_sim.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "ไม่พบ Django ในสภาพแวดล้อมนี้ "
            "ติดตั้งด้วย: pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
