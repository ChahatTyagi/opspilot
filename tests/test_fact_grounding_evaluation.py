from pydantic import ValidationError

from app.ai_models import AIFact, AIInvestigationResult
from experiments.evaluate_fact_grounding import (
    calculate_overall_metrics,
    evaluate_fact,
    evaluate_investigation,
)
from experiments.fact_grounding_cases import build_fact_grounding_cases


def get_fg06_case():
    cases = build_fact_grounding_cases()
    return next(case for case in cases if case.case_id == "FG-06")


def make_investigation(*facts):
    return AIInvestigationResult(
        observed_facts=[
            AIFact(
                statement=statement,
                evidence_ids=evidence_ids,
            )
            for statement, evidence_ids in facts
        ]
    )


def test_duplicate_statements_are_counted_as_repeated_matches():
    case = get_fg06_case()

    investigation = make_investigation(
        (
            "Version 2.4.1 deployment completed at 10:00 UTC.",
            [1006],
        ),
        (
            "Deployment completed at 10:00 UTC.",
            [1006],
        ),
        (
            "Order processing errors first appeared at 10:03 UTC.",
            [1007],
        ),
    )

    result = evaluate_investigation(
        case=case,
        investigation=investigation,
    )

    assert result["generated_fact_count"] == 3
    assert result["matched_expected_fact_count"] == 2
    assert result["repeated_match_count"] == 1

    assert result["grounded_fact_count"] == 2
    assert result["incomplete_fact_count"] == 1

    assert result["grounded_expected_fact_count"] == 2
    assert result["grounded_fact_precision"] == 0.6667
    assert result["grounded_fact_recall"] == 1.0

    assert result["facts"][0]["classification"] == "grounded"
    assert result["facts"][1]["classification"] == "incomplete"
    assert result["facts"][1]["is_repeated_match"] is True
    assert result["facts"][2]["classification"] == "grounded"


def test_missing_required_version_is_incomplete():
    case = get_fg06_case()

    expected_deployment = case.expected_facts[0]

    result = evaluate_fact(
        statement="Deployment completed at 10:00 UTC.",
        evidence_ids=[1006],
        case=case,
        matched_expected=expected_deployment,
    )

    assert result["classification"] == "incomplete"
    assert result["numeric_and_detail_checks_passed"] is False
    assert result["citation_checks_passed"] is True
    assert result["grounded"] is False


def test_invalid_citation_is_classified_as_citation_error():
    case = get_fg06_case()

    expected_deployment = case.expected_facts[0]

    result = evaluate_fact(
        statement="Version 2.4.1 deployment completed at 10:00 UTC.",
        evidence_ids=[999],
        case=case,
        matched_expected=expected_deployment,
    )

    assert result["classification"] == "citation_error"
    assert result["numeric_and_detail_checks_passed"] is True
    assert result["citation_checks_passed"] is False
    assert result["invalid_evidence_ids"] == [999]


def test_unmatched_statement_is_not_automatically_hallucination():
    case = get_fg06_case()

    investigation = make_investigation(
        (
            "The service may need additional monitoring.",
            [1006],
        ),
    )

    result = evaluate_investigation(
        case=case,
        investigation=investigation,
    )

    assert result["unmatched_fact_count"] == 1

    fact = result["facts"][0]

    assert fact["classification"] == "unmatched_or_incomplete"
    assert fact["matched_expected_fact"] is False
    assert fact["grounded"] is False

    assert any(
        "cannot be determined" in message
        for message in fact["failed_checks"]
    )


