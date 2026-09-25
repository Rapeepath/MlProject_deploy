"""
FastAPI service สำหรับทำนายเวลาจัดส่งอาหาร (ETA Prediction API)

Endpoints:
  GET  /                 ข้อมูลโดยย่อของ service
  GET  /health           สถานะและ metadata ของโมเดล (ใช้เป็น health check ของ Render)
  POST /predict          ทำนาย 1 ออเดอร์
  POST /predict/batch    ทำนายหลายออเดอร์พร้อมกัน (สูงสุด 200)
  GET  /random-sample    สุ่มออเดอร์ตามการกระจายตัวจริงของ Zomato Dataset
  GET  /random-sample/predict  สุ่มออเดอร์แล้วทำนายให้ในครั้งเดียว
  GET  /metadata         ค่าหมวดหมู่ ขอบเขตตัวเลข และรายชื่อเมือง

  --- โหมดเปรียบเทียบ 2 โมเดล (เทียบกับเฉลยจริงจาก text.csv) ---
  GET  /test-samples     ดึง/สุ่มออเดอร์จากชุดทดสอบ 1,000 แถว พร้อมเฉลย
  POST /compare          ทำนายด้วยทั้ง 2 โมเดล แล้วเทียบกับเฉลย
  POST /evaluate-batch   ประเมินทั้งชุด 1,000 แถว สรุป MAE / %Accuracy / Win rate

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

from .predictor import KNOWN_LEVELS, REFERENCE_LEVELS, dual, predictor
from .testset import TARGET_COL, testset
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
    CompareRequest,
    CompareResponse,
    EvaluateBatchRequest,
    EvaluateBatchResponse,
    HealthResponse,
    OrderRequest,
    PredictionResponse,
    TestSamplesResponse,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("eta-api")

API_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """โหลดโมเดลทั้ง 2 ตัว + ชุดทดสอบ ตอน startup ครั้งเดียว

    รวมกันใช้ RAM ราว 690 MB (tuned ~236 MB + baseline ~301 MB + ไลบรารี ~150 MB)
    จึงต้องโหลดตอน startup ไม่ใช่ตอน request แรก
    """
    started = time.perf_counter()
    try:
        dual.load()
        logger.info("โหลดโมเดลทั้งสองตัวเสร็จใน %.2f วินาที", time.perf_counter() - started)
    except Exception as exc:  # ไม่ให้ service ตายทั้งตัว /health จะรายงานว่าโหลดไม่สำเร็จ
        logger.exception("โหลดโมเดลไม่สำเร็จ: %s", exc)

    try:
        testset.load()
    except Exception as exc:
        logger.exception("โหลดชุดทดสอบไม่สำเร็จ: %s", exc)

    yield
    logger.info("ปิด service")


app = FastAPI(
    title="Food Delivery ETA — Dual-Model Comparison API",
    description=(
        "ทำนายเวลาจัดส่งอาหารด้วย Random Forest 2 ตัว (Tuned vs Baseline) "
        "แล้วเทียบกับเฉลยจริงจากชุดทดสอบ 1,000 แถว พร้อมคำนวณ % ความแม่นยำ"
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
    """โมเดล tuned พร้อมหรือยัง (ใช้กับ endpoint โมเดลเดียว)"""
    if not predictor.is_loaded:
        try:
            predictor.load()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"โมเดลยังไม่พร้อมใช้งาน: {exc}") from exc


def _ensure_both_loaded() -> None:
    """ทั้งสองโมเดลพร้อมหรือยัง (ใช้กับ endpoint เปรียบเทียบ)"""
    if not dual.is_loaded:
        try:
            dual.load()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"โมเดลยังไม่พร้อมใช้งาน: {exc}"
            ) from exc


def _ensure_testset_loaded() -> None:
    if not testset.is_loaded:
        try:
            testset.load()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"โหลดชุดทดสอบไม่สำเร็จ: {exc}"
            ) from exc


# =====================================================================
# Meta endpoints
# =====================================================================
@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Food Delivery ETA Prediction API",
        "version": API_VERSION,
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/predict",
            "/predict/batch",
            "/random-sample",
            "/metadata",
            "/test-samples",
            "/compare",
            "/evaluate-batch",
        ],
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """health check ที่บอกด้วยว่าโมเดลทั้งสองตัวและชุดทดสอบพร้อมหรือยัง"""
    if not predictor.is_loaded:
        return HealthResponse(
            status="degraded", model_loaded=False, model_path=predictor.model_path
        )

    def describe(p) -> dict:
        params = p.model.get_params()
        return {
            "label": p.label,
            "loaded": p.is_loaded,
            "path": p.model_path,
            "type": type(p.model).__name__,
            "n_estimators": params.get("n_estimators"),
            "max_depth": params.get("max_depth"),
            "metrics": p.metrics,
        }

    return HealthResponse(
        status="ok" if dual.is_loaded else "degraded",
        model_loaded=True,
        model_type=type(predictor.model).__name__,
        n_features=len(predictor.feature_names),
        target_col=predictor.target_col,
        model_metrics=predictor.metrics,  # type: ignore[arg-type]
        model_path=predictor.model_path,
        both_models_loaded=dual.is_loaded,
        models=[describe(dual.tuned)] + ([describe(dual.baseline)] if dual.baseline.is_loaded else []),
        testset_loaded=testset.is_loaded,
        testset_rows=len(testset) if testset.is_loaded else None,
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


# =====================================================================
# โหมดเปรียบเทียบ 2 โมเดลกับเฉลยจริง (Dual-Model Comparison)
# =====================================================================
@app.get("/test-samples", response_model=TestSamplesResponse, tags=["comparison"])
def test_samples(
    index: Optional[int] = Query(
        None, ge=0, description="ระบุแถวที่ต้องการ (0-based) ถ้าไม่ใส่จะสุ่มให้"
    ),
    count: int = Query(1, ge=1, le=100, description="จำนวนแถวที่ต้องการสุ่ม"),
    seed: Optional[int] = Query(None, description="ใส่เพื่อให้สุ่มซ้ำได้ผลเดิม"),
    offset: Optional[int] = Query(
        None, ge=0, description="ดึงแบบเรียงลำดับจากตำแหน่งนี้ (แทนการสุ่ม)"
    ),
) -> dict:
    """ดึงออเดอร์จากชุดทดสอบ text.csv พร้อมเฉลย Time_taken (min)

    มี 3 โหมด:
      * ระบุ index  -> ได้แถวนั้นแถวเดียว
      * ระบุ offset -> ได้แถวเรียงลำดับตั้งแต่ตำแหน่งนั้น (ใช้ไล่ดูทั้งไฟล์)
      * ไม่ระบุ     -> สุ่ม count แถวแบบไม่ซ้ำ
    """
    _ensure_testset_loaded()

    if index is not None:
        try:
            rows = [testset.get(index)]
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    elif offset is not None:
        rows = testset.page(offset=offset, limit=count)
        if not rows:
            raise HTTPException(status_code=404, detail=f"ไม่มีข้อมูลที่ offset {offset}")
    else:
        rows = testset.sample(count=count, seed=seed)

    return {"total": len(testset), "count": len(rows), "samples": rows}


@app.post("/compare", response_model=CompareResponse, tags=["comparison"])
def compare(request: CompareRequest) -> dict:
    """ทำนายออเดอร์เดียวด้วยทั้ง 2 โมเดล แล้วเทียบกับเฉลย

    ถ้าส่ง actual_minutes มาด้วย จะได้ error / diff / % ความแม่นยำ / ผู้ชนะ
    ถ้าไม่ส่ง จะได้แค่คำทำนายของทั้งสองโมเดล (ไม่มีส่วน comparison)

    ฟีเจอร์ถูก build แค่ครั้งเดียวแล้วป้อนให้ทั้งสองโมเดล เพราะทั้งคู่ใช้
    สัญญาฟีเจอร์ 33 คอลัมน์ชุดเดียวกัน (ตรวจสอบตอน startup)
    """
    _ensure_both_loaded()
    payload = request.order.model_dump(mode="json")
    return dual.compare_one(payload, actual_minutes=request.actual_minutes)


@app.get("/compare/test-sample", response_model=CompareResponse, tags=["comparison"])
def compare_test_sample(
    index: Optional[int] = Query(None, ge=0, description="ระบุแถว ถ้าไม่ใส่จะสุ่มให้"),
    seed: Optional[int] = Query(None),
) -> dict:
    """ทางลัด: ดึงออเดอร์จาก text.csv แล้วเปรียบเทียบให้เลยในครั้งเดียว"""
    _ensure_both_loaded()
    _ensure_testset_loaded()

    try:
        row = testset.get(index) if index is not None else testset.random_one(seed=seed)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = dual.compare_one(row["order"], actual_minutes=row["actual_minutes"])
    result["test_index"] = row["index"]
    # ส่งข้อมูลดิบกลับไปด้วย หน้าบ้านต้องใช้วาดแผนที่และแสดงตารางรายละเอียด
    result["order"] = row["order"]
    return result


@app.post("/evaluate-batch", response_model=EvaluateBatchResponse, tags=["comparison"])
def evaluate_batch(request: Optional[EvaluateBatchRequest] = None) -> dict:
    """ประเมินทั้งสองโมเดลกับชุดทดสอบ แล้วสรุปภาพรวม

    ถ้าไม่ส่ง body มา (หรือไม่ส่ง orders) จะประเมินทั้ง text.csv 1,000 แถว
    ถ้าส่ง orders + actuals มาเอง จะประเมินชุดนั้นแทน

    คืนค่า: MAE / RMSE / R² / %Accuracy เฉลี่ยและมัธยฐาน / จำนวนครั้งที่แต่ละโมเดลชนะ
    """
    _ensure_both_loaded()
    started = time.perf_counter()

    if request is not None and request.orders:
        if not request.actuals or len(request.actuals) != len(request.orders):
            raise HTTPException(
                status_code=400,
                detail="ต้องส่ง actuals มาให้ครบและยาวเท่ากับ orders",
            )
        orders = []
        for order, actual in zip(request.orders, request.actuals):
            payload = order.model_dump(mode="json")
            payload[TARGET_COL] = actual
            orders.append(payload)
        source = f"ข้อมูลที่ส่งมาเอง ({len(orders)} แถว)"
    else:
        _ensure_testset_loaded()
        orders = testset.all_orders()
        if request is not None and request.limit:
            orders = orders[: request.limit]
        source = f"{testset.stats()['source']} ({len(orders)} แถว)"

    try:
        result = dual.evaluate_batch(orders)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["source"] = source
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    logger.info(
        "ประเมิน %d แถวใน %.2f วินาที | tuned MAE=%.4f vs baseline MAE=%.4f",
        result["evaluated"],
        result["elapsed_seconds"],
        result["tuned"]["MAE"],
        result["baseline"]["MAE"],
    )
    return result


@app.get("/testset/stats", tags=["comparison"])
def testset_stats() -> dict:
    """ข้อมูลสรุปของชุดทดสอบ (จำนวนแถว ช่วงของเฉลย ฯลฯ)"""
    _ensure_testset_loaded()
    return testset.stats()
