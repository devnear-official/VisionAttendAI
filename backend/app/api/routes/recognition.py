"""Edge device face recognition and attendance check-in verification route."""

import json
import time
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import verify_device_key
from app.database.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.face import MatchStatus, RecognitionResponse
from app.services.attendance_service import AttendanceService
from app.services.device_service import DeviceService
from app.services.face_alignment import FaceAligner
from app.services.face_engine import FaceRecognitionEngine, ModelNotAvailableError, face_engine
from app.services.image_validation import ImageValidationError, ImageValidator, LandmarkValidationError
from app.services.vector_search_service import VectorSearchService
from app.utils.logger import logger

router = APIRouter(prefix="/face", tags=["Face Recognition"])


@router.post(
    "/recognize",
    response_model=RecognitionResponse,
    summary="Recognize edge camera face crop",
    description=(
        "Processes a face crop sent by the ESP32-S3 edge camera. Validates the image, aligns the face, "
        "extracts the 512-D embedding vector, searches pgvector for identity match, and transactionally "
        "records attendance if a confident match is verified. Requires X-Device-Api-Key header."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Validation failed"},
        401: {"model": ErrorResponse, "description": "Missing device API key"},
        403: {"model": ErrorResponse, "description": "Invalid device API key"},
        503: {"model": ErrorResponse, "description": "Face recognition model unavailable"},
    }
)
async def recognize_face(
    image: UploadFile = File(..., description="JPEG or PNG face crop from ESP32 edge camera"),
    device_id: Optional[str] = Form("ESP32-S3-CAM", description="Identifier/code of the transmitting device"),
    landmarks: Optional[str] = Form(
        None,
        description="Optional JSON string of 5-point landmark coordinates relative to the crop"
    ),
    landmarks_json: Optional[str] = Form(
        None,
        description="Backward-compatible alias for landmarks field"
    ),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_device_key),
):
    start_time = time.time()

    if not face_engine.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Face recognition model is not loaded. Download w600k_r50.onnx into models/ "
                "following backend/models/README.md."
            )
        )

    raw_bytes = await image.read()
    try:
        img = ImageValidator.decode_image_bytes(raw_bytes)
        ImageValidator.validate_quality(img)

        # Align face if landmarks are transmitted from edge ESP32 detector
        raw_landmarks = landmarks or landmarks_json
        if raw_landmarks:
            try:
                parsed_landmarks = json.loads(raw_landmarks)
                aligned = FaceAligner.align_face_112(img, parsed_landmarks)
            except Exception:
                import cv2
                aligned = cv2.resize(img, (112, 112), interpolation=cv2.INTER_LINEAR)
        else:
            import cv2
            aligned = cv2.resize(img, (112, 112), interpolation=cv2.INTER_LINEAR)

        # Extract 512-D normalized vector
        query_embedding = face_engine.extract_embedding(aligned)

    except (ImageValidationError, LandmarkValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Face crop failed quality validation: {str(e)}"
        )
    except ModelNotAvailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    # Search PostgreSQL + pgvector for closest student
    match_status, similarity, matched_student = VectorSearchService.search_closest_face(
        db, query_embedding
    )

    elapsed_ms = (time.time() - start_time) * 1000.0

    # Look up device UUID if device_id is code
    device_uuid: Optional[uuid.UUID] = None
    if device_id:
        try:
            device_uuid = uuid.UUID(device_id)
        except ValueError:
            dev = DeviceService.get_by_code(db, device_id)
            if dev:
                device_uuid = dev.id

    if match_status == MatchStatus.MATCH and matched_student is not None:
        # Create attendance record transactionally
        record, was_new = AttendanceService.record_attendance(
            db,
            student=matched_student,
            device_id=device_uuid,
            confidence=similarity,
            method="face_recognition",
            status="present",
        )
        db.commit()

        return RecognitionResponse(
            status=MatchStatus.MATCH,
            confidence=similarity,
            person_id=str(matched_student.id),
            student_id=matched_student.student_id,
            full_name=matched_student.full_name,
            department=matched_student.department,
            batch=matched_student.batch,
            attendance_recorded=True,
            already_checked_in=not was_new,
            attendance_id=str(record.id),
            inference_time_ms=elapsed_ms,
            message=(
                f"Identity verified for student {matched_student.full_name} ({matched_student.student_id}). "
                f"Attendance {'recorded' if was_new else 'already checked in today'}."
            ),
        )

    elif match_status == MatchStatus.AMBIGUOUS and matched_student is not None:
        # Ambiguous match: DO NOT record attendance
        return RecognitionResponse(
            status=MatchStatus.AMBIGUOUS,
            confidence=similarity,
            person_id=str(matched_student.id),
            student_id=matched_student.student_id,
            full_name=matched_student.full_name,
            department=matched_student.department,
            batch=matched_student.batch,
            attendance_recorded=False,
            already_checked_in=False,
            attendance_id=None,
            inference_time_ms=elapsed_ms,
            message="Match confidence is ambiguous. Please look directly at the camera and try again.",
        )

    else:
        # UNKNOWN face: DO NOT record attendance
        return RecognitionResponse(
            status=MatchStatus.UNKNOWN,
            confidence=similarity,
            person_id=None,
            student_id=None,
            full_name=None,
            department=None,
            batch=None,
            attendance_recorded=False,
            already_checked_in=False,
            attendance_id=None,
            inference_time_ms=elapsed_ms,
            message="Unknown face. Person is not registered in the system.",
        )
