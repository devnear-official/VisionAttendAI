"""Test health endpoint with PostgreSQL and pgvector diagnostics."""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["project"] == "VisionAttend-AI Backend"
    assert data["version"] == "0.5.2"
    assert "environment" in data
    assert "model_loaded" in data
    assert isinstance(data["model_details"], dict)
    assert "license" in data["model_details"]

    # Stage 5.2: Database health integration
    assert "database" in data
    db_info = data["database"]
    assert db_info["connected"] is True
    assert "pg_version" in db_info
    assert db_info["pgvector_installed"] is True
    assert "0.8" in db_info["pgvector_version"]


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "/docs" in data["docs"]
