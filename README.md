# Food Delivery ETA — Dual-Model Comparison System

ระบบเปรียบเทียบความแม่นยำของ Random Forest **2 ตัว** กับเฉลยจริง
แยก Frontend / Backend ออกจากกัน ใช้ข้อมูลจาก **Zomato Delivery Dataset**

| | |
|---|---|
| **Backend** | FastAPI · deploy บน Render.com (Docker) |
| **Frontend** | Django 5 · deploy บน Vercel (Serverless WSGI) |
| **โมเดล 1** | 🟢 Random Forest **Tuned** — 200 ต้น · max_depth 15 |
| **โมเดล 2** | 🔵 Random Forest **Baseline** — 100 ต้น · ไม่จำกัดความลึก |
| **ชุดทดสอบ** | `text.csv` 1,000 แถว · มีเฉลย `Time_taken (min)` ครบทุกแถว |
| **ข้อมูลเทรน** | 40,344 ออเดอร์ (จาก 45,584 แถว หลังทำความสะอาด) · ฟีเจอร์ 33 คอลัมน์ |

### ผลวัดจริงบนชุดทดสอบ 1,000 แถว

| ตัวชี้วัด | 🟢 Tuned | 🔵 Baseline | ผู้ชนะ |
|---|---:|---:|---|
| MAE (นาที) | **3.2306** | 3.2655 | 🟢 Tuned |
| RMSE | **3.9449** | 4.0066 | 🟢 Tuned |
| R² | **0.8375** | 0.8324 | 🟢 Tuned |
| ความแม่นยำเฉลี่ย % | **85.75%** | 85.64% | 🟢 Tuned |
| ความแม่นยำมัธยฐาน % | 88.97% | **89.05%** | 🔵 Baseline |
| พลาดมากที่สุด (นาที) | 11.758 | **11.410** | 🔵 Baseline |
| ชนะรายแถว | **537 (53.7%)** | 463 (46.3%) | 🟢 Tuned |

> **ข้อสังเกตที่ควรรู้ก่อนนำไปนำเสนอ:** การปรับจูน hyperparameter ในงานนี้ช่วยได้
> **เพียงเล็กน้อย** — MAE ดีขึ้น 1.07% และ % ความแม่นยำเฉลี่ยต่างกันแค่ **0.11%**
> โมเดล Baseline ยังชนะในบางตัวชี้วัด (มัธยฐาน, ค่าพลาดสูงสุด) ด้วย
> ตัวเลขในระบบเป็นผลวัดจริง ไม่ได้ปรับแต่งให้ดูดี

---

## สารบัญ

