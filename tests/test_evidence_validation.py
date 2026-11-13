
import pytest

from app.ai_models import (
    AIConfidence,
    AIFact,
    AIHypothesis,
    AIHypothesisAssessment,
    AIHypothesisVerdict,
    AIInvestigationResult,
    AIHypothesisVerificationResult,
)
from app.evidence_validation import (
    validate_evidence_references,
    validate_hypothesis_verification,
    validate_investigation_quality,
)


def make_result():
    return AIInvestigationResult(
        observed_facts=[
            AIFact(
                statement="Database errors occurred.",
                evidence_ids=[10, 11],
            )
        ],
        hypotheses=[
            AIHypothesis(
                explanation="The errors may relate to connection saturation.",
                supporting_evidence_ids=[11],
                confidence=AIConfidence.MEDIUM,
            )
        ],
    )


def make_assessment(
    index=0,
    verdict=AIHypothesisVerdict.SUPPORTED,
    evidence_ids=None,
    rationale="The cited evidence supports the proposed mechanism.",
):
    return AIHypothesisAssessment(
        hypothesis_index=index,
        verdict=verdict,
        evidence_ids=[11] if evidence_ids is None else evidence_ids,
        rationale=rationale,
    )


def test_accepts_references_belonging_to_incident():
    result = make_result()

    validated = validate_evidence_references(
        result,
        valid_evidence_ids={10, 11, 12},
    )

    assert validated is result


def test_rejects_invalid_fact_evidence_id():
    result = make_result()
    result.observed_facts[0].evidence_ids = [10, 99]

    with pytest.raises(ValueError, match="99"):
        validate_evidence_references(
            result,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_invalid_hypothesis_evidence_id():
    result = make_result()
    result.hypotheses[0].supporting_evidence_ids = [88]

    with pytest.raises(ValueError, match="88"):
        validate_evidence_references(
            result,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_multiple_invalid_references():
    result = make_result()
    result.observed_facts[0].evidence_ids = [77]
    result.hypotheses[0].supporting_evidence_ids = [88]

    with pytest.raises(ValueError, match="77, 88"):
        validate_evidence_references(
            result,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_exact_duplicate_hypotheses():
    result = make_result()

    result.hypotheses.append(
        AIHypothesis(
            explanation=(
                "The errors may relate to connection saturation."
            ),
            supporting_evidence_ids=[11],
            confidence=AIConfidence.MEDIUM,
        )
    )

    with pytest.raises(ValueError, match="duplicate hypothesis"):
        validate_evidence_references(
            result,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_duplicate_hypotheses_with_different_case_and_spacing():
    result = make_result()

    result.hypotheses.append(
        AIHypothesis(
            explanation=(
                "  THE ERRORS MAY RELATE TO CONNECTION SATURATION.  "
            ),
            supporting_evidence_ids=[11],
            confidence=AIConfidence.MEDIUM,
        )
    )

    with pytest.raises(ValueError, match="duplicate hypothesis"):
        validate_evidence_references(
            result,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_whitespace_only_fact_statement():
    result = make_result()
    result.observed_facts[0].statement = "   "

    with pytest.raises(ValueError, match="observed fact"):
        validate_investigation_quality(result)


def test_rejects_whitespace_only_hypothesis():
    result = make_result()
    result.hypotheses[0].explanation = "   "

    with pytest.raises(ValueError, match="hypothesis"):
        validate_investigation_quality(result)


@pytest.mark.parametrize(
    "field",
    [
        "reported_information",
        "recommended_checks",
        "unknowns",
    ],
)
def test_rejects_whitespace_only_list_entries(field):
    result = make_result()
    setattr(result, field, ["   "])

    with pytest.raises(ValueError, match=field):
        validate_investigation_quality(result)


def test_allows_legitimately_empty_lists():
    result = make_result()
    result.reported_information = []
    result.hypotheses = []
    result.recommended_checks = []
    result.unknowns = []

    assert validate_investigation_quality(result) is result


def test_keeps_supported_hypothesis():
    result = make_result()

    verification = AIHypothesisVerificationResult(
        assessments=[make_assessment()]
    )

    validated = validate_hypothesis_verification(
        result=result,
        verification=verification,
        valid_evidence_ids={10, 11, 12},
    )

    assert validated.hypotheses == result.hypotheses


@pytest.mark.parametrize(
    "verdict",
    [
        AIHypothesisVerdict.INSUFFICIENT,
        AIHypothesisVerdict.CONTRADICTED,
    ],
)
def test_removes_unsupported_hypotheses(verdict):
    result = make_result()

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(verdict=verdict)
        ]
    )

    validated = validate_hypothesis_verification(
        result=result,
        verification=verification,
        valid_evidence_ids={10, 11, 12},
    )

    assert validated.hypotheses == []


def test_rejects_missing_assessment():
    result = make_result()

    verification = AIHypothesisVerificationResult()

    with pytest.raises(ValueError, match="exactly one assessment"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_duplicate_assessment():
    result = make_result()

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(),
            make_assessment(),
        ]
    )

    with pytest.raises(ValueError, match="exactly one assessment"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_out_of_range_index():
    result = make_result()

    verification = AIHypothesisVerificationResult(
        assessments=[make_assessment(index=5)]
    )

    with pytest.raises(ValueError, match="out-of-range"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_evidence_not_cited_by_hypothesis():
    result = make_result()

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(evidence_ids=[10])
        ]
    )

    with pytest.raises(ValueError, match="not cited"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_blank_rationale():
    result = make_result()

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(rationale="   ")
        ]
    )

    with pytest.raises(ValueError, match="blank"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_hypothesis_without_supporting_evidence():
    result = make_result()
    result.hypotheses[0].supporting_evidence_ids = []

    verification = AIHypothesisVerificationResult(
        assessments=[
            AIHypothesisAssessment(
                hypothesis_index=0,
                verdict=AIHypothesisVerdict.INSUFFICIENT,
                evidence_ids=[],
                rationale="No evidence was cited.",
            )
        ]
    )

    with pytest.raises(ValueError, match="without supporting evidence"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )


def test_rejects_supported_verdict_without_evidence_ids():
    result = make_result()

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(evidence_ids=[])
        ]
    )

    with pytest.raises(ValueError, match="must cite supporting evidence"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )


def test_preserves_other_investigation_fields_when_filtering():
    result = make_result()
    result.unknowns = ["The exact cause remains unknown."]
    result.recommended_checks = ["Inspect connection usage."]

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(
                verdict=AIHypothesisVerdict.INSUFFICIENT
            )
        ]
    )

    validated = validate_hypothesis_verification(
        result=result,
        verification=verification,
        valid_evidence_ids={10, 11, 12},
    )

    assert validated.hypotheses == []
    assert validated.observed_facts == result.observed_facts
    assert validated.unknowns == result.unknowns
    assert validated.recommended_checks == result.recommended_checks
