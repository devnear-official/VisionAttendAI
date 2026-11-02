"""End-to-End Real-World Scenario Verification Test Suite.

Verifies the 10 real-world scenarios specified in the VisionAttend-AI integration requirements:
1. Create a new student and confirm it appears in Students.
2. Enroll the student's face and confirm enrollment status updates.
3. Recognize the student using ESP32.
4. Confirm attendance appears in Live Attendance.
5. Confirm the same record appears in Attendance History.
6. Confirm Overview statistics update.
7. Confirm Reports reflect the new attendance.
8. Confirm unknown faces do not create attendance.
9. Confirm duplicate check-in does not create another record.
10. Confirm device heartbeat updates online/offline status.
"""

import uuid
from datetime import date
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AttendanceRecord, Device, Student, StudentFaceEmbedding
from app.schemas.face import MatchStatus


@pytest.fixture(scope="module")
def e2e_face_crops():
    """Load pre-cropped real face images from tests/data/crops/."""
    crops_dir = Path(__file__).parent / "data" / "crops"
    assert crops_dir.exists(), "crops directory must exist."

    crops = {}
    for fname in ["person1_1.jpg", "person1_2.jpg", "person1_3.jpg", "person1_4.jpg", "person2_1.jpg"]:
        p = crops_dir / fname
        assert p.exists(), f"Image {fname} required."
        with open(p, "rb") as f:
            crops[fname] = f.read()
    return crops


