"""Test health endpoint."""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "VisionAttend-AI Backend"
    assert "version" in data
    assert "environment" in data
    assert "model_loaded" in data
    assert isinstance(data["model_details"], dict)
    assert "license" in data["model_details"]
    assert "not_connected" in data["database_status"]


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "/docs" in data["docs"]
