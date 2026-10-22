
from app.analyzer import analyze_evidence
from app.db_models import IncidentEvidence, IncidentRecord
from app.models import (
    ErrorPatternResponse,
    InvestigationReportResponse,
    RetrievedEvidenceResponse,
)
from app.retrieval_service import EvidenceRetriever

def build_investigation_report(
    incident: IncidentRecord,
    evidence: list[IncidentEvidence],
    retriever: EvidenceRetriever | None = None,
) -> InvestigationReportResponse:
    """Build an evidence-grounded report without guessing root causes."""

    analysis = analyze_evidence(incident.id, evidence)
    retrieved_evidence = []

    if retriever is not None and evidence:
        query = (
            f"Investigate incident '{incident.title}' "
            f"affecting service '{incident.service}'. "
            f"Description: {getattr(incident, 'description', '')}"
        )

        results = retriever.retrieve(
            query=query,
            evidence_items=evidence,
            top_k=5,
        )

        retrieved_evidence = [
            RetrievedEvidenceResponse(
                evidence_id=result.chunk.evidence_id,
                source_type=result.chunk.source_type,
                chunk_index=result.chunk.chunk_index,
                text=result.chunk.text,
                score=result.score,
            )
            for result in results
        ]

    observed_findings = list(analysis.findings)
    hypotheses: list[str] = []
    recommended_checks: list[str] = []
    evidence_gaps: list[str] = []

    source_types = {item.source_type for item in evidence}

    if analysis.recurring_patterns:
        observed_findings.append(
            f"Detected {len(analysis.recurring_patterns)} recurring "
            "error pattern(s) in the available logs."
        )

        hypotheses.append(
            "The recurring errors may share an underlying trigger; "
            "the available evidence does not establish a root cause."
        )

        recommended_checks.extend([
            "Inspect the original log entries for each recurring pattern.",
            "Compare error timestamps with service health and request failures.",
            "Check recent deployments and configuration changes for correlation.",
        ])
    elif analysis.error_lines_detected:
        hypotheses.append(
            "The detected errors may be isolated or may represent a pattern "
            "that cannot yet be established from the available logs."
        )
        recommended_checks.append(
            "Collect more logs from the affected time window and compare "
            "error messages across requests."
        )
    else:
        observed_findings.append(
            "No error-like lines were detected in the available logs."
        )
        recommended_checks.append(
            "Verify the incident time window and collect relevant service logs."
        )

    if "metric" not in source_types:
        evidence_gaps.append(
            "No metric evidence is available to assess resource usage "
            "or service-health trends."
        )
        recommended_checks.append(
            "Collect relevant metrics, such as error rate, latency, CPU, "
            "and memory usage."
        )

    if "deployment" not in source_types:
        evidence_gaps.append(
            "No deployment evidence is available to correlate errors "
            "with recent releases or configuration changes."
        )

    if "trace" not in source_types:
        evidence_gaps.append(
            "No trace evidence is available to follow failing requests "
            "across service boundaries."
        )

    if not evidence:
        evidence_gaps.append(
            "No evidence has been attached to this incident yet."
        )

    return InvestigationReportResponse(
        incident_id=incident.id,
        incident_title=incident.title,
        service=incident.service,
        severity=incident.severity,
        status=incident.status,
        evidence_count=len(evidence),
        observed_findings=observed_findings,
        recurring_patterns=[
            ErrorPatternResponse(
                pattern=pattern.pattern,
                occurrences=pattern.occurrences,
                evidence_ids=pattern.evidence_ids,
            )
            for pattern in analysis.recurring_patterns
        ],
        hypotheses=hypotheses,
        recommended_checks=recommended_checks,
        evidence_gaps=evidence_gaps,
        retrieved_evidence=retrieved_evidence,
    )
