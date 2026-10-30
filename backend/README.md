# VisionAttend-AI — Local FastAPI Backend Foundation (Stage 5.2)

Welcome to the **VisionAttend-AI** backend service. This service provides biometric facial quality validation, 5-point landmark alignment, 512-dimensional ArcFace embedding extraction, and PostgreSQL 17 + pgvector 0.8.6 cosine similarity matching for the GOOUUU ESP32-S3-CAM edge camera.

---

## Architecture Overview (Stage 5.2)

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
                                         VectorSearchService (pgvector HNSW)
                                                    │
                                                    ▼
                                         [PostgreSQL 17 Database]
                                         - students
                                         - student_face_embeddings (VECTOR 512)
                                         - devices
                                         - attendance_records
```

---

## 1. Prerequisites & Environment Setup

- **Operating System**: Windows 10/11
- **Python**: Version 3.11.7 (64-bit)
- **Database**: PostgreSQL 17 (Local Windows Installation, Port 5432)
- **Vector Extension**: `pgvector` 0.8.6 (enabled in `visionattend` database)

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

## 2. PostgreSQL 17 & pgvector Setup

### Verify pgvector Extension
Connect via `psql` to verify the database and extension:
```powershell
psql -U postgres -d visionattend -h localhost -p 5432 -c "SELECT extname, extversion FROM pg_extension;"
```
Expected output:
```text
 extname | extversion 
---------+------------
 plpgsql | 1.0
 vector  | 0.8.6
```

### Environment Configuration (`.env`)
Create `backend/.env` (modeled after `.env.example`):
```ini
PROJECT_NAME="VisionAttend-AI Backend"
PROJECT_VERSION="0.5.2"
ENVIRONMENT="development"
DEBUG=true

HOST="0.0.0.0"
PORT=8000

CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"

ADMIN_API_KEY="dev_admin_secret_key_change_in_production"
DEVICE_API_KEY="esp32_device_secret_key_change_in_production"

MODEL_DIR="models"
FACE_RECOGNITION_MODEL_NAME="w600k_r50.onnx"
ONNX_EXECUTION_PROVIDER="CPUExecutionProvider"
ONNX_INTRA_OP_NUM_THREADS=4

SIMILARITY_MATCH_THRESHOLD=0.65
SIMILARITY_AMBIGUOUS_THRESHOLD=0.50

DATABASE_URL="postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/visionattend"
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=5
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_PRE_PING=true
```
> [!CAUTION]
> Never commit `.env` or real database credentials to Git repository history.

---

## 3. Database Migrations (Alembic)

Migrations manage the database schema versioning:

```powershell
cd backend

# Apply migrations to database:
.\.venv\Scripts\alembic.exe upgrade head

# Rollback migration if necessary:
.\.venv\Scripts\alembic.exe downgrade -1
```

### Database Tables and Indexes

1. **`students`**: Master student records with soft deletion (`deleted_at`).
   - Indexes: `idx_students_student_id`, `idx_students_deleted_at`, `idx_students_active_lookup`.
2. **`student_face_embeddings`**: Normalized 512-D vectors referencing `students.id`.
   - Index: `idx_student_face_embeddings_hnsw` (HNSW cosine similarity index: `m=16`, `ef_construction=64`).
3. **`devices`**: Edge cameras with bcrypt-hashed API keys (`api_key_hash`).
   - Indexes: `idx_devices_device_code`, `idx_devices_is_active`.
4. **`attendance_records`**: Immutable audit check-in records preserving snapshots (`student_id_snapshot`, `student_name_snapshot`).
   - Constraints: `uq_attendance_student_date` (avoids duplicate check-in on the same day).
   - Indexes: `idx_attendance_date`, `idx_attendance_snapshot`, `idx_attendance_device_id`.

---

## 4. Model Licensing & Installation

### License Compliance
- **InsightFace Software Code**: MIT License.
- **Pretrained Model Weights (`buffalo_l` / `w600k_r50.onnx`)**: **Non-Commercial / Academic Research Use Only**.
  - **Permitted**: University lab research, classroom attendance proof-of-concept, personal development.
  - **Restricted**: Commercial deployment or paid SaaS distribution requires a commercial license directly from InsightFace ([insightface.ai](https://insightface.ai)).
  - **Commercial Alternative**: For commercial production, substitute an open-source Apache-2.0 or MIT model (e.g., MobileFaceNet).

### Downloading the ONNX Model
1. Large `.onnx` model files are ignored by Git and must not be committed.
2. Download `w600k_r50.onnx` into the `backend/models/` directory:
   - File path: `backend/models/w600k_r50.onnx`
   - File size: ~171 MB
   - Input tensor: `[1, 3, 112, 112]` (float32)
   - Output tensor: `[1, 512]` (float32 feature embedding)

---

## 5. Starting the Local Server

From the `backend/` directory:

```powershell
cd backend
.\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 6. Testing Endpoints & Interactive Documentation

Once the server is running:

1. **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs).
2. **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc).
3. **Health Check**:
   ```powershell
   curl http://localhost:8000/api/v1/health
   ```
   Sample response:
   ```json
   {
     "status": "healthy",
     "project": "VisionAttend-AI Backend",
     "version": "0.5.2",
     "environment": "development",
     "model_loaded": false,
     "model_details": {
       "model_name": "w600k_r50.onnx",
       "file_exists": false,
       "license": "Non-Commercial / Academic Research (InsightFace buffalo_l)"
     },
     "database": {
       "connected": true,
       "pg_version": "PostgreSQL 17.11",
       "pgvector_installed": true,
       "pgvector_version": "0.8.6"
     }
   }
   ```

---

## 7. Security & API Endpoints

| Endpoint | Method | Required Header | Purpose |
| :--- | :--- | :--- | :--- |
| `/api/v1/health` | GET | *None* | Health & database diagnostics |
| `/api/v1/students` | POST, GET | `Authorization: Bearer <ADMIN_API_KEY>` | Register or list student profiles |
| `/api/v1/students/{id}` | GET, PATCH | `Authorization: Bearer <ADMIN_API_KEY>` | View or update student record |
| `/api/v1/face/enroll` | POST | `Authorization: Bearer <ADMIN_API_KEY>` | Biometric face enrollment with duplicate check |
| `/api/v1/face/person/{id}` | GET, DELETE | `Authorization: Bearer <ADMIN_API_KEY>` | View person or soft-delete biometric profile |
| `/api/v1/face/recognize` | POST | `X-Device-Api-Key: <DEVICE_API_KEY>` | Edge ESP32 recognition & check-in verification |
| `/api/v1/attendance` | GET | `Authorization: Bearer <ADMIN_API_KEY>` | Query immutable attendance records with filters |
| `/api/v1/attendance/{id}`| GET | `Authorization: Bearer <ADMIN_API_KEY>` | View single attendance record |

---

## 8. Running the Automated Test Suite

All 41 unit and integration tests run inside isolated transactions with automatic rollback:

```powershell
# From project root
& "backend/.venv/Scripts/pytest.exe" backend/tests/ -v
```

---

## 9. Common Connection Errors & Troubleshooting

1. **`FATAL: password authentication failed for user "postgres"`**:
   Verify that `DATABASE_URL` in `backend/.env` has the correct password.
2. **`psycopg.OperationalError: connection to server at "127.0.0.1", port 5432 failed`**:
   Check if the Windows service `postgresql-x64-17` is running (`Get-Service *postgres*`).
3. **`extension "vector" is not available`**:
   Ensure `vector.control` is present in `C:\Program Files\PostgreSQL\17\share\extension\`.
