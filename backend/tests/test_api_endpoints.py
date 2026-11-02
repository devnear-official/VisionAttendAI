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


def test_student_filtering_and_delete_api(client: TestClient, admin_headers: dict):
    tag = uuid.uuid4().hex[:6]
    sid1 = f"STU-F1-{tag}"
    sid2 = f"STU-F2-{tag}"

    client.post(
        "/api/v1/students",
        json={"student_id": sid1, "full_name": f"Alice Filter {tag}", "department": "CSE", "batch": "2025"},
        headers=admin_headers,
    )
    client.post(
        "/api/v1/students",
        json={"student_id": sid2, "full_name": f"Bob Filter {tag}", "department": "EEE", "batch": "2024"},
        headers=admin_headers,
    )

    # Search filter
    res_search = client.get(f"/api/v1/students?search={sid1}", headers=admin_headers)
    assert res_search.status_code == 200
    assert any(s["student_id"] == sid1 for s in res_search.json()["students"])
    assert not any(s["student_id"] == sid2 for s in res_search.json()["students"])

    # Department filter
    res_dept = client.get(f"/api/v1/students?department=EEE", headers=admin_headers)
    assert res_dept.status_code == 200
    assert any(s["student_id"] == sid2 for s in res_dept.json()["students"])

    # Delete student
    res_del = client.delete(f"/api/v1/students/{sid1}", headers=admin_headers)
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "inactive"
    assert res_del.json()["deleted_at"] is not None


def test_attendance_csv_export_api(client: TestClient, admin_headers: dict, db_session: Session):
    tag = uuid.uuid4().hex[:6]
    sid = f"EXP-{tag}"
    student = StudentService.create_student(
        db_session, StudentCreate(student_id=sid, full_name=f"Export Student {tag}", department="CSE")
    )
    AttendanceService.record_attendance(db_session, student=student, confidence=0.89)

    res_csv = client.get(f"/api/v1/attendance/export?search={sid}", headers=admin_headers)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    text = res_csv.text
    assert "Record UUID,Date,Student ID,Student Name" in text
    assert sid in text


def test_analytics_reports_and_dashboard_api(client: TestClient, admin_headers: dict):
    res_dash = client.get("/api/v1/analytics/dashboard", headers=admin_headers)
    assert res_dash.status_code == 200
    dash_data = res_dash.json()
    assert "total_students" in dash_data
    assert "registered_face_templates" in dash_data
    assert "online_devices" in dash_data
    assert "attendance_trends" in dash_data

    res_rep = client.get("/api/v1/analytics/reports", headers=admin_headers)
    assert res_rep.status_code == 200
    rep_data = res_rep.json()
    assert "monthly_attendance_rate" in rep_data
    assert "mean_confidence" in rep_data
    assert "daily_trends" in rep_data


def test_device_heartbeat_admin_and_telemetry(client: TestClient, admin_headers: dict):
    res_hb = client.post("/api/v1/devices/heartbeat?device_code=esp32-cam-01", headers=admin_headers)
    assert res_hb.status_code == 200
    assert res_hb.json()["status"] == "success"


def test_delete_attendance_record_allows_recheckin(client: TestClient, admin_headers: dict, db_session: Session):
    tag = uuid.uuid4().hex[:6]
    sid = f"DEL-ATT-{tag}"
    student = StudentService.create_student(
        db_session, StudentCreate(student_id=sid, full_name=f"Recheckin Test {tag}", department="CSE")
    )

    # 1. First check-in
    rec, was_new = AttendanceService.record_attendance(db_session, student=student, confidence=0.88)
    assert was_new is True
    record_id = rec.id

    # Duplicate check on same day returns existing record
    _, dup_was_new = AttendanceService.record_attendance(db_session, student=student, confidence=0.90)
    assert dup_was_new is False

    # 2. Delete the attendance record via API
    res_del = client.delete(f"/api/v1/attendance/{record_id}", headers=admin_headers)
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "success"

    # Confirm it is gone from database
    check_deleted = AttendanceService.get_record_by_id(db_session, record_id)
    assert check_deleted is None

    # 3. New check-in for the same student on the same day now succeeds as NEW check-in
    rec_after, was_new_after = AttendanceService.record_attendance(db_session, student=student, confidence=0.92)
    assert was_new_after is True
    assert rec_after.id != record_id
