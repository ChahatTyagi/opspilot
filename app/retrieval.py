
from dataclasses import dataclass
from math import sqrt

from app.chunking import EvidenceChunk


@dataclass(frozen=True)
class RetrievalResult:
    chunk: EvidenceChunk
    score: float


def cosine_similarity(
    left: list[float],
    right: list[float],
) -> float:
    """Measure the cosine similarity between two vectors."""

    if not left or not right:
        raise ValueError("vectors must not be empty")

    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")

    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))

    if left_norm == 0 or right_norm == 0:
        raise ValueError("vectors must have non-zero magnitude")

    dot_product = sum(a * b for a, b in zip(left, right))

    return dot_product / (left_norm * right_norm)


def rank_chunks(
    query_embedding: list[float],
    chunks: list[EvidenceChunk],
    chunk_embeddings: list[list[float]],
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Rank evidence chunks by cosine similarity to a query."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")

    if len(chunks) != len(chunk_embeddings):
        raise ValueError("each chunk must have one embedding")

    scored_results = []

    for chunk, embedding in zip(chunks, chunk_embeddings):
        score = cosine_similarity(query_embedding, embedding)
        scored_results.append(RetrievalResult(chunk=chunk, score=score))

    scored_results.sort(key=lambda result: result.score, reverse=True)

    return scored_results[:top_k]
