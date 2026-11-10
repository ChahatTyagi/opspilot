
import pytest

from experiments.evaluate_final_retrieval_v3 import (
    evaluate_case,
    evaluate_dataset,
    macro_average,
)


def make_case():
    return {
        "name": "Test incident",
        "query": "database connection failure",
        "evidence": [
            (1, "log", "Database connection refused", False),
            (2, "log", "Connection pool exhausted", False),
            (3, "metric", "Database connection errors increased", False),
            (4, "log", "Database service unavailable", False),
            (5, "log", "Email delivery succeeded", False),
            (6, "metric", "CPU usage is normal", False),
        ],
    }


def make_search_function(retrieved_ids):
    def fake_search(query, incident_id, evidence_items, max_results=5):
        return [
            {"evidence_id": evidence_id}
            for evidence_id in retrieved_ids[:max_results]
        ]

    return fake_search


def test_relevance_is_restricted_to_current_scenario():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([1, 5, 3]),
        {1, 2, 999},
    )

    assert result["retrieved_relevant"] == [1]
    assert result["missed_ids"] == [2]
    assert result["irrelevant_ids"] == [5, 3]


def test_retrieved_and_missed_ids_are_correct():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([1, 5, 3, 6, 2]),
        {1, 2, 4},
    )

    assert result["retrieved_ids"] == [1, 5, 3, 6, 2]
    assert result["retrieved_relevant"] == [1, 2]
    assert result["missed_ids"] == [4]
    assert result["irrelevant_ids"] == [5, 3, 6]


def test_metrics_are_calculated_correctly():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([5, 6, 1, 2, 3]),
        {1, 2, 4},
    )

    assert result["recall_at_5"] == pytest.approx(2 / 3)
    assert result["precision_at_5"] == pytest.approx(2 / 5)
    assert result["precision_returned"] == pytest.approx(2 / 5)
    assert result["mrr"] == pytest.approx(1 / 3)


def test_direct_and_diagnostic_relevance_are_independent():
    case = make_case()
    search_function = make_search_function([1, 5, 3, 6, 2])

    direct_result = evaluate_case(
        case,
        "incident-1",
        search_function,
        {1, 2},
    )

    diagnostic_result = evaluate_case(
        case,
        "incident-1",
        search_function,
        {1, 2, 3, 4},
    )

    assert direct_result["retrieved_relevant"] == [1, 2]
    assert direct_result["missed_ids"] == []

    assert diagnostic_result["retrieved_relevant"] == [1, 3, 2]
    assert diagnostic_result["missed_ids"] == [4]

    assert direct_result["recall_at_5"] == pytest.approx(1.0)
    assert diagnostic_result["recall_at_5"] == pytest.approx(0.75)


def test_empty_search_results_are_handled():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([]),
        {1, 2},
    )

    assert result["retrieved_ids"] == []
    assert result["retrieved_relevant"] == []
    assert result["missed_ids"] == [1, 2]
    assert result["irrelevant_ids"] == []
    assert result["recall_at_5"] == 0.0
    assert result["precision_at_5"] == 0.0
    assert result["precision_returned"] == 0.0
    assert result["mrr"] == 0.0


def test_evaluate_dataset_uses_separate_incident_ids():
    cases = [make_case(), make_case()]

    results = evaluate_dataset(
        cases,
        make_search_function([1]),
        {1, 2},
    )

    assert len(results) == 2
    assert results[0]["name"] == "Test incident"
    assert results[1]["name"] == "Test incident"


def test_macro_average_calculates_mean():
    results = [
        {"recall_at_5": 0.5},
        {"recall_at_5": 1.0},
        {"recall_at_5": 0.0},
    ]

    assert macro_average(results, "recall_at_5") == pytest.approx(0.5)

