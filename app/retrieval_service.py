
from app.chunking import chunk_evidence
from app.embeddings import LocalEmbedder
from app.retrieval import RetrievalResult, rank_chunks


class EvidenceRetriever:
    """Orchestrate evidence chunking, embedding, and retrieval."""

    def __init__(self, embedder=None):
        self.embedder = embedder or LocalEmbedder()

    def retrieve(
        self,
        query: str,
        evidence_items: list,
        top_k: int = 5,
        chunk_size: int = 100,
        overlap: int = 20,
    ) -> list[RetrievalResult]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        if top_k <= 0:
            raise ValueError("top_k must be positive")

        chunks = []

        for evidence in evidence_items:
            chunks.extend(
                chunk_evidence(
                    evidence,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
            )

        if not chunks:
            return []

        texts = [query] + [chunk.text for chunk in chunks]
        vectors = self.embedder.embed_texts(texts)

        return rank_chunks(
            query_embedding=vectors[0],
            chunks=chunks,
            chunk_embeddings=vectors[1:],
            top_k=top_k,
        )
