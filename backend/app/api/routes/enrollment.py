"""Student face enrollment and administrative routes."""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.events import event_manager
from app.core.security import verify_admin_key, verify_device_key
from app.database.session import get_db
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.face import (
    DeviceSampleResponse,
    EnrollmentResponse,
    EnrollmentSessionCreate,
    EnrollmentSessionResponse,
    PersonResponse,
)
from app.schemas.student import StudentCreate
from app.services.device_service import DeviceService
from app.services.embedding_service import EmbeddingService
from app.services.enrollment_session_service import EnrollmentSessionService
from app.services.face_alignment import FaceAligner
from app.services.face_engine import FaceRecognitionEngine, ModelNotAvailableError, face_engine
from app.services.image_validation import ImageValidationError, ImageValidator, LandmarkValidationError
from app.services.student_service import StudentService
from app.services.vector_search_service import VectorSearchService
from app.utils.logger import logger

router = APIRouter(prefix="/face", tags=["Face Enrollment & Management"])


@router.post(
    "/enroll",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll student face templates",
    description=(
        "Enrolls a student with 1 to 5 face images. Validates image quality, extracts landmarks, "
        "computes 512-D ArcFace feature vectors, prevents duplicate enrollment via pgvector, "
        "and saves student and embeddings transactionally. Requires Admin Bearer Token."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Validation or duplicate face error"},
        401: {"model": ErrorResponse, "description": "Missing authentication credentials"},
        403: {"model": ErrorResponse, "description": "Invalid administrative credentials"},
        503: {"model": ErrorResponse, "description": "Face recognition model unavailable"},
    }
)
async def enroll_person(
    student_id: str = Form(..., description="Student ID number (e.g. 2022-CSE-042)"),
    name: str = Form(..., description="Full Name"),
    department: Optional[str] = Form(None, description="Academic Department"),
    batch: Optional[str] = Form(None, description="Academic Batch"),
    email: Optional[str] = Form(None, description="Student email"),
    phone: Optional[str] = Form(None, description="Contact phone"),
    images: List[UploadFile] = File(..., description="1 to 5 clear face images"),
    landmarks_json: Optional[str] = Form(
        None,
        description="Optional JSON string of 5-point landmarks per image for pre-detected crops"
    ),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    if len(images) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 1 face image is required for enrollment (3 to 5 recommended)."
        )

    if not face_engine.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Face recognition model is not loaded. Download w600k_r50.onnx into models/ "
                "following backend/models/README.md."
            )
        )

    # Parse optional landmarks
    parsed_landmarks_list = []
    if landmarks_json:
        try:
            parsed_landmarks_list = json.loads(landmarks_json)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid landmarks_json format. Expected JSON array of 5-point landmark coordinates."
            )

    # Process and validate each image in memory
    valid_embeddings = []
    for idx, img_file in enumerate(images):
        raw_bytes = await img_file.read()
        try:
            img = ImageValidator.decode_image_bytes(raw_bytes)
            ImageValidator.validate_quality(img)

            # Align face if landmarks are provided
            if parsed_landmarks_list and idx < len(parsed_landmarks_list):
                aligned = FaceAligner.align_face_112(img, parsed_landmarks_list[idx])
            else:
                import cv2
                aligned = cv2.resize(img, (112, 112), interpolation=cv2.INTER_LINEAR)

            embedding = face_engine.extract_embedding(aligned)
            valid_embeddings.append(embedding)

        except (ImageValidationError, LandmarkValidationError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image {idx+1} ({img_file.filename}) failed validation: {str(e)}"
            )
        except ModelNotAvailableError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e)
            )

    # 1. Check for duplicate enrollment using vector similarity search against active students
    clean_student_id = student_id.strip()
    dup_match = VectorSearchService.check_duplicate_enrollment(
        db,
        valid_embeddings,
        exclude_student_id=clean_student_id,
        duplicate_threshold=0.70,
    )
    if dup_match is not None:
        matched_student, score = dup_match
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Duplicate face detected! Submitted face highly matches existing student "
                f"'{matched_student.student_id}' ({matched_student.full_name}) with similarity {score:.2f}."
            )
        )

    # 2. Get or create student record
    existing_student = StudentService.get_by_student_id(db, clean_student_id, include_deleted=True)
    if existing_student:
        if existing_student.deleted_at is not None:
            # Reactivate soft-deleted student
            existing_student.deleted_at = None
            existing_student.status = "active"
        existing_student.full_name = name.strip()
        if department:
            existing_student.department = department.strip()
        if batch:
            existing_student.batch = batch.strip()
        if email:
            existing_student.email = email.strip().lower()
        if phone:
            existing_student.phone = phone.strip()
        student = existing_student
    else:
        student_in = StudentCreate(
            student_id=clean_student_id,
            full_name=name.strip(),
            department=department.strip() if department else None,
            batch=batch.strip() if batch else None,
            email=email.strip().lower() if email else None,
            phone=phone.strip() if phone else None,
        )
        student = StudentService.create_student(db, student_in)

    # 3. Store embeddings transactionally
    EmbeddingService.store_student_embeddings(db, student.id, valid_embeddings)
    db.commit()

    logger.info(
        f"Enrollment successful for student '{student.student_id}' with {len(valid_embeddings)} template(s)."
    )

    return EnrollmentResponse(
        status="success",
        message=f"Successfully enrolled {len(valid_embeddings)} face template(s) for student {student.student_id}.",
        person_id=str(student.id),
        student_id=student.student_id,
        embeddings_count=len(valid_embeddings),
    )


