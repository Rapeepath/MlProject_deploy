"""
โหลดชุดข้อมูลทดสอบ (Hold-out Test Set) จาก data/text.csv

text.csv มี 26 คอลัมน์ = ข้อมูลดิบ 19 ฟิลด์ + เฉลย Time_taken (min)
+ ฟีเจอร์ที่สกัดไว้แล้วอีก 6 ตัว (Distance_km, Prep_time_min, Order_hour,
Order_period, Order_dayofweek, Is_weekend)

สิ่งที่ตรวจสอบแล้วกับไฟล์จริง:
  * 1,000 แถว ไม่มี NaN เลยสักช่อง
  * ฟีเจอร์ 6 ตัวที่ให้มาตรงกับที่ predictor.py คำนวณเองทุกแถว
    (Distance_km ต่างกันสูงสุด 3.6e-15 = ความคลาดเคลื่อนของ float เท่านั้น)
    -> เราจึงส่งเฉพาะ "ข้อมูลดิบ" เข้า predictor แล้วให้มันคำนวณฟีเจอร์เอง
       เพื่อใช้โค้ดเส้นทางเดียวกับ /predict ปกติ ไม่ต้องมีทางลัดแยก
  * Order_Date ในไฟล์นี้เป็นรูปแบบ YYYY-MM-DD (เช่น 2022-03-10)
    ซึ่งต่างจาก DD-MM-YYYY ของ dataset ต้นฉบับ -> แปลงให้ตอนโหลด
"""

from __future__ import annotations

import logging
import os
import random
import threading
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

TARGET_COL = "Time_taken (min)"

# ฟิลด์ดิบที่ส่งต่อให้ predictor (ตรงกับ OrderRequest)
RAW_FIELDS = (
    "ID",
    "Delivery_person_ID",
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
)

# ฟีเจอร์ที่ไฟล์สกัดมาให้แล้ว — เก็บไว้แสดงผล/ตรวจทาน ไม่ได้ป้อนเข้าโมเดลโดยตรง
PRECOMPUTED_FEATURES = (
    "Distance_km",
    "Prep_time_min",
    "Order_hour",
    "Order_period",
    "Order_dayofweek",
    "Is_weekend",
)


def default_csv_path() -> str:
    env_path = os.getenv("TEST_CSV_PATH")
    if env_path:
        return env_path
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "data", "text.csv")


def _normalize_date(value: Any) -> str:
    """แปลงวันที่ให้เป็น DD-MM-YYYY ตามที่ OrderRequest ต้องการ

    text.csv เก็บเป็น YYYY-MM-DD ส่วน dataset ต้นฉบับเป็น DD-MM-YYYY
    รับได้ทั้งสองแบบเพื่อไม่ให้พังถ้าไฟล์เปลี่ยนรูปแบบ
    """
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return pd.to_datetime(text, format=fmt).strftime("%d-%m-%Y")
        except (ValueError, TypeError):
            continue
    # ทางสุดท้าย ให้ pandas เดาเอง (dayfirst=True กัน 03-10 สลับเดือน/วัน)
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"แปลงวันที่ '{value}' ไม่ได้")
    return parsed.strftime("%d-%m-%Y")


def _normalize_time(value: Any) -> str:
    """ตัดวินาทีทิ้งให้เหลือ HH:MM (บางไฟล์เก็บเป็น HH:MM:SS)"""
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except ValueError:
            pass
    return text


