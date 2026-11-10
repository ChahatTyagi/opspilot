
import pytest
from pydantic import ValidationError

from app.ai_models import (
    AIConfidence,
    AIFact,
    AIHypothesis,
    AIInvestigationResult,
)


def test_valid_ai_investigation_result():
    result = AIInvestigationResult(
        reported_information=[
            "Checkout requests are intermittently failing."
        ],
        observed_facts=[
            AIFact(
                statement="Database connection errors occurred.",
                evidence_ids=[10, 11],
            )
        ],
        hypotheses=[
            AIHypothesis(
                explanation=(
                    "The errors may be related to connection saturation."
                ),
                supporting_evidence_ids=[10],
                confidence=AIConfidence.MEDIUM,
            )
        ],
        recommended_checks=[
            "Inspect database connection pool metrics."
        ],
        unknowns=[
            "Database pool utilization is not available."
        ],
    )

    assert result.reported_information == [
        "Checkout requests are intermittently failing."
    ]
    assert len(result.observed_facts) == 1
    assert result.hypotheses[0].confidence == AIConfidence.MEDIUM


def test_fact_requires_evidence_ids():
    with pytest.raises(ValidationError):
        AIFact(
            statement="Database errors occurred.",
            evidence_ids=[],
        )


def test_confidence_rejects_invalid_value():
    with pytest.raises(ValidationError):
        AIHypothesis(
            explanation="Possible connection saturation.",
            confidence="certain",
        )


def test_result_defaults_to_empty_sections():
    result = AIInvestigationResult()

    assert result.reported_information == []
    assert result.observed_facts == []
    assert result.hypotheses == []
    assert result.recommended_checks == []
    assert result.unknowns == []