@router.get(
    "/person/{person_id}",
    response_model=PersonResponse,
    summary="Get enrolled person details",
    description="Retrieve student details and enrollment status by Student ID or UUID. Requires Admin Bearer Token.",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Person not found"},
    }
)
async def get_person(
    person_id: str,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    student = None
    try:
        val_uuid = uuid.UUID(person_id)
        student = StudentService.get_by_uuid(db, val_uuid, include_deleted=False)
    except ValueError:
        pass

    if not student:
        student = StudentService.get_by_student_id(db, person_id, include_deleted=False)

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person '{person_id}' not found or has been deactivated."
        )

    count = StudentService.count_active_embeddings(db, student.id)

    return PersonResponse(
        person_id=str(student.id),
        student_id=student.student_id,
        full_name=student.full_name,
        department=student.department,
        batch=student.batch,
        status=student.status,
        is_active=(student.status == "active" and student.deleted_at is None),
        enrolled_at=student.created_at.isoformat(),
        embeddings_count=count,
    )


@router.delete(
    "/person/{person_id}",
    response_model=SuccessResponse,
    summary="Delete enrolled person & biometric templates",
    description="Soft-deletes student profile and deactivates face embeddings. Attendance history is preserved.",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Person not found"},
    }
)
async def delete_person(
    person_id: str,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    # Try by UUID or student_id
    student = None
    try:
        val_uuid = uuid.UUID(person_id)
        student = StudentService.get_by_uuid(db, val_uuid, include_deleted=False)
    except ValueError:
        pass

    if not student:
        student = StudentService.get_by_student_id(db, person_id, include_deleted=False)

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person '{person_id}' not found or already deactivated."
        )

    StudentService.soft_delete_student(db, student.student_id)
    db.commit()

    return SuccessResponse(
        status="success",
        message=f"Student '{student.student_id}' ({student.full_name}) and biometric embeddings have been deactivated. Attendance history preserved.",
    )


