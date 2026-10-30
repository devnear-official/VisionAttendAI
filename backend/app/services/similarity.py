"""Vector similarity computation and match classification service."""

from typing import Tuple, List
import numpy as np

from app.core.config import get_settings
from app.schemas.face import MatchStatus

settings = get_settings()


class SimilarityService:
    """
    Computes cosine similarity between 512-D L2-normalized embeddings and evaluates
    identity match thresholds.

    NOTE ON CALIBRATION:
    Threshold values (default: MATCH >= 0.65, AMBIGUOUS >= 0.50) are empirical baselines.
    In real production deployment, optimal thresholds MUST be calibrated using a dedicated
    validation dataset with False Acceptance Rate (FAR) vs False Rejection Rate (FRR) curves.
    """

    @staticmethod
    def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """
        Compute cosine similarity between two 512-D embedding vectors.
        For L2-normalized vectors, cosine similarity equals the dot product.
        """
        if vec_a.shape != (512,) or vec_b.shape != (512,):
            raise ValueError(
                f"Embedding vector dimension mismatch. Both vectors must be (512,). "
                f"Got vec_a: {vec_a.shape}, vec_b: {vec_b.shape}."
            )

        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)

        if norm_a == 0.0 or norm_b == 0.0 or np.isnan(norm_a) or np.isnan(norm_b):
            raise ValueError("Zero or NaN norm encountered in similarity calculation.")

        # Dot product of normalized vectors
        cos_sim = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
        # Clamp to [-1.0, 1.0] to handle slight floating point imprecision
        return float(np.clip(cos_sim, -1.0, 1.0))

    @staticmethod
    def classify_match(
        similarity: float,
        match_thr: float | None = None,
        ambiguous_thr: float | None = None
    ) -> MatchStatus:
        """Categorize a similarity score into MATCH, AMBIGUOUS, or UNKNOWN."""
        m_thr = match_thr if match_thr is not None else settings.SIMILARITY_MATCH_THRESHOLD
        a_thr = ambiguous_thr if ambiguous_thr is not None else settings.SIMILARITY_AMBIGUOUS_THRESHOLD

        if similarity >= m_thr:
            return MatchStatus.MATCH
        elif similarity >= a_thr:
            return MatchStatus.AMBIGUOUS
        else:
            return MatchStatus.UNKNOWN

    @classmethod
    def find_best_match(
        cls,
        query_vec: np.ndarray,
        candidate_embeddings: List[Tuple[str, np.ndarray]],  # list of (person_id, embedding)
        match_thr: float | None = None,
        ambiguous_thr: float | None = None
    ) -> Tuple[MatchStatus, float, str | None]:
        """
        Search for the closest embedding among a list of candidates.
        Returns: (MatchStatus, highest_similarity, best_person_id_or_none)
        """
        if not candidate_embeddings:
            return MatchStatus.UNKNOWN, 0.0, None

        best_score = -1.0
        best_id = None

        for person_id, emb in candidate_embeddings:
            sim = cls.cosine_similarity(query_vec, emb)
            if sim > best_score:
                best_score = sim
                best_id = person_id

        status = cls.classify_match(best_score, match_thr, ambiguous_thr)
        matched_id = best_id if status != MatchStatus.UNKNOWN else None
        return status, best_score, matched_id
