# =====================================================================
# Food Delivery ETA Prediction API — image สำหรับ deploy บน Render.com
#
# build:  docker build -t eta-api ./backend
# run:    docker run -p 8000:8000 eta-api
# =====================================================================
FROM python:3.12-slim

# - PYTHONUNBUFFERED ให้ log ออกทันที (Render อ่าน stdout)
# - PYTHONDONTWRITEBYTECODE ลดขนาด layer
# - OMP/OPENBLAS threads: จำกัดเป็น 1 เพราะ instance ฟรีของ Render มี CPU น้อย
#   ปล่อยให้ Random Forest กาง thread เองจะทำให้ช้าลงและกิน RAM เพิ่ม
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    MODEL_PATH=/app/models/random_forest_eta.models \
    BASELINE_MODEL_PATH=/app/models/baseline.model \
    TEST_CSV_PATH=/app/data/text.csv

WORKDIR /app

# ติดตั้ง dependency ก่อนคัดลอกโค้ด เพื่อให้ Docker cache layer นี้ไว้
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# โมเดลเป็นไฟล์ใหญ่ (129 MB + 206 MB) คัดลอกแยก layer จะได้ไม่ต้อง rebuild ตอนแก้โค้ด
COPY models/ /app/models/
COPY data/ /app/data/
COPY app/ /app/app/

# รันด้วย user ที่ไม่ใช่ root
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Render ฉีดตัวแปร PORT เข้ามาเอง ถ้าไม่มีให้ fallback เป็น 8000
# ใช้ 1 worker เท่านั้น เพราะโมเดล 2 ตัวรวมกันกิน RAM ~690 MB ต่อ process
# (วัดจริง: ไลบรารี 150 + tuned 236 + baseline 301) แต่ละ worker จะโหลดซ้ำทั้งหมด
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
