"""pgvector cosine similarity search service for face recognition."""

from typing import List, Optional, Tuple, Union
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import Student, StudentFaceEmbedding
from app.schemas.face import MatchStatus
from app.services.embedding_service import EmbeddingService
from app.utils.logger import logger

settings = get_settings()


class VectorSearchService:
    """Performs cosine distance similarity queries over pgvector embeddings."""

    @classmethod
    def search_closest_face(
        cls,
        db: Session,
        query_embedding: Union[np.ndarray, List[float]],
        match_thr: Optional[float] = None,
        ambiguous_thr: Optional[float] = None,
        exclude_student_id: Optional[str] = None,
    ) -> Tuple[MatchStatus, float, Optional[Student]]:
        """
        Search for the closest active face embedding in PostgreSQL + pgvector.

        Returns: (MatchStatus, similarity_score, matched_student_or_none)
        """
        valid_query = EmbeddingService.validate_embedding(query_embedding)

        m_thr = match_thr if match_thr is not None else settings.SIMILARITY_MATCH_THRESHOLD
        a_thr = ambiguous_thr if ambiguous_thr is not None else settings.SIMILARITY_AMBIGUOUS_THRESHOLD

        # Query using pgvector cosine_distance operator (<=>)
        # Cosine distance d = 1 - cosine_similarity. Similarity s = 1 - d.
        distance_expr = StudentFaceEmbedding.embedding.cosine_distance(valid_query).label("distance")

        stmt = (
            select(StudentFaceEmbedding, Student, distance_expr)
            .join(Student, StudentFaceEmbedding.student_id == Student.id)
            .where(
                StudentFaceEmbedding.is_active.is_(True),
                Student.deleted_at.is_(None),
                Student.status == "active",
            )
        )

        if exclude_student_id:
            stmt = stmt.where(Student.student_id != exclude_student_id)

        stmt = stmt.order_by(distance_expr.asc()).limit(1)

        result = db.execute(stmt).first()

        if not result:
            return MatchStatus.UNKNOWN, 0.0, None

        embedding_rec, student_rec, distance = result
        similarity = float(np.clip(1.0 - distance, -1.0, 1.0))

        if similarity >= m_thr:
            status = MatchStatus.MATCH
            matched_student = student_rec
        elif similarity >= a_thr:
            status = MatchStatus.AMBIGUOUS
            matched_student = student_rec
        else:
            status = MatchStatus.UNKNOWN
            matched_student = None

        logger.info(
            f"pgvector search: Best candidate student='{student_rec.student_id}', "
            f"similarity={similarity:.4f}, status={status.value}"
        )

        return status, similarity, matched_student

    @classmethod
    def check_duplicate_enrollment(
        cls,
        db: Session,
        embeddings: List[Union[np.ndarray, List[float]]],
        exclude_student_id: Optional[str] = None,
        duplicate_threshold: float = 0.70,
    ) -> Optional[Tuple[Student, float]]:
        """
        Checks whether any candidate enrollment embedding matches an existing student.
        Returns (existing_student, highest_similarity) if similarity exceeds duplicate_threshold,
        otherwise None.
        """
        for emb in embeddings:
            status, score, matched_student = cls.search_closest_face(
                db,
                emb,
                match_thr=duplicate_threshold,
                ambiguous_thr=duplicate_threshold,
                exclude_student_id=exclude_student_id,
            )
            if matched_student is not None and score >= duplicate_threshold:
                return matched_student, score

        return None
