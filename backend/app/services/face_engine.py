"""InsightFace ArcFace ONNX Runtime Inference Engine."""

from pathlib import Path
from typing import Dict, Any, Optional
import cv2
import numpy as np
import onnxruntime as ort

from app.core.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class ModelNotAvailableError(RuntimeError):
    """Raised when face recognition model weights are not found or failed to load."""
    pass


class FaceRecognitionEngine:
    """Manages ONNX Runtime session for 512-D ArcFace feature vector extraction."""

    def __init__(self):
        self._session: Optional[ort.InferenceSession] = None
        self._model_path: Path = settings.model_path
        self._is_loaded: bool = False
        self._input_name: Optional[str] = None
        self._output_name: Optional[str] = None
        self._input_shape: Optional[list] = None
        self._load_error: Optional[str] = None

    def initialize(self) -> bool:
        """Attempt to load ONNX model weights from disk."""
        if not self._model_path.exists():
            self._load_error = (
                f"Model file not found at {self._model_path}. "
                "Download w600k_r50.onnx into backend/models/ as documented in backend/models/README.md."
            )
            logger.warning(f"FaceRecognitionEngine: {self._load_error}")
            self._is_loaded = False
            return False

        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = settings.ONNX_INTRA_OP_NUM_THREADS
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            providers = [settings.ONNX_EXECUTION_PROVIDER]
            if settings.ONNX_EXECUTION_PROVIDER not in ort.get_available_providers():
                logger.warning(
                    f"Requested provider {settings.ONNX_EXECUTION_PROVIDER} unavailable. "
                    f"Falling back to CPUExecutionProvider."
                )
                providers = ["CPUExecutionProvider"]

            self._session = ort.InferenceSession(
                str(self._model_path),
                sess_options=opts,
                providers=providers
            )

            inputs = self._session.get_inputs()
            outputs = self._session.get_outputs()

            self._input_name = inputs[0].name
            self._input_shape = inputs[0].shape
            self._output_name = outputs[0].name

            self._is_loaded = True
            self._load_error = None
            logger.info(
                f"FaceRecognitionEngine: Successfully loaded {self._model_path.name} "
                f"(Input: {self._input_name} {self._input_shape}, Output: {self._output_name})"
            )
            return True

        except Exception as e:
            self._load_error = f"Failed to initialize ONNX Runtime session: {str(e)}"
            logger.error(self._load_error)
            self._session = None
            self._is_loaded = False
            return False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def get_status_details(self) -> Dict[str, Any]:
        """Return diagnostic status of the recognition model engine."""
        return {
            "model_name": settings.FACE_RECOGNITION_MODEL_NAME,
            "model_path": str(self._model_path),
            "file_exists": self._model_path.exists(),
            "file_size_bytes": self._model_path.stat().st_size if self._model_path.exists() else 0,
            "is_loaded": self._is_loaded,
            "input_shape": self._input_shape,
            "execution_provider": settings.ONNX_EXECUTION_PROVIDER,
            "load_error": self._load_error,
            "license": "Non-Commercial / Academic Research (InsightFace buffalo_l)",
        }

    def extract_embedding(self, aligned_face_112: np.ndarray) -> np.ndarray:
        """
        Extract a 512-dimensional L2-normalized embedding vector from an aligned 112x112 BGR face image.
        Returns a float32 1D NumPy array of shape (512,).
        """
        if not self._is_loaded or self._session is None:
            raise ModelNotAvailableError(
                self._load_error or "Face recognition model is not loaded."
            )

        if aligned_face_112.shape != (112, 112, 3):
            raise ValueError(
                f"Aligned face image must have shape (112, 112, 3). Received {aligned_face_112.shape}."
            )

        # Standard InsightFace ArcFace Preprocessing:
        # 1. Color channel swap: BGR to RGB (ArcFace models expect RGB)
        # 2. Scaling and centering: (x - 127.5) / 127.5 = (x - 127.5) * (1 / 127.5)
        # 3. Transpose HWC (112, 112, 3) to NCHW (1, 3, 112, 112) float32
        blob = cv2.dnn.blobFromImages(
            [aligned_face_112],
            scalefactor=1.0 / 127.5,
            size=(112, 112),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
        )

        # Run inference
        outputs = self._session.run(
            [self._output_name],
            {self._input_name: blob}
        )

        raw_embedding = outputs[0].flatten()

        # Output shape validation
        if raw_embedding.shape[0] != 512:
            raise ValueError(
                f"Model output dimension mismatch: Expected 512, got {raw_embedding.shape[0]}."
            )

        # L2 Normalization
        norm = np.linalg.norm(raw_embedding)
        if norm == 0.0 or np.isnan(norm) or np.isinf(norm):
            raise ValueError("Zero or invalid vector norm computed during face embedding extraction.")

        normalized_embedding = (raw_embedding / norm).astype(np.float32)
        return normalized_embedding


# Global singleton instance
face_engine = FaceRecognitionEngine()
