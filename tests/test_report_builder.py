import pytest
from types import SimpleNamespace

from app.report_builder import build_investigation_report
from app.chunking import EvidenceChunk
from app.retrieval import RetrievalResult
def make_incident():
    return SimpleNamespace(
        id=1,
        title="Database connection failures",
        service="payment-service",
        severity="high",
        status="open",
    )


def make_evidence(source_type, content, evidence_id):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=1,
        source_type=source_type,
        content=content,
    )


def test_report_identifies_recurring_errors_and_evidence_gaps():
    incident = make_incident()
    evidence = [
        make_evidence(
            "log",
            "ERROR database connection failed for request 123",
            10,
        ),
        make_evidence(
            "log",
            "ERROR database connection failed for request 456",
            11,
        ),
    ]

    report = build_investigation_report(incident, evidence)

    assert report.incident_id == 1
    assert report.evidence_count == 2
    assert report.recurring_patterns
    assert report.recurring_patterns[0].occurrences == 2
    assert report.recurring_patterns[0].evidence_ids == [10, 11]
    assert report.hypotheses
    assert report.evidence_gaps
    assert any(
        "root cause" in hypothesis.lower()
        for hypothesis in report.hypotheses
    )


def test_report_handles_empty_evidence():
    report = build_investigation_report(make_incident(), [])

    assert report.evidence_count == 0
    assert report.recurring_patterns == []
    assert report.hypotheses == []
    assert report.evidence_gaps
    assert report.recommended_checks
    assert report.retrieved_evidence == []


def test_report_uses_metrics_and_deployments_when_available():
    evidence = [
        make_evidence("metric", "Error rate: 12%", 20),
        make_evidence("deployment", "Release v2.1 deployed", 21),
        make_evidence("trace", "Request trace collected", 22),
    ]

    report = build_investigation_report(make_incident(), evidence)

    assert not any(
        "No metric evidence" in gap for gap in report.evidence_gaps
    )
    assert not any(
        "No deployment evidence" in gap for gap in report.evidence_gaps
    )
    assert not any(
        "No trace evidence" in gap for gap in report.evidence_gaps
    )

def test_report_includes_retrieved_evidence():
    class FakeRetriever:
        def __init__(self):
            self.query = None

        def retrieve(self, query, evidence_items, top_k):
            self.query = query
            assert len(evidence_items) == 1
            assert top_k == 5

            return [
                RetrievalResult(
                    chunk=EvidenceChunk(
                        incident_id=1,
                        evidence_id=10,
                        source_type="log",
                        chunk_index=0,
                        text="ERROR database connection failed",
                    ),
                    score=0.92,
                )
            ]

    retriever = FakeRetriever()
    evidence = [
        make_evidence(
            "log",
            "ERROR database connection failed",
            10,
        )
    ]

    report = build_investigation_report(
        make_incident(),
        evidence,
        retriever=retriever,
    )

    assert retriever.query
    assert "Database connection failures" in retriever.query
    assert len(report.retrieved_evidence) == 1

    result = report.retrieved_evidence[0]
    assert result.evidence_id == 10
    assert result.source_type == "log"
    assert result.chunk_index == 0
    assert result.text == "ERROR database connection failed"
    assert result.score == 0.92

def test_report_handles_no_retrieval_results():
    class EmptyRetriever:
        def retrieve(self, query, evidence_items, top_k):
            assert evidence_items
            assert top_k == 5
            return []

    evidence = [
        make_evidence(
            "log",
            "ERROR database connection failed",
            10,
        )
    ]

    report = build_investigation_report(
        make_incident(),
        evidence,
        retriever=EmptyRetriever(),
    )

    assert report.evidence_count == 1
    assert report.retrieved_evidence == []
    assert report.observed_findings

def test_report_propagates_retrieval_failure():
    class BrokenRetriever:
        def retrieve(self, query, evidence_items, top_k):
            raise RuntimeError("embedding service failed")

    evidence = [
        make_evidence(
            "log",
            "ERROR database connection failed",
            10,
        )
    ]

    with pytest.raises(
        RuntimeError,
        match="embedding service failed",
    ):
        build_investigation_report(
            make_incident(),
            evidence,
            retriever=BrokenRetriever(),
        )