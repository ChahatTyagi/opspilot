import re

from app.ai_models import (
    AIHypothesisVerdict,
    AIInvestigationResult,
    AIHypothesisVerificationResult,
)


# Accept both natural-language and machine-style evidence references:
# Evidence 123, Evidence ID 123, Evidence IDs: 123, evidence_id: 123,
# evidence_ids: 123, 124, etc.
_EVIDENCE_REFERENCE_PATTERN = re.compile(
    r"\b(?:evidence(?:\s+ids?)?|evidence_ids?)\s*[:#]?\s*#?(\d+)",
    re.IGNORECASE,
)

_ADDITIONAL_EVIDENCE_REFERENCE_PATTERN = re.compile(
    r"\s*(?:,|and|&)\s*#?(\d+)\b",
    re.IGNORECASE,
)


def _extract_rationale_evidence_ids(rationale: str) -> set[int]:
    """Extract explicitly written evidence IDs from a verifier rationale.

    Supported examples include:
    - Evidence 123
    - Evidence ID 123
    - Evidence IDs: 123, 124
    - Evidence 123 and 124
    - Evidence #123
    - evidence_id 123
    - evidence_id: 123
    - evidence_ids: 123, 124

    Ordinary numbers that are not introduced as evidence references are
    deliberately ignored.
    """

    evidence_ids: set[int] = set()

    for match in _EVIDENCE_REFERENCE_PATTERN.finditer(rationale):
        evidence_ids.add(int(match.group(1)))
        position = match.end()

        # Support lists such as "Evidence 123, 124 and 125" and
        # "evidence_ids: 123, 124".
        while True:
            additional_match = _ADDITIONAL_EVIDENCE_REFERENCE_PATTERN.match(
                rationale,
                position,
            )
            if additional_match is None:
                break

            evidence_ids.add(int(additional_match.group(1)))
            position = additional_match.end()

    return evidence_ids


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
            "AI result references evidence IDs not belonging "
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
                    f"AI result contains a blank entry in {field_name}."
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

        # Explicit IDs in free-text rationale must agree with the
        # structured evidence_ids field.
        rationale_ids = _extract_rationale_evidence_ids(
            assessment.rationale
        )

        if not rationale_ids.issubset(assessment_ids):
            invalid_rationale_ids = rationale_ids - assessment_ids
            invalid_ids_text = ", ".join(
                str(evidence_id)
                for evidence_id in sorted(invalid_rationale_ids)
            )
            raise ValueError(
                "Verifier rationale references evidence IDs "
                "that are missing from its structured evidence_ids: "
                f"{invalid_ids_text}"
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
