"""Test cosine similarity math and classification logic."""

import numpy as np
import pytest

from app.schemas.face import MatchStatus
from app.services.similarity import SimilarityService


def test_cosine_similarity_identical_vectors():
    vec = np.random.randn(512).astype(np.float32)
    vec /= np.linalg.norm(vec)

    sim = SimilarityService.cosine_similarity(vec, vec)
    assert pytest.approx(sim, abs=1e-5) == 1.0


def test_cosine_similarity_opposite_vectors():
    vec = np.random.randn(512).astype(np.float32)
    vec /= np.linalg.norm(vec)

    sim = SimilarityService.cosine_similarity(vec, -vec)
    assert pytest.approx(sim, abs=1e-5) == -1.0


def test_cosine_similarity_orthogonal_vectors():
    vec_a = np.zeros(512, dtype=np.float32)
    vec_b = np.zeros(512, dtype=np.float32)
    vec_a[0] = 1.0
    vec_b[1] = 1.0

    sim = SimilarityService.cosine_similarity(vec_a, vec_b)
    assert pytest.approx(sim, abs=1e-5) == 0.0


def test_cosine_similarity_dimension_mismatch():
    vec_512 = np.ones(512, dtype=np.float32)
    vec_128 = np.ones(128, dtype=np.float32)

    with pytest.raises(ValueError, match="Both vectors must be .*512"):
        SimilarityService.cosine_similarity(vec_512, vec_128)


def test_classify_match_categories():
    # Test configurable threshold classification
    match_thr = 0.65
    ambiguous_thr = 0.50

    # Above match threshold -> MATCH
    assert SimilarityService.classify_match(0.85, match_thr, ambiguous_thr) == MatchStatus.MATCH
    assert SimilarityService.classify_match(0.65, match_thr, ambiguous_thr) == MatchStatus.MATCH

    # Between ambiguous and match -> AMBIGUOUS
    assert SimilarityService.classify_match(0.64, match_thr, ambiguous_thr) == MatchStatus.AMBIGUOUS
    assert SimilarityService.classify_match(0.50, match_thr, ambiguous_thr) == MatchStatus.AMBIGUOUS

    # Below ambiguous threshold -> UNKNOWN
    assert SimilarityService.classify_match(0.49, match_thr, ambiguous_thr) == MatchStatus.UNKNOWN
    assert SimilarityService.classify_match(0.12, match_thr, ambiguous_thr) == MatchStatus.UNKNOWN


def test_find_best_match():
    # Setup candidate vectors
    target_vec = np.zeros(512, dtype=np.float32)
    target_vec[0] = 1.0

    match_vec = np.zeros(512, dtype=np.float32)
    match_vec[0] = 0.9
    match_vec[1] = 0.43588989  # norm = 1.0, dot product with target = 0.90
    match_vec /= np.linalg.norm(match_vec)

    other_vec = np.zeros(512, dtype=np.float32)
    other_vec[10] = 1.0

    candidates = [
        ("student_001", other_vec),
        ("student_002", match_vec),
    ]

    status, score, matched_id = SimilarityService.find_best_match(
        target_vec, candidates, match_thr=0.65, ambiguous_thr=0.50
    )

    assert status == MatchStatus.MATCH
    assert matched_id == "student_002"
    assert score >= 0.89
