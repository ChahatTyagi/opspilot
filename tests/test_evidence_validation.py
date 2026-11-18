
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


def validate_assessment(
    assessment,
    result=None,
    valid_evidence_ids=None,
):
    if result is None:
        result = make_result()

    if valid_evidence_ids is None:
        valid_evidence_ids = {10, 11, 12}

    verification = AIHypothesisVerificationResult(
        assessments=[assessment]
    )

    return validate_hypothesis_verification(
        result=result,
        verification=verification,
        valid_evidence_ids=valid_evidence_ids,
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

    with pytest.raises(
        ValueError,
        match="without supporting evidence",
    ):
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

    with pytest.raises(
        ValueError,
        match="must cite supporting evidence",
    ):
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


# ---------------------------------------------------------
# New tests: rationale evidence citation consistency
# ---------------------------------------------------------


@pytest.mark.parametrize(
    "rationale",
    [
        "Evidence 11 supports the proposed mechanism.",
        "Evidence ID 11 supports the proposed mechanism.",
        "Evidence #11 supports the proposed mechanism.",
        "Evidence IDs: 11 support the proposed mechanism.",
    ],
)
def test_accepts_rationale_referencing_structured_evidence(rationale):
    assessment = make_assessment(
        evidence_ids=[11],
        rationale=rationale,
    )

    validated = validate_assessment(assessment)

    assert len(validated.hypotheses) == 1


def test_accepts_rationale_without_explicit_evidence_ids():
    assessment = make_assessment(
        evidence_ids=[11],
        rationale=(
            "The observed connection pool saturation supports "
            "the proposed mechanism."
        ),
    )

    validated = validate_assessment(assessment)

    assert len(validated.hypotheses) == 1


def test_accepts_multiple_rationale_ids_matching_structured_ids():
    result = make_result()
    result.hypotheses[0].supporting_evidence_ids = [10, 11]

    assessment = make_assessment(
        evidence_ids=[10, 11],
        rationale="Evidence IDs 10 and 11 support this assessment.",
    )

    validated = validate_assessment(
        assessment,
        result=result,
    )

    assert len(validated.hypotheses) == 1


def test_accepts_comma_separated_rationale_evidence_ids():
    result = make_result()
    result.hypotheses[0].supporting_evidence_ids = [10, 11]

    assessment = make_assessment(
        evidence_ids=[10, 11],
        rationale="Evidence IDs: 10, 11 support this assessment.",
    )

    validated = validate_assessment(
        assessment,
        result=result,
    )

    assert len(validated.hypotheses) == 1


def test_rejects_rationale_with_unknown_evidence_id():
    assessment = make_assessment(
        evidence_ids=[11],
        rationale="Evidence 999 supports this assessment.",
    )

    with pytest.raises(
        ValueError,
        match="missing from its structured evidence_ids: 999",
    ):
        validate_assessment(assessment)


def test_rejects_rationale_with_id_not_in_structured_citations():
    result = make_result()
    result.hypotheses[0].supporting_evidence_ids = [10, 11]

    assessment = make_assessment(
        evidence_ids=[11],
        rationale="Evidence 10 and 11 support this assessment.",
    )

    with pytest.raises(
        ValueError,
        match="missing from its structured evidence_ids: 10",
    ):
        validate_assessment(assessment, result=result)


def test_rejects_rationale_with_multiple_uncited_evidence_ids():
    result = make_result()
    result.hypotheses[0].supporting_evidence_ids = [10, 11, 12]

    assessment = make_assessment(
        evidence_ids=[11],
        rationale="Evidence IDs 10, 12 and 99 support this assessment.",
    )

    with pytest.raises(
        ValueError,
        match="10, 12, 99",
    ):
        validate_assessment(
            assessment,
            result=result,
            valid_evidence_ids={10, 11, 12, 99},
        )


def test_rejects_contradicted_rationale_with_missing_structured_ids():
    assessment = make_assessment(
        verdict=AIHypothesisVerdict.CONTRADICTED,
        evidence_ids=[],
        rationale="Evidence 11 contradicts the hypothesis.",
    )

    with pytest.raises(
        ValueError,
        match="missing from its structured evidence_ids: 11",
    ):
        validate_assessment(assessment)


def test_does_not_treat_ordinary_numbers_as_evidence_ids():
    assessment = make_assessment(
        evidence_ids=[11],
        rationale=(
            "The service returned HTTP 500 errors at 10:30. "
            "This supports the proposed mechanism."
        ),
    )

    validated = validate_assessment(assessment)

    assert len(validated.hypotheses) == 1


@pytest.mark.parametrize(
    "rationale",
    [
        "evidence_id 11 supports the proposed mechanism.",
        "evidence_id: 11 supports the proposed mechanism.",
        "evidence_ids: 11 support the proposed mechanism.",
        "Evidence_ids: 11 support the proposed mechanism.",
    ],
)
def test_accepts_underscore_evidence_reference_formats(rationale):
    assessment = make_assessment(
        evidence_ids=[11],
        rationale=rationale,
    )

    validated = validate_assessment(assessment)

    assert len(validated.hypotheses) == 1


def test_accepts_comma_separated_underscore_evidence_ids():
    result = make_result()
    result.hypotheses[0].supporting_evidence_ids = [10, 11]

    assessment = make_assessment(
        evidence_ids=[10, 11],
        rationale="evidence_ids: 10, 11 support this assessment.",
    )

    validated = validate_assessment(assessment, result=result)

    assert len(validated.hypotheses) == 1


def test_rejects_underscore_rationale_id_missing_from_structured_ids():
    assessment = make_assessment(
        evidence_ids=[11],
        rationale="The finding is supported by evidence_id: 999.",
    )

    with pytest.raises(
        ValueError,
        match="missing from its structured evidence_ids: 999",
    ):
        validate_assessment(assessment)


def test_does_not_treat_ordinary_underscore_words_or_numbers_as_evidence_ids():
    assessment = make_assessment(
        evidence_ids=[11],
        rationale=(
            "The evidence processing job handled 111 records and "
            "returned HTTP 500 at 10:30."
        ),
    )

    validated = validate_assessment(assessment)

    assert len(validated.hypotheses) == 1


def test_rejects_negative_hypothesis_index():
    with pytest.raises(ValueError):
        make_assessment(index=-1)


def test_maps_assessments_by_index_not_response_order():
    result = make_result()

    result.hypotheses.append(
        AIHypothesis(
            explanation="The database may be experiencing high latency.",
            supporting_evidence_ids=[10],
            confidence=AIConfidence.MEDIUM,
        )
    )

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(
                index=1,
                verdict=AIHypothesisVerdict.INSUFFICIENT,
                evidence_ids=[10],
            ),
            make_assessment(
                index=0,
                verdict=AIHypothesisVerdict.SUPPORTED,
                evidence_ids=[11],
            ),
        ]
    )

    validated = validate_hypothesis_verification(
        result=result,
        verification=verification,
        valid_evidence_ids={10, 11, 12},
    )

    assert len(validated.hypotheses) == 1
    assert validated.hypotheses[0].explanation == (
        result.hypotheses[0].explanation
    )


def test_rejects_duplicate_indexes_with_matching_assessment_count():
    result = make_result()

    result.hypotheses.append(
        AIHypothesis(
            explanation="The database may be experiencing high latency.",
            supporting_evidence_ids=[10],
            confidence=AIConfidence.MEDIUM,
        )
    )

    verification = AIHypothesisVerificationResult(
        assessments=[
            make_assessment(index=0),
            make_assessment(index=0),
        ]
    )

    with pytest.raises(ValueError, match="duplicate hypothesis assessment"):
        validate_hypothesis_verification(
            result=result,
            verification=verification,
            valid_evidence_ids={10, 11, 12},
        )
