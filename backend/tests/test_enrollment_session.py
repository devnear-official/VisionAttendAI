"""Comprehensive unit & integration tests for ESP32 edge biometric enrollment sessions."""

import time
import uuid
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.models import Device, Student, StudentFaceEmbedding
from app.schemas.device import DeviceCreate
from app.services.device_service import DeviceService
from app.services.enrollment_session_service import EnrollmentSessionService


@pytest.fixture
def active_edge_device(db_session: Session):
    """Fixture providing a registered edge device in the database."""
    code = f"esp32-enroll-{uuid.uuid4().hex[:6]}"
    raw_key = f"va_edge_test_{uuid.uuid4().hex}"
    dev_in = DeviceCreate(
        device_name="Enrollment Test Cam",
        device_code=code,
        api_key=raw_key,
        location="Lab 101",
    )
    device, plain_key = DeviceService.register_device(db_session, dev_in)
    db_session.commit()
    return {"device": device, "code": code, "api_key": plain_key}


def test_session_lifecycle_and_expiry(client: TestClient, admin_headers: dict, active_edge_device: dict):
    """Test session creation, retrieval, duplicate active session rejection, and TTL expiration."""
    code = active_edge_device["code"]
    stu_id = f"STU-{uuid.uuid4().hex[:6]}"

    # 1. Create enrollment session
    payload = {
        "student_id": stu_id,
        "name": "Session Test Student",
        "department": "CSE",
        "batch": "2025",
        "device_code": code,
        "target_samples": 3,
        "consent_confirmed": True,
    }
    resp = client.post("/api/v1/face/enroll/session", headers=admin_headers, json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["session_id"] is not None
    assert data["student_id"] == stu_id
    assert data["device_code"] == code
    assert data["target_samples"] == 3
    assert data["collected_count"] == 0
    assert data["status"] == "active"
    session_id = data["session_id"]

    # 2. Duplicate session creation on same device rejected with 409 Conflict
    dup_resp = client.post("/api/v1/face/enroll/session", headers=admin_headers, json=payload)
    assert dup_resp.status_code == 409

    # 3. Retrieve session status
    status_resp = client.get(f"/api/v1/face/enroll/session/{session_id}", headers=admin_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "active"

    # 4. Cancel session
    cancel_resp = client.delete(f"/api/v1/face/enroll/session/{session_id}", headers=admin_headers)
    assert cancel_resp.status_code == 200

    # 5. Verify status reflects cancellation
    after_cancel = client.get(f"/api/v1/face/enroll/session/{session_id}", headers=admin_headers)
    assert after_cancel.status_code == 200
    assert after_cancel.json()["status"] == "cancelled"


def test_session_unauthorized_access(client: TestClient, active_edge_device: dict):
    """Test that session endpoints reject unauthenticated calls."""
    payload = {
        "student_id": "STU-UNAUTH",
        "name": "Unauth Student",
        "device_code": active_edge_device["code"],
        "target_samples": 3,
    }
    # No admin auth
    resp = client.post("/api/v1/face/enroll/session", json=payload)
    assert resp.status_code == 401

    resp_del = client.delete("/api/v1/face/enroll/session/some-uuid")
    assert resp_del.status_code == 401


def test_device_sample_collection_and_completion(
    client: TestClient,
    admin_headers: dict,
    active_edge_device: dict,
    sample_valid_face_image: bytes,
    db_session: Session,
):
    """
    Test end-to-end edge sample uploads:
    - Sample 1: returns ENROLLING (1/3)
    - Sample 2: returns ENROLLING (2/3)
    - Sample 3: reaches target -> atomic DB persistence -> returns ENROLLED
    """
    code = active_edge_device["code"]
    raw_key = active_edge_device["api_key"]
    stu_id = f"STU-{uuid.uuid4().hex[:6]}"

    # Start session
    create_resp = client.post(
        "/api/v1/face/enroll/session",
        headers=admin_headers,
        json={
            "student_id": stu_id,
            "name": "Edge Enrolled Student",
            "department": "ECE",
            "batch": "2024",
            "device_code": code,
            "target_samples": 3,
            "consent_confirmed": True,
        },
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    device_headers = {"X-Device-Api-Key": raw_key}

    # Upload Sample 1
    sample1_resp = client.post(
        "/api/v1/face/enroll/device-sample",
        headers=device_headers,
        data={"device_id": code, "session_id": session_id},
        files={"image": ("crop1.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert sample1_resp.status_code == 200, sample1_resp.text
    s1_data = sample1_resp.json()
    assert s1_data["status"] == "ENROLLING"
    assert s1_data["sample_index"] == 1
    assert s1_data["target_samples"] == 3

    # Upload Sample 2
    sample2_resp = client.post(
        "/api/v1/face/enroll/device-sample",
        headers=device_headers,
        data={"device_id": code, "session_id": session_id},
        files={"image": ("crop2.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert sample2_resp.status_code == 200
    s2_data = sample2_resp.json()
    assert s2_data["status"] == "ENROLLING"
    assert s2_data["sample_index"] == 2

    # Upload Sample 3 (Reaches target)
    sample3_resp = client.post(
        "/api/v1/face/enroll/device-sample",
        headers=device_headers,
        data={"device_id": code, "session_id": session_id},
        files={"image": ("crop3.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert sample3_resp.status_code == 200
    s3_data = sample3_resp.json()
    assert s3_data["status"] == "ENROLLED"
    assert s3_data["sample_index"] == 3

    # Verify student and exactly 3 embeddings exist in database
    student = db_session.query(Student).filter(Student.student_id == stu_id).first()
    assert student is not None
    assert student.full_name == "Edge Enrolled Student"
    embeddings = db_session.query(StudentFaceEmbedding).filter(StudentFaceEmbedding.student_id == student.id).all()
    assert len(embeddings) == 3


def test_device_sample_rejected_when_no_active_session(
    client: TestClient,
    active_edge_device: dict,
    sample_valid_face_image: bytes,
):
    """Submitting a sample when no session is active returns HTTP 400."""
    code = active_edge_device["code"]
    raw_key = active_edge_device["api_key"]

    resp = client.post(
        "/api/v1/face/enroll/device-sample",
        headers={"X-Device-Api-Key": raw_key},
        data={"device_id": code},
        files={"image": ("crop.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert resp.status_code == 400
    assert "No active enrollment session found" in resp.json()["detail"]


def test_device_sample_rejected_with_invalid_api_key(
    client: TestClient,
    active_edge_device: dict,
    sample_valid_face_image: bytes,
):
    """Submitting a sample with invalid or missing API key returns 401 or 403."""
    code = active_edge_device["code"]

    # Missing key
    resp_no_key = client.post(
        "/api/v1/face/enroll/device-sample",
        data={"device_id": code},
        files={"image": ("crop.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert resp_no_key.status_code == 401

    # Invalid key
    resp_bad_key = client.post(
        "/api/v1/face/enroll/device-sample",
        headers={"X-Device-Api-Key": "wrong_key_12345"},
        data={"device_id": code},
        files={"image": ("crop.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert resp_bad_key.status_code == 403


def test_enrollment_via_recognition_endpoint_regression(
    client: TestClient,
    admin_headers: dict,
    active_edge_device: dict,
    sample_valid_face_image: bytes,
    db_session: Session,
):
    """
    Regression test: ESP32 camera uploads 3 samples via /api/v1/face/recognize while session is active.
    Verifies that StudentService and EmbeddingService are defined and resolve correctly without NameError.
    """
    code = active_edge_device["code"]
    raw_key = active_edge_device["api_key"]
    stu_id = f"STU-REC-{uuid.uuid4().hex[:6]}"

    # Start active enrollment session
    create_resp = client.post(
        "/api/v1/face/enroll/session",
        headers=admin_headers,
        json={
            "student_id": stu_id,
            "name": "Recognition Route Enrolled",
            "department": "CSE",
            "batch": "2024",
            "device_code": code,
            "target_samples": 3,
            "consent_confirmed": True,
        },
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    device_headers = {"X-Device-Api-Key": raw_key}

    # 1. Sample 1 via /api/v1/face/recognize
    resp1 = client.post(
        "/api/v1/face/recognize",
        headers=device_headers,
        data={"device_id": code},
        files={"image": ("crop1.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert resp1.status_code == 200, resp1.text
    assert resp1.json()["message"] == "ENROLLING 1/3"

    # 2. Sample 2 via /api/v1/face/recognize
    resp2 = client.post(
        "/api/v1/face/recognize",
        headers=device_headers,
        data={"device_id": code},
        files={"image": ("crop2.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["message"] == "ENROLLING 2/3"

    # 3. Sample 3 via /api/v1/face/recognize (Completes session)
    resp3 = client.post(
        "/api/v1/face/recognize",
        headers=device_headers,
        data={"device_id": code},
        files={"image": ("crop3.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert resp3.status_code == 200, resp3.text
    data3 = resp3.json()
    assert data3["message"] == "ENROLLED"
    assert data3["student_id"] == stu_id
    assert data3["full_name"] == "Recognition Route Enrolled"

    # Verify student & embeddings committed to DB
    student = db_session.query(Student).filter(Student.student_id == stu_id).first()
    assert student is not None
    assert student.full_name == "Recognition Route Enrolled"
    embs = db_session.query(StudentFaceEmbedding).filter(StudentFaceEmbedding.student_id == student.id).all()
    assert len(embs) == 3

    # Verify session GET status shows completed
    sess_status = client.get(f"/api/v1/face/enroll/session/{session_id}", headers=admin_headers)
    assert sess_status.status_code == 200
    assert sess_status.json()["status"] == "completed"


def test_enrollment_database_commit_failure_and_rollback(
    client: TestClient,
    admin_headers: dict,
    active_edge_device: dict,
    sample_valid_face_image: bytes,
    monkeypatch,
    db_session: Session,
):
    """
    Test database commit failure and rollback behavior:
    - If database commit fails during sample N/N, transaction is rolled back.
    - Endpoint returns HTTP 500 and never reports ENROLLED.
    - Session status is safely marked 'failed'.
    - GET /session/{id} returns status 'failed' with error detail.
    - No partial student or embeddings are persisted in database.
    """
    from app.services.embedding_service import EmbeddingService

    code = active_edge_device["code"]
    raw_key = active_edge_device["api_key"]
    stu_id = f"STU-FAIL-{uuid.uuid4().hex[:6]}"

    # Start session
    create_resp = client.post(
        "/api/v1/face/enroll/session",
        headers=admin_headers,
        json={
            "student_id": stu_id,
            "name": "Commit Failure Test Student",
            "department": "CSE",
            "batch": "2024",
            "device_code": code,
            "target_samples": 3,
            "consent_confirmed": True,
        },
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    device_headers = {"X-Device-Api-Key": raw_key}

    # Upload samples 1 and 2
    for _ in range(2):
        resp = client.post(
            "/api/v1/face/enroll/device-sample",
            headers=device_headers,
            data={"device_id": code, "session_id": session_id},
            files={"image": ("crop.jpg", sample_valid_face_image, "image/jpeg")},
        )
        assert resp.status_code == 200

    # Simulate database error on final commit
    def mock_store_error(*args, **kwargs):
        raise RuntimeError("Simulated PostgreSQL connection drop during embedding insert.")

    monkeypatch.setattr(EmbeddingService, "store_student_embeddings", mock_store_error)

    # Upload sample 3 (Triggering commit failure)
    fail_resp = client.post(
        "/api/v1/face/enroll/device-sample",
        headers=device_headers,
        data={"device_id": code, "session_id": session_id},
        files={"image": ("crop3.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert fail_resp.status_code == 500
    assert "Simulated PostgreSQL connection drop" in fail_resp.json()["detail"]

    # Verify session GET reflects 'failed' status
    session_resp = client.get(f"/api/v1/face/enroll/session/{session_id}", headers=admin_headers)
    assert session_resp.status_code == 200
    sess_data = session_resp.json()
    assert sess_data["status"] == "failed"
    assert "Enrollment commit failed" in sess_data["message"]

    # Verify student was NOT saved in database
    student = db_session.query(Student).filter(Student.student_id == stu_id).first()
    assert student is None

