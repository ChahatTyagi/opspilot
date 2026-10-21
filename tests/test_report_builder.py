
from types import SimpleNamespace

from app.report_builder import build_investigation_report


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
