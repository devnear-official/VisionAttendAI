"""Pydantic schemas for dashboard analytics and performance KPIs."""

from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.attendance import AttendanceResponse


class DepartmentStat(BaseModel):
    department: str = Field(..., description="Department name or designation")
    total_students: int = Field(..., ge=0, description="Total active enrolled students in department")
    present_today: int = Field(..., ge=0, description="Number of students checked in today")
    attendance_rate: float = Field(..., ge=0.0, le=100.0, description="Department attendance rate percentage")


class DailyTrendStat(BaseModel):
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    attendance_count: int = Field(..., ge=0, description="Check-ins recorded on this day")
    unique_students: int = Field(..., ge=0, description="Unique students verified on this day")


class DashboardSummaryResponse(BaseModel):
    total_students: int = Field(default=0, ge=0, description="Total registered students (including inactive)")
    total_active_students: int = Field(..., ge=0, description="Total active students eligible for attendance")
    today_attendance_count: int = Field(..., ge=0, description="Total attendance check-in records for today")
    unique_students_present: int = Field(..., ge=0, description="Count of distinct students verified today")
    attendance_rate: float = Field(..., ge=0.0, le=100.0, description="Overall institutional attendance rate percentage")
    average_confidence: Optional[float] = Field(None, description="Average ArcFace cosine similarity score today")
    registered_face_templates: int = Field(default=0, ge=0, description="Total active ArcFace embeddings saved in PostgreSQL")
    total_devices: int = Field(default=0, ge=0, description="Total registered edge camera devices")
    online_devices: int = Field(default=0, ge=0, description="Count of edge devices currently online")
    departments: List[DepartmentStat] = Field(default_factory=list, description="Department breakdown statistics")
    recent_activity: List[AttendanceResponse] = Field(default_factory=list, description="Latest verified check-in records")
    attendance_trends: List[DailyTrendStat] = Field(default_factory=list, description="Daily attendance trends for past 14 days")


class ReportsResponse(BaseModel):
    monthly_attendance_rate: float = Field(..., ge=0.0, le=100.0, description="Overall monthly attendance rate percentage")
    total_monthly_checkins: int = Field(..., ge=0, description="Total attendance check-in records in last 30 days")
    mean_confidence: float = Field(..., ge=0.0, le=1.0, description="Average recognition confidence across all check-ins")
    total_active_students: int = Field(..., ge=0, description="Total active students")
    registered_face_templates: int = Field(..., ge=0, description="Total enrolled face embeddings")
    departments: List[DepartmentStat] = Field(default_factory=list, description="Department performance breakdown")
    daily_trends: List[DailyTrendStat] = Field(default_factory=list, description="Daily trends for the past 30 days")
