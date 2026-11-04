from app.ai_models import AIInvestigationResult


def validate_evidence_references(
    result: AIInvestigationResult,
    valid_evidence_ids: set[int],
) -> AIInvestigationResult:
    """Reject AI claims that reference evidence outside this incident."""

    invalid_ids: set[int] = set()

    for fact in result.observed_facts:
        invalid_ids.update(
            evidence_id
            for evidence_id in fact.evidence_ids
            if evidence_id not in valid_evidence_ids
        )

    for hypothesis in result.hypotheses:
        invalid_ids.update(
            evidence_id
            for evidence_id in hypothesis.supporting_evidence_ids
            if evidence_id not in valid_evidence_ids
        )

    if invalid_ids:
        invalid_ids_text = ", ".join(
            str(evidence_id) for evidence_id in sorted(invalid_ids)
        )
        raise ValueError(
            f"AI result references evidence IDs not belonging "
            f"to this incident: {invalid_ids_text}"
        )

    return result