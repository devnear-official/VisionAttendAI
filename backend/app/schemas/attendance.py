"""Pydantic schemas for attendance records."""

import uuid
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class AttendanceBase(BaseModel):
    student_id_snapshot: str = Field(..., description="Snapshot of student ID at check-in")
    student_name_snapshot: str = Field(..., description="Snapshot of student name at check-in")
    attendance_date: date = Field(..., description="Date of attendance")
    check_in_time: datetime = Field(..., description="Timezone-aware check-in timestamp")
    device_id: Optional[uuid.UUID] = Field(default=None, description="ID of the verifying edge device")
    recognition_confidence: Optional[float] = Field(default=None, description="Cosine similarity confidence score")
    recognition_method: str = Field("face_recognition", description="Method of verification")
    status: str = Field("present", description="Attendance status: present/late")
    device_name: Optional[str] = Field(default=None, description="Verifying edge camera node name")
    device_code: Optional[str] = Field(default=None, description="Verifying edge camera node code")
    department: Optional[str] = Field(default=None, description="Student academic department")


class AttendanceCreate(AttendanceBase):
    student_id: Optional[uuid.UUID] = None


class AttendanceResponse(AttendanceBase):
    id: uuid.UUID
    student_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AttendanceListResponse(BaseModel):
    total: int
    records: List[AttendanceResponse]
