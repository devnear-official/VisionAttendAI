"""Test image quality and landmark validation service."""

import cv2
import numpy as np
import pytest

from app.services.image_validation import (
    ImageValidationError,
    ImageValidator,
    LandmarkValidationError,
)


def test_decode_valid_image(sample_valid_face_image: bytes):
    img = ImageValidator.decode_image_bytes(sample_valid_face_image)
    assert isinstance(img, np.ndarray)
    assert img.shape == (160, 160, 3)


def test_decode_empty_bytes():
    with pytest.raises(ImageValidationError, match="empty or too small"):
        ImageValidator.decode_image_bytes(b"")


def test_decode_corrupted_bytes():
    with pytest.raises(ImageValidationError, match="Failed to decode"):
        ImageValidator.decode_image_bytes(b"corrupted_non_image_binary_data_padding")


def test_validate_dimensions_too_small():
    tiny_img = np.full((32, 32, 3), 128, dtype=np.uint8)
    with pytest.raises(ImageValidationError, match="below minimum required"):
        ImageValidator.validate_quality(tiny_img, min_width=48, min_height=48)


def test_validate_blurry_image(sample_blurry_image: bytes):
    img = ImageValidator.decode_image_bytes(sample_blurry_image)
    with pytest.raises(ImageValidationError, match="too blurry"):
        ImageValidator.validate_quality(img, min_laplacian_var=50.0)


def test_validate_underexposed_image():
    dark_img = np.full((160, 160, 3), 10, dtype=np.uint8)
    with pytest.raises(ImageValidationError, match="underexposed"):
        ImageValidator.validate_quality(dark_img, min_brightness=25.0)


def test_validate_overexposed_image():
    bright_img = np.full((160, 160, 3), 250, dtype=np.uint8)
    with pytest.raises(ImageValidationError, match="overexposed"):
        ImageValidator.validate_quality(bright_img, max_brightness=235.0)


def test_validate_valid_landmarks(sample_valid_landmarks: list):
    pts = ImageValidator.validate_landmarks(sample_valid_landmarks, (160, 160))
    assert pts.shape == (5, 2)
    assert pts.dtype == np.float32


def test_validate_landmarks_out_of_bounds():
    out_pts = [[60.0, 65.0], [200.0, 65.0], [80.0, 85.0], [65.0, 118.0], [95.0, 118.0]]
    with pytest.raises(LandmarkValidationError, match="outside image boundaries"):
        ImageValidator.validate_landmarks(out_pts, (160, 160))


def test_validate_landmarks_inverted_eyes():
    # Right eye X is smaller than Left eye X
    inverted_pts = [[100.0, 65.0], [60.0, 65.0], [80.0, 85.0], [65.0, 118.0], [95.0, 118.0]]
    with pytest.raises(LandmarkValidationError, match="Left eye X .* must be strictly to the left"):
        ImageValidator.validate_landmarks(inverted_pts, (160, 160))


def test_validate_landmarks_upside_down_mouth():
    # Mouth Y is above eyes Y
    upside_down = [[60.0, 100.0], [100.0, 100.0], [80.0, 85.0], [65.0, 50.0], [95.0, 50.0]]
    with pytest.raises(LandmarkValidationError, match="Eye level Y .* must be above mouth level"):
        ImageValidator.validate_landmarks(upside_down, (160, 160))
