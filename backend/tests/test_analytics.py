"""Tests for dashboard analytics and performance aggregation routes."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_dashboard_analytics_api_unauthorized(client: TestClient):
    """Test that unauthorized access without admin token is rejected."""
    res = client.get("/api/v1/analytics/dashboard")
    assert res.status_code == 401


def test_dashboard_analytics_api_success(client: TestClient, admin_headers: dict):
    """Test retrieving aggregated real-time dashboard summary."""
    res = client.get("/api/v1/analytics/dashboard", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()

    assert "total_active_students" in data
    assert "today_attendance_count" in data
    assert "unique_students_present" in data
    assert "attendance_rate" in data
    assert "departments" in data
    assert "recent_activity" in data
    assert isinstance(data["departments"], list)
    assert isinstance(data["recent_activity"], list)
