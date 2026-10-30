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
    confidence: float = Field(..., ge=0.0, le=1.0)
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
