"""Edge device face recognition verification route."""

import json
import time
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.security import verify_device_key
from app.schemas.common import ErrorResponse
from app.schemas.face import MatchStatus, RecognitionResponse
from app.services.face_alignment import FaceAligner
from app.services.face_engine import FaceRecognitionEngine, ModelNotAvailableError, face_engine
from app.services.image_validation import ImageValidationError, ImageValidator, LandmarkValidationError
from app.utils.logger import logger

router = APIRouter(prefix="/face", tags=["Face Recognition"])


@router.post(
    "/recognize",
    response_model=RecognitionResponse,
    summary="Recognize edge camera face crop",
    description=(
        "Processes a face crop sent by the ESP32-S3 edge camera. Validates the image, aligns the face, "
        "extracts the 512-D embedding vector, and matches it against enrolled vectors. "
        "Requires X-Device-Api-Key header."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Validation failed"},
        401: {"model": ErrorResponse, "description": "Missing device API key"},
        403: {"model": ErrorResponse, "description": "Invalid device API key"},
        501: {"model": ErrorResponse, "description": "Vector database matching scheduled for Stage 5.2"},
        503: {"model": ErrorResponse, "description": "Face recognition model unavailable"},
    }
)
async def recognize_face(
    image: UploadFile = File(..., description="JPEG or PNG face crop from ESP32 edge camera"),
    device_id: str = Form("ESP32-S3-CAM", description="Identifier of the transmitting device"),
    landmarks_json: Optional[str] = Form(
        None,
        description="Optional JSON string of 5-point landmark coordinates relative to the crop"
    ),
    _authorized: bool = Depends(verify_device_key),
):
    start_time = time.time()

    if not face_engine.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Face recognition model is not loaded. Please download w600k_r50.onnx into models/ "
                "following backend/models/README.md."
            )
        )

    raw_bytes = await image.read()
    try:
        img = ImageValidator.decode_image_bytes(raw_bytes)
        ImageValidator.validate_quality(img)

        # Align face if landmarks are transmitted from edge ESP32 detector
        if landmarks_json:
            landmarks = json.loads(landmarks_json)
            aligned = FaceAligner.align_face_112(img, landmarks)
        else:
            import cv2
            aligned = cv2.resize(img, (112, 112), interpolation=cv2.INTER_LINEAR)

        # Extract 512-D vector
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

    elapsed_ms = (time.time() - start_time) * 1000.0

    # In strict accordance with project rules:
    # "Do not create fake recognition results or mock successful recognition."
    # Vector matching against PostgreSQL + pgvector is scheduled for Stage 5.2.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"Stage 5.1 Foundation: Edge crop validated and 512-D embedding extracted in {elapsed_ms:.1f}ms. "
            "Vector database identity matching (pgvector) is scheduled for Stage 5.2. No mock result generated."
        )
    )
