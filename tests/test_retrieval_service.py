
import json
from types import SimpleNamespace

import pytest

from app.retrieval_service import EvidenceRetriever
from app.embeddings import LocalEmbedder
from app.ollama_embeddings import OllamaEmbedder


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


class ConstantFakeEmbedder:
    """Return identical vectors to isolate topology ranking behaviour."""

    def embed_texts(self, texts):
        return [[1.0, 0.0] for _ in texts]


def make_evidence(evidence_id, content, source_type="log"):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=42,
        source_type=source_type,
        content=content,
    )


def make_trace(
    evidence_id,
    service_name,
    span_id,
    trace_id="1" * 32,
    parent_span_id=None,
):
    record = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "service_name": service_name,
        "span_name": "request",
        "status_code": 0,
        "duration_ms": 5.0,
    }

    return make_evidence(
        evidence_id,
        json.dumps(record),
        source_type="trace",
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


@pytest.mark.parametrize(
    "returned_vectors",
    [
        [[1.0, 0.0]],
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.5, 0.5],
        ],
    ],
)
def test_retrieve_rejects_wrong_number_of_embedding_vectors(
    returned_vectors,
):
    class MalformedEmbedder:
        def embed_texts(self, texts):
            return returned_vectors

    retriever = EvidenceRetriever(embedder=MalformedEmbedder())
    evidence = [
        make_evidence(1, "Database connection pool exhausted")
    ]

    with pytest.raises(
        ValueError,
        match="embedder must return one vector per input text",
    ):
        retriever.retrieve("Why is payment failing?", evidence)

    assert retriever._embedding_cache == {}


def test_retriever_defaults_to_local_embedder(monkeypatch):
    monkeypatch.setattr(
        "app.retrieval_service.get_embedding_provider",
        lambda: "local",
    )

    retriever = EvidenceRetriever()

    assert isinstance(retriever.embedder, LocalEmbedder)


def test_retriever_selects_ollama_embedder(monkeypatch):
    monkeypatch.setattr(
        "app.retrieval_service.get_embedding_provider",
        lambda: "ollama",
    )

    retriever = EvidenceRetriever()

    assert isinstance(retriever.embedder, OllamaEmbedder)


def test_retriever_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr(
        "app.retrieval_service.get_embedding_provider",
        lambda: "unsupported",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported embedding provider",
    ):
        EvidenceRetriever()


def test_explicit_embedder_overrides_configured_provider(monkeypatch):
    embedder = FakeEmbedder()

    def unexpected_provider_lookup():
        raise AssertionError(
            "Provider should not be checked when an embedder is supplied"
        )

    monkeypatch.setattr(
        "app.retrieval_service.get_embedding_provider",
        unexpected_provider_lookup,
    )

    retriever = EvidenceRetriever(embedder=embedder)

    assert retriever.embedder is embedder


def test_topology_boosts_traces_for_mentioned_service_and_dependency():
    retriever = EvidenceRetriever(embedder=ConstantFakeEmbedder())

    evidence = [
        make_trace(
            evidence_id=1,
            service_name="frontend",
            span_id="c" * 16,
            trace_id="2" * 32,
        ),
        make_trace(
            evidence_id=2,
            service_name="database",
            span_id="a" * 16,
        ),
        make_trace(
            evidence_id=3,
            service_name="payment-service",
            span_id="b" * 16,
            parent_span_id="a" * 16,
        ),
    ]

    results = retriever.retrieve(
        query="Investigate the payment service failure",
        evidence_items=evidence,
        top_k=3,
    )

    returned_ids = [
        result.chunk.evidence_id
        for result in results
    ]

    # The payment service and its directly connected database dependency
    # are promoted above the unrelated frontend trace.
    assert returned_ids == [2, 3, 1]

    assert results[0].score == pytest.approx(1.10)
    assert results[1].score == pytest.approx(1.10)
    assert results[2].score == pytest.approx(1.00)


def test_topology_does_not_change_ranking_when_query_has_no_service_match():
    retriever = EvidenceRetriever(embedder=ConstantFakeEmbedder())

    evidence = [
        make_trace(
            evidence_id=1,
            service_name="frontend",
            span_id="c" * 16,
            trace_id="2" * 32,
        ),
        make_trace(
            evidence_id=2,
            service_name="database",
            span_id="a" * 16,
        ),
        make_trace(
            evidence_id=3,
            service_name="payment-service",
            span_id="b" * 16,
            parent_span_id="a" * 16,
        ),
    ]

    results = retriever.retrieve(
        query="Investigate an unknown failure",
        evidence_items=evidence,
        top_k=3,
    )

    assert [
        result.chunk.evidence_id
        for result in results
    ] == [1, 2, 3]

    assert all(
        result.score == pytest.approx(1.0)
        for result in results
    )


def test_topology_does_not_boost_log_evidence():
    retriever = EvidenceRetriever(embedder=ConstantFakeEmbedder())

    evidence = [
        make_evidence(
            1,
            "Payment service returned an error",
            source_type="log",
        ),
        make_trace(
            evidence_id=2,
            service_name="payment-service",
            span_id="a" * 16,
        ),
    ]

    results = retriever.retrieve(
        query="Investigate the payment service failure",
        evidence_items=evidence,
        top_k=2,
    )

    assert results[0].chunk.evidence_id == 2
    assert results[0].score == pytest.approx(1.10)

    assert results[1].chunk.evidence_id == 1
    assert results[1].score == pytest.approx(1.00)



def test_topology_does_not_match_partial_service_name():
    retriever = EvidenceRetriever(embedder=ConstantFakeEmbedder())

    evidence = [
        make_trace(
            evidence_id=1,
            service_name="pay",
            span_id="a" * 16,
        ),
        make_trace(
            evidence_id=2,
            service_name="frontend",
            span_id="b" * 16,
            trace_id="2" * 32,
        ),
    ]

    results = retriever.retrieve(
        query="Investigate the payment service failure",
        evidence_items=evidence,
        top_k=2,
    )

    assert [
        result.chunk.evidence_id
        for result in results
    ] == [1, 2]

    assert all(
        result.score == pytest.approx(1.0)
        for result in results
    )
