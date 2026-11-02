"""Test face engine status, ONNX inference, similarity, and API contract."""

import os
from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.services.face_engine import FaceRecognitionEngine, ModelNotAvailableError, face_engine
from app.services.similarity import SimilarityService


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


def test_face_engine_model_loaded_and_inference():
    """Verify that the official ArcFace model loads and produces a normalized 512-D float32 vector."""
    if not face_engine.is_loaded:
        face_engine.initialize()
    assert face_engine.is_loaded is True, "Face recognition model should be loaded in Stage 5.3"
    status = face_engine.get_status_details()
    assert status["is_loaded"] is True
    assert status["file_exists"] is True
    assert status["file_size_bytes"] > 100_000_000  # ~174 MB

    # Inference test with valid 112x112 image
    test_face = np.random.randint(0, 256, (112, 112, 3), dtype=np.uint8)
    embedding = face_engine.extract_embedding(test_face)

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32
    assert not np.isnan(embedding).any()
    assert not np.isinf(embedding).any()

    # Verify L2 normalization: ||v|| = 1.0
    norm = np.linalg.norm(embedding)
    assert np.isclose(norm, 1.0, atol=1e-5)


def test_enrollment_route_success_with_model(
    client: TestClient,
    admin_headers: dict,
    sample_valid_face_image: bytes
):
    """With real ArcFace loaded, enrollment endpoint creates a student and stores embedding."""
    response = client.post(
        "/api/v1/face/enroll",
        headers=admin_headers,
        data={
            "student_id": "TEST-ARCFACE-01",
            "name": "Jane ArcFace",
            "department": "CSE",
            "batch": "2023"
        },
        files=[("images", ("face.jpg", sample_valid_face_image, "image/jpeg"))],
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["student_id"] == "TEST-ARCFACE-01"
    assert data["embeddings_count"] >= 1


def test_recognition_route_success_with_model(
    client: TestClient,
    device_headers: dict,
    sample_valid_face_image: bytes
):
    """With real ArcFace loaded, recognition endpoint runs inference and searches vector DB."""
    response = client.post(
        "/api/v1/face/recognize",
        headers=device_headers,
        data={"device_id": "ESP32-S3-CAM"},
        files={"image": ("face.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "confidence" in data
    assert "inference_time_ms" in data
    assert data["inference_time_ms"] > 0


def test_routes_return_503_when_model_unloaded(
    client: TestClient,
    admin_headers: dict,
    device_headers: dict,
    sample_valid_face_image: bytes,
    monkeypatch
):
    """When model is unloaded/unavailable, endpoints return 503 instead of crashing or returning fake results."""
    monkeypatch.setattr(face_engine, "_is_loaded", False)

    # Enrollment route 503 check
    enroll_resp = client.post(
        "/api/v1/face/enroll",
        headers=admin_headers,
        data={"student_id": "STU503", "name": "Test Missing", "department": "CSE", "batch": "2022"},
        files=[("images", ("face.jpg", sample_valid_face_image, "image/jpeg"))],
    )
    assert enroll_resp.status_code == 503
    assert "Face recognition model is not loaded" in enroll_resp.json()["detail"]

    # Recognition route 503 check
    recog_resp = client.post(
        "/api/v1/face/recognize",
        headers=device_headers,
        data={"device_id": "ESP32-S3-CAM"},
        files={"image": ("face.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert recog_resp.status_code == 503
    assert "Face recognition model is not loaded" in recog_resp.json()["detail"]


def test_arcface_similarity_benchmark():
    """Verify distinct separation between same person vs different person similarity."""
    data_dir = Path(__file__).parent / "data"
    p1_a_path = data_dir / "person1_a.jpg"
    p1_b_path = data_dir / "person1_b.jpg"
    p2_a_path = data_dir / "person2_a.jpg"

    if not (p1_a_path.exists() and p1_b_path.exists() and p2_a_path.exists()):
        pytest.skip("Benchmark image assets not found in tests/data")

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def crop_face(path: Path) -> np.ndarray:
        img = cv2.imread(str(path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        assert len(faces) > 0, f"No face detected in {path.name}"
        x, y, w, h = faces[0]
        margin = int(w * 0.1)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(img.shape[1], x + w + margin)
        y2 = min(img.shape[0], y + h + margin)
        return cv2.resize(img[y1:y2, x1:x2], (112, 112))

    crop1_a = crop_face(p1_a_path)
    crop1_b = crop_face(p1_b_path)
    crop2_a = crop_face(p2_a_path)

    emb1_a = face_engine.extract_embedding(crop1_a)
    emb1_b = face_engine.extract_embedding(crop1_b)
    emb2_a = face_engine.extract_embedding(crop2_a)

    sim_same = SimilarityService.cosine_similarity(emb1_a, emb1_b)
    sim_diff = SimilarityService.cosine_similarity(emb1_a, emb2_a)

    # Same person should have high cosine similarity (> 0.50)
    assert sim_same > 0.50, f"Same person similarity unexpectedly low: {sim_same}"
    # Different persons should have low cosine similarity (< 0.35)
    assert sim_diff < 0.35, f"Different persons similarity unexpectedly high: {sim_diff}"
    # There must be a clear margin between same and different person
    assert (sim_same - sim_diff) > 0.40, f"Separation margin too small: {sim_same - sim_diff}"
