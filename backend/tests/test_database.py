"""Comprehensive database integration tests: PostgreSQL 17 + pgvector 0.8.6."""

import uuid
from datetime import date, datetime, timezone
import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.models import AttendanceRecord, Device, Student, StudentFaceEmbedding
from app.database.session import check_database_health
from app.schemas.device import DeviceCreate
from app.schemas.face import MatchStatus
from app.schemas.student import StudentCreate, StudentUpdate
from app.services.attendance_service import AttendanceService
from app.services.device_service import DeviceService
from app.services.embedding_service import EmbeddingService, EmbeddingValidationError
from app.services.student_service import StudentService
from app.services.vector_search_service import VectorSearchService


def test_database_connection_and_pgvector(db_session: Session):
    """Verify live PostgreSQL 17 connection and pgvector extension."""
    health = check_database_health()
    assert health["connected"] is True
    assert "PostgreSQL 17" in health["pg_version"]
    assert health["pgvector_installed"] is True
    assert health["pgvector_version"] == "0.8.6"

    # Verify vector math inside PostgreSQL
    res = db_session.execute(text("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector;")).scalar()
    assert pytest.approx(float(res), abs=1e-5) == 0.0


def test_student_crud_and_soft_delete(db_session: Session):
    """Test student creation, query, update, and soft deletion."""
    unique_id = f"TEST-{uuid.uuid4().hex[:6]}"
    student_in = StudentCreate(
        student_id=unique_id,
        full_name="Alice Test",
        department="Computer Science",
        batch="2024",
        email=f"{unique_id.lower()}@university.edu",
    )

    # 1. Create
    student = StudentService.create_student(db_session, student_in)
    assert student.id is not None
    assert student.student_id == unique_id
    assert student.status == "active"
    assert student.deleted_at is None

    # 2. Read
    fetched = StudentService.get_by_student_id(db_session, unique_id)
    assert fetched is not None
    assert fetched.full_name == "Alice Test"

    # 3. Update
    updated = StudentService.update_student(
        db_session, unique_id, StudentUpdate(full_name="Alice Updated", department="Software Engineering")
    )
    assert updated is not None
    assert updated.full_name == "Alice Updated"
    assert updated.department == "Software Engineering"

    # 4. Soft Delete
    deleted = StudentService.soft_delete_student(db_session, unique_id)
    assert deleted is not None
    assert deleted.status == "inactive"
    assert deleted.deleted_at is not None

    # Normal lookup should NOT return soft-deleted student
    assert StudentService.get_by_student_id(db_session, unique_id, include_deleted=False) is None

    # Lookup with include_deleted=True SHOULD return it
    assert StudentService.get_by_student_id(db_session, unique_id, include_deleted=True) is not None


def test_embedding_validation_and_storage(db_session: Session, sample_normalized_embedding_512: np.ndarray):
    """Test vector dimension checks, finiteness, L2 normalization, and storage."""
    # 1. Valid 512-D vector passes
    validated = EmbeddingService.validate_embedding(sample_normalized_embedding_512)
    assert validated.shape == (512,)

    # 2. Invalid dimensions fail
    invalid_dim = np.ones(128, dtype=np.float32)
    with pytest.raises(EmbeddingValidationError, match="must have exactly 512 dimensions"):
        EmbeddingService.validate_embedding(invalid_dim)

    # 3. NaN or Inf fails
    nan_vec = np.copy(sample_normalized_embedding_512)
    nan_vec[10] = np.nan
    with pytest.raises(EmbeddingValidationError, match="contains NaN or Infinite"):
        EmbeddingService.validate_embedding(nan_vec)

    # 4. Unnormalized vector fails
    unnormalized = sample_normalized_embedding_512 * 5.0
    with pytest.raises(EmbeddingValidationError, match="not L2-normalized"):
        EmbeddingService.validate_embedding(unnormalized)

    # 5. Store embeddings for student
    unique_id = f"TEST-{uuid.uuid4().hex[:6]}"
    student = StudentService.create_student(
        db_session, StudentCreate(student_id=unique_id, full_name="Bob Embedding Test")
    )

    records = EmbeddingService.store_student_embeddings(
        db_session, student.id, [sample_normalized_embedding_512]
    )
    assert len(records) == 1
    assert records[0].student_id == student.id
    assert records[0].is_active is True
    assert records[0].embedding.shape == (512,)


