
from collections import OrderedDict

from app.chunking import chunk_evidence
from app.embeddings import LocalEmbedder
from app.retrieval import RetrievalResult, rank_chunks


class EvidenceRetriever:
    """Orchestrate evidence chunking, embedding, and retrieval."""

    def __init__(self, embedder=None, cache_size: int = 1000):
        if cache_size <= 0:
            raise ValueError("cache_size must be positive")

        self.embedder = (
            embedder if embedder is not None else LocalEmbedder()
        )
        self.cache_size = cache_size
        self._embedding_cache: OrderedDict[str, list[float]] = (
            OrderedDict()
        )

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

        chunk_texts = [chunk.text for chunk in chunks]

        missing_texts = list(
            dict.fromkeys(
                text
                for text in chunk_texts
                if text not in self._embedding_cache
            )
        )

        texts_to_embed = [query] + missing_texts
        vectors = self.embedder.embed_texts(texts_to_embed)


        new_embeddings = dict(zip(missing_texts, vectors[1:]))

        # Keep the current retrieval's vectors available, even if
        # the cache is too small to retain all of them.
        chunk_embeddings = [
            self._embedding_cache.get(text, new_embeddings.get(text))
            for text in chunk_texts
        ]

        for text, vector in new_embeddings.items():
            self._embedding_cache[text] = vector
            self._embedding_cache.move_to_end(text)

            while len(self._embedding_cache) > self.cache_size:
                self._embedding_cache.popitem(last=False)

        for text in dict.fromkeys(chunk_texts):
            if text in self._embedding_cache:
                self._embedding_cache.move_to_end(text)

        return rank_chunks(
            query_embedding=vectors[0],
            chunks=chunks,
            chunk_embeddings=chunk_embeddings,
            top_k=top_k,
        )
