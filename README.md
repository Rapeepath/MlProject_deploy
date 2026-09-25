# Food Delivery ETA — Simulation & Prediction System

ระบบทำนายและจำลองการจัดส่งอาหาร แยก Frontend / Backend ออกจากกัน
ใช้โมเดล Random Forest ที่เทรนไว้แล้วจาก **Zomato Delivery Dataset**

| | |
|---|---|
| **Backend** | FastAPI · deploy บน Render.com (Docker) |
| **Frontend** | Django 5 · deploy บน Vercel (Serverless WSGI) |
| **โมเดล** | Random Forest (tuned) — MAE **3.13 นาที** · RMSE 3.87 · R² **0.832** |
| **ข้อมูลเทรน** | 40,344 ออเดอร์ (จาก 45,584 แถว หลังทำความสะอาด) · ฟีเจอร์ 33 คอลัมน์ |

---

## สารบัญ

1. [ภาพรวมสถาปัตยกรรม](#1-ภาพรวมสถาปัตยกรรม)
1.1 [หน้าตาของระบบ](#11-หน้าตาของระบบ)
2. [โครงสร้างไฟล์](#2-โครงสร้างไฟล์)
3. [ทดสอบบนเครื่อง (Local)](#3-ทดสอบบนเครื่อง-local)
4. [API Reference](#4-api-reference)
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
│  index.html          │ ─────► │  · สุ่มออเดอร์จำลอง       │ ─────► │ · โหลด .models    │
│  app.js / style.css  │ ◄───── │  · proxy ไป Backend     │ ◄───── │ · Preprocess     │
│                      │  JSON  │  · ไม่ใช้ฐานข้อมูล        │  JSON  │ · Predict        │
└──────────────────────┘        └──────────────────────┘        └──────────────────┘
```

**ทำไมเบราว์เซอร์ไม่ยิงหา Backend ตรง ๆ?**
Django ทำตัวเป็น proxy บาง ๆ ให้ ได้ประโยชน์ 2 ข้อ — ไม่ต้องเปิด CORS กว้าง ๆ ที่ Backend
และ URL ของ Backend ไม่หลุดไปอยู่ใน JavaScript ฝั่ง client

**ทำไมหน้าบ้านสุ่มออเดอร์เอง แทนที่จะเรียก `/random-sample` ของ Backend?**
Django สุ่มเองแล้วส่งไปให้ Backend ทำนายในครั้งเดียว จึงยิงแค่ request เดียวต่อการกดปุ่ม
หนึ่งครั้ง ซึ่งสำคัญมากกับ Render แพ็กเกจฟรีที่ latency สูง
(`backend/app/sampler.py` กับ `frontend/simulator/generator.py` จึงเป็นไฟล์ฝาแฝดกัน —
**แก้ไฟล์ไหนต้องแก้อีกไฟล์ให้ตรงกันเสมอ**)

---

## 1.1 หน้าตาของระบบ

หน้าเว็บเป็น **แผนที่จำลองติดตามไรเดอร์** แบบเดียวกับแอปสั่งอาหารจริง ไม่ใช่ฟอร์มกรอกข้อมูล

```
┌──────────────────────────────────────────┬─────────────────┐
│  📍 Chennai              ┌─────────────┐ │ ไรเดอร์ที่กำลังส่ง │
│                          │ 🛵 CHENRES..│ │ ┌─────────────┐ │
│       🏠 จุดส่ง           │ 31.7 นาที   │ │ │ Chennai     │ │
│        ╎                 │ ▓▓▓░░░░░░░  │ │ │ 37.3 นาที   │ │
│        ╎ (เส้นประ=ยังไม่ถึง) └─────────────┘ │ │ [ดูรายละเอียด]│ │
│   🛵━━━━╯                                │ └─────────────┘ │
│   ┃ (เส้นทึบ=วิ่งผ่านแล้ว)                   │                 │
│  🍜 ร้านอาหาร                             │                 │
│           ┌──────────────────────────┐   │                 │
│           │ [เมือง▾] [🛵 สร้างไรเดอร์] │   │                 │
│           │      1×  4×  10×         │   │                 │
│           └──────────────────────────┘   │                 │
└──────────────────────────────────────────┴─────────────────┘
```

**ลำดับการทำงานเมื่อกด "สร้างไรเดอร์"**

1. Django สุ่มออเดอร์ 1 รายการ (ใน `generator.py`) แล้วส่งให้ Backend ทำนายในครั้งเดียว
   ผ่าน `/api/simulate/` — ยิงแค่ request เดียว ไม่ใช่สองรอบ
2. หน้าเว็บวาดแผนที่เมืองนั้นขึ้นมา (ถนน / บล็อกอาคาร / แม่น้ำ / สวน)
   ลวดลายสุ่มด้วย seed จากรหัสเมือง — **เมืองเดิมจะได้แผนที่หน้าตาเดิมเสมอ**
3. แปลงพิกัด lat/lon จริงของร้านและจุดส่งลงบนแผนที่ แล้วลากเส้นทางแบบหักมุมตามถนน
4. ไรเดอร์วิ่งจากร้านไปจุดส่งด้วยความเร็วที่ผูกกับ ETA ที่โมเดลทำนาย
   (1 นาทีที่ทำนาย = 0.9 วินาทีบนหน้าจอ ที่ความเร็ว 1×)

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
│   │   ├── predictor.py     # ★ หัวใจ: Preprocessing + Predict (ต้องตรงกับ notebook เป๊ะ)
│   │   ├── sampler.py       # ตัวสุ่มออเดอร์ตามการกระจายตัวจริงของ dataset
│   │   └── schemas.py       # Pydantic: ตรวจสอบ Request/Response
│   ├── models/
│   │   └── random_forest_eta.models   # bundle dict (~129 MB)
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

> **หมายเหตุ** ไฟล์ที่เพิ่มจากโครงสร้างที่กำหนดไว้เดิม 4 ไฟล์ ได้แก่
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

ทดลองสุ่มออเดอร์แล้วทำนายในคำสั่งเดียว:

```bash
curl "http://localhost:8000/random-sample/predict?count=3&city=BANG"
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

เปิด <http://localhost:8001> จะเห็นหน้าแผนที่ว่าง ๆ รอให้กดปุ่ม **สร้างไรเดอร์**

> ไม่ต้องรัน `migrate` — โปรเจกต์นี้ตั้ง `DATABASES = {}` ไว้ ไม่ใช้ฐานข้อมูลเลย

### 3.3 เช็กว่าทุกอย่างต่อกันติด

| ตรวจสอบ | ผลที่ควรได้ |
|---|---|
| จุดสถานะมุมขวาบน | เป็นสีเขียว "โมเดลพร้อม" |
| กด **🛵 สร้างไรเดอร์** | แผนที่เมืองถูกวาดขึ้น · หมุดร้าน 🍜 กับจุดส่ง 🏠 ปรากฏ · ไรเดอร์เริ่มวิ่งตามเส้นทาง |
| การ์ด ETA มุมขวาบนแผนที่ | นับถอยหลังเวลาที่เหลือลงเรื่อย ๆ พร้อมแถบความคืบหน้า |
| กด **1× / 4× / 10×** | ไรเดอร์วิ่งเร็วขึ้นตามที่เลือก |
| กด **ดูรายละเอียด** บนการ์ดไรเดอร์ | เปิดหน้าต่างแสดงข้อมูลดิบ 19 ฟิลด์ + ฟีเจอร์ที่โมเดลคำนวณ 6 ตัว + ปัจจัยสำคัญ |
| กดการ์ดไรเดอร์ในแถบข้าง | แผนที่ซูมไปที่ไรเดอร์คนนั้น คันอื่นจะถูกหรี่ลง |

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

## 5. Deploy Backend ขึ้น Render

### ⚠️ จัดการไฟล์โมเดล 129 MB ก่อน

GitHub ไม่รับไฟล์เกิน 100 MB ผ่าน git ปกติ **ต้องใช้ Git LFS**
(`backend/.gitattributes` ตั้งค่าไว้ให้แล้ว):

```bash
git lfs install
git lfs track "backend/models/*.models"
git add .gitattributes backend/models/random_forest_eta.models
git commit -m "Add ETA model via LFS"
```

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

แพ็กเกจฟรีของ Render มี RAM **512 MB** จากการวัดจริงบน Python 3.12:

| | RSS |
|---|---|
| หลัง import numpy/pandas/sklearn | ~150 MB |
| หลังโหลดโมเดล (เพิ่มอีก ~236 MB) | **~386 MB** |

เหลือ headroom ราว 125 MB ซึ่งพอรันได้แต่ไม่เหลือเฟือ ถ้าเจอ out-of-memory
ให้เลือกทางใดทางหนึ่ง:

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

### 7.4 การแปลงเวลา 3 รูปแบบ

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
| กด "สร้างไรเดอร์" แล้วไม่มีอะไรเกิดขึ้น (403) | cookie `csrftoken` ไม่ถูกตั้ง · หน้านี้ไม่มี `<form>` จึงใช้ `@ensure_csrf_cookie` ที่ view `index` แทน ตรวจว่า decorator ยังอยู่ |
| CSS ไม่ขึ้นบน Vercel | ตรวจว่า `WHITENOISE_USE_FINDERS = True` ยังอยู่ และ `whitenoise` อยู่ใน `requirements.txt` |

---

## ที่มาของโมเดล

โมเดลถูกเทรนไว้แล้วใน `../Untitled42.ipynb` (ไม่ต้องเทรนใหม่เพื่อรันระบบนี้)
ไฟล์ `.models` เป็น bundle dictionary ที่มี 5 คีย์:

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

เปรียบเทียบกับโมเดลอื่นบนชุดทดสอบ 8,069 ออเดอร์:

| โมเดล | MAE | RMSE | R² |
|---|---|---|---|
| Linear Regression (baseline) | 4.793 | 5.994 | 0.597 |
| Random Forest (default) | 3.157 | 3.919 | 0.828 |
| **Random Forest (tuned)** ← ใช้ตัวนี้ | **3.126** | **3.874** | **0.832** |

**จุดอ่อนที่รู้อยู่แล้ว:** โมเดลแม่นน้อยลงที่ปลายทั้งสองข้าง —
MAE 3.74 สำหรับออเดอร์ที่ส่งจริงภายใน 15 นาที และ 3.54 สำหรับที่เกิน 35 นาที
เทียบกับ 2.59 ในช่วงกลาง (16–25 นาที)
