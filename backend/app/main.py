"""
FastAPI service สำหรับทำนายเวลาจัดส่งอาหาร (ETA Prediction API)

Endpoints:
  GET  /                 ข้อมูลโดยย่อของ service
  GET  /health           สถานะและ metadata ของโมเดล (ใช้เป็น health check ของ Render)
  POST /predict          ทำนาย 1 ออเดอร์
  POST /predict/batch    ทำนายหลายออเดอร์พร้อมกัน (สูงสุด 200)
  GET  /random-sample    สุ่มออเดอร์ตามการกระจายตัวจริงของ Zomato Dataset
  GET  /random-sample/predict  สุ่มออเดอร์แล้วทำนายให้ในครั้งเดียว
  GET  /metadata         ค่าหมวดหมู่ ขอบเขตตัวเลข และรายชื่อเมือง (ให้หน้าบ้านสร้างฟอร์ม)

รันโลคัล:  uvicorn app.main:app --reload --port 8000
เอกสาร:    http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .predictor import KNOWN_LEVELS, REFERENCE_LEVELS, predictor
from .sampler import (
    AGE_MAX,
    AGE_MIN,
    PREP_TIME_CHOICES,
    RATING_MAX,
    RATING_MIN,
    available_cities,
    generate_random_order,
    generate_random_orders,
)
from .schemas import (
    BatchPredictRequest,
    BatchPredictionResponse,
    HealthResponse,
    OrderRequest,
    PredictionResponse,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("eta-api")

API_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """โหลดโมเดลตอน startup ครั้งเดียว ไม่ให้ request แรกต้องรอ ~129 MB"""
    started = time.perf_counter()
    try:
        predictor.load()
        logger.info("โหลดโมเดลเสร็จใน %.2f วินาที", time.perf_counter() - started)
    except Exception as exc:  # ไม่ให้ service ตายทั้งตัว /health จะรายงานว่าโหลดไม่สำเร็จ
        logger.exception("โหลดโมเดลไม่สำเร็จ: %s", exc)
    yield
    logger.info("ปิด service")


app = FastAPI(
    title="Food Delivery ETA Prediction API",
    description=(
        "ทำนายเวลาจัดส่งอาหารด้วย Random Forest ที่เทรนจาก Zomato Delivery Dataset "
        "(MAE 3.13 นาที, R² 0.83) พร้อมตัวสุ่มออเดอร์จำลองตามการกระจายตัวจริงของข้อมูล"
    ),
    version=API_VERSION,
    lifespan=lifespan,
)

# CORS: หน้าบ้าน Django บน Vercel เรียกข้ามโดเมนมา
_origins = os.getenv("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins.strip() == "*" else [o.strip() for o in _origins.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """แปลง ValueError จากขั้นตอน preprocessing ให้เป็น 400 แทน 500"""
    logger.warning("ข้อมูลเข้าไม่ถูกต้อง: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _ensure_model_loaded() -> None:
    if not predictor.is_loaded:
        try:
            predictor.load()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"โมเดลยังไม่พร้อมใช้งาน: {exc}") from exc


# =====================================================================
# Meta endpoints
# =====================================================================
@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Food Delivery ETA Prediction API",
        "version": API_VERSION,
        "docs": "/docs",
        "endpoints": ["/health", "/predict", "/predict/batch", "/random-sample", "/metadata"],
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """health check ที่บอกด้วยว่าโมเดลโหลดติดหรือยัง"""
    if not predictor.is_loaded:
        return HealthResponse(status="degraded", model_loaded=False, model_path=predictor.model_path)

    return HealthResponse(
        status="ok",
        model_loaded=True,
        model_type=type(predictor.model).__name__,
        n_features=len(predictor.feature_names),
        target_col=predictor.target_col,
        model_metrics=predictor.metrics,  # type: ignore[arg-type]
        model_path=predictor.model_path,
    )


@app.get("/metadata", tags=["meta"])
def metadata() -> dict:
    """ค่าที่หน้าบ้านต้องใช้สร้างฟอร์ม/dropdown และอธิบายโมเดล"""
    _ensure_model_loaded()
    return {
        "categorical_levels": {k: list(v) for k, v in KNOWN_LEVELS.items()},
        "reference_levels": REFERENCE_LEVELS,
        "numeric_ranges": {
            "Delivery_person_Age": {"min": AGE_MIN, "max": AGE_MAX},
            "Delivery_person_Ratings": {"min": RATING_MIN, "max": RATING_MAX, "step": 0.1},
            "Vehicle_condition": {"min": 0, "max": 3},
            "multiple_deliveries": {"min": 0, "max": 3},
        },
        "prep_time_choices": list(PREP_TIME_CHOICES),
        "cities": available_cities(),
        "feature_names": predictor.feature_names,
        "target_col": predictor.target_col,
        "model_metrics": predictor.metrics,
        "notes": {
            "bicycle": (
                "dataset ดิบมี bicycle 68 แถว แต่ถูกขั้นตอน cleaning ตัดทิ้งทั้งหมด "
                "โมเดลจึงไม่รู้จัก ถ้าส่งเข้ามาจะถูกตีเป็น electric_scooter"
            ),
            "reference_levels": (
                "หมวดหมู่ที่เป็นระดับอ้างอิงถูกเข้ารหัสเป็นศูนย์ทุกคอลัมน์ "
                "(ผลของ pd.get_dummies(drop_first=True) ตอนเทรน)"
            ),
        },
    }


# =====================================================================
# Prediction endpoints
# =====================================================================
@app.post("/predict", response_model=PredictionResponse, tags=["prediction"])
def predict(order: OrderRequest) -> dict:
    """ทำนายเวลาจัดส่งของออเดอร์เดียว

    ส่งข้อมูลดิบมาแบบเดียวกับ 1 แถวใน Zomato Dataset ได้เลย ฝั่ง server จะคำนวณ
    Distance_km / Prep_time_min / Order_hour / Order_period / Order_dayofweek /
    Is_weekend ให้เอง แล้วจัดคอลัมน์ให้ตรงกับที่โมเดลเทรนมา
    """
    _ensure_model_loaded()
    payload = order.model_dump(mode="json")
    return predictor.predict_one(payload)


@app.post("/predict/batch", response_model=BatchPredictionResponse, tags=["prediction"])
def predict_batch(request: BatchPredictRequest) -> dict:
    """ทำนายหลายออเดอร์พร้อมกัน พร้อมสรุปภาพรวมของทั้งชุด"""
    _ensure_model_loaded()
    payloads = [o.model_dump(mode="json") for o in request.orders]
    predictions = predictor.predict_many(payloads)

    minutes = [p["predicted_minutes"] for p in predictions]
    distances = [p["derived_features"]["Distance_km"] for p in predictions]

    return {
        "count": len(predictions),
        "predictions": predictions,
        "summary": {
            "mean_minutes": round(sum(minutes) / len(minutes), 2),
            "min_minutes": round(min(minutes), 2),
            "max_minutes": round(max(minutes), 2),
            "total_distance_km": round(sum(distances), 2),
        },
    }


# =====================================================================
# Random sample endpoints
# =====================================================================
@app.get("/random-sample", tags=["simulation"])
def random_sample(
    count: int = Query(1, ge=1, le=200, description="จำนวนออเดอร์ที่ต้องการสุ่ม"),
    seed: Optional[int] = Query(None, description="ใส่เพื่อให้สุ่มซ้ำได้ผลเดิม"),
    city: Optional[str] = Query(None, description="บังคับเมือง เช่น BANG, PUNE"),
) -> dict:
    """สุ่มออเดอร์จำลองตามการกระจายตัวจริงของ Zomato Dataset (ยังไม่ทำนาย)"""
    orders = generate_random_orders(count=count, seed=seed, city_code=city)
    return {
        "count": len(orders),
        "orders": [
            {k: v for k, v in o.items() if not k.startswith("_")} for o in orders
        ],
        "city_names": [o["_city_name"] for o in orders],
        "city_codes": [o["_city_code"] for o in orders],
    }


@app.get("/random-sample/predict", tags=["simulation"])
def random_sample_predict(
    count: int = Query(1, ge=1, le=50, description="จำนวนออเดอร์ที่สุ่มแล้วทำนายเลย"),
    seed: Optional[int] = Query(None),
    city: Optional[str] = Query(None),
) -> dict:
    """สุ่มออเดอร์แล้วทำนายให้ในครั้งเดียว (สะดวกสำหรับปุ่ม 'จำลองออเดอร์' หน้าบ้าน)"""
    _ensure_model_loaded()
    orders = generate_random_orders(count=count, seed=seed, city_code=city)

    results: List[dict] = []
    for order in orders:
        city_name = order.pop("_city_name")
        city_code = order.pop("_city_code")
        prediction = predictor.predict_one(order)
        results.append(
            {
                "order": order,
                "city_name": city_name,
                "city_code": city_code,
                "prediction": prediction,
            }
        )

    minutes = [r["prediction"]["predicted_minutes"] for r in results]
    return {
        "count": len(results),
        "results": results,
        "summary": {
            "mean_minutes": round(sum(minutes) / len(minutes), 2),
            "min_minutes": round(min(minutes), 2),
            "max_minutes": round(max(minutes), 2),
        },
    }
