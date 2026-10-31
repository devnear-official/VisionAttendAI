"""Stage 5.4: End-to-end real face enrollment, recognition, attendance & threshold validation tests."""

import os
from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AttendanceRecord, Student, StudentFaceEmbedding
from app.schemas.face import MatchStatus
from app.services.face_engine import face_engine
from app.services.similarity import SimilarityService


@pytest.fixture(scope="module")
def real_face_crops():
    """Load pre-cropped real face images from tests/data/crops/."""
    crops_dir = Path(__file__).parent / "data" / "crops"
    assert crops_dir.exists(), "tests/data/crops directory must exist for Stage 5.4 validation."

    crops = {}
    for fname in ["person1_1.jpg", "person1_2.jpg", "person1_3.jpg", "person1_4.jpg", "person2_1.jpg", "person3_1.jpg"]:
        p = crops_dir / fname
        assert p.exists(), f"Required test image {fname} not found in {crops_dir}."
        with open(p, "rb") as f:
            crops[fname] = f.read()
    return crops


def test_stage54_real_enrollment_workflow(
    client: TestClient,
    admin_headers: dict,
    real_face_crops: dict,
    db_session: Session,
):
    """
    Task 2: Register a test student with 3 real photos.
    Verify:
      - HTTP 201 Created
      - Exact 512-D normalized embeddings saved to PostgreSQL
      - Foreign key relationships
      - Duplicate enrollment prevention
    """
    test_student_id = "STU-STAGE54-001"
    test_name = "Stage 5.4 Test Student"

    db = db_session

    # Ensure clean slate for test student
    existing = db.execute(select(Student).where(Student.student_id == test_student_id)).scalar_one_or_none()
    if existing:
        db.query(AttendanceRecord).filter(AttendanceRecord.student_id == existing.id).delete()
        db.query(StudentFaceEmbedding).filter(StudentFaceEmbedding.student_id == existing.id).delete()
        db.delete(existing)
        db.commit()

    # 1. Enroll with 3 real images (person1_1, person1_2, person1_3)
    files = [
        ("images", ("p1_1.jpg", real_face_crops["person1_1.jpg"], "image/jpeg")),
        ("images", ("p1_2.jpg", real_face_crops["person1_2.jpg"], "image/jpeg")),
        ("images", ("p1_3.jpg", real_face_crops["person1_3.jpg"], "image/jpeg")),
    ]
    data = {
        "student_id": test_student_id,
        "name": test_name,
        "department": "Computer Science & Engineering",
        "batch": "2024",
        "email": "test.stage54@university.edu",
    }

    response = client.post("/api/v1/face/enroll", headers=admin_headers, data=data, files=files)
    assert response.status_code == 201, f"Enrollment failed: {response.text}"
    resp_data = response.json()
    assert resp_data["status"] == "success"
    assert resp_data["student_id"] == test_student_id
    assert resp_data["embeddings_count"] == 3

    # 2. Verify database records and vector properties
    student = db.execute(select(Student).where(Student.student_id == test_student_id)).scalar_one_or_none()
    assert student is not None
    assert student.full_name == test_name
    assert student.status == "active"
    assert student.deleted_at is None

    embeddings = db.execute(
        select(StudentFaceEmbedding).where(StudentFaceEmbedding.student_id == student.id)
    ).scalars().all()
    assert len(embeddings) == 3

    for emb_rec in embeddings:
        assert emb_rec.is_active is True
        assert emb_rec.model_name == "w600k_r50.onnx"
        arr = np.array(emb_rec.embedding, dtype=np.float32)
        assert arr.shape == (512,), f"Embedding shape must be 512, got {arr.shape}"
        assert np.all(np.isfinite(arr)), "Embedding contains non-finite values"
        norm = np.linalg.norm(arr)
        assert np.isclose(norm, 1.0, atol=1e-3), f"Stored vector is not normalized (norm={norm})"

    # 3. Duplicate enrollment prevention:
    # Attempt to enroll another student (STU-STAGE54-002) using the same face
    dup_files = [("images", ("p1_1.jpg", real_face_crops["person1_1.jpg"], "image/jpeg"))]
    dup_data = {
        "student_id": "STU-STAGE54-002",
        "name": "Impostor Person",
        "department": "CSE",
        "batch": "2024",
    }
    dup_response = client.post("/api/v1/face/enroll", headers=admin_headers, data=dup_data, files=dup_files)
    assert dup_response.status_code == 400, "Duplicate enrollment should return HTTP 400"
    assert "Duplicate face detected" in dup_response.json()["detail"]


