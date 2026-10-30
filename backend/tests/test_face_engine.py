"""Test face engine status, unavailable behavior, and API contract."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.services.face_engine import FaceRecognitionEngine, ModelNotAvailableError


def test_face_engine_uninitialized_state():
    engine = FaceRecognitionEngine()
    status = engine.get_status_details()

    assert "model_name" in status
    assert "is_loaded" in status
    assert "license" in status
    assert "Non-Commercial" in status["license"]


def test_face_engine_extract_raises_when_not_loaded():
    engine = FaceRecognitionEngine()
    dummy_face = np.full((112, 112, 3), 128, dtype=np.uint8)

    with pytest.raises(ModelNotAvailableError, match="not loaded"):
        engine.extract_embedding(dummy_face)


def test_enrollment_route_returns_501_when_authorized(
    client: TestClient,
    admin_headers: dict,
    sample_valid_face_image: bytes
):
    # Tests that when authorized, the route does NOT return fake success or crash,
    # but cleanly reports 503 (model missing) or 501 (database scheduled for Stage 5.2).
    response = client.post(
        "/api/v1/face/enroll",
        headers=admin_headers,
        data={"student_id": "STU01", "name": "John Doe", "department": "CSE", "batch": "2022"},
        files=[("images", ("face.jpg", sample_valid_face_image, "image/jpeg"))],
    )
    # Either 503 (model weight file not in repo) or 501 (Stage 5.2 database commitment)
    assert response.status_code in [501, 503]
    if response.status_code == 503:
        assert "Face recognition model is not loaded" in response.json()["detail"]
    elif response.status_code == 501:
        assert "Stage 5.2" in response.json()["detail"]


def test_recognition_route_returns_501_or_503_when_authorized(
    client: TestClient,
    device_headers: dict,
    sample_valid_face_image: bytes
):
    response = client.post(
        "/api/v1/face/recognize",
        headers=device_headers,
        data={"device_id": "ESP32-S3-CAM"},
        files={"image": ("face.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert response.status_code in [501, 503]
