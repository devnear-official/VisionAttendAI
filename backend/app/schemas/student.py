"""Pydantic schemas for student management."""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, EmailStr


class StudentBase(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=32, description="Unique institutional Student ID")
    full_name: str = Field(..., min_length=1, max_length=128, description="Student's full legal name")
    email: Optional[EmailStr] = Field(default=None, description="Unique email address")
    department: Optional[str] = Field(default=None, max_length=64, description="Academic department")
    batch: Optional[str] = Field(default=None, max_length=32, description="Academic batch/year")
    phone: Optional[str] = Field(default=None, max_length=32, description="Contact phone number")


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    email: Optional[EmailStr] = None
    department: Optional[str] = Field(default=None, max_length=64)
    batch: Optional[str] = Field(default=None, max_length=32)
    phone: Optional[str] = Field(default=None, max_length=32)
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


class StudentResponse(StudentBase):
    id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    embeddings_count: int = 0
    attendance_count: int = 0
    last_attendance_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StudentListResponse(BaseModel):
    total: int
    students: List[StudentResponse]
