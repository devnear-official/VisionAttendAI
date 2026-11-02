"""Test authentication and authorization security."""

from fastapi.testclient import TestClient


def test_enrollment_unauthorized_missing_token(client: TestClient, sample_valid_face_image: bytes):
    response = client.post(
        "/api/v1/face/enroll",
        data={"student_id": "STU01", "name": "John Doe", "department": "CSE", "batch": "2022"},
        files=[("images", ("face.jpg", sample_valid_face_image, "image/jpeg"))],
    )
    assert response.status_code == 401
    assert "Admin Bearer token required" in response.json()["detail"]


def test_enrollment_forbidden_invalid_token(client: TestClient, sample_valid_face_image: bytes):
    response = client.post(
        "/api/v1/face/enroll",
        headers={"Authorization": "Bearer completely_wrong_secret_key"},
        data={"student_id": "STU01", "name": "John Doe", "department": "CSE", "batch": "2022"},
        files=[("images", ("face.jpg", sample_valid_face_image, "image/jpeg"))],
    )
    assert response.status_code == 403
    assert "Invalid administrative credentials" in response.json()["detail"]


def test_recognition_unauthorized_missing_device_key(client: TestClient, sample_valid_face_image: bytes):
    response = client.post(
        "/api/v1/face/recognize",
        data={"device_id": "ESP32-S3-CAM"},
        files={"image": ("face.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert response.status_code == 401
    assert "Missing X-Device-Api-Key" in response.json()["detail"]


def test_recognition_forbidden_invalid_device_key(client: TestClient, sample_valid_face_image: bytes):
    response = client.post(
        "/api/v1/face/recognize",
        headers={"X-Device-Api-Key": "invalid_esp32_device_key"},
        data={"device_id": "ESP32-S3-CAM"},
        files={"image": ("face.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert response.status_code == 403
    assert "Invalid device credentials" in response.json()["detail"]


def test_delete_person_unauthorized(client: TestClient):
    response = client.delete("/api/v1/face/person/p12345")
    assert response.status_code == 401


def test_get_person_unauthorized(client: TestClient):
    response = client.get("/api/v1/face/person/p12345")
    assert response.status_code == 401


def test_recognition_authorized_via_database_device(
    client: TestClient, db_session, sample_valid_face_image: bytes
):
    """Test that a device registered in PostgreSQL with bcrypt hash is successfully authorized."""
    import uuid
    from app.services.device_service import DeviceService
    from app.schemas.device import DeviceCreate

    code = f"esp32-test-{uuid.uuid4().hex[:6]}"
    raw_key = f"va_edge_secret_{uuid.uuid4().hex}"

    dev_in = DeviceCreate(
        device_name="Test Edge Cam",
        device_code=code,
        api_key=raw_key,
        location="Lab Entrance",
    )
    DeviceService.register_device(db_session, dev_in)

    response = client.post(
        "/api/v1/face/recognize",
        headers={"X-Device-Api-Key": raw_key},
        data={"device_id": code},
        files={"image": ("face.jpg", sample_valid_face_image, "image/jpeg")},
    )
    # Must NOT be 401 or 403
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        assert response.json()["status"] in ("MATCH", "UNKNOWN", "AMBIGUOUS")


def test_recognition_forbidden_inactive_database_device(
    client: TestClient, db_session, sample_valid_face_image: bytes
):
    """Test that an inactive device in PostgreSQL is rejected with 403 Forbidden."""
    import uuid
    from app.services.device_service import DeviceService
    from app.schemas.device import DeviceCreate

    code = f"esp32-inactive-{uuid.uuid4().hex[:6]}"
    raw_key = f"va_edge_inactive_{uuid.uuid4().hex}"

    dev_in = DeviceCreate(
        device_name="Inactive Edge Cam",
        device_code=code,
        api_key=raw_key,
        location="Storage",
    )
    device, _ = DeviceService.register_device(db_session, dev_in)
    device.is_active = False
    db_session.flush()

    response = client.post(
        "/api/v1/face/recognize",
        headers={"X-Device-Api-Key": raw_key},
        data={"device_id": code},
        files={"image": ("face.jpg", sample_valid_face_image, "image/jpeg")},
    )
    assert response.status_code == 403
    assert "Invalid device credentials" in response.json()["detail"]

