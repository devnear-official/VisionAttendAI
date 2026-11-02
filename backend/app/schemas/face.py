"""Face recognition, enrollment, alignment, and similarity schemas."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class MatchStatus(str, Enum):
    MATCH = "MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class Point2D(BaseModel):
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")


class FiveLandmarks(BaseModel):
    """Five-point facial landmark coordinates (left eye, right eye, nose, left mouth corner, right mouth corner)."""
    left_eye: Point2D
    right_eye: Point2D
    nose: Point2D
    left_mouth: Point2D
    right_mouth: Point2D

    def as_list(self) -> List[List[float]]:
        return [
            [self.left_eye.x, self.left_eye.y],
            [self.right_eye.x, self.right_eye.y],
            [self.nose.x, self.nose.y],
            [self.left_mouth.x, self.left_mouth.y],
            [self.right_mouth.x, self.right_mouth.y],
        ]


class PersonResponse(BaseModel):
    person_id: str
    student_id: str
    full_name: str
    department: Optional[str] = None
    batch: Optional[str] = None
    status: str
    is_active: bool
    enrolled_at: str
    embeddings_count: int = 0


class EnrollmentResponse(BaseModel):
    status: str
    message: str
    person_id: Optional[str] = None
    student_id: Optional[str] = None
    embeddings_count: int = 0


class RecognitionResponse(BaseModel):
    status: MatchStatus
    confidence: float = Field(..., ge=-1.0, le=1.0)
    person_id: Optional[str] = None
    student_id: Optional[str] = None
    full_name: Optional[str] = None
    department: Optional[str] = None
    batch: Optional[str] = None
    attendance_recorded: bool = False
    already_checked_in: bool = False
    attendance_id: Optional[str] = None
    inference_time_ms: float
    message: str


class EnrollmentSessionCreate(BaseModel):
    """Payload to initiate a new edge camera biometric enrollment session."""
    student_id: str = Field(..., min_length=1, description="Unique university student ID")
    name: str = Field(..., min_length=1, description="Student full name")
    department: Optional[str] = Field(None, description="Department name or code")
    batch: Optional[str] = Field(None, description="Academic batch or year")
    device_code: str = Field(..., min_length=1, description="Edge camera device identifier")
    target_samples: int = Field(default=3, ge=3, le=5, description="Number of face samples required (3 to 5)")
    consent_confirmed: bool = Field(True, description="Biometric data privacy consent confirmation")


class EnrollmentSessionResponse(BaseModel):
    """Telemetry and status representation of an active enrollment session."""
    session_id: str
    student_id: str
    name: str
    department: Optional[str] = None
    batch: Optional[str] = None
    device_code: str
    target_samples: int
    collected_count: int
    status: str
    expires_in_seconds: int
    created_at: str
    message: Optional[str] = None


class DeviceSampleResponse(BaseModel):
    """Response returned to edge device during enrollment capture."""
    status: str
    session_id: Optional[str] = None
    sample_index: int
    target_samples: int
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    message: str
    instructions: Optional[str] = None
