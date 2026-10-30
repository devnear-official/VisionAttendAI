"""Tests for student and attendance REST API endpoints."""

import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.student import StudentCreate
from app.services.attendance_service import AttendanceService
from app.services.student_service import StudentService


def test_create_and_get_student_api(client: TestClient, admin_headers: dict):
    student_id = f"API-{uuid.uuid4().hex[:6]}"
    payload = {
        "student_id": student_id,
        "full_name": "API Test Student",
        "email": f"{student_id.lower()}@campus.edu",
        "department": "Electrical Engineering",
        "batch": "2023",
        "phone": "+1234567890",
    }

    # 1. Create student
    res = client.post("/api/v1/students", json=payload, headers=admin_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["student_id"] == student_id
    assert data["full_name"] == "API Test Student"
    assert data["status"] == "active"

    # 2. Duplicate student ID rejected
    res_dup = client.post("/api/v1/students", json=payload, headers=admin_headers)
    assert res_dup.status_code == 400
    assert "already registered" in res_dup.json()["detail"]

    # 3. Get student by student_id
    res_get = client.get(f"/api/v1/students/{student_id}", headers=admin_headers)
    assert res_get.status_code == 200
    assert res_get.json()["student_id"] == student_id

    # 4. Patch student
    res_patch = client.patch(
        f"/api/v1/students/{student_id}",
        json={"full_name": "API Student Renamed", "department": "Robotics"},
        headers=admin_headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["full_name"] == "API Student Renamed"
    assert res_patch.json()["department"] == "Robotics"

    # 5. List students
    res_list = client.get("/api/v1/students", headers=admin_headers)
    assert res_list.status_code == 200
    assert res_list.json()["total"] >= 1


def test_delete_and_get_person_api(client: TestClient, admin_headers: dict, db_session: Session):
    student_id = f"PER-{uuid.uuid4().hex[:6]}"
    student = StudentService.create_student(
        db_session, StudentCreate(student_id=student_id, full_name="Person API Test")
    )

    # 1. Get person
    res_get = client.get(f"/api/v1/face/person/{student_id}", headers=admin_headers)
    assert res_get.status_code == 200
    assert res_get.json()["student_id"] == student_id
    assert res_get.json()["is_active"] is True

    # 2. Delete (soft-delete) person
    res_del = client.delete(f"/api/v1/face/person/{student_id}", headers=admin_headers)
    assert res_del.status_code == 200
    assert "deactivated" in res_del.json()["message"]

    # 3. Get person after deactivation returns 404
    res_get_del = client.get(f"/api/v1/face/person/{student_id}", headers=admin_headers)
    assert res_get_del.status_code == 404


def test_attendance_api(client: TestClient, admin_headers: dict, db_session: Session):
    student_id = f"ATTAPI-{uuid.uuid4().hex[:6]}"
    student = StudentService.create_student(
        db_session, StudentCreate(student_id=student_id, full_name="Attendance API Test")
    )

    record, was_new = AttendanceService.record_attendance(
        db_session, student=student, confidence=0.91
    )
    assert was_new is True

    # 1. List attendance
    res_list = client.get("/api/v1/attendance", headers=admin_headers)
    assert res_list.status_code == 200
    data = res_list.json()
    assert data["total"] >= 1

    # 2. Filter by student ID
    res_filtered = client.get(
        f"/api/v1/attendance?student_id={student_id}", headers=admin_headers
    )
    assert res_filtered.status_code == 200
    records = res_filtered.json()["records"]
    assert len(records) == 1
    assert records[0]["student_id_snapshot"] == student_id

    # 3. Get record by ID
    res_single = client.get(f"/api/v1/attendance/{record.id}", headers=admin_headers)
    assert res_single.status_code == 200
    assert res_single.json()["student_id_snapshot"] == student_id
