
from types import SimpleNamespace

import pytest

from app.retrieval_service import EvidenceRetriever


class FakeEmbedder:
    def embed_texts(self, texts):
        vectors = []

        for text in texts:
            normalized = text.lower()

            if "payment" in normalized or "database" in normalized:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])

        return vectors


def make_evidence(evidence_id, content, source_type="log"):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=42,
        source_type=source_type,
        content=content,
    )


def test_retrieve_returns_relevant_evidence_first():
    retriever = EvidenceRetriever(embedder=FakeEmbedder())
    evidence = [
        make_evidence(1, "Database connection pool exhausted"),
        make_evidence(2, "Frontend styling changed"),
    ]

    results = retriever.retrieve(
        query="Why is the payment service failing?",
        evidence_items=evidence,
    )

    assert results[0].chunk.evidence_id == 1
    assert results[0].chunk.incident_id == 42
    assert results[0].chunk.source_type == "log"


def test_retrieve_returns_empty_for_no_evidence():
    retriever = EvidenceRetriever(embedder=FakeEmbedder())

    assert retriever.retrieve("payment failure", []) == []


def test_retrieve_rejects_blank_query():
    retriever = EvidenceRetriever(embedder=FakeEmbedder())

    with pytest.raises(ValueError, match="non-empty string"):
        retriever.retrieve("   ", [])


def test_retrieve_rejects_invalid_top_k():
    retriever = EvidenceRetriever(embedder=FakeEmbedder())

    with pytest.raises(ValueError, match="top_k must be positive"):
        retriever.retrieve("payment failure", [], top_k=0)


def test_retrieve_respects_top_k():
    retriever = EvidenceRetriever(embedder=FakeEmbedder())
    evidence = [
        make_evidence(1, "Database connection pool exhausted"),
        make_evidence(2, "Payment database latency increased"),
        make_evidence(3, "Frontend styling changed"),
    ]

    results = retriever.retrieve(
        query="payment failure",
        evidence_items=evidence,
        top_k=1,
    )

    assert len(results) == 1


class CountingFakeEmbedder(FakeEmbedder):
    def __init__(self):
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        return super().embed_texts(texts)


def test_retrieve_reuses_cached_evidence_embeddings():
    embedder = CountingFakeEmbedder()
    retriever = EvidenceRetriever(embedder=embedder)
    evidence = [
        make_evidence(1, "Database connection pool exhausted"),
        make_evidence(2, "Frontend styling changed"),
    ]

    retriever.retrieve("Why is payment failing?", evidence)
    first_call_count = len(embedder.calls)

    retriever.retrieve("What caused the payment issue?", evidence)

    assert len(embedder.calls) == first_call_count + 1
    assert embedder.calls[-1] == [
        "What caused the payment issue?"
    ]


def test_retrieve_cache_respects_maximum_size():
    embedder = CountingFakeEmbedder()
    retriever = EvidenceRetriever(
        embedder=embedder,
        cache_size=1,
    )
    evidence = [
        make_evidence(1, "Database connection pool exhausted"),
        make_evidence(2, "Frontend styling changed"),
    ]

    retriever.retrieve("Why is payment failing?", evidence)

    assert len(retriever._embedding_cache) == 1


def test_retrieve_rejects_invalid_cache_size():
    with pytest.raises(ValueError, match="cache_size must be positive"):
        EvidenceRetriever(embedder=FakeEmbedder(), cache_size=0)
