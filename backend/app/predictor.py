"""
โหลดโมเดล 2 ตัวและทำ Preprocessing + Predict + เปรียบเทียบกับเฉลย

โมเดลทั้งสองตัวมาจาก notebook เดียวกันและใช้ "สัญญาฟีเจอร์ 33 คอลัมน์" ชุดเดียวกันเป๊ะ
(ตรวจสอบตอนโหลดด้วย DualPredictor.load()) ต่างกันแค่ hyperparameters:

  * model_tuned    : random_forest_eta.models — 200 ต้น, max_depth=15 (ผ่าน RandomizedSearchCV)
  * model_baseline : baseline.model           — 100 ต้น, max_depth=None (ค่าเริ่มต้น)

เพราะสัญญาฟีเจอร์เหมือนกัน เราจึง build_features() แค่ครั้งเดียวแล้วป้อนให้ทั้งสองโมเดล

ไฟล์นี้คือ "สัญญา" ระหว่าง notebook กับ API: ลำดับขั้นตอนทุกอย่างในนี้ต้องตรงกับ
Untitled42.ipynb เป๊ะ ๆ ไม่งั้นโมเดลจะเห็นฟีเจอร์ผิดรูปและทำนายเพี้ยน

ขั้นตอนที่ลอกมาจาก notebook (section 2-4):
  1. abs() พิกัด แล้วตัดพิกัดที่ใกล้ 0 ทิ้ง            -> ทำใน schemas.py ตอน validate
  2. เติมค่าว่างด้วย median/mode จาก bundle['impute_values']
  3. Distance_km  = Haversine(ร้าน, จุดส่ง), R = 6371 km
  4. Prep_time_min = picked - ordered (นาที), ถ้าติดลบบวก 1440
  5. Order_hour / Order_period / Order_dayofweek / Is_weekend
  6. drop คอลัมน์ ID, Delivery_person_ID, Order_Date, Time_Orderd, Time_Order_picked
  7. One-Hot Encoding แล้ว reindex ให้ตรง bundle['feature_names'] ทั้งชื่อและลำดับ

หมายเหตุสำคัญเรื่อง One-Hot:
  notebook ใช้ pd.get_dummies(..., drop_first=True) ซึ่งตัด "ระดับอ้างอิง" ของแต่ละ
  หมวดหมู่ทิ้งไป ที่นี่เราจึงต้องใช้ drop_first=False แล้วค่อย reindex ตาม
  feature_names เพราะถ้าใช้ drop_first=True กับข้อมูลแถวเดียว มันจะตัดหมวดหมู่
  เดียวที่มีอยู่ทิ้งเสมอ ผลลัพธ์ที่ได้จะเท่ากัน: ระดับอ้างอิงถูกแทนด้วยศูนย์ทั้งแถว
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# =====================================================================
# ระดับอ้างอิง (reference level) ที่ drop_first=True ตัดทิ้งไปตอนเทรน
# ค่าเหล่านี้จะถูกแทนด้วย 0 ทุกคอลัมน์ของหมวดหมู่นั้น ไม่ใช่ค่าที่ "หาย"
# =====================================================================
REFERENCE_LEVELS: Dict[str, str] = {
    "Weather_conditions": "Cloudy",
    "Road_traffic_density": "High",
    "Type_of_order": "Buffet",
    "Type_of_vehicle": "electric_scooter",
    "Festival": "No",
    "City": "Metropolitian",
    "Order_period": "Afternoon",
}

# หมวดหมู่ที่โมเดลรู้จักจริง ๆ (ระดับอ้างอิง + คอลัมน์ที่มีใน feature_names)
KNOWN_LEVELS: Dict[str, Tuple[str, ...]] = {
    "Weather_conditions": ("Cloudy", "Fog", "Sandstorms", "Stormy", "Sunny", "Windy"),
    "Road_traffic_density": ("High", "Jam", "Low", "Medium"),
    "Type_of_order": ("Buffet", "Drinks", "Meal", "Snack"),
    # 'bicycle' มีใน dataset ดิบเพียง 68 แถว และถูกขั้นตอน cleaning ตัดทิ้งหมด
    # โมเดลจึงไม่เคยเห็น -> ถ้าส่งเข้ามาจะถูกตีเป็น electric_scooter (ระดับอ้างอิง)
    "Type_of_vehicle": ("electric_scooter", "motorcycle", "scooter"),
    "Festival": ("No", "Yes"),
    "City": ("Metropolitian", "Semi-Urban", "Unknown", "Urban"),
}

CATEGORICAL_COLS: Tuple[str, ...] = (
    "Weather_conditions",
    "Road_traffic_density",
    "Type_of_order",
    "Type_of_vehicle",
    "Festival",
    "City",
    "Order_period",
)

# คอลัมน์ที่ notebook ตัดทิ้งก่อนเข้าโมเดล
DROP_COLS: Tuple[str, ...] = (
    "ID",
    "Delivery_person_ID",
    "Order_Date",
    "Time_Orderd",
    "Time_Order_picked",
)

EARTH_RADIUS_KM = 6371.0


# =====================================================================
# ฟังก์ชัน Feature Engineering (ยกมาจาก notebook section 3)
# =====================================================================
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """ระยะทางวงกลมใหญ่ระหว่างสองพิกัด หน่วยกิโลเมตร"""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return float(EARTH_RADIUS_KM * c)


def parse_time_value(value: Any) -> Optional[pd.Timestamp]:
    """แปลงเวลาที่ dataset เก็บมาได้ 3 แบบให้เป็น Timestamp เดียวกัน

    รองรับ: 'HH:MM' ปกติ, เศษส่วนของวันแบบ Excel (0.458333 = 11:00),
    และชั่วโมง >= 24 (24:05 = 00:05 ของวันถัดไป)
    """
    if value is None or (isinstance(value, float) and np.isnan(value)) or pd.isna(value):
        return None

    text = str(value).strip()

    # กรณี Excel time-serial: ตัวเลขทศนิยมระหว่าง 0 ถึง 1
    try:
        as_float = float(text)
        if 0 <= as_float <= 1:
            total_min = round(as_float * 1440) % 1440
            hour, minute = divmod(total_min, 60)
            return pd.Timestamp(f"{hour:02d}:{minute:02d}:00")
    except ValueError:
        pass

    parts = text.split(":")
    try:
        hour = int(parts[0]) % 24           # 24:05 -> 00:05
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return pd.Timestamp(f"{hour:02d}:{minute:02d}:{second:02d}")
    except (ValueError, IndexError):
        return None


def get_period(hour: int) -> str:
    """แบ่งช่วงเวลาของวันตามเกณฑ์เดียวกับ notebook"""
    if 5 <= hour < 11:
        return "Morning"
    if 11 <= hour < 15:
        return "Afternoon"
    if 15 <= hour < 20:
        return "Evening"
    return "Night"


def compute_prep_time(time_ordered: str, time_picked: str) -> float:
    """เวลาเตรียมอาหาร = picked - ordered (นาที) ถ้าติดลบแปลว่าข้ามเที่ยงคืน -> +1440"""
    t_ordered = parse_time_value(time_ordered)
    t_picked = parse_time_value(time_picked)
    if t_ordered is None or t_picked is None:
        raise ValueError("รูปแบบเวลาไม่ถูกต้อง แปลง Time_Orderd / Time_Order_picked ไม่ได้")

    minutes = (t_picked - t_ordered).total_seconds() / 60.0
    if minutes < 0:
        minutes += 1440.0
    return float(minutes)


# =====================================================================
# ตัวโหลดโมเดล (singleton + thread-safe, โหลดครั้งเดียวตอน startup)
# =====================================================================
TUNED_FILENAME = "random_forest_eta.models"
BASELINE_FILENAME = "baseline.model"


def models_dir() -> str:
    """โฟลเดอร์ที่เก็บไฟล์โมเดล (override ได้ด้วย MODELS_DIR)"""
    env_dir = os.getenv("MODELS_DIR")
    if env_dir:
        return env_dir
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "models")


def _default_model_path(filename: str = TUNED_FILENAME) -> str:
    """ตำแหน่งไฟล์โมเดล

    MODEL_PATH (ของเดิม) ยังใช้ได้กับโมเดล tuned เพื่อไม่ให้ค่าที่ตั้งไว้เดิมพัง
    ส่วน BASELINE_MODEL_PATH ใช้ชี้โมเดล baseline โดยเฉพาะ
    """
    if filename == TUNED_FILENAME:
        env_path = os.getenv("MODEL_PATH")
        if env_path:
            return env_path
    if filename == BASELINE_FILENAME:
        env_path = os.getenv("BASELINE_MODEL_PATH")
        if env_path:
            return env_path
    return os.path.join(models_dir(), filename)


class EtaPredictor:
    """ครอบ bundle dictionary ที่ notebook เซฟไว้ (model / feature_names / impute_values / metrics)"""

    def __init__(self, model_path: Optional[str] = None, label: str = "tuned") -> None:
        self.model_path = model_path or _default_model_path()
        self.label = label
        self._bundle: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()

    # ---------- lifecycle ----------
    def load(self) -> None:
        """โหลด .models เข้าหน่วยความจำ (ไฟล์ ~129 MB ใช้เวลาไม่กี่วินาที)"""
        with self._lock:
            if self._bundle is not None:
                return
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(
                    f"ไม่พบไฟล์โมเดลที่ {self.model_path} "
                    "(คัดลอก random_forest_eta.models มาไว้ใน backend/models/ หรือกำหนด MODEL_PATH)"
                )
            logger.info("[%s] กำลังโหลดโมเดลจาก %s", self.label, self.model_path)
            bundle = joblib.load(self.model_path)

            required = {"model", "feature_names", "target_col"}
            missing = required - set(bundle)
            if missing:
                raise ValueError(f"ไฟล์โมเดลขาดคีย์ที่จำเป็น: {sorted(missing)}")

            self._bundle = bundle
            params = bundle["model"].get_params()
            logger.info(
                "[%s] โหลดสำเร็จ: %s | %s ต้น, max_depth=%s | %d ฟีเจอร์",
                self.label,
                type(bundle["model"]).__name__,
                params.get("n_estimators"),
                params.get("max_depth"),
                len(bundle["feature_names"]),
            )

    @property
    def is_loaded(self) -> bool:
        return self._bundle is not None

    def _require_bundle(self) -> Dict[str, Any]:
        if self._bundle is None:
            raise RuntimeError("ยังไม่ได้โหลดโมเดล เรียก load() ก่อน")
        return self._bundle

    # ---------- metadata ----------
    @property
    def feature_names(self) -> List[str]:
        return list(self._require_bundle()["feature_names"])

    @property
    def target_col(self) -> str:
        return str(self._require_bundle()["target_col"])

    @property
    def metrics(self) -> Dict[str, float]:
        raw = self._require_bundle().get("metrics", {}) or {}
        return {k: float(v) for k, v in raw.items()}

    @property
    def impute_values(self) -> Dict[str, Any]:
        return dict(self._require_bundle().get("impute_values", {}) or {})

    @property
    def model(self):
        return self._require_bundle()["model"]

    def feature_importances(self) -> Dict[str, float]:
        model = self.model
        if not hasattr(model, "feature_importances_"):
            return {}
        return {
            name: float(score)
            for name, score in zip(self.feature_names, model.feature_importances_)
        }

    # ---------- preprocessing ----------
    def build_features(self, order: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any], List[str]]:
        """แปลงออเดอร์ดิบ 1 รายการ -> DataFrame 1 แถวที่มีคอลัมน์ตรง feature_names

        คืนค่า (X, derived, warnings)
        """
        warnings: List[str] = []
        row = dict(order)

        # --- 1) เติมค่าว่างด้วยสถิติเดียวกับตอนเทรน ---
        for col, fill in self.impute_values.items():
            if row.get(col) is None:
                row[col] = fill
                warnings.append(f"{col} ว่าง -> เติมด้วยค่าจากชุดเทรน ({fill})")

        # --- 2) แก้เครื่องหมายพิกัด (notebook ใช้ abs()) ---
        for col in (
            "Restaurant_latitude",
            "Restaurant_longitude",
            "Delivery_location_latitude",
            "Delivery_location_longitude",
        ):
            row[col] = abs(float(row[col]))

        # --- 3) Feature Engineering ---
        distance_km = haversine(
            row["Restaurant_latitude"],
            row["Restaurant_longitude"],
            row["Delivery_location_latitude"],
            row["Delivery_location_longitude"],
        )
        prep_time_min = compute_prep_time(row["Time_Orderd"], row["Time_Order_picked"])

        t_ordered = parse_time_value(row["Time_Orderd"])
        order_hour = int(t_ordered.hour)
        order_period = get_period(order_hour)

        order_date = pd.to_datetime(row["Order_Date"], format="%d-%m-%Y", errors="coerce")
        if pd.isna(order_date):
            raise ValueError("Order_Date ต้องอยู่ในรูปแบบ DD-MM-YYYY")
        order_dayofweek = int(order_date.dayofweek)
        is_weekend = int(order_dayofweek in (5, 6))

        row["Distance_km"] = distance_km
        row["Prep_time_min"] = prep_time_min
        row["Order_hour"] = order_hour
        row["Order_period"] = order_period
        row["Order_dayofweek"] = order_dayofweek
        row["Is_weekend"] = is_weekend

        derived = {
            "Distance_km": round(distance_km, 4),
            "Prep_time_min": prep_time_min,
            "Order_hour": order_hour,
            "Order_period": order_period,
            "Order_dayofweek": order_dayofweek,
            "Is_weekend": is_weekend,
        }

        # --- 4) เตือนถ้าส่งหมวดหมู่ที่โมเดลไม่เคยเห็น ---
        for col, known in KNOWN_LEVELS.items():
            value = row.get(col)
            if value is not None and value not in known:
                warnings.append(
                    f"'{value}' ไม่อยู่ในหมวดหมู่ที่โมเดลเคยเห็นของ {col} "
                    f"-> ถูกตีความเป็นระดับอ้างอิง '{REFERENCE_LEVELS.get(col)}'"
                )

        # --- 5) ตัดคอลัมน์ที่ไม่เข้าโมเดล + target (ถ้าติดมา) ---
        for col in (*DROP_COLS, self.target_col):
            row.pop(col, None)

        frame = pd.DataFrame([row])

        # --- 6) One-Hot Encoding แล้วบังคับให้คอลัมน์ตรงกับตอนเทรน ---
        # ใช้ drop_first=False เพราะแถวเดียวมีหมวดหมู่เดียว การ reindex ด้านล่าง
        # จะทิ้งคอลัมน์ระดับอ้างอิงเองอยู่แล้ว (ผลเท่ากับ drop_first=True ตอนเทรน)
        present_cats = [c for c in CATEGORICAL_COLS if c in frame.columns]
        frame = pd.get_dummies(frame, columns=present_cats, drop_first=False)

        features = self.feature_names
        X = frame.reindex(columns=features, fill_value=0).astype(float)

        if X.isna().any().any():
            bad = X.columns[X.isna().any()].tolist()
            raise ValueError(f"ยังมีค่าว่างหลัง preprocessing ในคอลัมน์: {bad}")

        return X, derived, warnings

    # ---------- prediction ----------
    def predict_from_features(self, X: pd.DataFrame, with_std: bool = True) -> Tuple[float, float]:
        """ทำนายจาก DataFrame ที่ build_features() เตรียมไว้แล้ว

        แยกออกมาเพื่อให้ DualPredictor build ฟีเจอร์ครั้งเดียวแล้วป้อนให้ทั้งสองโมเดล
        คืนค่า (prediction, std) โดย std คือการกระจายตัวของคำทำนายจากต้นไม้แต่ละต้น
        """
        model = self.model
        prediction = float(model.predict(X)[0])

        std = 0.0
        if with_std:
            estimators = getattr(model, "estimators_", None)
            if estimators:
                values = X.values
                per_tree = np.array([est.predict(values)[0] for est in estimators], dtype=float)
                std = float(per_tree.std())
        return prediction, std

    def predict_one(self, order: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
        """ทำนายออเดอร์เดียว พร้อมรายละเอียดฟีเจอร์และความไม่แน่นอน"""
        X, derived, warnings = self.build_features(order)
        prediction, std = self.predict_from_features(X)

        mae = self.metrics.get("MAE", 0.0)
        eta_range = {
            "low": round(max(0.0, prediction - mae), 2),
            "high": round(prediction + mae, 2),
        }

        # ฟีเจอร์ที่โมเดลให้น้ำหนักสูงสุด พร้อมค่าที่ออเดอร์นี้ถืออยู่
        importances = self.feature_importances()
        top_factors = []
        if importances:
            ranked = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
            row_values = X.iloc[0]
            top_factors = [
                {
                    "feature": name,
                    "value": round(float(row_values.get(name, 0.0)), 4),
                    "importance": round(score, 4),
                }
                for name, score in ranked
            ]

        return {
            "predicted_minutes": round(prediction, 2),
            "eta_range": eta_range,
            "prediction_std": round(std, 3),
            "derived_features": derived,
            "top_factors": top_factors,
            "model_metrics": self.metrics,
            "order_id": order.get("ID"),
            "warnings": warnings,
        }

    def predict_many(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """ทำนายหลายออเดอร์ (วนทีละรายการเพื่อให้ได้ derived features ครบทุกแถว)"""
        return [self.predict_one(order) for order in orders]


# =====================================================================
# การเปรียบเทียบกับเฉลย (Ground Truth)
# =====================================================================
def accuracy_percent(actual: float, predicted: float) -> float:
    """% ความแม่นยำ = max(0, 100 * (1 - |actual - predicted| / actual))

    ถ้า actual เป็น 0 สูตรนี้ใช้ไม่ได้ (หารด้วยศูนย์) — ในทางปฏิบัติไม่เกิด
    เพราะ Time_taken ต่ำสุดใน dataset คือ 10 นาที แต่กันไว้ก่อน
    """
    actual = float(actual)
    if actual == 0:
        return 100.0 if float(predicted) == 0 else 0.0
    return max(0.0, 100.0 * (1.0 - abs(actual - float(predicted)) / abs(actual)))


class DualPredictor:
    """ถือโมเดล 2 ตัวไว้พร้อมกัน แล้วทำนายจากฟีเจอร์ชุดเดียวกัน

    ข้อสมมติสำคัญ: ทั้งสองโมเดลต้องมี feature_names เหมือนกันทุกตัวและเรียงเหมือนกัน
    ถ้าไม่ตรง load() จะโยน error ทันที ดีกว่าปล่อยให้ทำนายผิดเงียบ ๆ
    """

    def __init__(self) -> None:
        self.tuned = EtaPredictor(_default_model_path(TUNED_FILENAME), label="tuned")
        self.baseline = EtaPredictor(_default_model_path(BASELINE_FILENAME), label="baseline")

    # ---------- lifecycle ----------
    def load(self) -> None:
        self.tuned.load()
        self.baseline.load()

        if self.tuned.feature_names != self.baseline.feature_names:
            only_tuned = set(self.tuned.feature_names) - set(self.baseline.feature_names)
            only_base = set(self.baseline.feature_names) - set(self.tuned.feature_names)
            raise ValueError(
                "สัญญาฟีเจอร์ของสองโมเดลไม่ตรงกัน จึงเปรียบเทียบกันไม่ได้ "
                f"(มีเฉพาะใน tuned: {sorted(only_tuned)}, "
                f"มีเฉพาะใน baseline: {sorted(only_base)}, หรือลำดับคอลัมน์ต่างกัน)"
            )
        if self.tuned.target_col != self.baseline.target_col:
            raise ValueError("target_col ของสองโมเดลไม่ตรงกัน")

        logger.info(
            "โหลดครบทั้ง 2 โมเดล และสัญญาฟีเจอร์ตรงกัน (%d คอลัมน์)",
            len(self.tuned.feature_names),
        )

    @property
    def is_loaded(self) -> bool:
        return self.tuned.is_loaded and self.baseline.is_loaded

    @property
    def target_col(self) -> str:
        return self.tuned.target_col

    # ---------- comparison ----------
    def compare_one(
        self,
        order: Dict[str, Any],
        actual_minutes: Optional[float] = None,
        with_std: bool = True,
    ) -> Dict[str, Any]:
        """ทำนายด้วยทั้งสองโมเดลจากออเดอร์เดียวกัน แล้วเทียบกับเฉลย (ถ้ามี)

        Args:
            order: ข้อมูลดิบ 1 ออเดอร์
            actual_minutes: เฉลยเวลาจริง ถ้าไม่ส่งมาจะพยายามอ่านจาก order[target_col]
            with_std: คำนวณ std จากต้นไม้ทุกต้นหรือไม่ (ปิดตอน batch เพื่อความเร็ว)
        """
        # เฉลยอาจติดมากับ order เอง (เช่นแถวจาก text.csv)
        if actual_minutes is None:
            raw_actual = order.get(self.target_col)
            if raw_actual is not None and not pd.isna(raw_actual):
                actual_minutes = float(raw_actual)

        # build ครั้งเดียว ใช้ทั้งสองโมเดล (สัญญาฟีเจอร์ตรงกัน ตรวจแล้วตอน load)
        X, derived, warnings = self.tuned.build_features(order)

        tuned_pred, tuned_std = self.tuned.predict_from_features(X, with_std=with_std)
        baseline_pred, baseline_std = self.baseline.predict_from_features(X, with_std=with_std)

        result: Dict[str, Any] = {
            "order_id": order.get("ID"),
            "derived_features": derived,
            "warnings": warnings,
            "tuned": {
                "model": "Random Forest (Tuned)",
                "predicted_minutes": round(tuned_pred, 2),
                "prediction_std": round(tuned_std, 3),
                "model_metrics": self.tuned.metrics,
            },
            "baseline": {
                "model": "Random Forest (Baseline)",
                "predicted_minutes": round(baseline_pred, 2),
                "prediction_std": round(baseline_std, 3),
                "model_metrics": self.baseline.metrics,
            },
            "actual_minutes": None,
            "comparison": None,
        }

        if actual_minutes is None:
            return result

        actual = float(actual_minutes)
        tuned_err = abs(actual - tuned_pred)
        baseline_err = abs(actual - baseline_pred)
        tuned_acc = accuracy_percent(actual, tuned_pred)
        baseline_acc = accuracy_percent(actual, baseline_pred)

        # ตัดสินผู้ชนะจากค่าความคลาดเคลื่อน ใช้ epsilon กันปัญหาทศนิยมลอยตัว
        if abs(tuned_err - baseline_err) < 1e-9:
            winner = "tie"
        elif tuned_err < baseline_err:
            winner = "tuned"
        else:
            winner = "baseline"

        result["actual_minutes"] = round(actual, 2)
        result["tuned"].update(
            {
                "error": round(tuned_err, 3),
                "diff": round(tuned_pred - actual, 2),   # ติดลบ = ทำนายเร็วกว่าจริง
                "accuracy_percent": round(tuned_acc, 2),
            }
        )
        result["baseline"].update(
            {
                "error": round(baseline_err, 3),
                "diff": round(baseline_pred - actual, 2),
                "accuracy_percent": round(baseline_acc, 2),
            }
        )
        result["comparison"] = {
            "winner": winner,
            "accuracy_gap": round(abs(tuned_acc - baseline_acc), 2),
            "error_gap": round(abs(tuned_err - baseline_err), 3),
            "better_model": {
                "tuned": "Random Forest (Tuned)",
                "baseline": "Random Forest (Baseline)",
                "tie": "เสมอกัน",
            }[winner],
        }
        return result

    # ---------- batch ----------
    def evaluate_batch(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """ประเมินทั้งชุดแล้วสรุป MAE / RMSE / %Accuracy เฉลี่ย / Win rate

        ทำเป็น batch จริง (predict ทีเดียวทั้งก้อน) แทนการวนทีละแถว เพราะ
        1,000 แถว x 300 ต้นไม้ ถ้าวนทีละแถวจะช้ามาก
        """
        if not orders:
            raise ValueError("ไม่มีข้อมูลให้ประเมิน")

        rows: List[pd.DataFrame] = []
        actuals: List[float] = []
        skipped: List[Dict[str, Any]] = []

        for index, order in enumerate(orders):
            raw_actual = order.get(self.target_col)
            if raw_actual is None or pd.isna(raw_actual):
                skipped.append({"index": index, "reason": f"ไม่มีเฉลย '{self.target_col}'"})
                continue
            try:
                X, _, _ = self.tuned.build_features(order)
            except (ValueError, KeyError) as exc:
                skipped.append({"index": index, "reason": str(exc)})
                continue
            rows.append(X)
            actuals.append(float(raw_actual))

        if not rows:
            raise ValueError("ไม่มีแถวไหนผ่านการเตรียมฟีเจอร์เลย")

        X_all = pd.concat(rows, ignore_index=True)
        y_true = np.asarray(actuals, dtype=float)

        y_tuned = np.asarray(self.tuned.model.predict(X_all), dtype=float)
        y_baseline = np.asarray(self.baseline.model.predict(X_all), dtype=float)

        err_tuned = np.abs(y_true - y_tuned)
        err_baseline = np.abs(y_true - y_baseline)

        # % ความแม่นยำคิดรายแถวก่อน แล้วค่อยเฉลี่ย (ไม่ใช่คำนวณย้อนจาก MAE รวม)
        safe = np.where(y_true == 0, 1.0, y_true)
        acc_tuned = np.maximum(0.0, 100.0 * (1.0 - err_tuned / np.abs(safe)))
        acc_baseline = np.maximum(0.0, 100.0 * (1.0 - err_baseline / np.abs(safe)))

        tuned_wins = int(np.sum(err_tuned < err_baseline - 1e-9))
        baseline_wins = int(np.sum(err_baseline < err_tuned - 1e-9))
        total = int(len(y_true))
        ties = total - tuned_wins - baseline_wins

        def stats(y_pred, err, acc, wins):
            ss_res = float(np.sum((y_true - y_pred) ** 2))
            ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
            return {
                "MAE": round(float(err.mean()), 4),
                "RMSE": round(float(np.sqrt(np.mean((y_true - y_pred) ** 2))), 4),
                "R2": round(1.0 - ss_res / ss_tot, 4) if ss_tot else 0.0,
                "mean_accuracy_percent": round(float(acc.mean()), 2),
                "median_accuracy_percent": round(float(np.median(acc)), 2),
                "max_error": round(float(err.max()), 3),
                "wins": wins,
            }

        tuned_stats = stats(y_tuned, err_tuned, acc_tuned, tuned_wins)
        baseline_stats = stats(y_baseline, err_baseline, acc_baseline, baseline_wins)

        overall_winner = (
            "tuned"
            if tuned_stats["MAE"] < baseline_stats["MAE"]
            else "baseline"
            if baseline_stats["MAE"] < tuned_stats["MAE"]
            else "tie"
        )

        return {
            "evaluated": total,
            "skipped": skipped,
            "tuned": tuned_stats,
            "baseline": baseline_stats,
            "win_rate": {
                "tuned_wins": tuned_wins,
                "baseline_wins": baseline_wins,
                "ties": ties,
                "tuned_win_percent": round(100.0 * tuned_wins / total, 2),
                "baseline_win_percent": round(100.0 * baseline_wins / total, 2),
                "tie_percent": round(100.0 * ties / total, 2),
            },
            "overall_winner": overall_winner,
            "mae_improvement_percent": (
                round(
                    100.0 * (baseline_stats["MAE"] - tuned_stats["MAE"]) / baseline_stats["MAE"], 2
                )
                if baseline_stats["MAE"]
                else 0.0
            ),
            "accuracy_gap": round(
                tuned_stats["mean_accuracy_percent"] - baseline_stats["mean_accuracy_percent"], 2
            ),
        }


# instance เดียวที่ใช้ร่วมกันทั้งแอป
dual = DualPredictor()

# ชื่อเดิม ชี้ไปที่โมเดล tuned เพื่อให้ /predict ของเดิมยังทำงานเหมือนเดิม
predictor = dual.tuned