def test_ten_real_world_integration_scenarios(
    client: TestClient,
    admin_headers: dict,
    device_headers: dict,
    e2e_face_crops: dict,
    db_session: Session,
):
    db = db_session
    uid = uuid.uuid4().hex[:6]
    test_student_id = f"STU-E2E-{uid}"
    test_student_name = f"E2E Integration Student {uid}"
    test_dept = "Computer Science & Engineering"
    test_batch = "2024"

    # Clean up any potential conflicting students with person1 face embeddings
    for sid in [test_student_id, "STU-STAGE54-001", "STU-STAGE54-REC", "STU-2024-001"]:
        existing = db.execute(select(Student).where(Student.student_id == sid)).scalar_one_or_none()
        if existing:
            db.query(AttendanceRecord).filter(AttendanceRecord.student_id == existing.id).delete()
            db.query(StudentFaceEmbedding).filter(StudentFaceEmbedding.student_id == existing.id).delete()
            db.delete(existing)
            db.commit()

    # -------------------------------------------------------------
    # Scenario 1: Create a new student and confirm it appears in Students
    # -------------------------------------------------------------
    create_payload = {
        "student_id": test_student_id,
        "full_name": test_student_name,
        "department": test_dept,
        "batch": test_batch,
        "email": f"e2e.{uid}@university.edu",
    }
    create_res = client.post("/api/v1/students", json=create_payload, headers=admin_headers)
    assert create_res.status_code == 201, f"Student creation failed: {create_res.text}"
    created_data = create_res.json()
    assert created_data["student_id"] == test_student_id
    assert created_data["embeddings_count"] == 0

    list_res = client.get(f"/api/v1/students?search={test_student_id}", headers=admin_headers)
    assert list_res.status_code == 200
    students_in_list = list_res.json()["students"]
    assert any(s["student_id"] == test_student_id for s in students_in_list)

    # -------------------------------------------------------------
    # Scenario 2: Enroll the student's face and confirm enrollment status updates
    # -------------------------------------------------------------
    enroll_files = [
        ("images", ("p1_1.jpg", e2e_face_crops["person1_1.jpg"], "image/jpeg")),
        ("images", ("p1_2.jpg", e2e_face_crops["person1_2.jpg"], "image/jpeg")),
        ("images", ("p1_3.jpg", e2e_face_crops["person1_3.jpg"], "image/jpeg")),
    ]
    enroll_data = {
        "student_id": test_student_id,
        "name": test_student_name,
        "department": test_dept,
        "batch": test_batch,
    }
    enroll_res = client.post("/api/v1/face/enroll", headers=admin_headers, data=enroll_data, files=enroll_files)
    assert enroll_res.status_code == 201, f"Enrollment failed: {enroll_res.text}"
    assert enroll_res.json()["embeddings_count"] == 3

    stu_res = client.get(f"/api/v1/students/{test_student_id}", headers=admin_headers)
    assert stu_res.status_code == 200
    assert stu_res.json()["embeddings_count"] == 3

    # -------------------------------------------------------------
    # Scenario 3: Recognize the student using ESP32 camera crop
    # -------------------------------------------------------------
    rec_files = {"image": ("query.jpg", e2e_face_crops["person1_4.jpg"], "image/jpeg")}
    rec_data = {"device_id": "esp32-cam-01"}
    rec_res = client.post("/api/v1/face/recognize", headers=device_headers, data=rec_data, files=rec_files)
    assert rec_res.status_code == 200, f"Recognition failed: {rec_res.text}"
    rec_json = rec_res.json()
    assert rec_json["status"] == MatchStatus.MATCH.value
    assert rec_json["student_id"] == test_student_id
    assert rec_json["attendance_recorded"] is True
    assert rec_json["already_checked_in"] is False
    attendance_uuid = rec_json["attendance_id"]
    assert attendance_uuid is not None

    # -------------------------------------------------------------
    # Scenario 4: Confirm attendance appears in Live Attendance feed
    # -------------------------------------------------------------
    live_res = client.get("/api/v1/attendance?limit=10", headers=admin_headers)
    assert live_res.status_code == 200
    live_records = live_res.json()["records"]
    matched_live = [r for r in live_records if r["id"] == attendance_uuid]
    assert len(matched_live) == 1
    assert matched_live[0]["student_id_snapshot"] == test_student_id
    assert matched_live[0]["student_name_snapshot"] == test_student_name
    assert matched_live[0]["status"] == "present"

    # -------------------------------------------------------------
    # Scenario 5: Confirm same record appears in Attendance History and CSV export
    # -------------------------------------------------------------
    hist_res = client.get(f"/api/v1/attendance?search={test_student_id}", headers=admin_headers)
    assert hist_res.status_code == 200
    hist_records = hist_res.json()["records"]
    assert len(hist_records) >= 1
    assert hist_records[0]["id"] == attendance_uuid

    export_res = client.get(f"/api/v1/attendance/export?search={test_student_id}", headers=admin_headers)
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert test_student_id in export_res.text
    assert attendance_uuid in export_res.text

    # -------------------------------------------------------------
    # Scenario 6: Confirm Overview statistics update
    # -------------------------------------------------------------
    dash_res = client.get("/api/v1/analytics/dashboard", headers=admin_headers)
    assert dash_res.status_code == 200
    dash_json = dash_res.json()
    assert dash_json["total_students"] >= 1
    assert dash_json["today_attendance_count"] >= 1
    assert dash_json["unique_students_present"] >= 1
    assert dash_json["attendance_rate"] > 0.0
    assert dash_json["registered_face_templates"] >= 3
    # Confirm recent activity in overview contains the event
    assert any(r["id"] == attendance_uuid for r in dash_json["recent_activity"])

    # -------------------------------------------------------------
    # Scenario 7: Confirm Reports reflect the new attendance
    # -------------------------------------------------------------
    reports_res = client.get("/api/v1/analytics/reports", headers=admin_headers)
    assert reports_res.status_code == 200
    rep_json = reports_res.json()
    assert rep_json["total_monthly_checkins"] >= 1
    assert rep_json["monthly_attendance_rate"] > 0.0
    assert rep_json["mean_confidence"] > 0.0

    # -------------------------------------------------------------
    # Scenario 8: Confirm unknown faces do NOT create attendance
    # -------------------------------------------------------------
    imp_files = {"image": ("impostor.jpg", e2e_face_crops["person2_1.jpg"], "image/jpeg")}
    imp_res = client.post("/api/v1/face/recognize", headers=device_headers, data=rec_data, files=imp_files)
    assert imp_res.status_code == 200
    imp_json = imp_res.json()
    assert imp_json["status"] == MatchStatus.UNKNOWN.value
    assert imp_json["attendance_recorded"] is False
    assert imp_json["attendance_id"] is None
    assert imp_json["student_id"] is None

    # -------------------------------------------------------------
    # Scenario 9: Confirm duplicate check-in does NOT create another record
    # -------------------------------------------------------------
    dup_res = client.post("/api/v1/face/recognize", headers=device_headers, data=rec_data, files=rec_files)
    assert dup_res.status_code == 200
    dup_json = dup_res.json()
    assert dup_json["status"] == MatchStatus.MATCH.value
    assert dup_json["already_checked_in"] is True
    assert dup_json["attendance_id"] == attendance_uuid

    # Count attendance records in database for this student today
    today_records = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.student_id_snapshot == test_student_id,
            AttendanceRecord.attendance_date == date.today(),
        )
    ).scalars().all()
    assert len(today_records) == 1, "Duplicate check-in created a duplicate attendance record!"

    # -------------------------------------------------------------
    # Scenario 10: Confirm device heartbeat updates online/offline status
    # -------------------------------------------------------------
    hb_res = client.post("/api/v1/devices/heartbeat?device_code=esp32-cam-01", headers=admin_headers)
    assert hb_res.status_code == 200

    dev_res = client.get("/api/v1/devices", headers=admin_headers)
    assert dev_res.status_code == 200
    devices = dev_res.json()["devices"]
    cam_node = next((d for d in devices if d["device_code"] == "esp32-cam-01"), None)
    assert cam_node is not None
    assert cam_node["is_online"] is True
    assert cam_node["last_seen_at"] is not None

    # Clean up test records
    student = db.execute(select(Student).where(Student.student_id == test_student_id)).scalar_one_or_none()
    if student:
        db.query(AttendanceRecord).filter(AttendanceRecord.student_id == student.id).delete()
        db.query(StudentFaceEmbedding).filter(StudentFaceEmbedding.student_id == student.id).delete()
        db.delete(student)
        db.commit()
