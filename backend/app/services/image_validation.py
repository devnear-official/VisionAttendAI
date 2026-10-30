"""Image decoding and quality validation service."""

from typing import List, Tuple
import cv2
import numpy as np

from app.core.config import get_settings
from app.schemas.face import FiveLandmarks

settings = get_settings()


class ImageValidationError(ValueError):
    """Raised when an input image fails decoding or quality validation."""
    pass


class LandmarkValidationError(ValueError):
    """Raised when facial landmarks are missing, out-of-bounds, or geometrically invalid."""
    pass


class ImageValidator:
    """Validates raw image bytes and facial landmarks."""

    @staticmethod
    def decode_image_bytes(image_bytes: bytes) -> np.ndarray:
        """Decode raw image bytes into a BGR uint8 NumPy array."""
        if not image_bytes or len(image_bytes) < 16:
            raise ImageValidationError("Image payload is empty or too small to be a valid image file.")

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None or img.size == 0:
            raise ImageValidationError("Failed to decode image. Unsupported or corrupted file format.")

        return img

    @staticmethod
    def validate_quality(
        img: np.ndarray,
        min_width: int | None = None,
        min_height: int | None = None,
        min_laplacian_var: float | None = None,
        min_brightness: float | None = None,
        max_brightness: float | None = None,
    ) -> dict:
        """Check image dimensions, blur, and lighting exposure."""
        h, w = img.shape[:2]
        mw = min_width if min_width is not None else settings.MIN_FACE_WIDTH
        mh = min_height if min_height is not None else settings.MIN_FACE_HEIGHT

        if w < mw or h < mh:
            raise ImageValidationError(
                f"Image dimensions ({w}x{h}) are below minimum required face resolution ({mw}x{mh})."
            )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. Exposure / Brightness check (check before blur, since pitch black or washed white lacks edges)
        mean_brightness = float(np.mean(gray))
        mb = min_brightness if min_brightness is not None else settings.MIN_BRIGHTNESS
        xb = max_brightness if max_brightness is not None else settings.MAX_BRIGHTNESS

        if mean_brightness < mb:
            raise ImageValidationError(
                f"Image is severely underexposed/dark (average brightness: {mean_brightness:.1f} < {mb:.1f})."
            )
        if mean_brightness > xb:
            raise ImageValidationError(
                f"Image is severely overexposed/washed out (average brightness: {mean_brightness:.1f} > {xb:.1f})."
            )

        # 2. Blur check via Laplacian variance
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        mlv = min_laplacian_var if min_laplacian_var is not None else settings.MIN_LAPLACIAN_VARIANCE
        if laplacian_var < mlv:
            raise ImageValidationError(
                f"Image is too blurry (Laplacian variance: {laplacian_var:.1f} < threshold {mlv:.1f})."
            )

        return {
            "width": w,
            "height": h,
            "laplacian_variance": laplacian_var,
            "mean_brightness": mean_brightness,
        }

    @staticmethod
    def validate_landmarks(
        landmarks: FiveLandmarks | List[List[float]],
        image_shape: Tuple[int, int]
    ) -> np.ndarray:
        """
        Validate 5-point facial landmarks against image dimensions and geometric plausibility.
        Returns a (5, 2) float32 NumPy array.
        """
        h, w = image_shape[:2]

        if isinstance(landmarks, FiveLandmarks):
            pts = np.array(landmarks.as_list(), dtype=np.float32)
        else:
            pts = np.array(landmarks, dtype=np.float32)

        if pts.shape != (5, 2):
            raise LandmarkValidationError(
                f"Landmarks must contain exactly 5 points of (x, y) coordinates. Found shape {pts.shape}."
            )

        # Bounds check
        if np.any(pts < 0.0):
            raise LandmarkValidationError("Landmark coordinates cannot be negative.")
        if np.any(pts[:, 0] > w) or np.any(pts[:, 1] > h):
            raise LandmarkValidationError(
                f"Landmark coordinates fall outside image boundaries ({w}x{h})."
            )

        # Geometric sanity check
        left_eye, right_eye, nose, left_mouth, right_mouth = pts

        # In image coordinates: X increases rightwards, Y increases downwards.
        # Left eye (subject's right or viewer's left) must have a smaller X than right eye
        if left_eye[0] >= right_eye[0]:
            raise LandmarkValidationError(
                f"Geometric inconsistency: Left eye X ({left_eye[0]:.1f}) must be strictly to the left of Right eye X ({right_eye[0]:.1f})."
            )

        # Eyes must be located vertically above the mouth corners (smaller Y)
        eyes_y = (left_eye[1] + right_eye[1]) / 2.0
        mouth_y = (left_mouth[1] + right_mouth[1]) / 2.0
        if eyes_y >= mouth_y:
            raise LandmarkValidationError(
                f"Geometric inconsistency: Eye level Y ({eyes_y:.1f}) must be above mouth level Y ({mouth_y:.1f})."
            )

        return pts