def test_overall_metrics_use_unique_grounded_expected_facts():
    case = get_fg06_case()

    investigation = make_investigation(
        (
            "Version 2.4.1 deployment completed at 10:00 UTC.",
            [1006],
        ),
        (
            "Deployment completed at 10:00 UTC.",
            [1006],
        ),
        (
            "Order processing errors first appeared at 10:03 UTC.",
            [1007],
        ),
    )

    case_result = evaluate_investigation(
        case=case,
        investigation=investigation,
    )

    benchmark_result = {
        "status": "success",
        "latency_seconds": 10.0,
        **case_result,
    }

    metrics = calculate_overall_metrics([benchmark_result])

    assert metrics["expected_facts"] == 2
    assert metrics["generated_facts"] == 3
    assert metrics["matched_expected_facts"] == 2

    assert metrics["grounded_facts"] == 2
    assert metrics["grounded_expected_facts"] == 2
    assert metrics["repeated_matches"] == 1

    assert metrics["grounded_fact_precision"] == 0.6667
    assert metrics["fact_match_recall"] == 1.0
    assert metrics["grounded_fact_recall"] == 1.0


def test_ai_fact_rejects_empty_evidence_ids():
    try:
        AIFact(
            statement="A test observation.",
            evidence_ids=[],
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("AIFact should reject empty evidence IDs")



def test_fg05_unknown_statement_is_only_partial_preservation():
    from experiments.evaluate_fact_grounding import (
        evaluate_information_preservation,
    )

    cases = build_fact_grounding_cases()
    case = next(c for c in cases if c.case_id == "FG-05")

    investigation = AIInvestigationResult(
        unknowns=[
            "The specific issue that might require restarting "
            "the notification service is not described."
        ]
    )

    result = evaluate_information_preservation(
        case=case,
        investigation=investigation,
    )

    recommendation = result["information_items"][0]
    confirmation = result["information_items"][1]

    assert recommendation["status"] == "partial"
    assert recommendation["preserved"] is False

    assert confirmation["status"] == "partial"
    assert confirmation["preserved"] is False

    assert result["preserved_information_count"] == 0
    assert result["partially_preserved_information_count"] == 2
    assert result["missing_information_count"] == 0
    assert result["information_preservation_recall"] == 0.0


def test_fg05_recommendation_and_confirmation_are_preserved_separately():
    from experiments.evaluate_fact_grounding import (
        evaluate_information_preservation,
    )

    cases = build_fact_grounding_cases()
    case = next(c for c in cases if c.case_id == "FG-05")

    investigation = AIInvestigationResult(
        recommended_checks=[
            "Consider restarting the notification service "
            "if the issue persists."
        ],
        reported_information=[
            "No restart has been confirmed."
        ],
    )

    result = evaluate_information_preservation(
        case=case,
        investigation=investigation,
    )

    recommendation = result["information_items"][0]
    confirmation = result["information_items"][1]

    assert recommendation["status"] == "preserved"
    assert confirmation["status"] == "preserved"

    assert result["preserved_information_count"] == 2
    assert result["partially_preserved_information_count"] == 0
    assert result["missing_information_count"] == 0
    assert result["information_preservation_recall"] == 1.0


def test_information_preservation_marks_absent_information_as_missing():
    from experiments.evaluate_fact_grounding import (
        evaluate_information_preservation,
    )

    cases = build_fact_grounding_cases()
    case = next(c for c in cases if c.case_id == "FG-05")

    investigation = AIInvestigationResult(
        reported_information=[
            "The service was investigated."
        ]
    )

    result = evaluate_information_preservation(
        case=case,
        investigation=investigation,
    )

    assert result["preserved_information_count"] == 0
    assert result["partially_preserved_information_count"] == 0
    assert result["missing_information_count"] == 2
    assert result["information_preservation_recall"] == 0.0


def test_overall_metrics_aggregate_partial_information_preservation():
    results = [
        {
            "status": "success",
            "latency_seconds": 5.0,
            "information_preservation": {
                "expected_information_count": 4,
                "preserved_information_count": 2,
                "partially_preserved_information_count": 1,
                "missing_information_count": 1,
                "information_preservation_recall": 0.5,
                "information_items": [],
            },
        }
    ]

    metrics = calculate_overall_metrics(results)

    assert metrics["expected_information"] == 4
    assert metrics["preserved_information"] == 2
    assert metrics["partially_preserved_information"] == 1
    assert metrics["missing_information"] == 1
    assert metrics["information_preservation_recall"] == 0.5