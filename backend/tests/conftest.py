"""Pytest fixtures and test setup with isolated database transactions."""

import sys
from pathlib import Path
from typing import Generator
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings
from app.database.session import SessionLocal, engine, get_db
from app.main import app

settings = get_settings()


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Isolated database session fixture that wraps each test inside an uncommitted
    transaction and rolls it back cleanly upon completion.
    No test records are persisted to development or production tables.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient fixture with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    """Headers for authorized administrative requests."""
    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


@pytest.fixture
def device_headers():
    """Headers for authorized edge device requests."""
    return {"X-Device-Api-Key": settings.DEVICE_API_KEY}


@pytest.fixture
def sample_normalized_embedding_512() -> np.ndarray:
    """Generate a valid, normalized 512-D float32 embedding vector."""
    np.random.seed(42)
    vec = np.random.randn(512).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec


@pytest.fixture
def sample_valid_face_image() -> bytes:
    """Generate a clean synthetic 160x160 face image with high contrast and sharp features."""
    img = np.full((160, 160, 3), 180, dtype=np.uint8)
    # Draw head oval
    cv2.ellipse(img, (80, 80), (50, 65), 0, 0, 360, (140, 120, 100), -1)
    # Draw high contrast eyes
    cv2.circle(img, (60, 65), 8, (255, 255, 255), -1)
    cv2.circle(img, (60, 65), 4, (20, 20, 20), -1)
    cv2.circle(img, (100, 65), 8, (255, 255, 255), -1)
    cv2.circle(img, (100, 65), 4, (20, 20, 20), -1)
    # Draw nose
    cv2.line(img, (80, 75), (80, 95), (60, 50, 40), 3)
    # Draw mouth
    cv2.rectangle(img, (65, 115), (95, 122), (40, 30, 90), -1)

    _, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return encoded.tobytes()


@pytest.fixture
def sample_valid_landmarks() -> list:
    """Standard 5-point landmarks for the 160x160 synthetic face."""
    return [
        [60.0, 65.0],   # Left eye
        [100.0, 65.0],  # Right eye
        [80.0, 85.0],   # Nose tip
        [65.0, 118.0],  # Left mouth corner
        [95.0, 118.0],  # Right mouth corner
    ]


@pytest.fixture
def sample_blurry_image() -> bytes:
    """Generate an extremely blurred image (low Laplacian variance)."""
    img = np.full((160, 160, 3), 128, dtype=np.uint8)
    img = cv2.GaussianBlur(img, (51, 51), 0)
    _, encoded = cv2.imencode(".jpg", img)
    return encoded.tobytes()
