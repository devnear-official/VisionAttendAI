"""Face embedding validation and database persistence service."""

import uuid
from typing import List, Union
import numpy as np
from sqlalchemy.orm import Session

from app.database.models import StudentFaceEmbedding
from app.utils.logger import logger


class EmbeddingValidationError(ValueError):
    """Raised when an embedding vector fails dimension, finiteness, or normalization checks."""
    pass


class EmbeddingService:
    """Validates and persists 512-dimensional face embeddings."""

    @staticmethod
    def validate_embedding(embedding: Union[np.ndarray, List[float]]) -> np.ndarray:
        """
        Validate that an embedding is a 1D float32 array of shape (512,),
        contains only finite real values, and is L2-normalized.
        """
        if not isinstance(embedding, np.ndarray):
            arr = np.array(embedding, dtype=np.float32)
        else:
            arr = embedding.astype(np.float32)

        if arr.ndim != 1 or arr.shape[0] != 512:
            raise EmbeddingValidationError(
                f"Embedding vector must have exactly 512 dimensions. Got shape: {arr.shape}."
            )

        if not np.all(np.isfinite(arr)):
            raise EmbeddingValidationError("Embedding vector contains NaN or Infinite values.")

        norm = float(np.linalg.norm(arr))
        if norm == 0.0:
            raise EmbeddingValidationError("Embedding vector has zero norm.")

        # Check normalization (must be unit length ~ 1.0 within floating tolerance)
        if abs(norm - 1.0) > 1e-2:
            raise EmbeddingValidationError(
                f"Embedding vector is not L2-normalized (magnitude: {norm:.4f}, expected ~1.0)."
            )

        return arr

    @classmethod
    def store_student_embeddings(
        cls,
        db: Session,
        student_id: uuid.UUID,
        embeddings: List[Union[np.ndarray, List[float]]],
        model_name: str = "w600k_r50.onnx",
        model_version: str = "buffalo_l",
    ) -> List[StudentFaceEmbedding]:
        """Validate and store multiple face embeddings for a student transactionally."""
        if not embeddings:
            raise EmbeddingValidationError("At least one embedding is required to store.")

        records = []
        for emb in embeddings:
            valid_emb = cls.validate_embedding(emb)
            rec = StudentFaceEmbedding(
                student_id=student_id,
                embedding=valid_emb,
                model_name=model_name,
                model_version=model_version,
                is_active=True,
            )
            db.add(rec)
            records.append(rec)

        db.flush()
        logger.info(f"Stored {len(records)} face embedding(s) for student UUID: {student_id}")
        return records

    @staticmethod
    def deactivate_embeddings(db: Session, student_id: uuid.UUID) -> int:
        """Deactivate all active face embeddings for a student."""
        updated = (
            db.query(StudentFaceEmbedding)
            .filter(
                StudentFaceEmbedding.student_id == student_id,
                StudentFaceEmbedding.is_active.is_(True),
            )
            .update({"is_active": False}, synchronize_session="fetch")
        )
        db.flush()
        logger.info(f"Deactivated {updated} embedding(s) for student UUID: {student_id}")
        return updated
