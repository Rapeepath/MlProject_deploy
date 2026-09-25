"""
Pydantic schemas สำหรับตรวจสอบ Request / Response ของ ETA Prediction API

ค่าที่ยอมรับได้ (enum + ขอบเขตตัวเลข) อ้างอิงจากการสำรวจ Zomato Dataset.csv จริง
หลังผ่านขั้นตอน cleaning เดียวกับใน Untitled42.ipynb:

  - Delivery_person_Age        : 15 - 50 ปี
  - Delivery_person_Ratings    : 1.0 - 5.0 (ค่า > 5.0 ในไฟล์ดิบถือว่าผิดปกติ)
  - พิกัด                       : อยู่ในกรอบประเทศอินเดีย (lat 8-35, lon 68-92)
  - Vehicle_condition          : 0 - 3
  - multiple_deliveries        : 0 - 3
  - Prep_time_min (คำนวณเอง)    : พบเพียง 5 / 10 / 15 นาที
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# =====================================================================
# Enum ของตัวแปรหมวดหมู่ (ตรงกับค่าที่พบจริงใน dataset)
# =====================================================================
class WeatherConditions(str, Enum):
    sunny = "Sunny"
    stormy = "Stormy"
    sandstorms = "Sandstorms"
    cloudy = "Cloudy"
    fog = "Fog"
    windy = "Windy"


class RoadTrafficDensity(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    jam = "Jam"


class TypeOfOrder(str, Enum):
    snack = "Snack"
    meal = "Meal"
    drinks = "Drinks"
    buffet = "Buffet"


class TypeOfVehicle(str, Enum):
    motorcycle = "motorcycle"
    scooter = "scooter"
    electric_scooter = "electric_scooter"
    bicycle = "bicycle"


class Festival(str, Enum):
    yes = "Yes"
    no = "No"


class City(str, Enum):
    metropolitian = "Metropolitian"   # สะกดตามใน dataset ต้นฉบับ (ไม่ใช่ Metropolitan)
    urban = "Urban"
    semi_urban = "Semi-Urban"
    unknown = "Unknown"               # ค่าที่ notebook เติมแทน NaN -> มี dummy จริงในโมเดล


# =====================================================================
# Request
# =====================================================================
class OrderRequest(BaseModel):
    """ออเดอร์ 1 รายการในรูปแบบ "ข้อมูลดิบ" เหมือนหนึ่งแถวของ Zomato Dataset

    ฟีเจอร์ที่โมเดลใช้จริง (Distance_km, Prep_time_min, Order_hour, Order_period,
    Order_dayofweek, Is_weekend) จะถูกคำนวณให้อัตโนมัติฝั่ง server ใน predictor.py
    ผู้เรียก API ไม่ต้องส่งมาเอง
    """

    Delivery_person_Age: float = Field(..., ge=15, le=50, description="อายุไรเดอร์ (ปี)")
    Delivery_person_Ratings: float = Field(..., ge=1.0, le=5.0, description="คะแนนไรเดอร์ 1.0-5.0")

    Restaurant_latitude: float = Field(..., description="ละติจูดร้านอาหาร")
    Restaurant_longitude: float = Field(..., description="ลองจิจูดร้านอาหาร")
    Delivery_location_latitude: float = Field(..., description="ละติจูดจุดส่ง")
    Delivery_location_longitude: float = Field(..., description="ลองจิจูดจุดส่ง")

    Order_Date: str = Field(..., description="วันที่สั่ง รูปแบบ DD-MM-YYYY", examples=["12-02-2022"])
    Time_Orderd: str = Field(..., description="เวลาที่สั่ง รูปแบบ HH:MM", examples=["21:55"])
    Time_Order_picked: str = Field(..., description="เวลาที่ไรเดอร์รับของ รูปแบบ HH:MM", examples=["22:10"])

    Weather_conditions: WeatherConditions
    Road_traffic_density: RoadTrafficDensity
    Vehicle_condition: int = Field(..., ge=0, le=3, description="สภาพรถ 0 (แย่สุด) - 3 (ดีสุด)")
    Type_of_order: TypeOfOrder
    Type_of_vehicle: TypeOfVehicle
    multiple_deliveries: float = Field(..., ge=0, le=3, description="จำนวนออเดอร์พ่วงเพิ่มเติม")
    Festival: Festival
    City: City

    # ฟิลด์ระบุตัวตน ไม่เข้าโมเดล (notebook drop ทิ้ง) แต่ใช้แสดงผลหน้าบ้าน
    ID: Optional[str] = Field(default=None, description="รหัสออเดอร์ (ไม่เข้าโมเดล)")
    Delivery_person_ID: Optional[str] = Field(default=None, description="รหัสไรเดอร์ (ไม่เข้าโมเดล)")

    @field_validator("Time_Orderd", "Time_Order_picked")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        """รับเฉพาะ HH:MM โดยยอมให้ชั่วโมง >= 24 ได้ (เช่น 24:05 = 00:05 ของวันถัดไป)

        กติกานี้ลอกมาจาก parse_time_value() ใน notebook ซึ่งใช้ hour % 24
        """
        parts = str(v).strip().split(":")
        if len(parts) < 2:
            raise ValueError("ต้องอยู่ในรูปแบบ HH:MM")
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError as exc:
            raise ValueError("ชั่วโมงและนาทีต้องเป็นตัวเลข") from exc
        if not (0 <= hour <= 47 and 0 <= minute <= 59):
            raise ValueError("ชั่วโมงต้องอยู่ระหว่าง 0-47 และนาทีระหว่าง 0-59")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("Order_Date")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        """รับได้ทั้ง DD-MM-YYYY (dataset ต้นฉบับ) และ YYYY-MM-DD (text.csv)

        ทำให้เป็นรูปแบบเดียว (DD-MM-YYYY) ก่อนส่งต่อ เพื่อให้ predictor.py
        แปลงด้วย format='%d-%m-%Y' ได้เสมอ
        """
        from datetime import datetime

        text = str(v).strip()
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
            except ValueError:
                continue
        raise ValueError("ต้องอยู่ในรูปแบบ DD-MM-YYYY หรือ YYYY-MM-DD เช่น 12-02-2022")

    @field_validator(
        "Restaurant_latitude",
        "Delivery_location_latitude",
    )
    @classmethod
    def _validate_lat(cls, v: float) -> float:
        # notebook ใช้ abs() แก้เครื่องหมายพิกัดที่เสีย แล้วตัดแถวที่ค่าน้อยกว่า 1 ทิ้ง
        v = abs(v)
        if v < 1:
            raise ValueError("ละติจูดใกล้ 0 ถือเป็นพิกัดเสีย (notebook ตัดแถวแบบนี้ทิ้ง)")
        if v > 90:
            raise ValueError("ละติจูดต้องไม่เกิน 90")
        return v

    @field_validator(
        "Restaurant_longitude",
        "Delivery_location_longitude",
    )
    @classmethod
    def _validate_lon(cls, v: float) -> float:
        v = abs(v)
        if v < 1:
            raise ValueError("ลองจิจูดใกล้ 0 ถือเป็นพิกัดเสีย (notebook ตัดแถวแบบนี้ทิ้ง)")
        if v > 180:
            raise ValueError("ลองจิจูดต้องไม่เกิน 180")
        return v


class BatchPredictRequest(BaseModel):
    """ทำนายหลายออเดอร์พร้อมกัน (ใช้ตอนจำลองกองออเดอร์ในหน้า Dashboard)"""

    orders: List[OrderRequest] = Field(..., min_length=1, max_length=200)


# =====================================================================
# Response
# =====================================================================
class DerivedFeatures(BaseModel):
    """ฟีเจอร์ที่ server คำนวณให้ (โปร่งใสว่าโมเดลเห็นอะไรบ้าง)"""

    Distance_km: float = Field(..., description="ระยะทาง Haversine ร้าน -> จุดส่ง (กม.)")
    Prep_time_min: float = Field(..., description="เวลาเตรียมอาหาร (นาที) รองรับข้ามเที่ยงคืน")
    Order_hour: int = Field(..., description="ชั่วโมงที่สั่ง 0-23")
    Order_period: str = Field(..., description="Morning / Afternoon / Evening / Night")
    Order_dayofweek: int = Field(..., description="0=จันทร์ ... 6=อาทิตย์")
    Is_weekend: int = Field(..., description="1 ถ้าเป็นเสาร์-อาทิตย์")


class EtaRange(BaseModel):
    low: float = Field(..., description="ขอบล่างของช่วงเวลาที่คาด (นาที)")
    high: float = Field(..., description="ขอบบนของช่วงเวลาที่คาด (นาที)")


class ModelMetrics(BaseModel):
    MAE: float
    RMSE: float
    R2: float


class PredictionResponse(BaseModel):
    predicted_minutes: float = Field(..., description="เวลาจัดส่งที่ทำนายได้ (นาที)")
    eta_range: EtaRange = Field(..., description="ช่วง ± MAE ของโมเดล")
    prediction_std: float = Field(
        ..., description="ส่วนเบี่ยงเบนมาตรฐานของคำทำนายจากต้นไม้ทั้ง 200 ต้น (ความไม่แน่นอน)"
    )
    derived_features: DerivedFeatures
    top_factors: List["FactorContribution"] = Field(
        default_factory=list, description="ฟีเจอร์ที่มีน้ำหนักสูงสุดต่อโมเดลโดยรวม พร้อมค่าของออเดอร์นี้"
    )
    model_metrics: ModelMetrics
    order_id: Optional[str] = None
    warnings: List[str] = Field(
        default_factory=list,
        description="ข้อควรระวัง เช่น ส่งค่าหมวดหมู่ที่โมเดลไม่เคยเห็นตอนเทรน",
    )


class FactorContribution(BaseModel):
    feature: str
    value: float
    importance: float


class BatchPredictionResponse(BaseModel):
    count: int
    predictions: List[PredictionResponse]
    summary: "BatchSummary"


class BatchSummary(BaseModel):
    mean_minutes: float
    min_minutes: float
    max_minutes: float
    total_distance_km: float


class RandomSampleResponse(BaseModel):
    """ออเดอร์สุ่มที่ generate ตามการกระจายตัวจริงของ dataset"""

    order: OrderRequest
    city_name: str = Field(..., description="ชื่อเมืองที่สุ่มได้ (มาจาก prefix ของ Delivery_person_ID)")


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_type: Optional[str] = None
    n_features: Optional[int] = None
    target_col: Optional[str] = None
    model_metrics: Optional[ModelMetrics] = None
    model_path: Optional[str] = None

    # สถานะของโหมดเปรียบเทียบ 2 โมเดล
    both_models_loaded: bool = Field(default=False, description="โหลดครบทั้ง 2 โมเดลหรือยัง")
    models: List[dict] = Field(default_factory=list, description="รายละเอียดของแต่ละโมเดล")
    testset_loaded: bool = Field(default=False, description="โหลด text.csv แล้วหรือยัง")
    testset_rows: Optional[int] = Field(default=None, description="จำนวนแถวในชุดทดสอบ")

    model_config = {"protected_namespaces": ()}


class ErrorResponse(BaseModel):
    detail: str


# =====================================================================
# โหมดเปรียบเทียบ 2 โมเดล (Dual-Model Comparison)
# =====================================================================
class ModelSide(BaseModel):
    """ผลของโมเดลฝั่งหนึ่งในการเปรียบเทียบ"""

    model: str = Field(..., description="ชื่อโมเดลที่อ่านออก เช่น 'Random Forest (Tuned)'")
    predicted_minutes: float = Field(..., description="เวลาที่โมเดลนี้ทำนาย (นาที)")
    prediction_std: float = Field(..., description="SD ของคำทำนายจากต้นไม้ทุกต้น")
    model_metrics: ModelMetrics = Field(..., description="metrics ตอนเทรนของโมเดลนี้")

    # 3 ฟิลด์ล่างมีเฉพาะตอนที่ส่งเฉลยมาด้วย
    error: Optional[float] = Field(None, description="|actual - predicted|")
    diff: Optional[float] = Field(
        None, description="predicted - actual (ติดลบ = ทำนายเร็วกว่าจริง)"
    )
    accuracy_percent: Optional[float] = Field(
        None, description="max(0, 100 * (1 - |actual - predicted| / actual))"
    )

    # ปิด protected namespace 'model_' ของ pydantic ไม่งั้นจะเตือนเรื่องชื่อฟิลด์
    model_config = {"protected_namespaces": ()}


class ComparisonVerdict(BaseModel):
    winner: str = Field(..., description="tuned / baseline / tie")
    better_model: str = Field(..., description="ชื่อโมเดลที่ชนะ")
    accuracy_gap: float = Field(..., description="ผลต่าง % ความแม่นยำของสองโมเดล")
    error_gap: float = Field(..., description="ผลต่างค่าความคลาดเคลื่อนของสองโมเดล")


class CompareRequest(BaseModel):
    """ออเดอร์ 1 รายการ + เฉลย (ถ้ามี) สำหรับเปรียบเทียบสองโมเดล"""

    order: OrderRequest
    actual_minutes: Optional[float] = Field(
        None,
        ge=0,
        description="เฉลยเวลาจริง ถ้าไม่ส่งมาจะทำนายอย่างเดียวโดยไม่คำนวณความแม่นยำ",
    )


class CompareResponse(BaseModel):
    order_id: Optional[str] = None
    test_index: Optional[int] = Field(
        None, description="ลำดับแถวใน text.csv (มีเฉพาะตอนเรียกผ่าน /compare/test-sample)"
    )
    order: Optional[OrderRequest] = Field(
        None, description="ข้อมูลดิบของออเดอร์ (ส่งกลับมาให้หน้าบ้านแสดงรายละเอียด)"
    )
    actual_minutes: Optional[float] = Field(None, description="เฉลยเวลาจริง (ถ้าส่งมา)")
    tuned: ModelSide
    baseline: ModelSide
    comparison: Optional[ComparisonVerdict] = Field(
        None, description="มีเฉพาะตอนที่มีเฉลยให้เทียบ"
    )
    derived_features: DerivedFeatures
    warnings: List[str] = Field(default_factory=list)

    model_config = {"protected_namespaces": ()}


class TestSample(BaseModel):
    """1 แถวจาก text.csv พร้อมเฉลย"""

    index: int = Field(..., description="ลำดับแถวในไฟล์ เริ่มจาก 0")
    order: OrderRequest
    actual_minutes: float = Field(..., description="เฉลยเวลาจัดส่งจริง (นาที)")
    precomputed: dict = Field(
        default_factory=dict,
        description="ฟีเจอร์ที่ไฟล์สกัดมาให้แล้ว ใช้ตรวจทานกับที่ server คำนวณเอง",
    )


class TestSamplesResponse(BaseModel):
    total: int = Field(..., description="จำนวนแถวทั้งหมดในชุดทดสอบ")
    count: int = Field(..., description="จำนวนแถวที่คืนมาครั้งนี้")
    samples: List[TestSample]


class ModelEvalStats(BaseModel):
    MAE: float
    RMSE: float
    R2: float
    mean_accuracy_percent: float
    median_accuracy_percent: float
    max_error: float
    wins: int


class WinRate(BaseModel):
    tuned_wins: int
    baseline_wins: int
    ties: int
    tuned_win_percent: float
    baseline_win_percent: float
    tie_percent: float


class EvaluateBatchRequest(BaseModel):
    """ถ้าไม่ส่ง orders มา จะประเมินทั้ง text.csv"""

    orders: Optional[List[OrderRequest]] = Field(
        None, description="ออเดอร์ที่ต้องการประเมิน (ต้องมีเฉลยใน actuals)"
    )
    actuals: Optional[List[float]] = Field(
        None, description="เฉลยของแต่ละออเดอร์ ต้องยาวเท่ากับ orders"
    )
    limit: Optional[int] = Field(
        None, ge=1, description="จำกัดจำนวนแถวจาก text.csv (ไว้ทดสอบเร็ว ๆ)"
    )


class EvaluateBatchResponse(BaseModel):
    evaluated: int = Field(..., description="จำนวนแถวที่ประเมินได้จริง")
    skipped: List[dict] = Field(default_factory=list, description="แถวที่ข้ามไปพร้อมเหตุผล")
    tuned: ModelEvalStats
    baseline: ModelEvalStats
    win_rate: WinRate
    overall_winner: str
    mae_improvement_percent: float = Field(
        ..., description="Tuned ลด MAE ลงกี่ % เทียบกับ Baseline"
    )
    accuracy_gap: float = Field(..., description="% ความแม่นยำเฉลี่ยของ Tuned ลบด้วยของ Baseline")
    source: Optional[str] = Field(None, description="ที่มาของข้อมูลที่ประเมิน")
    elapsed_seconds: Optional[float] = None

    model_config = {"protected_namespaces": ()}


# แก้ forward reference ของ nested models
PredictionResponse.model_rebuild()
BatchPredictionResponse.model_rebuild()
CompareResponse.model_rebuild()