1. [ภาพรวมสถาปัตยกรรม](#1-ภาพรวมสถาปัตยกรรม)
1.1 [หน้าตาของระบบ](#11-หน้าตาของระบบ)
2. [โครงสร้างไฟล์](#2-โครงสร้างไฟล์)
3. [ทดสอบบนเครื่อง (Local)](#3-ทดสอบบนเครื่อง-local)
4. [API Reference](#4-api-reference)
4.1 [API โหมดเปรียบเทียบ 2 โมเดล](#41-api-โหมดเปรียบเทียบ-2-โมเดล)
5. [Deploy Backend ขึ้น Render](#5-deploy-backend-ขึ้น-render)
6. [Deploy Frontend ขึ้น Vercel](#6-deploy-frontend-ขึ้น-vercel)
7. [ข้อควรรู้ก่อนแก้โค้ด](#7-ข้อควรรู้ก่อนแก้โค้ด)
8. [แก้ปัญหาที่พบบ่อย](#8-แก้ปัญหาที่พบบ่อย)

---

## 1. ภาพรวมสถาปัตยกรรม

```
┌──────────────────────┐        ┌──────────────────────┐        ┌──────────────────┐
│  เบราว์เซอร์            │        │  Frontend (Vercel)    │        │ Backend (Render) │
│                      │  AJAX  │  Django 5             │  HTTP  │ FastAPI          │
│  index.html          │ ─────► │  · proxy ไป Backend     │ ─────► │ · โหลด 2 โมเดล    │
│  app.js / style.css  │ ◄───── │  · ไม่ใช้ฐานข้อมูล        │ ◄───── │ · text.csv (เฉลย) │
│                      │  JSON  │                       │  JSON  │ · Compare + Eval │
└──────────────────────┘        └──────────────────────┘        └──────────────────┘
```

**ทำไมเบราว์เซอร์ไม่ยิงหา Backend ตรง ๆ?**
Django ทำตัวเป็น proxy บาง ๆ ให้ ได้ประโยชน์ 2 ข้อ — ไม่ต้องเปิด CORS กว้าง ๆ ที่ Backend
และ URL ของ Backend ไม่หลุดไปอยู่ใน JavaScript ฝั่ง client

**ทำไมข้อมูลทดสอบอยู่ฝั่ง Backend ไม่ใช่ Frontend?**
เพราะ `text.csv` มี **เฉลย** อยู่ด้วย การเก็บไว้ฝั่งเดียวกับโมเดลทำให้ยิงแค่ request เดียว
ก็ได้ทั้งข้อมูล คำทำนายของ 2 โมเดล และผลเปรียบเทียบครบ (`/compare/test-sample`)
ซึ่งสำคัญมากกับ Render ที่ latency สูง

**ตัวสุ่มออเดอร์เดิมยังอยู่ไหม?**
ยังอยู่ที่ `/random-sample` (backend) และ `/api/random/` (frontend) แต่หน้าเว็บไม่ได้ใช้แล้ว
เพราะเปลี่ยนมาใช้ข้อมูลจริงที่มีเฉลยเทียบได้ — `sampler.py` / `generator.py` ยังเป็นไฟล์ฝาแฝดกัน
**แก้ไฟล์ไหนต้องแก้อีกไฟล์ให้ตรงกัน**

---

## 1.1 หน้าตาของระบบ

หน้าเว็บมี 2 ส่วน: **แผนที่จำลองติดตามไรเดอร์** ทางซ้าย และ **แผงเปรียบเทียบ 2 โมเดล** ทางขวา

```
┌──────────────────────────────────────────┬───────────────────────┐
│  📍 Pune                  ┌────────────┐ │ ผลเปรียบเทียบ #87/1000│
│                           │ 🛵 PUNERES.│ │ ┌───────────────────┐ │
│       🏠 จุดส่ง            │ 25.3 นาที  │ │ │ 🎯 เวลาจริง (เฉลย) │ │
│        ╎                  │ ▓▓▓░░░░░░  │ │ │      41.0 นาที    │ │
│        ╎ (เส้นประ=ยังไม่ถึง) └────────────┘ │ └───────────────────┘ │
│   🛵━━━━╯                                │ ┌────────┬──────────┐ │
│   ┃ (เส้นทึบ=วิ่งผ่านแล้ว)                   │ │🟢Tuned👑│🔵Baseline│ │
│  🍜 ร้านอาหาร                             │ │ 35.0   │  34.7    │ │
│                                          │ │ −6.0   │  −6.3    │ │
│ ┌──────────────────────────────────────┐ │ │ 85.4%  │  84.6%   │ │
│ │ [#สุ่ม] [🎲 ดึงจาก text.csv]           │ │ │ ▓▓▓▓░  │  ▓▓▓▓░   │ │
│ │ [⚡ ทดสอบทั้ง 1,000 แถว]  1× 4× 10×   │ │ └────────┴──────────┘ │
│ └──────────────────────────────────────┘ │ 🏆 Tuned ชนะ 0.78%    │
└──────────────────────────────────────────┴───────────────────────┘
```

**ลำดับการทำงานเมื่อกด "🎲 ดึงออเดอร์จาก text.csv"**

1. Django เรียก `/compare/test-sample` ของ Backend — **ยิงแค่ request เดียว** ได้ครบทั้ง
   ข้อมูลดิบ, เฉลย, คำทำนายของ 2 โมเดล และผลเปรียบเทียบ
2. Backend หยิบ 1 แถวจาก `text.csv` (สุ่ม หรือระบุเลขแถวในช่อง `#` ได้)
   แล้วคำนวณฟีเจอร์ใหม่จากข้อมูลดิบ → ป้อนให้ทั้ง 2 โมเดล → เทียบกับเฉลย
3. หน้าเว็บวาดแผนที่เมืองนั้น แล้วลากเส้นทางจากพิกัดจริงของร้านและจุดส่ง
4. **ไรเดอร์วิ่งตามเวลาจริง (เฉลย) ไม่ใช่ตามคำทำนาย** — เพราะนั่นคือสิ่งที่เกิดขึ้นจริง
   ส่วนคำทำนายของสองโมเดลเอาไว้เทียบว่าใครใกล้เคียงกว่ากัน
5. แผงขวาแสดงเฉลย → การ์ด 2 ฝั่ง (คำทำนาย / ส่วนต่าง / % ความแม่นยำ + progress bar)
   → แถบสรุปผู้ชนะ พร้อมสะสมประวัติและสกอร์รวมไว้ด้านล่าง

**ปุ่ม "⚡ ทดสอบทั้ง 1,000 แถว"** สั่งให้ Backend ประเมินทั้งชุดรวดเดียว
(ใช้เวลาราว **4 วินาที**) แล้วเปิดหน้าต่างสรุป: ตารางเทียบ 6 ตัวชี้วัด
พร้อมทำเครื่องหมายว่าใครชนะแต่ละตัว และแถบสัดส่วนการชนะรายแถว

**รายละเอียดที่ตั้งใจออกแบบ**

- **แผนที่ไม่ได้ใช้ tile จากภายนอก** — วาดเป็น SVG ทั้งหมด จึงไม่ต้องใช้ API key
  ไม่มี request ออกนอกเครื่อง และทำงานได้แม้ออฟไลน์
- **พื้นที่ปลอดภัย (safe area)** — ก่อนวางเส้นทาง หน้าเว็บจะวัดตำแหน่งจริงของการ์ด ETA
  ป้ายชื่อเมือง และแผงควบคุม แล้วหลบไม่ให้เส้นทางไปอยู่ใต้แผงเหล่านั้น
  ปรับตามขนาดจอเองโดยไม่ต้องฮาร์ดโค้ด
- **viewBox ผูกกับขนาดกล่องจริง** — หน่วยใน SVG เท่ากับพิกเซล CSS พอดี
  ทำให้คำนวณพื้นที่ปลอดภัยได้แม่นและไม่มีส่วนไหนของแผนที่ถูกตัดทิ้ง
- ไรเดอร์สะสมบนแผนที่ได้สูงสุด **8 คัน** เกินนั้นจะเอาคันที่ส่งเสร็จแล้วออกก่อน

---

## 2. โครงสร้างไฟล์

```text
ml_project/
├── backend/
│   ├── app/
│   │   ├── main.py          # API endpoints + CORS + โหลดโมเดลตอน startup
│   │   ├── predictor.py     # ★ หัวใจ: Preprocessing + DualPredictor + คำนวณ % ความแม่นยำ
│   │   ├── testset.py       # โหลด text.csv + แปลงรูปแบบวันที่ + สุ่ม/ดึงแถว
│   │   ├── sampler.py       # ตัวสุ่มออเดอร์ (ของเดิม หน้าเว็บไม่ได้ใช้แล้ว)
│   │   └── schemas.py       # Pydantic: ตรวจสอบ Request/Response
│   ├── models/
│   │   ├── random_forest_eta.models   # 🟢 Tuned    — bundle dict (~129 MB)
│   │   └── baseline.model             # 🔵 Baseline — bundle dict (~206 MB)
│   ├── data/
│   │   └── text.csv                   # ชุดทดสอบ 1,000 แถว พร้อมเฉลย
│   ├── Dockerfile           # image สำหรับ Render
│   ├── render.yaml          # Render Blueprint
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── delivery_sim/        # Django project config
│   │   ├── settings.py      # ไม่ใช้ DB · WhiteNoise · อ่าน BACKEND_API_URL
│   │   ├── urls.py
│   │   └── wsgi.py          # entry point ของ Vercel (export ตัวแปร `app`)
│   ├── simulator/
│   │   ├── views.py         # ★ สุ่มออเดอร์ + proxy ไป Backend + จัดการ error
│   │   ├── generator.py     # สำเนาของ backend/app/sampler.py
│   │   ├── urls.py
│   │   └── templates/simulator/index.html   # หน้าแผนที่ติดตามไรเดอร์
│   ├── static/css/style.css # ธีมแผนที่กลางคืน
│   ├── static/js/app.js     # ★ วาดแผนที่ + อนิเมชันไรเดอร์ + modal รายละเอียด
│   ├── manage.py
│   ├── vercel.json
│   ├── requirements.txt
│   └── .env.example
│
└── README.md
```

> **หมายเหตุ** ไฟล์ที่เพิ่มจากโครงสร้างที่กำหนดไว้เดิม 5 ไฟล์ ได้แก่
> `backend/app/testset.py` (โหลดและจัดการ `text.csv`),
> `backend/app/sampler.py` (แยกตรรกะการสุ่มออกจาก `main.py`),
> `frontend/simulator/generator.py` (สำเนาฝั่งหน้าบ้าน),
> `frontend/manage.py` (Django บังคับต้องมีเพื่อรัน `runserver`) และ
> `frontend/delivery_sim/asgi.py` (สำรองไว้เผื่อ deploy ด้วย uvicorn)

---

## 3. ทดสอบบนเครื่อง (Local)

ต้องเปิด **2 เทอร์มินัล** เพราะเป็นคนละ service กัน

### 3.1 Backend (พอร์ต 8000)

```bash
cd ml_project/backend

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
copy .env.example .env          # Windows  (cp บน macOS/Linux)

uvicorn app.main:app --reload --port 8000
```

ตรวจสอบว่าโมเดลโหลดติด:

```bash
curl http://localhost:8000/health
# {"status":"ok","model_loaded":true,"model_type":"RandomForestRegressor","n_features":33, ...}
```

เอกสาร API แบบโต้ตอบได้: <http://localhost:8000/docs>

ทดลองดึงออเดอร์จริงแล้วให้ 2 โมเดลแข่งกันทำนาย:

```bash
curl "http://localhost:8000/compare/test-sample?index=142"
curl "http://localhost:8000/testset/stats"
```

รัน benchmark ทั้งชุด (ใช้เวลาราว 4 วินาที):

```bash
curl -X POST "http://localhost:8000/evaluate-batch" -H "Content-Type: application/json" -d "{}"
```

### 3.2 Frontend (พอร์ต 8001)

```bash
cd ml_project/frontend

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
copy .env.example .env
# แก้ใน .env ให้ชี้มาที่ Backend ที่เพิ่งเปิด:
#   BACKEND_API_URL=http://localhost:8000
#   DJANGO_DEBUG=true

python manage.py runserver 8001
```

เปิด <http://localhost:8001> จะเห็นหน้าแผนที่ว่าง ๆ รอให้กดปุ่ม **ดึงออเดอร์จาก text.csv**

> ไม่ต้องรัน `migrate` — โปรเจกต์นี้ตั้ง `DATABASES = {}` ไว้ ไม่ใช้ฐานข้อมูลเลย

### 3.3 เช็กว่าทุกอย่างต่อกันติด

| ตรวจสอบ | ผลที่ควรได้ |
|---|---|
| จุดสถานะมุมขวาบน | เป็นสีเขียว "โมเดลพร้อม" |
| กด **🎲 ดึงออเดอร์จาก text.csv** | แผนที่ถูกวาด · แผงขวาแสดง `#เลขแถว / 1000` · การ์ดเฉลยขึ้นเวลาจริง |
| การ์ด 🟢 Tuned / 🔵 Baseline | แสดงคำทำนาย · ส่วนต่างจากเฉลย · % ความแม่นยำ + progress bar |
| การ์ดฝั่งที่ชนะ | มี 👑 และกรอบสว่างขึ้น |
| แถบผู้ชนะ | เช่น "🏆 Tuned Model แม่นยำกว่า Baseline อยู่ 0.78%" |
| พิมพ์เลขในช่อง **#** แล้วกดดึง | ได้แถวนั้นตรง ๆ (ใส่เกิน 999 ต้องขึ้น error อ่านรู้เรื่อง) |
| กด **⚡ ทดสอบทั้ง 1,000 แถว** | เปิดหน้าต่างสรุป · ตาราง 6 ตัวชี้วัด · แถบสัดส่วนการชนะ 53.7% / 46.3% |
| กด **ดูรายละเอียดข้อมูลที่ดึงมา** | แสดงข้อมูลดิบ 19 ฟิลด์ + ฟีเจอร์ที่ server คำนวณ 6 ตัว |
| กด **1× / 4× / 10×** | ไรเดอร์วิ่งเร็วขึ้นตามที่เลือก |

---

## 4. API Reference

Base URL ตอน dev: `http://localhost:8000`

### `GET /health`
สถานะ service + metadata ของโมเดล (Render ใช้เส้นนี้เป็น health check)

### `POST /predict`
ทำนายออเดอร์เดียว — ส่ง **ข้อมูลดิบ** แบบเดียวกับ 1 แถวใน CSV ได้เลย
ฝั่ง server จะคำนวณ `Distance_km`, `Prep_time_min`, `Order_hour`, `Order_period`,
`Order_dayofweek`, `Is_weekend` ให้เอง

<details>
<summary>ตัวอย่าง request / response</summary>

```json
{
  "Delivery_person_Age": 36,
  "Delivery_person_Ratings": 4.2,
  "Restaurant_latitude": 30.327968,
  "Restaurant_longitude": 78.046106,
  "Delivery_location_latitude": 30.397968,
  "Delivery_location_longitude": 78.116106,
  "Order_Date": "12-02-2022",
  "Time_Orderd": "21:55",
  "Time_Order_picked": "22:10",
  "Weather_conditions": "Fog",
  "Road_traffic_density": "Jam",
  "Vehicle_condition": 2,
  "Type_of_order": "Snack",
  "Type_of_vehicle": "motorcycle",
  "multiple_deliveries": 3,
  "Festival": "No",
  "City": "Metropolitian"
}
```

```json
{
  "predicted_minutes": 35.73,
  "eta_range": { "low": 32.6, "high": 38.85 },
  "prediction_std": 3.345,
  "derived_features": {
    "Distance_km": 10.4516, "Prep_time_min": 15.0, "Order_hour": 21,
    "Order_period": "Night", "Order_dayofweek": 5, "Is_weekend": 1
  },
  "top_factors": [ { "feature": "Delivery_person_Ratings", "value": 4.2, "importance": 0.2209 } ],
  "model_metrics": { "MAE": 3.126, "RMSE": 3.874, "R2": 0.832 },
  "warnings": []
}
```
</details>

`prediction_std` คือส่วนเบี่ยงเบนมาตรฐานของคำทำนายจากต้นไม้ทั้ง 200 ต้น
ยิ่งสูงแปลว่าต้นไม้แต่ละต้นเห็นไม่ตรงกัน = โมเดลไม่มั่นใจกับออเดอร์นี้

### `POST /predict/batch`
ทำนายหลายออเดอร์ในครั้งเดียว (สูงสุด 200) — `{"orders": [ ... ]}`
พร้อมสรุป `mean_minutes` / `min_minutes` / `max_minutes` / `total_distance_km`

### `GET /random-sample?count=&seed=&city=`
สุ่มออเดอร์ตามการกระจายตัวจริง · `seed` เดิมให้ผลเดิมเสมอ · `city` เช่น `BANG`, `PUNE`

### `GET /random-sample/predict?count=&seed=&city=`
สุ่มแล้วทำนายให้เลยในครั้งเดียว (สูงสุด 50)

### `GET /metadata`
ค่าหมวดหมู่ที่รับได้ · ขอบเขตตัวเลข · รายชื่อเมือง 22 แห่ง · `feature_names` ทั้ง 33 คอลัมน์

---

## 4.1 API โหมดเปรียบเทียบ 2 โมเดล

### `GET /test-samples`
ดึงออเดอร์จาก `text.csv` พร้อมเฉลย มี 3 โหมด:

| พารามิเตอร์ | ผลลัพธ์ |
|---|---|
| `?index=142` | ได้แถวที่ 142 แถวเดียว |
| `?offset=0&count=20` | ได้ 20 แถวเรียงลำดับจากต้น (ไว้ไล่ดูทั้งไฟล์) |
| `?count=5&seed=42` | สุ่ม 5 แถวไม่ซ้ำ (`seed` เดิมให้ผลเดิม) |

### `POST /compare`
รับออเดอร์ 1 รายการ ทำนายด้วยทั้ง 2 โมเดล แล้วเทียบกับเฉลย

```json
{ "order": { ...19 ฟิลด์... }, "actual_minutes": 41.0 }
```

ถ้าไม่ส่ง `actual_minutes` จะได้แค่คำทำนายของทั้งสองโมเดล (ส่วน `comparison` จะเป็น `null`)

<details>
<summary>ตัวอย่าง response</summary>

```json
{
  "test_index": 142,
  "actual_minutes": 35.0,
  "tuned": {
    "model": "Random Forest (Tuned)",
    "predicted_minutes": 37.32,
    "error": 2.322,
    "diff": 2.32,
    "accuracy_percent": 93.37,
    "prediction_std": 4.1
  },
  "baseline": {
    "model": "Random Forest (Baseline)",
    "predicted_minutes": 36.88,
    "error": 1.88,
    "diff": 1.88,
    "accuracy_percent": 94.63,
    "prediction_std": 4.6
  },
  "comparison": {
    "winner": "baseline",
    "better_model": "Random Forest (Baseline)",
    "accuracy_gap": 1.26,
    "error_gap": 0.442
  },
  "derived_features": { "Distance_km": 16.851, "Prep_time_min": 5.0, "...": "..." }
}
```
</details>

ความหมายของแต่ละค่า:

- `error` = `|actual − predicted|` — ยิ่งน้อยยิ่งดี
- `diff` = `predicted − actual` — **ติดลบ = ทำนายเร็วกว่าจริง**, บวก = ช้ากว่าจริง
- `accuracy_percent` = `max(0, 100 × (1 − |actual − predicted| / actual))`
- `winner` = โมเดลที่ `error` น้อยกว่า (`tie` ถ้าเท่ากัน)

### `GET /compare/test-sample`
ทางลัดที่หน้าเว็บใช้จริง — ดึงแถวจาก `text.csv` แล้วเปรียบเทียบให้เลยในครั้งเดียว
รับ `?index=` (ระบุแถว) หรือ `?seed=` (สุ่มแบบซ้ำได้)

### `POST /evaluate-batch`
ประเมินทั้งชุดแล้วสรุปภาพรวม ส่ง `{}` มาเพื่อใช้ `text.csv` ทั้ง 1,000 แถว
หรือส่ง `{"limit": 100}` เพื่อทดสอบเร็ว ๆ หรือส่ง `orders` + `actuals` เพื่อประเมินชุดของตัวเอง

คืนค่า `MAE` / `RMSE` / `R²` / `mean_accuracy_percent` / `median_accuracy_percent` /
`max_error` / `wins` ของแต่ละโมเดล พร้อม `win_rate`, `overall_winner`,
`mae_improvement_percent` และ `accuracy_gap`

> ทำ predict ทีเดียวทั้งก้อน (ไม่ได้วนทีละแถว) จึงใช้เวลาราว **4 วินาที** สำหรับ
> 1,000 แถว × 2 โมเดล × รวม 300 ต้นไม้

### `GET /testset/stats`
จำนวนแถว · ช่วงของเฉลย (10–54 นาที) · ค่าเฉลี่ย (26.64 นาที) · ชื่อไฟล์ต้นทาง

---

## 5. Deploy Backend ขึ้น Render

### ⚠️ จัดการไฟล์โมเดล 129 MB ก่อน

GitHub ไม่รับไฟล์เกิน 100 MB ผ่าน git ปกติ **ต้องใช้ Git LFS**
(`backend/.gitattributes` ตั้งค่าไว้ให้แล้ว):

```bash
git lfs install
git lfs track "backend/models/*.models"
git lfs track "backend/models/*.model"
git add .gitattributes backend/models/random_forest_eta.models backend/models/baseline.model
git commit -m "Add both ETA models via LFS"
```

> `backend/.gitattributes` ตั้งค่าไว้ให้แล้วทั้ง `*.models` และ `*.model`
> (ต่างกันแค่ตัว s — ถ้าตั้งแค่แบบเดียวไฟล์อีกตัวจะหลุดไปเป็น blob ปกติแล้ว push ไม่ผ่าน)
> ส่วน `data/text.csv` เล็กแค่ 180 KB เก็บเป็น text ปกติได้ ไม่ต้องใช้ LFS

> ถ้าไม่อยากใช้ LFS: อัปโหลดโมเดลขึ้น object storage (S3 / R2 / Google Drive)
> แล้วแก้ `Dockerfile` ให้ `curl` ดาวน์โหลดมาตอน build พร้อมตั้ง `MODEL_PATH` ให้ตรง

### วิธีที่ 1 — ใช้ Blueprint (แนะนำ)

1. ย้าย `backend/render.yaml` ไปไว้ที่ **root ของ repo** (Render อ่านจาก root เท่านั้น)
2. ที่ Render เลือก **New → Blueprint** แล้วชี้มาที่ repo
3. Render จะอ่านค่าทั้งหมดจาก `render.yaml` เอง

### วิธีที่ 2 — สร้าง Web Service เอง

| ช่อง | ค่าที่ใส่ |
|---|---|
| Runtime | **Docker** |
| Root Directory | `backend` |
| Dockerfile Path | `./Dockerfile` |
| Health Check Path | `/health` |

Environment Variables:

```
MODEL_PATH        = /app/models/random_forest_eta.models
ALLOWED_ORIGINS   = https://your-frontend.vercel.app
LOG_LEVEL         = INFO
OMP_NUM_THREADS   = 1
```

> ไม่ต้องตั้ง `PORT` — Render ฉีดให้เอง และ `Dockerfile` อ่านค่านั้นอยู่แล้ว

### เรื่องหน่วยความจำ

⚠️ **โหลด 2 โมเดลพร้อมกันเกินโควตาของ Render แพ็กเกจฟรีแล้ว** จากการวัดจริงบน Python 3.12:

| ขั้นตอน | RSS สะสม | เพิ่มขึ้น |
|---|---:|---:|
| หลัง import numpy / pandas / sklearn | ~150 MB | — |
| + โหลด 🟢 Tuned (129 MB บนดิสก์) | ~386 MB | +236 MB |
| + โหลด 🔵 Baseline (206 MB บนดิสก์) | **~687 MB** | +301 MB |

Baseline กิน RAM **มากกว่า** Tuned ทั้งที่มีต้นไม้น้อยกว่าครึ่ง เพราะ `max_depth=None`
ทำให้ต้นไม้โตจนสุด (โหนดเยอะกว่ามาก) ส่วน Tuned ถูกจำกัดที่ 15 ชั้น

**512 MB ของแพ็กเกจฟรีไม่พอ** — `render.yaml` จึงตั้ง `plan: standard` (2 GB) ไว้แล้ว
ถ้าจำเป็นต้องใช้แพ็กเกจฟรีจริง ๆ ให้เลือกทางใดทางหนึ่ง:

- โหลดเฉพาะโมเดล Tuned แล้วปิดฟีเจอร์เปรียบเทียบ (ใช้ `/predict` แทน `/compare`)
- เทรน Baseline ใหม่โดยใส่ `max_depth` จำกัด แล้วเซฟทับ — ไฟล์จะเล็กลงมาก
- เพิ่ม `compress=3` ตอน `joblib.dump` (ช่วยขนาดไฟล์บนดิสก์ ไม่ช่วย RAM ตอนรัน)

ทางเลือกอื่นถ้าเจอ out-of-memory:

- อัปเกรดเป็นแพ็กเกจ Starter (512 MB → 2 GB) — ง่ายและชัวร์ที่สุด
- ลดขนาดโมเดล: เทรนใหม่ด้วย `n_estimators=50` แทน 200 แล้วเซฟทับ
  (MAE จะแย่ลงเล็กน้อยแต่ไฟล์เล็กลงราว 4 เท่า)
- เพิ่ม `compress=3` ตอน `joblib.dump` ใน notebook เพื่อบีบไฟล์บนดิสก์
  (ช่วยเรื่องขนาดไฟล์ ไม่ได้ช่วยเรื่อง RAM ตอนรัน)

`Dockerfile` ตั้ง `--workers 1` และ `OMP_NUM_THREADS=1` ไว้แล้วด้วยเหตุผลเดียวกัน

---

## 6. Deploy Frontend ขึ้น Vercel

```bash
npm i -g vercel
cd ml_project/frontend
vercel          # ครั้งแรก: ตอบคำถามตั้งค่าโปรเจกต์
vercel --prod   # deploy จริง
```

ตั้ง Environment Variables ที่ **Vercel → Project Settings → Environment Variables**:

```
BACKEND_API_URL             = https://eta-prediction-api.onrender.com
BACKEND_TIMEOUT             = 60
DJANGO_SECRET_KEY           = <สร้างใหม่ ดูคำสั่งด้านล่าง>
DJANGO_DEBUG                = false
DJANGO_ALLOWED_HOSTS        = .vercel.app
DJANGO_CSRF_TRUSTED_ORIGINS = https://*.vercel.app
ALLOW_BACKEND_DOWN          = true
```

สร้าง secret key ใหม่:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**หลัง deploy เสร็จ** อย่าลืมกลับไปแก้ `ALLOWED_ORIGINS` ที่ Render
ให้เป็นโดเมน Vercel จริง แทนที่จะปล่อย `*` ไว้

### รายละเอียดที่ทำให้ Django รันบน Vercel ได้

- `vercel.json` ชี้ไปที่ `delivery_sim/wsgi.py` ซึ่ง export ตัวแปรชื่อ `app`
  (Vercel มองหาชื่อนี้)
- `settings.py` ตั้ง `DATABASES = {}` และตัด app ที่ต้องใช้ DB ออก
  (`admin` / `auth` / `sessions`) — serverless จึงไม่ต้อง migrate
- Static เสิร์ฟด้วย WhiteNoise โดยเปิด `WHITENOISE_USE_FINDERS = True`
  ทำให้ **ไม่ต้องรัน `collectstatic` ตอน build** ซึ่งตั้งค่ายุ่งยากกับ `@vercel/python`

---

## 7. ข้อควรรู้ก่อนแก้โค้ด

### 7.1 สัญญา 33 คอลัมน์ (สำคัญที่สุด)

`backend/app/predictor.py` ต้องสร้างฟีเจอร์ให้ตรงกับที่โมเดลเทรนมา
**ทั้งชื่อและลำดับ** ไฟล์โมเดลเก็บลำดับไว้ที่คีย์ `feature_names`

notebook ใช้ `pd.get_dummies(X, drop_first=True)` ซึ่งตัด "ระดับอ้างอิง" ของแต่ละหมวดทิ้ง
ระดับเหล่านี้จึงถูกเข้ารหัสเป็น **ศูนย์ทุกคอลัมน์** ไม่ใช่ค่าที่หายไป:

| คอลัมน์ | ระดับอ้างอิง (= 0 ทุกคอลัมน์) |
|---|---|
| `Weather_conditions` | `Cloudy` |
| `Road_traffic_density` | `High` |
| `Type_of_order` | `Buffet` |
| `Type_of_vehicle` | `electric_scooter` |
| `Festival` | `No` |
| `City` | `Metropolitian` |
| `Order_period` | `Afternoon` |

`predictor.py` จึงใช้ `drop_first=False` แล้วค่อย `reindex(columns=feature_names, fill_value=0)`
— ถ้าใช้ `drop_first=True` กับข้อมูลแถวเดียว มันจะตัดหมวดหมู่เดียวที่มีอยู่ทิ้งเสมอ

> ✅ ตรวจสอบแล้ว: ฟีเจอร์ที่ `predictor.py` สร้างทีละแถว **ตรงกันเป๊ะ** กับที่ notebook
> สร้างแบบ batch (เทียบ 300 แถวสุ่ม ผลต่างสูงสุด 0.0)

### 7.2 กับดัก `bicycle`

`Type_of_vehicle` ในไฟล์ดิบมี 4 ค่า แต่ `bicycle` มีแค่ 68 แถว และถูกขั้นตอน
cleaning (ตัดพิกัดเสีย + ตัดแถวไม่มีเวลาสั่ง) **ตัดทิ้งทั้งหมด**
โมเดลจึงเหลือแค่ 3 หมวดและไม่เคยเห็น `bicycle` เลย

- ถ้าส่ง `bicycle` เข้ามา API จะทำนายให้ แต่ใส่ `warnings` เตือนว่าถูกตีเป็น `electric_scooter`
- ตัวสุ่มออเดอร์ **ไม่** generate `bicycle` ออกมา

### 7.3 ตัวสุ่มอิงข้อมูลจริง ไม่ได้เดา

ค่าคงที่ใน `sampler.py` / `generator.py` สกัดจาก CSV จริงทั้งหมด:

- **22 เมือง** พร้อมกรอบพิกัดจริง (มาจาก prefix 4 ตัวแรกของ `Delivery_person_ID`)
- **จุดส่ง = ร้าน + delta** โดย delta ของ lat กับ lon เท่ากันเสมอ
  และอยู่ในเซต `{0.01–0.09, 0.11, 0.13, 0.14}` (ไม่มี 0.10 กับ 0.12)
- **`Prep_time_min` มีแค่ 5 / 10 / 15 นาที** → เวลารับของ = เวลาสั่ง + ค่านี้
- **ชั่วโมงที่สั่ง 8–23 เท่านั้น** หนาแน่นช่วง 17–23 · นาทีเป็นพหุคูณของ 5 ตั้งแต่ `:10` ถึง `:55`
- **คะแนนไรเดอร์** 90% กระจุกอยู่ช่วง 4.2–5.0 (median จริง = 4.7)

ถ้าจะแก้ค่าเหล่านี้ **ต้องแก้ทั้ง 2 ไฟล์** ให้ตรงกัน

### 7.4 สองโมเดลใช้สัญญาฟีเจอร์ชุดเดียวกัน

ตรวจสอบแล้วว่า `feature_names` ของทั้งสองโมเดล **ตรงกันทุกตัวและเรียงเหมือนกัน**
(33 คอลัมน์) `DualPredictor.load()` จึงเช็คเงื่อนไขนี้ตอน startup — ถ้าไม่ตรงจะโยน error
ทันทีแทนที่จะปล่อยให้ทำนายผิดเงียบ ๆ

ผลพลอยได้: `compare_one()` เรียก `build_features()` **แค่ครั้งเดียว** แล้วป้อน
DataFrame ชุดเดียวกันให้ทั้งสองโมเดล ไม่ต้องคำนวณฟีเจอร์ซ้ำ

### 7.5 รูปแบบวันที่ใน text.csv ต่างจาก dataset ต้นฉบับ

`text.csv` เก็บ `Order_Date` เป็น **`YYYY-MM-DD`** (เช่น `2022-03-10`)
ส่วน `Zomato Dataset.csv` เป็น **`DD-MM-YYYY`**

จัดการไว้ 2 ชั้น:
1. `testset.py::_normalize_date()` แปลงเป็น `DD-MM-YYYY` ตอนโหลดไฟล์
2. `schemas.py` ของ `OrderRequest` รับได้ทั้งสองรูปแบบแล้วแปลงให้เป็นแบบเดียว

ถ้าไม่แปลง `predictor.py` จะ parse ด้วย `format='%d-%m-%Y'` ไม่ผ่านทุกแถว

### 7.6 ฟีเจอร์ใน text.csv ตรงกับที่ server คำนวณเอง

`text.csv` มีฟีเจอร์สกัดไว้ให้แล้ว 6 ตัว (`Distance_km`, `Prep_time_min`, `Order_hour`,
`Order_period`, `Order_dayofweek`, `Is_weekend`) แต่ระบบ **ไม่ได้ใช้ค่าเหล่านั้นโดยตรง** —
ส่งเฉพาะข้อมูลดิบ 19 ฟิลด์เข้า `predictor.build_features()` แล้วให้คำนวณใหม่เอง
เพื่อใช้โค้ดเส้นทางเดียวกับ `/predict` ปกติ ไม่ต้องมีทางลัดแยก

ตรวจสอบแล้วว่าค่าที่คำนวณเองตรงกับที่ไฟล์ให้มาทุกแถว
(`Distance_km` ต่างกันสูงสุด **3.6e-15** = ความคลาดเคลื่อนของ float เท่านั้น)
ค่าที่ไฟล์ให้มาถูกส่งกลับไปในฟิลด์ `precomputed` ของ `/test-samples` ไว้ให้ตรวจทานได้

### 7.7 การแปลงเวลา 3 รูปแบบ

`parse_time_value()` ใน `predictor.py` รับเวลาได้ 3 แบบเหมือน notebook:
`HH:MM` ปกติ · เศษส่วนของวันแบบ Excel (`0.458333` = 11:00) · ชั่วโมง ≥ 24 (`24:05` = `00:05`)
**ห้ามแทนด้วย `pd.to_datetime` เปล่า ๆ**

---

## 8. แก้ปัญหาที่พบบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| หน้าเว็บขึ้นแบนเนอร์เหลือง "เชื่อมต่อ Backend ไม่ได้" | Backend ยังไม่เปิด หรือ `BACKEND_API_URL` ผิด · ตรวจด้วย `curl $BACKEND_API_URL/health` |
| ครั้งแรกที่กดทำนายแล้วรอนานมาก | Render แพ็กเกจฟรีหลับเมื่อไม่มีทราฟฟิก · การปลุก + โหลดโมเดล 129 MB ใช้เวลา 30–60 วินาที · `BACKEND_TIMEOUT` ตั้งไว้ 60 วินาทีแล้ว |
| `InconsistentVersionWarning` ตอนโหลดโมเดล | เวอร์ชัน scikit-learn ไม่ตรงกับตอนเทรน · ยึดตาม `requirements.txt` (1.7.1) |
| `FileNotFoundError` หาไฟล์โมเดลไม่เจอ | คัดลอก `random_forest_eta.models` มาไว้ที่ `backend/models/` หรือตั้ง `MODEL_PATH` ให้ถูก |
| Render ขึ้น out-of-memory ตอน deploy | RAM 512 MB ไม่พอ · ดู [หัวข้อ 5](#เรื่องหน่วยความจำ) |
| Vercel ตอบ 400 `DisallowedHost` | เพิ่มโดเมนเข้า `DJANGO_ALLOWED_HOSTS` |
| กดปุ่มแล้ว CSRF ไม่ผ่าน (403) | เพิ่มโดเมนเข้า `DJANGO_CSRF_TRUSTED_ORIGINS` (ต้องมี `https://` นำหน้า) |
| API ตอบ 422 พร้อมชื่อฟิลด์ | ค่าเกินขอบเขตที่ `schemas.py` กำหนด เช่น เรตติ้ง > 5.0 หรืออายุนอกช่วง 15–50 |
| Backend ตายตอน startup บน Render | RAM ไม่พอโหลด 2 โมเดล (ต้องการ ~690 MB) · ต้องใช้ plan standard ขึ้นไป |
| `ValueError: สัญญาฟีเจอร์ของสองโมเดลไม่ตรงกัน` | ไฟล์โมเดลคนละรุ่นกัน · ต้องเซฟจาก notebook รอบเดียวกันที่ใช้ `feature_names` ชุดเดียวกัน |
| `/test-samples` ตอบ 503 | ไม่พบ `backend/data/text.csv` · คัดลอกไฟล์มาหรือตั้ง `TEST_CSV_PATH` |
| ดึงออเดอร์แล้วขึ้น "index ต้องอยู่ระหว่าง 0 ถึง 999" | ใส่เลขแถวเกินขนาดไฟล์ (มี 1,000 แถว index 0–999) |
| benchmark timeout | เพิ่ม `BATCH_TIMEOUT` ฝั่ง frontend (ค่าเริ่มต้น 180 วินาที) |
| กด "ดึงออเดอร์" แล้วไม่มีอะไรเกิดขึ้น (403) | cookie `csrftoken` ไม่ถูกตั้ง · หน้านี้ไม่มี `<form>` จึงใช้ `@ensure_csrf_cookie` ที่ view `index` แทน ตรวจว่า decorator ยังอยู่ |
| CSS ไม่ขึ้นบน Vercel | ตรวจว่า `WHITENOISE_USE_FINDERS = True` ยังอยู่ และ `whitenoise` อยู่ใน `requirements.txt` |

---

## ที่มาของโมเดล

โมเดลทั้งสองถูกเทรนไว้แล้วใน `../Untitled42.ipynb` (ไม่ต้องเทรนใหม่เพื่อรันระบบนี้)
ทั้งคู่เป็น bundle dictionary รูปแบบเดียวกัน มี 5 คีย์:

```python
{
  'model':          RandomForestRegressor(n_estimators=200, max_depth=15, min_samples_leaf=1),
  'feature_names':  [...33 ชื่อ เรียงลำดับสำคัญ...],
  'target_col':     'Time_taken (min)',
  'impute_values':  {'Delivery_person_Age': 30.0, 'Delivery_person_Ratings': 4.7,
                     'multiple_deliveries': 1.0, 'Festival': 'No'},
  'metrics':        {'MAE': 3.126, 'RMSE': 3.874, 'R2': 0.832}
}
```

ค่า `metrics` ที่ฝังอยู่ในไฟล์ คือผลตอนเทรนบนชุดทดสอบ 8,069 ออเดอร์ของ notebook:

| โมเดล | MAE | RMSE | R² | อยู่ในระบบนี้ |
|---|---|---|---|---|
| Linear Regression | 4.793 | 5.994 | 0.597 | ✗ (ไม่ได้เซฟไฟล์ไว้) |
| Random Forest (default) | 3.157 | 3.919 | 0.828 | 🔵 `baseline.model` |
| Random Forest (tuned) | **3.126** | **3.874** | **0.832** | 🟢 `random_forest_eta.models` |

**อย่าสับสนระหว่างตัวเลข 2 ชุด:** ค่าข้างบนคือผลบนชุดทดสอบของ notebook (8,069 แถว)
ส่วนตัวเลขที่ระบบแสดงมาจากการประเมิน `text.csv` (1,000 แถว) จึงไม่เท่ากัน —
`/health` คืนค่าชุดแรก ส่วน `/evaluate-batch` คืนค่าชุดหลัง

**จุดอ่อนที่รู้อยู่แล้ว:** โมเดลแม่นน้อยลงที่ปลายทั้งสองข้าง —
MAE 3.74 สำหรับออเดอร์ที่ส่งจริงภายใน 15 นาที และ 3.54 สำหรับที่เกิน 35 นาที
เทียบกับ 2.59 ในช่วงกลาง (16–25 นาที)
