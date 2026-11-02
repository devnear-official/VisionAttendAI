"""Edge device face recognition and attendance check-in verification route."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import verify_device_key
from app.database.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.face import MatchStatus, RecognitionResponse
from app.schemas.student import StudentCreate
from app.services.attendance_service import AttendanceService
from app.services.device_service import DeviceService
from app.services.embedding_service import EmbeddingService
from app.services.enrollment_session_service import EnrollmentSessionService
from app.services.face_alignment import FaceAligner
from app.services.face_engine import FaceRecognitionEngine, ModelNotAvailableError, face_engine
from app.services.image_validation import ImageValidationError, ImageValidator, LandmarkValidationError
from app.services.student_service import StudentService
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
        logger.warning(f"Face crop validation failed for device '{device_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Face crop failed quality validation: {str(e)}"
        )
    except ModelNotAvailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    # 1. Seamless Edge Enrollment Interception
    active_enroll_session = (
        EnrollmentSessionService.get_active_session_for_device(device_id) if device_id else None
    )
    if active_enroll_session and active_enroll_session.status == "active":
        dup_match = VectorSearchService.check_duplicate_enrollment(
            db, [query_embedding], exclude_student_id=active_enroll_session.student_id, duplicate_threshold=0.70
        )
        if dup_match is not None:
            matched_stu, score = dup_match
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate face detected! Matches '{matched_stu.student_id}' ({matched_stu.full_name}) at {score:.2f}.",
            )

        active_enroll_session, is_complete = EnrollmentSessionService.add_sample(
            session_id=active_enroll_session.session_id,
            embedding=query_embedding,
            quality_score=1.0,
        )

        try:
            from app.core.events import event_manager
            await event_manager.broadcast_attendance_event({
                "event": "enrollment_sample_added",
                "session_id": active_enroll_session.session_id,
                "student_id": active_enroll_session.student_id,
                "student_name": active_enroll_session.name,
                "device_code": active_enroll_session.device_code,
                "sample_index": active_enroll_session.collected_count,
                "target_samples": active_enroll_session.target_samples,
                "is_complete": is_complete,
            })
        except Exception:
            pass

        if is_complete:
            try:
                existing_stu = StudentService.get_by_student_id(
                    db, active_enroll_session.student_id, include_deleted=True
                )
                if existing_stu:
                    if existing_stu.deleted_at is not None:
                        existing_stu.deleted_at = None
                        existing_stu.status = "active"
                    existing_stu.full_name = active_enroll_session.name
                    if active_enroll_session.department:
                        existing_stu.department = active_enroll_session.department
                    if active_enroll_session.batch:
                        existing_stu.batch = active_enroll_session.batch
                    # Deactivate prior embeddings on re-enrollment to prevent duplicates
                    EmbeddingService.deactivate_embeddings(db, existing_stu.id)
                    student = existing_stu
                else:
                    student_in = StudentCreate(
                        student_id=active_enroll_session.student_id,
                        full_name=active_enroll_session.name,
                        department=active_enroll_session.department,
                        batch=active_enroll_session.batch,
                    )
                    student = StudentService.create_student(db, student_in)

                all_embeddings = [s.embedding for s in active_enroll_session.samples]
                EmbeddingService.store_student_embeddings(db, student.id, all_embeddings)
                db.commit()

                # Mark session completed in memory store only after successful commit
                EnrollmentSessionService.mark_completed(active_enroll_session.session_id)

                try:
                    await event_manager.broadcast_attendance_event({
                        "event": "enrollment_completed",
                        "session_id": active_enroll_session.session_id,
                        "student_id": student.student_id,
                        "student_name": student.full_name,
                        "device_code": active_enroll_session.device_code,
                        "embeddings_count": len(all_embeddings),
                    })
                except Exception:
                    pass

                return RecognitionResponse(
                    status=MatchStatus.MATCH,
                    confidence=1.0,
                    person_id=str(student.id),
                    student_id=student.student_id,
                    full_name=student.full_name,
                    department=student.department,
                    batch=student.batch,
                    attendance_recorded=False,
                    already_checked_in=False,
                    inference_time_ms=(time.time() - start_time) * 1000.0,
                    message="ENROLLED",
                )
            except Exception as e:
                db.rollback()
                EnrollmentSessionService.mark_failed(active_enroll_session.session_id, str(e))
                logger.error(f"Failed committing enrolled student: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database commit error during enrollment: {str(e)}",
                )

        return RecognitionResponse(
            status=MatchStatus.MATCH,
            confidence=1.0,
            person_id=None,
            student_id=active_enroll_session.student_id,
            full_name=active_enroll_session.name,
            department=active_enroll_session.department,
            batch=active_enroll_session.batch,
            attendance_recorded=False,
            already_checked_in=False,
            inference_time_ms=(time.time() - start_time) * 1000.0,
            message=f"ENROLLING {active_enroll_session.collected_count}/{active_enroll_session.target_samples}",
        )

    # 2. Search PostgreSQL + pgvector for closest student
    match_status, similarity, matched_student = VectorSearchService.search_closest_face(
        db, query_embedding
    )

    elapsed_ms = (time.time() - start_time) * 1000.0
    safe_confidence = max(0.0, min(1.0, float(similarity)))

    # Look up device UUID and update last_seen_at
    device_uuid: Optional[uuid.UUID] = None
    if device_id:
        try:
            device_uuid = uuid.UUID(device_id)
            dev = DeviceService.get_by_id(db, device_uuid)
            if dev:
                dev.last_seen_at = datetime.now(timezone.utc)
                db.flush()
        except ValueError:
            dev = DeviceService.get_by_code(db, device_id)
            if dev:
                device_uuid = dev.id
                dev.last_seen_at = datetime.now(timezone.utc)
                db.flush()

    if match_status == MatchStatus.MATCH and matched_student is not None:
        # Create attendance record transactionally
        record, was_new = AttendanceService.record_attendance(
            db,
            student=matched_student,
            device_id=device_uuid,
            confidence=safe_confidence,
            method="face_recognition",
            status="present",
        )
        db.commit()

        # Broadcast real-time attendance event to connected dashboard clients
        try:
            from app.core.events import event_manager
            await event_manager.broadcast_attendance_event({
                "event": "attendance_verified",
                "attendance_id": str(record.id),
                "student_id": matched_student.student_id,
                "full_name": matched_student.full_name,
                "department": matched_student.department,
                "batch": matched_student.batch,
                "check_in_time": record.check_in_time.isoformat(),
                "confidence": safe_confidence,
                "device_code": device_id or "ESP32-S3-CAM",
                "status": "present",
                "is_new": was_new,
                "already_checked_in": not was_new,
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast attendance event: {e}")

        return RecognitionResponse(
            status=MatchStatus.MATCH,
            confidence=safe_confidence,
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
            confidence=safe_confidence,
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
            confidence=safe_confidence,
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
