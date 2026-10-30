"""Student face enrollment and administrative routes."""

import json
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.security import verify_admin_key
from app.schemas.common import ErrorResponse
from app.schemas.face import EnrollmentResponse, FiveLandmarks, PersonResponse
from app.services.face_alignment import FaceAligner
from app.services.face_engine import FaceRecognitionEngine, ModelNotAvailableError, face_engine
from app.services.image_validation import ImageValidationError, ImageValidator, LandmarkValidationError
from app.utils.logger import logger

router = APIRouter(prefix="/face", tags=["Face Enrollment & Management"])


@router.post(
    "/enroll",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll student face templates",
    description=(
        "Enrolls a student with 3 to 5 face images. Validates image quality, extracts landmarks, "
        "and computes 512-D ArcFace feature vectors. Requires Admin Bearer Token."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Validation failed"},
        401: {"model": ErrorResponse, "description": "Missing authentication credentials"},
        403: {"model": ErrorResponse, "description": "Invalid administrative credentials"},
        501: {"model": ErrorResponse, "description": "Database persistence scheduled for Stage 5.2"},
        503: {"model": ErrorResponse, "description": "Face recognition model unavailable"},
    }
)
async def enroll_person(
    student_id: str = Form(..., description="Student ID number (e.g. 2022-CSE-042)"),
    name: str = Form(..., description="Full Name"),
    department: str = Form(..., description="Academic Department"),
    batch: str = Form(..., description="Academic Batch"),
    images: List[UploadFile] = File(..., description="3 to 5 clear face images"),
    landmarks_json: Optional[str] = Form(
        None,
        description="Optional JSON string of 5-point landmarks per image for pre-detected crops"
    ),
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
                "Face recognition model is not loaded. Please download w600k_r50.onnx into models/ "
                "following backend/models/README.md."
            )
        )

    # Process and validate each image in memory
    valid_embeddings = []
    parsed_landmarks_list = []
    if landmarks_json:
        try:
            parsed_landmarks_list = json.loads(landmarks_json)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid landmarks_json format. Expected JSON array of 5-point landmark lists."
            )

    for idx, img_file in enumerate(images):
        raw_bytes = await img_file.read()
        try:
            img = ImageValidator.decode_image_bytes(raw_bytes)
            ImageValidator.validate_quality(img)

            # If external landmarks provided, align using them
            if parsed_landmarks_list and idx < len(parsed_landmarks_list):
                aligned = FaceAligner.align_face_112(img, parsed_landmarks_list[idx])
            else:
                # If no landmarks provided, resize to 112x112 as raw crop
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

    # Database commitment scheduled for Stage 5.2
    # In strict accordance with guidelines: Do NOT return fake success responses.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"Stage 5.1 Foundation: Biometric feature extraction succeeded for {len(valid_embeddings)} image(s) "
            f"for student '{student_id}'. Database persistence and pgvector indexing are scheduled for Stage 5.2. "
            "No record was committed."
        )
    )


@router.get(
    "/person/{person_id}",
    response_model=PersonResponse,
    summary="Get enrolled person details",
    description="Retrieve student details and enrollment status by ID. Requires Admin Bearer Token.",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        501: {"model": ErrorResponse, "description": "Database queries scheduled for Stage 5.2"},
    }
)
async def get_person(
    person_id: str,
    _authorized: bool = Depends(verify_admin_key),
):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Person query for ID '{person_id}' is scheduled for Stage 5.2 (PostgreSQL integration)."
    )


@router.delete(
    "/person/{person_id}",
    summary="Delete enrolled person & biometric templates",
    description="Permanently remove biometric templates for privacy compliance. Requires Admin Bearer Token.",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        501: {"model": ErrorResponse, "description": "Database operations scheduled for Stage 5.2"},
    }
)
async def delete_person(
    person_id: str,
    _authorized: bool = Depends(verify_admin_key),
):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Biometric deletion for ID '{person_id}' is scheduled for Stage 5.2 (PostgreSQL integration)."
    )
