
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceChunk:
    incident_id: int
    evidence_id: int
    source_type: str
    chunk_index: int
    text: str


def chunk_text(
    text: str,
    chunk_size: int = 100,
    overlap: int = 20,
) -> list[str]:
    """Split text into word-based chunks with overlapping context."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0:
        raise ValueError("overlap cannot be negative")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    words = text.split()

    if not words:
        return []

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))

        if end == len(words):
            break

        start = end - overlap

    return chunks


def chunk_evidence(
    evidence,
    chunk_size: int = 100,
    overlap: int = 20,
) -> list[EvidenceChunk]:
    """Chunk evidence while preserving its incident and source metadata."""

    text_chunks = chunk_text(
        evidence.content,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    return [
        EvidenceChunk(
            incident_id=evidence.incident_id,
            evidence_id=evidence.id,
            source_type=evidence.source_type,
            chunk_index=index,
            text=text,
        )
        for index, text in enumerate(text_chunks)
    ]
