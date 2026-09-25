"""
ตัวสุ่มออเดอร์จำลอง (Random Order Generator)

ค่าคงที่ทั้งหมดในไฟล์นี้สกัดมาจาก Zomato Dataset.csv จริง (45,584 แถว) หลังผ่าน
ขั้นตอน cleaning เดียวกับ notebook ไม่ได้เดาเอา รายละเอียดที่สำคัญ:

  * เมือง 22 แห่ง อ้างอิงจาก prefix 4 ตัวแรกของ Delivery_person_ID (เช่น BANG, PUNE)
    พร้อมกรอบพิกัดจริงของร้านอาหารในเมืองนั้น
  * จุดส่งในชุดข้อมูลนี้ถูกสร้างแบบ "ร้าน + delta" โดยที่ delta ของ lat และ lon
    เท่ากันเสมอ และมีค่าอยู่ในเซต {0.01-0.09, 0.11, 0.13, 0.14} (ไม่มี 0.10 / 0.12)
  * Prep_time_min มีเพียง 5 / 10 / 15 นาที -> เวลารับของ = เวลาสั่ง + ค่านี้
  * เวลาสั่งพบเฉพาะชั่วโมง 8-23 และนาทีเป็นพหุคูณของ 5 ตั้งแต่ :10 ถึง :55
  * 'bicycle' มี 68 แถวในไฟล์ดิบแต่ถูก cleaning ตัดทิ้งหมด โมเดลจึงไม่รู้จัก
    ตัวสุ่มนี้จึงไม่ generate bicycle ออกมา
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# เมืองและกรอบพิกัดร้านอาหารจริงใน dataset
# (code, ชื่อเมือง, lat_min, lat_max, lon_min, lon_max, น้ำหนักตามจำนวนแถวจริง)
# =====================================================================
CITY_CLUSTERS: List[Tuple[str, str, float, float, float, float, int]] = [
    ("JAPR", "Jaipur",      26.7665, 26.9564, 75.7528, 75.8373, 3443),
    ("BANG", "Bangalore",   12.9062, 13.0292, 77.5710, 77.6994, 3193),
    ("SURR", "Surat",       21.1496, 21.1869, 72.7687, 72.8145, 3187),
    ("HYDR", "Hyderabad",   17.4104, 17.4832, 78.3296, 78.5521, 3179),
    ("MUMR", "Mumbai",      18.9276, 19.2546, 72.8131, 72.9723, 3173),
    ("COIM", "Coimbatore",  10.9618, 11.0261, 76.9404, 77.0154, 3169),
    ("INDO", "Indore",      22.6518, 22.7616, 75.8661, 75.9034, 3158),
    ("CHEN", "Chennai",     12.9728, 13.0918, 80.1746, 80.2752, 3144),
    ("PUNE", "Pune",        18.5142, 18.6362, 73.7511, 73.9166, 3132),
    ("MYSR", "Mysore",      12.2847, 12.3521, 76.6031, 76.6658, 3011),
    ("RANC", "Ranchi",      23.3330, 23.4168, 85.3168, 85.3905, 2563),
    ("VADR", "Vadodara",    22.3079, 22.3200, 73.1589, 73.1709, 1576),
    ("KOCR", "Kochi",        9.9571, 10.0356, 76.2430, 76.3495,  701),
    ("KOLR", "Kolkata",     22.5141, 22.5778, 88.3223, 88.4335,  700),
    ("LUDH", "Ludhiana",    30.8740, 30.9141, 75.7870, 75.8427,  687),
    ("KNPR", "Kanpur",      26.4635, 26.4921, 80.2998, 80.3729,  676),
    ("GOAR", "Goa",         15.1579, 15.5857, 73.7423, 73.9509,  609),
    ("ALHR", "Allahabad",   25.4440, 25.4598, 81.8317, 81.8602,  568),
    ("AURG", "Aurangabad",  19.8670, 19.8887, 75.3167, 75.3724,  555),
    ("AGRR", "Agra",        27.1578, 27.2017, 77.9981, 78.0570,  550),
    ("DEHR", "Dehradun",    30.3195, 30.3722, 78.0403, 78.0772,  492),
    ("BHPR", "Bhopal",      23.1850, 23.2663, 77.3736, 77.4370,  478),
]

# ระยะห่างร้าน -> จุดส่ง (หน่วยองศา) ใช้กับทั้ง lat และ lon เท่า ๆ กัน
LOCATION_DELTAS: Tuple[float, ...] = (
    0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.11, 0.13, 0.14,
)

# ตัวแปรหมวดหมู่ พร้อมน้ำหนักตามสัดส่วนจริงในไฟล์ (หลัง cleaning)
WEATHER_CHOICES: Tuple[str, ...] = ("Fog", "Stormy", "Cloudy", "Sandstorms", "Windy", "Sunny")
WEATHER_WEIGHTS: Tuple[int, ...] = (7653, 7584, 7533, 7494, 7422, 7282)

TRAFFIC_CHOICES: Tuple[str, ...] = ("Low", "Jam", "Medium", "High")
TRAFFIC_WEIGHTS: Tuple[int, ...] = (15476, 14139, 10945, 4423)

ORDER_TYPE_CHOICES: Tuple[str, ...] = ("Snack", "Meal", "Drinks", "Buffet")
ORDER_TYPE_WEIGHTS: Tuple[int, ...] = (11530, 11456, 11321, 11277)

# ไม่รวม bicycle เพราะโมเดลไม่เคยเห็น (ถูก cleaning ตัดทิ้งทั้ง 68 แถว)
VEHICLE_CHOICES: Tuple[str, ...] = ("motorcycle", "scooter", "electric_scooter")
VEHICLE_WEIGHTS: Tuple[int, ...] = (23654, 13486, 3204)

VEHICLE_CONDITION_CHOICES: Tuple[int, ...] = (0, 1, 2, 3)
VEHICLE_CONDITION_WEIGHTS: Tuple[int, ...] = (15005, 15028, 15031, 520)

MULTI_DELIVERY_CHOICES: Tuple[float, ...] = (0.0, 1.0, 2.0, 3.0)
MULTI_DELIVERY_WEIGHTS: Tuple[int, ...] = (14094, 28151, 1985, 361)

CITY_TYPE_CHOICES: Tuple[str, ...] = ("Metropolitian", "Urban", "Unknown", "Semi-Urban")
CITY_TYPE_WEIGHTS: Tuple[int, ...] = (34087, 10133, 1059, 164)

FESTIVAL_CHOICES: Tuple[str, ...] = ("No", "Yes")
FESTIVAL_WEIGHTS: Tuple[int, ...] = (44460, 896)

# ชั่วโมงที่พบจริง: ช่วงสาย 8-11 และช่วงเย็น-ดึก 17-23 หนาแน่นกว่าช่วงบ่ายมาก
HOUR_CHOICES: Tuple[int, ...] = (8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23)
HOUR_WEIGHTS: Tuple[int, ...] = (
    1675, 1792, 1824, 1803, 826, 719, 723, 800, 649, 3944, 4133, 4230, 4195, 4315, 4193, 4127,
)

MINUTE_CHOICES: Tuple[int, ...] = (10, 15, 20, 25, 30, 35, 40, 45, 50, 55)

# เวลาเตรียมอาหารมีเพียง 3 ค่านี้ กระจายเกือบเท่ากัน
PREP_TIME_CHOICES: Tuple[int, ...] = (5, 10, 15)

# ช่วงวันที่ของ dataset ต้นฉบับ
DATE_START = datetime(2022, 2, 11)
DATE_END = datetime(2022, 4, 6)

AGE_MIN, AGE_MAX = 15, 50
RATING_MIN, RATING_MAX = 1.0, 5.0

_CITY_WEIGHTS = [c[6] for c in CITY_CLUSTERS]


def _hex_order_id(rng: random.Random) -> str:
    """รหัสออเดอร์รูปแบบเดียวกับคอลัมน์ ID เช่น 0xcdcd"""
    return "0x" + "".join(rng.choice("0123456789abcdef") for _ in range(4))


def _delivery_person_id(rng: random.Random, city_code: str) -> str:
    """รหัสไรเดอร์รูปแบบ <CITYCODE>RES<NN>DEL<NN> เช่น PUNERES13DEL03"""
    return f"{city_code}RES{rng.randint(1, 20):02d}DEL{rng.randint(1, 3):02d}"


def _sample_rating(rng: random.Random) -> float:
    """คะแนนไรเดอร์: ในไฟล์จริงกระจุกแถว 4.5-5.0 (median 4.7) และมีหางล่างบาง ๆ"""
    if rng.random() < 0.90:
        return round(rng.uniform(4.2, 5.0), 1)
    return round(rng.uniform(RATING_MIN, 4.2), 1)


def generate_random_order(
    seed: Optional[int] = None,
    city_code: Optional[str] = None,
) -> Dict[str, Any]:
    """สร้างออเดอร์สุ่ม 1 รายการในรูปแบบเดียวกับ 1 แถวของ Zomato Dataset

    Args:
        seed: ใส่เพื่อให้ผลลัพธ์ซ้ำได้ (ใช้ตอนเดโม/เทสต์)
        city_code: บังคับเมือง เช่น 'BANG' ถ้าไม่ใส่จะสุ่มตามสัดส่วนจริง

    Returns:
        dict ที่มีคีย์ครบตาม OrderRequest บวก '_city_name' สำหรับแสดงผล
    """
    rng = random.Random(seed)

    # --- เลือกเมืองและพิกัดร้าน ---
    if city_code:
        matches = [c for c in CITY_CLUSTERS if c[0] == city_code.upper()]
        if not matches:
            valid = ", ".join(c[0] for c in CITY_CLUSTERS)
            raise ValueError(f"ไม่รู้จักรหัสเมือง '{city_code}' (ที่รองรับ: {valid})")
        cluster = matches[0]
    else:
        cluster = rng.choices(CITY_CLUSTERS, weights=_CITY_WEIGHTS, k=1)[0]

    code, city_name, lat_min, lat_max, lon_min, lon_max, _ = cluster

    restaurant_lat = round(rng.uniform(lat_min, lat_max), 6)
    restaurant_lon = round(rng.uniform(lon_min, lon_max), 6)

    # จุดส่ง = ร้าน + delta เท่ากันทั้ง lat/lon ตามโครงสร้างจริงของ dataset
    delta = rng.choice(LOCATION_DELTAS)
    delivery_lat = round(restaurant_lat + delta, 6)
    delivery_lon = round(restaurant_lon + delta, 6)

    # --- เวลา ---
    hour = rng.choices(HOUR_CHOICES, weights=HOUR_WEIGHTS, k=1)[0]
    minute = rng.choice(MINUTE_CHOICES)
    prep_minutes = rng.choice(PREP_TIME_CHOICES)

    ordered_at = datetime(2022, 1, 1, hour, minute)
    picked_at = ordered_at + timedelta(minutes=prep_minutes)

    span_days = (DATE_END - DATE_START).days
    order_date = DATE_START + timedelta(days=rng.randint(0, span_days))

    order: Dict[str, Any] = {
        "ID": _hex_order_id(rng),
        "Delivery_person_ID": _delivery_person_id(rng, code),
        "Delivery_person_Age": float(rng.randint(AGE_MIN, AGE_MAX)),
        "Delivery_person_Ratings": _sample_rating(rng),
        "Restaurant_latitude": restaurant_lat,
        "Restaurant_longitude": restaurant_lon,
        "Delivery_location_latitude": delivery_lat,
        "Delivery_location_longitude": delivery_lon,
        "Order_Date": order_date.strftime("%d-%m-%Y"),
        "Time_Orderd": ordered_at.strftime("%H:%M"),
        "Time_Order_picked": picked_at.strftime("%H:%M"),
        "Weather_conditions": rng.choices(WEATHER_CHOICES, weights=WEATHER_WEIGHTS, k=1)[0],
        "Road_traffic_density": rng.choices(TRAFFIC_CHOICES, weights=TRAFFIC_WEIGHTS, k=1)[0],
        "Vehicle_condition": rng.choices(
            VEHICLE_CONDITION_CHOICES, weights=VEHICLE_CONDITION_WEIGHTS, k=1
        )[0],
        "Type_of_order": rng.choices(ORDER_TYPE_CHOICES, weights=ORDER_TYPE_WEIGHTS, k=1)[0],
        "Type_of_vehicle": rng.choices(VEHICLE_CHOICES, weights=VEHICLE_WEIGHTS, k=1)[0],
        "multiple_deliveries": rng.choices(
            MULTI_DELIVERY_CHOICES, weights=MULTI_DELIVERY_WEIGHTS, k=1
        )[0],
        "Festival": rng.choices(FESTIVAL_CHOICES, weights=FESTIVAL_WEIGHTS, k=1)[0],
        "City": rng.choices(CITY_TYPE_CHOICES, weights=CITY_TYPE_WEIGHTS, k=1)[0],
        "_city_name": city_name,
        "_city_code": code,
    }
    return order


def generate_random_orders(
    count: int,
    seed: Optional[int] = None,
    city_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """สร้างออเดอร์สุ่มหลายรายการ (seed เดียวให้ชุดผลลัพธ์เดิมเสมอ)"""
    if count < 1:
        raise ValueError("count ต้องมากกว่า 0")
    base = random.Random(seed)
    return [
        generate_random_order(seed=base.randrange(2**31), city_code=city_code)
        for _ in range(count)
    ]


def available_cities() -> List[Dict[str, Any]]:
    """รายชื่อเมืองที่สุ่มได้ พร้อมกรอบพิกัดจริง

    หน้าบ้านใช้ `bounds` วาดลวดลายเมืองบนแผนที่จำลองให้ต่างกันไปตามเมือง
    """
    return [
        {
            "code": code,
            "name": name,
            "sample_count": weight,
            "bounds": {
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max,
            },
        }
        for code, name, lat_min, lat_max, lon_min, lon_max, weight in CITY_CLUSTERS
    ]
