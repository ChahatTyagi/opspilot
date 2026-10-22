
import pytest

from app.chunking import EvidenceChunk
from app.retrieval import cosine_similarity, rank_chunks


def make_chunk(evidence_id: int, text: str) -> EvidenceChunk:
    return EvidenceChunk(
        incident_id=1,
        evidence_id=evidence_id,
        source_type="log",
        chunk_index=0,
        text=text,
    )


def test_identical_vectors_have_similarity_one():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_orthogonal_vectors_have_similarity_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_opposite_vectors_have_similarity_negative_one():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_similarity_rejects_mismatched_dimensions():
    with pytest.raises(ValueError, match="same dimensions"):
        cosine_similarity([1.0, 0.0], [1.0])


def test_similarity_rejects_zero_vectors():
    with pytest.raises(ValueError, match="non-zero magnitude"):
        cosine_similarity([0.0, 0.0], [1.0, 0.0])


def test_rank_chunks_returns_most_similar_first():
    chunks = [
        make_chunk(1, "unrelated frontend event"),
        make_chunk(2, "database connection failure"),
        make_chunk(3, "payment service timeout"),
    ]
    embeddings = [
        [0.0, 1.0],
        [0.8, 0.2],
        [1.0, 0.0],
    ]

    results = rank_chunks(
        query_embedding=[1.0, 0.0],
        chunks=chunks,
        chunk_embeddings=embeddings,
    )

    assert [result.chunk.evidence_id for result in results] == [3, 2, 1]
    assert results[0].score == pytest.approx(1.0)


def test_rank_chunks_respects_top_k():
    chunks = [make_chunk(1, "first"), make_chunk(2, "second")]
    embeddings = [[1.0, 0.0], [0.0, 1.0]]

    results = rank_chunks([1.0, 0.0], chunks, embeddings, top_k=1)

    assert len(results) == 1
    assert results[0].chunk.evidence_id == 1


def test_rank_chunks_rejects_invalid_top_k():
    with pytest.raises(ValueError, match="top_k must be positive"):
        rank_chunks([1.0], [], [], top_k=0)


def test_rank_chunks_rejects_missing_embeddings():
    with pytest.raises(ValueError, match="one embedding"):
        rank_chunks([1.0], [make_chunk(1, "text")], [])


def test_rank_chunks_returns_empty_for_no_chunks():
    assert rank_chunks([1.0, 0.0], [], []) == []
