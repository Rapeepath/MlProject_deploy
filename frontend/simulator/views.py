"""
View logic ของหน้าบ้าน Delivery ETA Simulator

หน้าที่หลัก:
  1. ดึงออเดอร์จริงพร้อมเฉลยจากชุดทดสอบ text.csv (ผ่าน Backend)
  2. ส่งให้ Backend ทำนายด้วย 2 โมเดล แล้วเทียบกับเฉลย
  3. สั่งรัน benchmark ทั้ง 1,000 แถว
  4. เสิร์ฟหน้าแผนที่ + แดชบอร์ดเปรียบเทียบ

หมายเหตุ: การ "สุ่มออเดอร์ขึ้นมาเอง" (generator.py) ยังเก็บไว้ที่ /api/random/
แต่หน้าเว็บไม่ได้ใช้แล้ว เพราะเปลี่ยนมาใช้ข้อมูลจริงที่มีเฉลยแทน

ทุก endpoint ของหน้าบ้านทำตัวเป็น proxy บาง ๆ ไปหา Backend เพื่อไม่ให้เบราว์เซอร์
ต้องยิงข้ามโดเมนเอง (ไม่ต้องเปิด CORS กว้าง และ URL ของ Backend ไม่หลุดไปฝั่ง client)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

import requests
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .generator import (
    available_cities,
    generate_random_orders,
)

logger = logging.getLogger(__name__)

# ฟิลด์ที่ Backend ต้องการครบทุกตัว (ตรงกับ OrderRequest ใน schemas.py)
ORDER_FIELDS: Tuple[str, ...] = (
    "Delivery_person_Age",
    "Delivery_person_Ratings",
    "Restaurant_latitude",
    "Restaurant_longitude",
    "Delivery_location_latitude",
    "Delivery_location_longitude",
    "Order_Date",
    "Time_Orderd",
    "Time_Order_picked",
    "Weather_conditions",
    "Road_traffic_density",
    "Vehicle_condition",
    "Type_of_order",
    "Type_of_vehicle",
    "multiple_deliveries",
    "Festival",
    "City",
    "ID",
    "Delivery_person_ID",
)

NUMERIC_FIELDS: Tuple[str, ...] = (
    "Delivery_person_Age",
    "Delivery_person_Ratings",
    "Restaurant_latitude",
    "Restaurant_longitude",
    "Delivery_location_latitude",
    "Delivery_location_longitude",
    "Vehicle_condition",
    "multiple_deliveries",
)


# =====================================================================
# ตัวช่วยคุยกับ Backend
# =====================================================================
class BackendError(Exception):
    """Backend ตอบไม่สำเร็จ หรือเชื่อมต่อไม่ได้"""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def call_backend(
    path: str,
    method: str = "GET",
    payload: Any = None,
    params: Any = None,
    timeout: float | None = None,
) -> Any:
    """เรียก Backend API พร้อมแปลง error ให้อ่านเข้าใจง่ายเป็นภาษาไทย

    timeout: ใส่เมื่อ endpoint นั้นใช้เวลานานกว่าปกติ (เช่น benchmark 1,000 แถว)
    """
    url = f"{settings.BACKEND_API_URL}{path}"
    try:
        response = requests.request(
            method,
            url,
            json=payload,
            params=params,
            timeout=timeout or settings.BACKEND_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
    except requests.exceptions.ConnectTimeout as exc:
        raise BackendError(
            "เชื่อมต่อ Backend ไม่ทันเวลา — ถ้าใช้ Render แพ็กเกจฟรี "
            "เซิร์ฟเวอร์อาจกำลังตื่นจากโหมดหลับ ลองใหม่อีกครั้งใน 1 นาที",
            504,
        ) from exc
    except requests.exceptions.ReadTimeout as exc:
        raise BackendError("Backend ตอบกลับช้าเกินกำหนด ลองใหม่อีกครั้ง", 504) from exc
    except requests.exceptions.ConnectionError as exc:
        raise BackendError(
            f"เชื่อมต่อ Backend ที่ {settings.BACKEND_API_URL} ไม่ได้ "
            "ตรวจสอบว่า service เปิดอยู่และตั้งค่า BACKEND_API_URL ถูกต้อง",
            503,
        ) from exc

    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        raise BackendError(detail, response.status_code)

    try:
        return response.json()
    except ValueError as exc:
        raise BackendError("Backend ตอบกลับมาในรูปแบบที่ไม่ใช่ JSON", 502) from exc


def _extract_error_detail(response: requests.Response) -> str:
    """ดึงข้อความ error จาก FastAPI (รองรับทั้ง 400 ธรรมดาและ 422 validation)"""
    try:
        body = response.json()
    except ValueError:
        return f"Backend ตอบกลับรหัส {response.status_code}"

    detail = body.get("detail", body)
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        # รูปแบบ validation error ของ FastAPI/Pydantic
        parts = []
        for item in detail:
            loc = " -> ".join(str(p) for p in item.get("loc", []) if p != "body")
            parts.append(f"{loc}: {item.get('msg', '')}".strip(": "))
        return "ข้อมูลไม่ผ่านการตรวจสอบ — " + "; ".join(parts)
    return json.dumps(detail, ensure_ascii=False)


def clean_order_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """คัดเฉพาะฟิลด์ที่ Backend รู้จัก และแปลงชนิดตัวเลขให้ถูกต้อง

    ข้อมูลจากฟอร์ม HTML มาเป็น string ทั้งหมด ถ้าส่งดิบ ๆ Pydantic จะตีกลับ 422
    """
    payload: Dict[str, Any] = {}
    for field in ORDER_FIELDS:
        if field not in raw or raw[field] in ("", None):
            continue
        value = raw[field]
        if field in NUMERIC_FIELDS:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise BackendError(f"ฟิลด์ {field} ต้องเป็นตัวเลข (ได้รับ '{value}')", 400)
            if field in ("Vehicle_condition",):
                value = int(value)
        payload[field] = value
    return payload


def _parse_json_body(request: HttpRequest) -> Dict[str, Any]:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackendError("เนื้อหา request ไม่ใช่ JSON ที่ถูกต้อง", 400) from exc
    if not isinstance(data, dict):
        raise BackendError("เนื้อหา request ต้องเป็น JSON object", 400)
    return data


# =====================================================================
# หน้า Dashboard
# =====================================================================
# ensure_csrf_cookie: หน้านี้ไม่มี <form> ที่จะเรนเดอร์ {% csrf_token %} ให้
# แต่ JavaScript ต้องใช้ csrftoken cookie ตอน POST ไป /api/simulate/
@ensure_csrf_cookie
@require_GET
def index(request: HttpRequest) -> HttpResponse:
    """หน้าแผนที่จำลองการส่งอาหาร

    หน้านี้เริ่มจากแผนที่ว่าง ผู้ใช้กดปุ่ม "Generate Rider" เพื่อสุ่มไรเดอร์ขึ้นมา
    ตัวหน้าเว็บจึงไม่ต้องมีออเดอร์ตั้งต้น ส่งไปแค่รายชื่อเมือง (พร้อมกรอบพิกัด)
    กับสถานะ Backend — และต้องเรนเดอร์ได้แม้ Backend ล่ม
    """
    backend_status: Dict[str, Any] = {"online": False, "detail": None, "metrics": None}
    try:
        health = call_backend("/health")
        backend_status = {
            "online": health.get("model_loaded", False),
            "detail": health.get("status"),
            "metrics": health.get("model_metrics"),
        }
    except BackendError as exc:
        logger.warning("ตรวจสอบสถานะ Backend ไม่สำเร็จ: %s", exc)
        backend_status["detail"] = str(exc)
        if not settings.ALLOW_BACKEND_DOWN:
            raise

    # จำนวนแถวในชุดทดสอบ ใช้แสดง "Test Sample #142 / 1000"
    testset_info: Dict[str, Any] = {"count": None}
    if backend_status["online"]:
        try:
            testset_info = call_backend("/testset/stats")
        except BackendError as exc:
            logger.warning("อ่านสถิติชุดทดสอบไม่สำเร็จ: %s", exc)

    context = {
        "backend_status": backend_status,
        # รายชื่อเมือง 22 แห่ง พร้อมกรอบพิกัดจริง — หน้าบ้านใช้วาดลวดลายแผนที่
        "cities": available_cities(),
        "testset": testset_info,
    }
    return render(request, "simulator/index.html", context)


# =====================================================================
# API สำหรับ AJAX
# =====================================================================
@require_GET
def api_random_order(request: HttpRequest) -> JsonResponse:
    """สุ่มออเดอร์ใหม่ (ทำในฝั่ง Django ตอบกลับทันที ไม่ต้องรอ Backend)"""
    city = request.GET.get("city") or None
    seed = request.GET.get("seed")
    try:
        count = int(request.GET.get("count", 1))
    except ValueError:
        return JsonResponse({"error": "count ต้องเป็นจำนวนเต็ม"}, status=400)
    count = max(1, min(count, 50))

    try:
        orders = generate_random_orders(
            count=count,
            seed=int(seed) if seed else None,
            city_code=city,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    payload = []
    for order in orders:
        name = order.pop("_city_name")
        code = order.pop("_city_code")
        payload.append({"order": order, "city_name": name, "city_code": code})

    return JsonResponse({"count": len(payload), "samples": payload})


@require_POST
def api_predict(request: HttpRequest) -> JsonResponse:
    """รับออเดอร์จากฟอร์ม -> ส่งต่อให้ Backend ทำนาย -> คืนผลกลับหน้าเว็บ"""
    try:
        body = _parse_json_body(request)
        payload = clean_order_payload(body)
        missing = [
            f
            for f in ORDER_FIELDS
            if f not in ("ID", "Delivery_person_ID") and f not in payload
        ]
        if missing:
            return JsonResponse(
                {"error": f"ข้อมูลไม่ครบ ขาดฟิลด์: {', '.join(missing)}"}, status=400
            )
        result = call_backend("/predict", method="POST", payload=payload)
    except BackendError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)

    return JsonResponse({"order": payload, "prediction": result})


@require_POST
def api_simulate(request: HttpRequest) -> JsonResponse:
    """จำลองหลายออเดอร์พร้อมกัน: สุ่มในฝั่ง Django แล้วส่งเป็น batch ไปทำนายทีเดียว

    ใช้ /predict/batch ของ Backend เพื่อยิงแค่รอบเดียว แทนที่จะยิง N รอบ
    (สำคัญมากกับ Render free tier ที่ latency สูง)
    """
    try:
        body = _parse_json_body(request)
        count = int(body.get("count", 5))
    except (BackendError, ValueError) as exc:
        status = exc.status_code if isinstance(exc, BackendError) else 400
        return JsonResponse({"error": str(exc)}, status=status)

    count = max(1, min(count, 50))
    city = body.get("city") or None
    seed = body.get("seed")

    try:
        generated = generate_random_orders(
            count=count,
            seed=int(seed) if seed not in (None, "") else None,
            city_code=city,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    city_names: List[str] = []
    city_codes: List[str] = []
    orders: List[Dict[str, Any]] = []
    for order in generated:
        city_names.append(order.pop("_city_name"))
        city_codes.append(order.pop("_city_code"))
        orders.append(order)

    try:
        result = call_backend("/predict/batch", method="POST", payload={"orders": orders})
    except BackendError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)

    predictions = result.get("predictions", [])
    combined = [
        {"order": o, "city_name": name, "city_code": code, "prediction": p}
        for o, name, code, p in zip(orders, city_names, city_codes, predictions)
    ]
    return JsonResponse(
        {"count": result.get("count", len(combined)), "results": combined, "summary": result.get("summary")}
    )


@require_GET
def api_health(request: HttpRequest) -> JsonResponse:
    """เช็คสถานะ Backend จากหน้าเว็บ (ใช้กับปุ่มลองเชื่อมต่อใหม่)"""
    try:
        health = call_backend("/health")
    except BackendError as exc:
        return JsonResponse({"online": False, "error": str(exc)}, status=exc.status_code)
    return JsonResponse({"online": health.get("model_loaded", False), "health": health})


# =====================================================================
# โหมดเปรียบเทียบ 2 โมเดล (ข้อมูลจริงพร้อมเฉลยจาก text.csv)
# =====================================================================
@require_GET
def api_test_sample(request: HttpRequest) -> JsonResponse:
    """ดึงออเดอร์จาก text.csv แล้วให้ Backend เปรียบเทียบ 2 โมเดลให้เลย

    ใช้ /compare/test-sample ของ Backend ซึ่งทำทั้งดึงข้อมูลและทำนายในครั้งเดียว
    จึงยิงแค่ request เดียวต่อการกดปุ่มหนึ่งครั้ง
    """
    params = {}
    index = request.GET.get("index")
    if index not in (None, ""):
        try:
            params["index"] = int(index)
        except ValueError:
            return JsonResponse({"error": "index ต้องเป็นจำนวนเต็ม"}, status=400)
    seed = request.GET.get("seed")
    if seed not in (None, ""):
        try:
            params["seed"] = int(seed)
        except ValueError:
            return JsonResponse({"error": "seed ต้องเป็นจำนวนเต็ม"}, status=400)

    try:
        result = call_backend("/compare/test-sample", params=params)
    except BackendError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)

    return JsonResponse(result)


@require_POST
def api_compare(request: HttpRequest) -> JsonResponse:
    """ส่งออเดอร์ที่ผู้ใช้กำหนดเองไปเปรียบเทียบ 2 โมเดล (เฉลยจะส่งมาหรือไม่ก็ได้)"""
    try:
        body = _parse_json_body(request)
        order = clean_order_payload(body.get("order", body))
        payload: Dict[str, Any] = {"order": order}
        actual = body.get("actual_minutes")
        if actual not in (None, ""):
            payload["actual_minutes"] = float(actual)
        result = call_backend("/compare", method="POST", payload=payload)
    except BackendError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)
    except (TypeError, ValueError) as exc:
        return JsonResponse({"error": f"actual_minutes ต้องเป็นตัวเลข ({exc})"}, status=400)

    return JsonResponse(result)


@require_POST
def api_evaluate_batch(request: HttpRequest) -> JsonResponse:
    """สั่งรัน benchmark ทั้งชุด 1,000 แถวที่ฝั่ง Backend

    งานนี้หนักกว่า request ปกติ (predict 1,000 แถว x 2 โมเดล) จึงขยาย timeout
    ให้ยาวกว่าค่าปกติ ไม่งั้นจะตัดกลางคันทั้งที่ Backend ยังคำนวณอยู่
    """
    try:
        body = _parse_json_body(request)
    except BackendError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)

    payload: Dict[str, Any] = {}
    limit = body.get("limit")
    if limit not in (None, ""):
        try:
            payload["limit"] = int(limit)
        except (TypeError, ValueError):
            return JsonResponse({"error": "limit ต้องเป็นจำนวนเต็ม"}, status=400)

    try:
        result = call_backend(
            "/evaluate-batch",
            method="POST",
            payload=payload,
            timeout=settings.BATCH_TIMEOUT,
        )
    except BackendError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)

    return JsonResponse(result)


@require_GET
def api_testset_stats(request: HttpRequest) -> JsonResponse:
    """ข้อมูลสรุปของชุดทดสอบ (ใช้แสดง 'x / 1000' บนหน้าเว็บ)"""
    try:
        return JsonResponse(call_backend("/testset/stats"))
    except BackendError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status_code)
