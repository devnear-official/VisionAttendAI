"""Student face enrollment and administrative routes."""

import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key
from app.database.session import get_db
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.face import EnrollmentResponse, PersonResponse
from app.schemas.student import StudentCreate
from app.services.embedding_service import EmbeddingService
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
