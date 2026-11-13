
from app.ai_models import (
    AIHypothesisVerdict,
    AIInvestigationResult,
    AIHypothesisVerificationResult,
)


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


def validate_investigation_quality(
    result: AIInvestigationResult,
) -> AIInvestigationResult:
    """Reject blank text in an AI investigation result."""

    for fact in result.observed_facts:
        if not fact.statement.strip():
            raise ValueError(
                "AI result contains a blank observed fact."
            )

    for hypothesis in result.hypotheses:
        if not hypothesis.explanation.strip():
            raise ValueError(
                "AI result contains a blank hypothesis."
            )

    text_fields = {
        "reported_information": result.reported_information,
        "recommended_checks": result.recommended_checks,
        "unknowns": result.unknowns,
    }

    for field_name, entries in text_fields.items():
        for entry in entries:
            if not entry.strip():
                raise ValueError(
                    f"AI result contains a blank entry in "
                    f"{field_name}."
                )

    return result


def validate_hypothesis_verification(
    *,
    result: AIInvestigationResult,
    verification: AIHypothesisVerificationResult,
    valid_evidence_ids: set[int],
) -> AIInvestigationResult:
    """Validate verifier assessments and retain supported hypotheses."""

    hypotheses = result.hypotheses
    assessments = verification.assessments

    if len(assessments) != len(hypotheses):
        raise ValueError(
            "Verifier must return exactly one assessment "
            "for every hypothesis."
        )

    assessments_by_index = {}

    for assessment in assessments:
        index = assessment.hypothesis_index

        if index >= len(hypotheses):
            raise ValueError(
                "Verifier returned an out-of-range hypothesis index."
            )

        if index in assessments_by_index:
            raise ValueError(
                "Verifier returned a duplicate hypothesis assessment."
            )

        if not assessment.rationale.strip():
            raise ValueError(
                "Verifier returned a blank assessment rationale."
            )

        hypothesis = hypotheses[index]
        cited_ids = set(hypothesis.supporting_evidence_ids)
        assessment_ids = set(assessment.evidence_ids)

        if not cited_ids:
            raise ValueError(
                "Cannot verify a hypothesis without supporting evidence."
            )

        if not cited_ids.issubset(valid_evidence_ids):
            raise ValueError(
                "Hypothesis contains evidence IDs outside the "
                "valid incident evidence."
            )

        if not assessment_ids.issubset(cited_ids):
            raise ValueError(
                "Verifier referenced evidence not cited by "
                "the original hypothesis."
            )

        if not assessment_ids.issubset(valid_evidence_ids):
            raise ValueError(
                "Verifier referenced invalid incident evidence."
            )

        if (
            assessment.verdict == AIHypothesisVerdict.SUPPORTED
            and not assessment_ids
        ):
            raise ValueError(
                "Supported assessment must cite supporting evidence."
            )

        assessments_by_index[index] = assessment

    expected_indexes = set(range(len(hypotheses)))

    if set(assessments_by_index) != expected_indexes:
        raise ValueError(
            "Verifier assessments do not cover every hypothesis."
        )

    supported_hypotheses = [
        hypothesis
        for index, hypothesis in enumerate(hypotheses)
        if (
            assessments_by_index[index].verdict
            == AIHypothesisVerdict.SUPPORTED
        )
    ]

    return result.model_copy(
        update={"hypotheses": supported_hypotheses}
    )
