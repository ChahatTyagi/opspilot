
from collections import OrderedDict
import re

from app.chunking import chunk_evidence
from app.config import get_embedding_provider
from app.embeddings import LocalEmbedder
from app.ollama_embeddings import OllamaEmbedder
from app.retrieval import RetrievalResult, rank_chunks
from app.telemetry import build_service_topology


TOPOLOGY_RELEVANCE_BOOST = 0.10


def _normalize_service_name(value: str) -> str:
    """Normalize service names and query text into whole-word tokens."""

    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _contains_phrase(query: str, phrase: str) -> bool:
    """Check whether all phrase tokens occur contiguously in the query."""

    query_tokens = query.split()
    phrase_tokens = phrase.split()

    if not phrase_tokens or len(phrase_tokens) > len(query_tokens):
        return False

    phrase_length = len(phrase_tokens)

    return any(
        query_tokens[index:index + phrase_length] == phrase_tokens
        for index in range(len(query_tokens) - phrase_length + 1)
    )


def _topology_relevant_evidence_ids(
    query: str,
    evidence_items: list,
) -> set[int]:
    """
    Find trace evidence supporting services mentioned in the query
    and their directly connected services.
    """

    if not any(
        getattr(evidence, "source_type", None) == "trace"
        for evidence in evidence_items
    ):
        return set()

    normalized_query = _normalize_service_name(query)

    if not normalized_query:
        return set()

    topology = build_service_topology(evidence_items)

    nodes = topology["nodes"]
    edges = topology["edges"]

    matched_services = {
        node["service"]
        for node in nodes
        if isinstance(node.get("service"), str)
        and _contains_phrase(
            normalized_query,
            _normalize_service_name(node["service"]),
        )
    }

    if not matched_services:
        return set()

    related_services = set(matched_services)
    relevant_evidence_ids: set[int] = set()

    # Include evidence directly supporting the mentioned services.
    for node in nodes:
        if node["service"] in matched_services:
            relevant_evidence_ids.update(
                evidence_id
                for evidence_id in node.get("evidence_ids", [])
                if isinstance(evidence_id, int)
                and not isinstance(evidence_id, bool)
            )

    # Include evidence and services on directly connected edges.
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        if source in matched_services or target in matched_services:
            if isinstance(source, str):
                related_services.add(source)

            if isinstance(target, str):
                related_services.add(target)

            relevant_evidence_ids.update(
                evidence_id
                for evidence_id in edge.get("evidence_ids", [])
                if isinstance(evidence_id, int)
                and not isinstance(evidence_id, bool)
            )

    # Include spans belonging to the directly connected services.
    for node in nodes:
        if node["service"] in related_services:
            relevant_evidence_ids.update(
                evidence_id
                for evidence_id in node.get("evidence_ids", [])
                if isinstance(evidence_id, int)
                and not isinstance(evidence_id, bool)
            )

    return relevant_evidence_ids


class EvidenceRetriever:
    """Orchestrate evidence chunking, embedding, and retrieval."""

    def __init__(
        self,
        embedder=None,
        cache_size: int = 1000,
    ):
        if cache_size <= 0:
            raise ValueError("cache_size must be positive")

        if embedder is not None:
            self.embedder = embedder
        else:
            provider = get_embedding_provider()

            if provider == "local":
                self.embedder = LocalEmbedder()

            elif provider == "ollama":
                self.embedder = OllamaEmbedder()

            else:
                raise ValueError(
                    f"Unsupported embedding provider: {provider}. "
                    "Supported providers are 'local' and 'ollama'."
                )

        self.cache_size = cache_size

        self._embedding_cache: OrderedDict[
            str, list[float]
        ] = OrderedDict()

    def retrieve(
        self,
        query: str,
        evidence_items: list,
        top_k: int = 5,
        chunk_size: int = 100,
        overlap: int = 20,
    ) -> list[RetrievalResult]:
        """Retrieve relevant evidence using semantic and topology signals."""

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

        chunk_texts = [
            chunk.text for chunk in chunks
        ]

        missing_texts = list(
            dict.fromkeys(
                text
                for text in chunk_texts
                if text not in self._embedding_cache
            )
        )

        texts_to_embed = [query] + missing_texts

        vectors = self.embedder.embed_texts(
            texts_to_embed
        )

        if len(vectors) != len(texts_to_embed):
            raise ValueError(
                "embedder must return one vector per input text"
            )

        new_embeddings = dict(
            zip(missing_texts, vectors[1:])
        )

        # Keep the current retrieval's vectors available,
        # even if the cache is too small to retain all of them.
        chunk_embeddings = [
            self._embedding_cache.get(
                text,
                new_embeddings.get(text),
            )
            for text in chunk_texts
        ]

        # Insert new embeddings into the LRU cache.
        for text, vector in new_embeddings.items():
            self._embedding_cache[text] = vector
            self._embedding_cache.move_to_end(text)

            while len(self._embedding_cache) > self.cache_size:
                self._embedding_cache.popitem(last=False)

        # Mark reused embeddings as recently accessed.
        for text in dict.fromkeys(chunk_texts):
            if text in self._embedding_cache:
                self._embedding_cache.move_to_end(text)

        # Rank all chunks so topology can promote relevant traces.
        semantic_results = rank_chunks(
            query_embedding=vectors[0],
            chunks=chunks,
            chunk_embeddings=chunk_embeddings,
            top_k=len(chunks),
        )

        relevant_topology_ids = _topology_relevant_evidence_ids(
            query=query,
            evidence_items=evidence_items,
        )

        if not relevant_topology_ids:
            return semantic_results[:top_k]

        adjusted_results = [
            RetrievalResult(
                chunk=result.chunk,
                score=(
                    result.score + TOPOLOGY_RELEVANCE_BOOST
                    if (
                        result.chunk.source_type == "trace"
                        and result.chunk.evidence_id
                        in relevant_topology_ids
                    )
                    else result.score
                ),
            )
            for result in semantic_results
        ]

        adjusted_results.sort(
            key=lambda result: result.score,
            reverse=True,
        )

        return adjusted_results[:top_k]
