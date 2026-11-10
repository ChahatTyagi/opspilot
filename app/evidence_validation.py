from app.ai_models import AIInvestigationResult


def validate_evidence_references(
    result: AIInvestigationResult,
    valid_evidence_ids: set[int],
) -> AIInvestigationResult:
    """Validate evidence references and reject duplicate hypotheses."""

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

    # Normalize hypothesis explanations before checking for duplicates.
    seen_hypotheses: set[str] = set()

    for hypothesis in result.hypotheses:
        normalized_explanation = " ".join(
            hypothesis.explanation.casefold().split()
        )

        if normalized_explanation in seen_hypotheses:
            raise ValueError(
                "AI result contains a duplicate hypothesis."
            )

        seen_hypotheses.add(normalized_explanation)

    return result
