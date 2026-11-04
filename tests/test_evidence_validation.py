import pytest

from app.ai_models import (
    AIConfidence,
    AIFact,
    AIHypothesis,
    AIInvestigationResult,
)
from app.evidence_validation import validate_evidence_references


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