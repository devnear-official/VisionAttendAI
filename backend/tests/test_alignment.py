"""Test facial alignment service."""

import numpy as np
import pytest

from app.services.face_alignment import FaceAligner
from app.services.image_validation import ImageValidator, LandmarkValidationError


def test_align_face_shape_and_dtype(sample_valid_face_image: bytes, sample_valid_landmarks: list):
    img = ImageValidator.decode_image_bytes(sample_valid_face_image)
    aligned = FaceAligner.align_face_112(img, sample_valid_landmarks)

    assert isinstance(aligned, np.ndarray)
    assert aligned.shape == (112, 112, 3)
    assert aligned.dtype == np.uint8


def test_align_face_invalid_landmarks(sample_valid_face_image: bytes):
    img = ImageValidator.decode_image_bytes(sample_valid_face_image)
    invalid_landmarks = [[10.0, 10.0]]  # Only 1 point instead of 5

    with pytest.raises(LandmarkValidationError, match="must contain exactly 5 points"):
        FaceAligner.align_face_112(img, invalid_landmarks)
