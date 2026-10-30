# VisionAttend-AI — Local FastAPI Backend Foundation (Stage 5.1)

Welcome to the **VisionAttend-AI** backend service. This service provides biometric facial quality validation, 5-point landmark alignment, 512-dimensional ArcFace embedding extraction, and cosine similarity matching for the GOOUUU ESP32-S3-CAM edge camera.

---

## Architecture Overview (Stage 5.1 Foundation)

```text
  [ESP32-S3 Edge Node]                   [FastAPI Local Backend]
  MSR/MNP Face Detection (46ms)          ImageValidator (Blur, Light, Size)
       │                                            │
       ▼                                            ▼
  Dynamic Crop + JPEG (2.4KB) ──HTTPS/Token──▶ FaceAligner (5-Pt to 112×112)
                                                    │
                                                    ▼
                                         FaceEngine (ArcFace 512-D ONNX)
                                                    │
                                                    ▼
                                         SimilarityService (Cosine Sim)
                                                    │
                                                    ▼
                                         [Stage 5.2: PostgreSQL + pgvector]
```

---

## 1. Prerequisites & Environment Setup

- **Python**: Version 3.10 or 3.11 (64-bit) recommended.
- **Package Manager**: Standard `pip` or high-speed `uv`.

### Step 1: Create Virtual Environment
Using `uv`:
```powershell
uv venv backend/.venv --python 3.11
```
Or using standard Python:
```powershell
python -m venv backend/.venv
```

### Step 2: Activate Environment & Install Dependencies
```powershell
# Windows PowerShell
.\backend\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r backend/requirements.txt
```

---

## 2. Model Licensing & Installation

### License Compliance
- **InsightFace Software Code**: MIT License.
- **Pretrained Model Weights (`buffalo_l` / `w600k_r50.onnx`)**: **Non-Commercial / Academic Research Use Only**.
  - **Permitted**: University lab research, classroom attendance proof-of-concept, personal development.
  - **Restricted**: Commercial deployment, SaaS distribution, or paid enterprise use requires a commercial license directly from InsightFace ([insightface.ai](https://insightface.ai)).
  - **Commercial Alternative**: For commercial production, substitute an open-source Apache-2.0 or MIT model (e.g., MobileFaceNet).

### Downloading the ONNX Model
1. In accordance with security practices, **large `.onnx` model files are ignored by Git** and must not be committed.
2. Download `w600k_r50.onnx` into the `backend/models/` directory:
   - File path: `backend/models/w600k_r50.onnx`
   - File size: ~171 MB
   - Input tensor: `[1, 3, 112, 112]` (float32)
   - Output tensor: `[1, 512]` (float32 feature embedding)

---

## 3. Starting the Local Server

From the `backend/` directory:

```powershell
cd backend
.\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. Testing Endpoints & Interactive Documentation

Once the server is running:

1. **Interactive Swagger UI**: Open your browser at [http://localhost:8000/docs](http://localhost:8000/docs).
2. **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc).
3. **Health Check**:
   ```powershell
   curl http://localhost:8000/api/v1/health
   ```
   Expected response:
   ```json
   {
     "status": "healthy",
     "project": "VisionAttend-AI Backend",
     "version": "0.5.1",
     "environment": "development",
     "model_loaded": false,
     "model_details": {
       "model_name": "w600k_r50.onnx",
       "file_exists": false,
       "license": "Non-Commercial / Academic Research (InsightFace buffalo_l)"
     },
     "database_status": "not_connected (scheduled for Stage 5.2)"
   }
   ```

---

## 5. Security & Authentication

Endpoints are secured using two distinct authentication schemes:

| Endpoint | Method | Required Header | Purpose |
| :--- | :--- | :--- | :--- |
| `/api/v1/health` | GET | *None* | Public monitoring & health status |
| `/api/v1/face/enroll` | POST | `Authorization: Bearer <ADMIN_API_KEY>` | Student face registration |
| `/api/v1/face/person/{id}` | GET/DELETE | `Authorization: Bearer <ADMIN_API_KEY>` | Student record & template management |
| `/api/v1/face/recognize` | POST | `X-Device-Api-Key: <DEVICE_API_KEY>` | Edge ESP32 device query |

Secrets are defined in `backend/.env` and must never be committed to Git.

---

## 6. Running the Test Suite

The test suite covers health check, image validation, 5-point alignment, cosine similarity math, security rejection, and model state reporting:

```powershell
# From project root
& "backend/.venv/Scripts/pytest.exe" backend/tests/ -v
```

---

## 7. Current Implementation Status & Roadmap

### What is Completed in Stage 5.1:
- [x] Full FastAPI application structure with startup/shutdown lifecycle.
- [x] Image quality validator (blur detection via Laplacian variance, lighting exposure check, resolution bounds).
- [x] 5-point facial landmark validator (geometric sanity & bounds checks).
- [x] 112×112 affine alignment engine.
- [x] 512-D ArcFace ONNX Runtime embedding extractor with L2 normalization.
- [x] Cosine similarity matching engine with configurable MATCH / AMBIGUOUS / UNKNOWN thresholds.
- [x] Security dependencies (Admin Bearer token and Device API Key authentication).
- [x] 31 comprehensive unit tests (100% passing).

### What is Intentionally Postponed to Stage 5.2+:
- **PostgreSQL & pgvector Integration (Stage 5.2)**: Database tables, HNSW vector indexing, persistent storage of student profiles and attendance records.
- **ESP32 Edge Integration (Stage 5.3)**: Firmware HTTP/HTTPS client sending face crops from the GOOUUU ESP32-S3-CAM to `/api/v1/face/recognize`.
- **Web Frontend Dashboard (Stage 6)**: Next.js administrative attendance dashboard.