class TestSet:
    """โหลด text.csv ครั้งเดียวตอน startup แล้วเก็บไว้ในหน่วยความจำ (ไฟล์เล็กมาก ~180 KB)"""

    def __init__(self, csv_path: Optional[str] = None) -> None:
        self.csv_path = csv_path or default_csv_path()
        self._rows: Optional[List[Dict[str, Any]]] = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._rows is not None:
                return
            if not os.path.exists(self.csv_path):
                raise FileNotFoundError(
                    f"ไม่พบไฟล์ชุดทดสอบที่ {self.csv_path} "
                    "(คัดลอก text.csv มาไว้ใน backend/data/ หรือกำหนด TEST_CSV_PATH)"
                )

            df = pd.read_csv(self.csv_path)

            missing = [c for c in RAW_FIELDS if c not in df.columns]
            if missing:
                raise ValueError(f"text.csv ขาดคอลัมน์ที่จำเป็น: {missing}")
            if TARGET_COL not in df.columns:
                raise ValueError(f"text.csv ไม่มีคอลัมน์เฉลย '{TARGET_COL}'")

            rows: List[Dict[str, Any]] = []
            for position, (_, raw) in enumerate(df.iterrows()):
                order = {field: raw[field] for field in RAW_FIELDS}
                order["Order_Date"] = _normalize_date(order["Order_Date"])
                order["Time_Orderd"] = _normalize_time(order["Time_Orderd"])
                order["Time_Order_picked"] = _normalize_time(order["Time_Order_picked"])
                order["Vehicle_condition"] = int(order["Vehicle_condition"])
                for numeric in (
                    "Delivery_person_Age",
                    "Delivery_person_Ratings",
                    "Restaurant_latitude",
                    "Restaurant_longitude",
                    "Delivery_location_latitude",
                    "Delivery_location_longitude",
                    "multiple_deliveries",
                ):
                    order[numeric] = float(order[numeric])

                rows.append(
                    {
                        "index": position,
                        "order": order,
                        "actual_minutes": float(raw[TARGET_COL]),
                        # ฟีเจอร์ที่ไฟล์ให้มา ใช้ตรวจทานกับที่ predictor คำนวณเอง
                        "precomputed": {
                            name: (
                                raw[name].item() if hasattr(raw[name], "item") else raw[name]
                            )
                            for name in PRECOMPUTED_FEATURES
                            if name in df.columns
                        },
                    }
                )

            self._rows = rows
            logger.info("โหลดชุดทดสอบ %d แถว จาก %s", len(rows), self.csv_path)

    @property
    def is_loaded(self) -> bool:
        return self._rows is not None

    def _require(self) -> List[Dict[str, Any]]:
        if self._rows is None:
            self.load()
        assert self._rows is not None
        return self._rows

    def __len__(self) -> int:
        return len(self._require())

    # ---------- การเข้าถึงข้อมูล ----------
    def get(self, index: int) -> Dict[str, Any]:
        rows = self._require()
        if not 0 <= index < len(rows):
            raise ValueError(f"index ต้องอยู่ระหว่าง 0 ถึง {len(rows) - 1} (ได้รับ {index})")
        return rows[index]

    def random_one(self, seed: Optional[int] = None) -> Dict[str, Any]:
        rows = self._require()
        rng = random.Random(seed)
        return rows[rng.randrange(len(rows))]

    def sample(self, count: int, seed: Optional[int] = None) -> List[Dict[str, Any]]:
        """สุ่มหลายแถวแบบไม่ซ้ำกัน"""
        rows = self._require()
        count = max(1, min(count, len(rows)))
        rng = random.Random(seed)
        return rng.sample(rows, count)

    def page(self, offset: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._require()
        offset = max(0, offset)
        return rows[offset : offset + max(1, limit)]

    def all_orders(self) -> List[Dict[str, Any]]:
        """ออเดอร์ทุกแถวพร้อมเฉลยฝังอยู่ในคีย์ target — ใช้กับ evaluate_batch()"""
        result = []
        for row in self._require():
            order = dict(row["order"])
            order[TARGET_COL] = row["actual_minutes"]
            result.append(order)
        return result

    def stats(self) -> Dict[str, Any]:
        rows = self._require()
        actuals = [r["actual_minutes"] for r in rows]
        return {
            "count": len(rows),
            "target_col": TARGET_COL,
            "actual_min": min(actuals),
            "actual_max": max(actuals),
            "actual_mean": round(sum(actuals) / len(actuals), 2),
            "source": os.path.basename(self.csv_path),
        }


# instance เดียวที่ใช้ร่วมกันทั้งแอป
testset = TestSet()