def test_pgvector_similarity_search(db_session: Session):
    """Test cosine similarity search in PostgreSQL + pgvector using HNSW index."""
    # Create two students with distinct 512-D vectors
    stu1_id = f"STU-{uuid.uuid4().hex[:6]}"
    stu2_id = f"STU-{uuid.uuid4().hex[:6]}"

    student1 = StudentService.create_student(
        db_session, StudentCreate(student_id=stu1_id, full_name="Candidate One")
    )
    student2 = StudentService.create_student(
        db_session, StudentCreate(student_id=stu2_id, full_name="Candidate Two")
    )

    # Create target vector and close vector for student1
    base_vec = np.zeros(512, dtype=np.float32)
    base_vec[0] = 1.0  # unit vector along dim 0

    close_vec = np.zeros(512, dtype=np.float32)
    close_vec[0] = 0.95
    close_vec[1] = 0.3122499  # norm ~ 1.0, dot product with base_vec ~ 0.95
    close_vec /= np.linalg.norm(close_vec)

    # Orthogonal vector for student2
    ortho_vec = np.zeros(512, dtype=np.float32)
    ortho_vec[50] = 1.0

    EmbeddingService.store_student_embeddings(db_session, student1.id, [close_vec])
    EmbeddingService.store_student_embeddings(db_session, student2.id, [ortho_vec])

    # Search with base_vec: should match student1
    status, score, matched = VectorSearchService.search_closest_face(
        db_session, query_embedding=base_vec, match_thr=0.65, ambiguous_thr=0.50
    )

    assert status == MatchStatus.MATCH
    assert matched is not None
    assert matched.student_id == stu1_id
    assert score >= 0.90

    # Search with orthogonal vector: student2 matches
    status2, score2, matched2 = VectorSearchService.search_closest_face(
        db_session, query_embedding=ortho_vec, match_thr=0.65, ambiguous_thr=0.50
    )
    assert status2 == MatchStatus.MATCH
    assert matched2.student_id == stu2_id
    assert pytest.approx(score2, abs=1e-3) == 1.0

    # Search with unrelated random vector: should be UNKNOWN
    random_vec = np.zeros(512, dtype=np.float32)
    random_vec[200] = 1.0
    status3, score3, matched3 = VectorSearchService.search_closest_face(
        db_session, query_embedding=random_vec, match_thr=0.65, ambiguous_thr=0.50
    )
    assert status3 == MatchStatus.UNKNOWN
    assert matched3 is None


def test_attendance_and_duplicate_prevention(db_session: Session):
    """Test attendance insertion, snapshot preservation, and duplicate check-in prevention."""
    unique_id = f"ATT-{uuid.uuid4().hex[:6]}"
    student = StudentService.create_student(
        db_session, StudentCreate(student_id=unique_id, full_name="Charlie Attendance")
    )

    today = date.today()
    check_time = datetime.now(timezone.utc)

    # 1. First check-in: succeeds
    rec1, was_new = AttendanceService.record_attendance(
        db_session,
        student=student,
        confidence=0.89,
        method="face_recognition",
        status="present",
        check_in_time=check_time,
    )
    assert was_new is True
    assert rec1.student_id == student.id
    assert rec1.student_id_snapshot == unique_id
    assert rec1.student_name_snapshot == "Charlie Attendance"
    assert rec1.attendance_date == today

    # 2. Second check-in on the same date: detected as duplicate
    rec2, was_new2 = AttendanceService.record_attendance(
        db_session,
        student=student,
        confidence=0.92,
        check_in_time=check_time,
    )
    assert was_new2 is False
    assert rec2.id == rec1.id  # Returns existing record without duplicate insertion


def test_historical_attendance_preservation_on_student_deletion(db_session: Session):
    """Verify attendance history is preserved with snapshots even if student is deleted."""
    unique_id = f"DEL-{uuid.uuid4().hex[:6]}"
    student = StudentService.create_student(
        db_session, StudentCreate(student_id=unique_id, full_name="David History")
    )

    # Record attendance
    rec, was_new = AttendanceService.record_attendance(
        db_session, student=student, confidence=0.88
    )
    assert was_new is True

    # Soft delete student
    StudentService.soft_delete_student(db_session, unique_id)

    # Attendance record MUST remain intact with snapshots
    fetched_rec = AttendanceService.get_record_by_id(db_session, rec.id)
    assert fetched_rec is not None
    assert fetched_rec.student_id_snapshot == unique_id
    assert fetched_rec.student_name_snapshot == "David History"


def test_device_registration_and_authentication(db_session: Session):
    """Test secure device API key hashing and constant-time authentication."""
    code = f"DEV-{uuid.uuid4().hex[:6]}"
    raw_key = f"secret_key_{uuid.uuid4().hex}"

    dev_in = DeviceCreate(
        device_name="Main Gate S3 Camera",
        device_code=code,
        api_key=raw_key,
        location="Campus Gate 1",
    )

    # 1. Register device
    device = DeviceService.register_device(db_session, dev_in)
    assert device.id is not None
    assert device.device_code == code
    # API key must NOT be stored in plaintext
    assert device.api_key_hash != raw_key
    assert "$2b$" in device.api_key_hash  # bcrypt hash format

    # 2. Authenticate with correct key
    authenticated = DeviceService.authenticate_device(db_session, code, raw_key)
    assert authenticated is not None
    assert authenticated.device_code == code
    assert authenticated.last_seen_at is not None

    # 3. Authenticate with wrong key: fails
    failed = DeviceService.authenticate_device(db_session, code, "wrong_password_attempt")
    assert failed is None
