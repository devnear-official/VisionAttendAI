"""Five-point facial landmark alignment service for 112x112 ArcFace input."""

import cv2
import numpy as np

from app.services.image_validation import ImageValidator, LandmarkValidationError

# Standard InsightFace / ArcFace 112x112 reference landmarks (Umeyama coordinate space)
ARCFACE_REFERENCE_LANDMARKS_112 = np.array(
    [
        [38.2946, 51.6963],  # Left Eye
        [73.5318, 51.5014],  # Right Eye
        [56.0252, 71.7366],  # Nose Tip
        [41.5493, 92.3655],  # Left Mouth Corner
        [70.7266, 92.2041],  # Right Mouth Corner
    ],
    dtype=np.float32,
)


class FaceAligner:
    """Warps an arbitrary face crop to standard 112x112 aligned format using 5 facial landmarks."""

    @staticmethod
    def align_face_112(
        img: np.ndarray,
        landmarks: np.ndarray | list,
        output_size: tuple[int, int] = (112, 112)
    ) -> np.ndarray:
        """
        Compute similarity transform matrix from input landmarks to standard 112x112 template
        and warp the face image.
        Returns uint8 BGR array of shape (112, 112, 3).
        """
        # Validate landmarks and shape
        pts = ImageValidator.validate_landmarks(landmarks, img.shape[:2])

        # Compute similarity transform (rotation + uniform scale + translation)
        # using estimateAffinePartial2D which is the robust Levenberg-Marquardt / LMedS estimator
        tform, inliers = cv2.estimateAffinePartial2D(
            pts,
            ARCFACE_REFERENCE_LANDMARKS_112,
            method=cv2.LMEDS
        )

        if tform is None:
            raise LandmarkValidationError("Failed to estimate affine transform from given landmarks.")

        # Warp image to standard 112x112 canvas
        aligned_face = cv2.warpAffine(
            img,
            tform,
            output_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0)
        )

        return aligned_face