@router.post(
    "/enroll/session",
    response_model=EnrollmentSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate edge camera biometric enrollment session",
    description="Registers an active temporary enrollment session on the selected edge camera. Requires Admin Bearer Token.",
)
async def create_enrollment_session(
    payload: EnrollmentSessionCreate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    if not payload.consent_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Biometric consent confirmation is required to start an enrollment session.",
        )

    # Verify device exists and is active
    device = DeviceService.get_by_code(db, payload.device_code)
    if not device:
        try:
            val_uuid = uuid.UUID(payload.device_code)
            device = DeviceService.get_by_id(db, val_uuid)
        except ValueError:
            pass

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge camera device '{payload.device_code}' not found in registry.",
        )

    if not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Edge device '{device.device_code}' is currently inactive.",
        )

    try:
        session = EnrollmentSessionService.create_session(
            student_id=payload.student_id,
            name=payload.name,
            department=payload.department,
            batch=payload.batch,
            device_code=device.device_code,
            target_samples=payload.target_samples,
            ttl_seconds=120,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # Broadcast session initiation to connected clients
    try:
        await event_manager.broadcast_attendance_event({
            "event": "enrollment_session_started",
            "session_id": session.session_id,
            "student_id": session.student_id,
            "student_name": session.name,
            "device_code": session.device_code,
            "target_samples": session.target_samples,
            "expires_in_seconds": session.expires_in_seconds,
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast session start: {e}")

    return EnrollmentSessionResponse(
        session_id=session.session_id,
        student_id=session.student_id,
        name=session.name,
        department=session.department,
        batch=session.batch,
        device_code=session.device_code,
        target_samples=session.target_samples,
        collected_count=session.collected_count,
        status=session.status,
        expires_in_seconds=session.expires_in_seconds,
        created_at=datetime.fromtimestamp(session.created_at, timezone.utc).isoformat(),
        message="Enrollment session initiated. Position student in front of camera.",
    )


@router.get(
    "/enroll/session/{session_id}",
    response_model=EnrollmentSessionResponse,
    summary="Get enrollment session status",
)
async def get_enrollment_session_status(
    session_id: str,
    _authorized: bool = Depends(verify_admin_key),
):
    session = EnrollmentSessionService.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Enrollment session '{session_id}' not found or purged.",
        )

    return EnrollmentSessionResponse(
        session_id=session.session_id,
        student_id=session.student_id,
        name=session.name,
        department=session.department,
        batch=session.batch,
        device_code=session.device_code,
        target_samples=session.target_samples,
        collected_count=session.collected_count,
        status=session.status,
        expires_in_seconds=session.expires_in_seconds,
        created_at=datetime.fromtimestamp(session.created_at, timezone.utc).isoformat(),
        message=(
            f"Enrollment commit failed: {session.error_message}"
            if session.status == "failed" and session.error_message
            else ("Session active" if session.status == "active" else f"Session is {session.status}")
        ),
    )


@router.delete(
    "/enroll/session/{session_id}",
    response_model=SuccessResponse,
    summary="Cancel active enrollment session",
)
async def cancel_enrollment_session(
    session_id: str,
    _authorized: bool = Depends(verify_admin_key),
):
    cancelled = EnrollmentSessionService.cancel_session(session_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Enrollment session '{session_id}' not active or not found.",
        )

    try:
        await event_manager.broadcast_attendance_event({
            "event": "enrollment_session_cancelled",
            "session_id": session_id,
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast session cancel: {e}")

    return SuccessResponse(
        status="success",
        message=f"Enrollment session '{session_id}' has been cancelled.",
    )


@router.post(
    "/enroll/device-sample",
    response_model=DeviceSampleResponse,
    summary="Upload edge camera face sample for active enrollment session",
    description="Processes and indexes face samples captured by ESP32-CAM. Requires X-Device-Api-Key.",
)
async def submit_device_enrollment_sample(
    image: UploadFile = File(..., description="JPEG crop from edge camera"),
    device_id: str = Form(..., description="Code or UUID of edge camera"),
    session_id: Optional[str] = Form(None, description="Optional enrollment session UUID"),
    landmarks: Optional[str] = Form(None, description="JSON array of 5 landmark pairs"),
    db: Session = Depends(get_db),
    _device_auth: bool = Depends(verify_device_key),
):
    if not face_engine.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Face recognition engine is unavailable.",
        )

    # 1. Resolve active session for device
    session = None
    if session_id:
        session = EnrollmentSessionService.get_session(session_id)
    if not session:
        session = EnrollmentSessionService.get_active_session_for_device(device_id)

    if not session or session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No active enrollment session found for edge camera '{device_id}'.",
        )

    # 2. Parse landmarks if provided
    parsed_landmarks = None
    if landmarks:
        try:
            parsed_landmarks = json.loads(landmarks)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid landmarks format. Expected JSON array of coordinates.",
            )

    # 3. Read and validate raw image crop in memory
    raw_bytes = await image.read()
    try:
        img = ImageValidator.decode_image_bytes(raw_bytes)
        ImageValidator.validate_quality(img)

        # Align with landmarks if available
        if parsed_landmarks and len(parsed_landmarks) >= 5:
            aligned = FaceAligner.align_face_112(img, parsed_landmarks)
        else:
            import cv2
            aligned = cv2.resize(img, (112, 112), interpolation=cv2.INTER_LINEAR)

        embedding = face_engine.extract_embedding(aligned)
    except (ImageValidationError, LandmarkValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sample failed quality check: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image processing failed: {str(e)}",
        )

    # 4. Duplicate face protection against other enrolled students
    dup_match = VectorSearchService.check_duplicate_enrollment(
        db,
        [embedding],
        exclude_student_id=session.student_id,
        duplicate_threshold=0.70,
    )
    if dup_match is not None:
        matched_student, score = dup_match
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate face detected! Matches '{matched_student.student_id}' ({matched_student.full_name}) at {score:.2f}.",
        )

    # 5. Append sample to session
    try:
        session, is_complete = EnrollmentSessionService.add_sample(
            session_id=session.session_id,
            embedding=embedding,
            quality_score=1.0,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 6. Broadcast progress event to dashboard
    try:
        await event_manager.broadcast_attendance_event({
            "event": "enrollment_sample_added",
            "session_id": session.session_id,
            "student_id": session.student_id,
            "student_name": session.name,
            "device_code": session.device_code,
            "sample_index": session.collected_count,
            "target_samples": session.target_samples,
            "is_complete": is_complete,
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast sample add: {e}")

    # 7. If target reached, commit to PostgreSQL transactionally
    if is_complete:
        try:
            existing_student = StudentService.get_by_student_id(db, session.student_id, include_deleted=True)
            if existing_student:
                if existing_student.deleted_at is not None:
                    existing_student.deleted_at = None
                    existing_student.status = "active"
                existing_student.full_name = session.name
                if session.department:
                    existing_student.department = session.department
                if session.batch:
                    existing_student.batch = session.batch
                # Prevent duplicate active embeddings on re-enrollment
                EmbeddingService.deactivate_embeddings(db, existing_student.id)
                student = existing_student
            else:
                student_in = StudentCreate(
                    student_id=session.student_id,
                    full_name=session.name,
                    department=session.department,
                    batch=session.batch,
                )
                student = StudentService.create_student(db, student_in)

            all_embeddings = [s.embedding for s in session.samples]
            EmbeddingService.store_student_embeddings(db, student.id, all_embeddings)
            db.commit()

            # Mark session completed in memory store only after successful commit
            EnrollmentSessionService.mark_completed(session.session_id)

            logger.info(
                f"Successfully committed {len(all_embeddings)} ArcFace templates for student '{student.student_id}'"
            )

            # Broadcast final completion event
            try:
                await event_manager.broadcast_attendance_event({
                    "event": "enrollment_completed",
                    "session_id": session.session_id,
                    "student_id": student.student_id,
                    "student_name": student.full_name,
                    "device_code": session.device_code,
                    "embeddings_count": len(all_embeddings),
                })
            except Exception as e:
                logger.warning(f"Failed to broadcast completion: {e}")

            return DeviceSampleResponse(
                status="ENROLLED",
                session_id=session.session_id,
                sample_index=session.collected_count,
                target_samples=session.target_samples,
                student_id=student.student_id,
                student_name=student.full_name,
                message=f"Enrollment complete! {len(all_embeddings)} face templates indexed.",
                instructions="Enrollment finished. Edge camera returning to normal recognition.",
            )
        except Exception as e:
            db.rollback()
            EnrollmentSessionService.mark_failed(session.session_id, str(e))
            logger.error(f"Failed to persist student enrollment in database: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database commit error during enrollment: {str(e)}",
            )

    # Partial sample collected; guide user for next pose
    next_pose = "Please turn head slightly left." if session.collected_count == 1 else "Please turn head slightly right."
    return DeviceSampleResponse(
        status="ENROLLING",
        session_id=session.session_id,
        sample_index=session.collected_count,
        target_samples=session.target_samples,
        student_id=session.student_id,
        student_name=session.name,
        message=f"Sample {session.collected_count} of {session.target_samples} captured.",
        instructions=next_pose,
    )