def test_stage54_real_recognition_and_attendance(
    client: TestClient,
    device_headers: dict,
    admin_headers: dict,
    real_face_crops: dict,
    db_session: Session,
):
    """
    Tasks 3 & 5: Real recognition and attendance lifecycle.
    Verify:
      - Enrolls student STU-STAGE54-001 with 3 photos
      - Unseen photograph of enrolled student matches with high confidence (> 0.65)
      - Attendance record created on first check-in
      - Duplicate attendance prevented on second check-in (same calendar date)
      - Impostor photograph returns UNKNOWN and records no attendance
      - Invalid/blurry image returns HTTP 400
      - Historical attendance preserved when student is soft-deleted
    """
    db = db_session
    test_student_id = "STU-STAGE54-REC"
    test_name = "Stage 5.4 Recognition Student"

    # Enroll student STU-STAGE54-REC with 3 real images
    enroll_files = [
        ("images", ("p1_1.jpg", real_face_crops["person1_1.jpg"], "image/jpeg")),
        ("images", ("p1_2.jpg", real_face_crops["person1_2.jpg"], "image/jpeg")),
        ("images", ("p1_3.jpg", real_face_crops["person1_3.jpg"], "image/jpeg")),
    ]
    enroll_data = {
        "student_id": test_student_id,
        "name": test_name,
        "department": "CSE",
        "batch": "2024",
    }
    enroll_resp = client.post("/api/v1/face/enroll", headers=admin_headers, data=enroll_data, files=enroll_files)
    assert enroll_resp.status_code == 201, f"Enrollment failed: {enroll_resp.text}"

    # 1. Query with UNSEEN photograph of enrolled student (person1_4.jpg)
    rec_files = {"image": ("query.jpg", real_face_crops["person1_4.jpg"], "image/jpeg")}
    rec_data = {"device_id": "ESP32-S3-CAM"}

    rec_response = client.post("/api/v1/face/recognize", headers=device_headers, data=rec_data, files=rec_files)
    assert rec_response.status_code == 200, f"Recognition failed: {rec_response.text}"
    result = rec_response.json()

    assert result["status"] == MatchStatus.MATCH.value
    assert result["student_id"] == test_student_id
    assert result["confidence"] >= 0.65, f"Expected high confidence, got {result['confidence']}"
    assert result["attendance_recorded"] is True
    assert result["already_checked_in"] is False
    assert result["attendance_id"] is not None
    attendance_id_1 = result["attendance_id"]

    # Verify attendance record in database
    student = db.execute(select(Student).where(Student.student_id == test_student_id)).scalar_one()
    att_rec = db.execute(select(AttendanceRecord).where(AttendanceRecord.student_id == student.id)).scalar_one_or_none()
    assert att_rec is not None
    assert str(att_rec.id) == attendance_id_1
    assert att_rec.student_id_snapshot == test_student_id
    assert att_rec.status == "present"

    # 2. Repeat check-in with same student on same day -> must prevent duplicate
    rec_response_2 = client.post("/api/v1/face/recognize", headers=device_headers, data=rec_data, files=rec_files)
    assert rec_response_2.status_code == 200
    result_2 = rec_response_2.json()
    assert result_2["status"] == MatchStatus.MATCH.value
    assert result_2["already_checked_in"] is True
    assert result_2["attendance_id"] == attendance_id_1

    # Ensure no second attendance record was created in the database
    att_count = db.execute(
        select(AttendanceRecord).where(AttendanceRecord.student_id == student.id)
    ).scalars().all()
    assert len(att_count) == 1, "Duplicate attendance record was created!"

    # 3. Query with an impostor face (person2_1.jpg)
    imp_files = {"image": ("impostor.jpg", real_face_crops["person2_1.jpg"], "image/jpeg")}
    imp_response = client.post("/api/v1/face/recognize", headers=device_headers, data=rec_data, files=imp_files)
    assert imp_response.status_code == 200
    imp_result = imp_response.json()
    assert imp_result["status"] == MatchStatus.UNKNOWN.value
    assert imp_result["confidence"] < 0.50, f"Impostor confidence should be < 0.50, got {imp_result['confidence']}"
    assert imp_result["attendance_recorded"] is False
    assert imp_result["person_id"] is None

    # 4. Query with a blurry image -> HTTP 400
    img_arr = cv2.imdecode(np.frombuffer(real_face_crops["person1_4.jpg"], np.uint8), cv2.IMREAD_COLOR)
    blurry = cv2.GaussianBlur(img_arr, (41, 41), 15)
    _, blurry_bytes = cv2.imencode(".jpg", blurry)
    blur_files = {"image": ("blurry.jpg", blurry_bytes.tobytes(), "image/jpeg")}

    blur_resp = client.post("/api/v1/face/recognize", headers=device_headers, data=rec_data, files=blur_files)
    assert blur_resp.status_code == 400
    assert "blurry" in blur_resp.json()["detail"].lower()

    # 5. Historical Attendance Preservation:
    # Delete student and verify attendance records are preserved
    del_resp = client.delete(f"/api/v1/face/person/{test_student_id}", headers=admin_headers)
    assert del_resp.status_code == 200

    # Verify student is soft-deleted
    db.expire_all()
    deleted_student = db.execute(
        select(Student).where(Student.student_id == test_student_id)
    ).scalar_one()
    assert deleted_student.status == "inactive"
    assert deleted_student.deleted_at is not None

    # Verify biometric templates are deactivated
    active_embeddings = db.execute(
        select(StudentFaceEmbedding).where(
            StudentFaceEmbedding.student_id == deleted_student.id,
            StudentFaceEmbedding.is_active.is_(True)
        )
    ).scalars().all()
    assert len(active_embeddings) == 0, "Biometric templates should be deactivated"

    # Verify historical attendance record is STILL PRESERVED in database
    preserved_attendance = db.execute(
        select(AttendanceRecord).where(AttendanceRecord.student_id == deleted_student.id)
    ).scalars().all()
    assert len(preserved_attendance) == 1, "Historical attendance record was deleted!"
    assert preserved_attendance[0].student_id_snapshot == test_student_id

    # Clean up test records after verification
    db.query(AttendanceRecord).filter(AttendanceRecord.student_id == deleted_student.id).delete()
    db.query(StudentFaceEmbedding).filter(StudentFaceEmbedding.student_id == deleted_student.id).delete()
    db.delete(deleted_student)
    db.commit()
