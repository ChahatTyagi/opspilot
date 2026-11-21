
import pytest

from app.retrieval_service import EvidenceRetriever

from experiments.evaluate_topology_retrieval_v2 import (
    QUERY_TRACKS,
    PERSPECTIVES,
    aggregate_by_track_and_perspective,
    aggregate_results,
    calculate_metrics,
    evaluate_case,
    run_benchmark,
)
from experiments.topology_retrieval_v2_dataset import (
    TOP_K,
    build_dataset,
    get_relevant_ids,
    validate_dataset,
)


class ConstantFakeEmbedder:
    """
    Return identical vectors for every input.

    This removes semantic ranking differences and makes it easier
    to isolate the effect of the topology boost.
    """

    def embed_texts(self, texts):
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def fake_retriever():
    return EvidenceRetriever(embedder=ConstantFakeEmbedder())


def test_dataset_validation_passes():
    assert validate_dataset() is True


def test_evaluation_dimensions_are_correct():
    assert QUERY_TRACKS == (
        "service_anchored",
        "symptom_only",
    )
    assert PERSPECTIVES == (
        "direct",
        "diagnostic",
    )


def test_calculate_metrics():
    metrics = calculate_metrics(
        retrieved_ids=[1, 2, 3, 4, 5],
        relevant_ids={2, 4, 6},
        top_k=5,
    )

    assert metrics["recall_at_k"] == pytest.approx(2 / 3)
    assert metrics["precision_at_k"] == pytest.approx(2 / 5)
    assert metrics["mrr"] == pytest.approx(1 / 2)
    assert metrics["relevant_retrieved"] == 2
    assert metrics["relevant_total"] == 3


def test_calculate_metrics_rejects_invalid_top_k():
    with pytest.raises(ValueError, match="top_k must be positive"):
        calculate_metrics(
            retrieved_ids=[1, 2],
            relevant_ids={1},
            top_k=0,
        )


def test_calculate_metrics_rejects_duplicate_retrieved_ids():
    with pytest.raises(ValueError, match="must be unique"):
        calculate_metrics(
            retrieved_ids=[1, 1, 2],
            relevant_ids={1, 2},
        )


def test_calculate_metrics_rejects_empty_relevant_ids():
    with pytest.raises(ValueError, match="cannot be empty"):
        calculate_metrics(
            retrieved_ids=[1, 2, 3],
            relevant_ids=set(),
        )


def test_direct_relevance_uses_only_direct_labels():
    case = build_dataset()[0]

    relevant_ids = get_relevant_ids(case, "direct")

    assert relevant_ids
    assert all(
        case["labels"][evidence_id] == "DIRECT"
        for evidence_id in relevant_ids
    )


def test_diagnostic_relevance_includes_contributing_evidence():
    case = build_dataset()[0]

    direct_ids = get_relevant_ids(case, "direct")
    diagnostic_ids = get_relevant_ids(case, "diagnostic")

    assert direct_ids.issubset(diagnostic_ids)
    assert case["trace_ids"]["target"] in diagnostic_ids
    assert case["trace_ids"]["target"] not in direct_ids


def test_evaluate_case_rejects_invalid_query_track(fake_retriever):
    case = build_dataset()[0]

    with pytest.raises(ValueError, match="query_track"):
        evaluate_case(
            case,
            fake_retriever,
            query_track="unknown",
            perspective="direct",
        )


def test_evaluate_case_rejects_invalid_perspective(fake_retriever):
    case = build_dataset()[0]

    with pytest.raises(ValueError, match="perspective"):
        evaluate_case(
            case,
            fake_retriever,
            query_track="service_anchored",
            perspective="unknown",
        )


def test_service_anchored_query_promotes_connected_trace_records(
    fake_retriever,
):
    case = build_dataset()[0]

    result = evaluate_case(
        case,
        fake_retriever,
        query_track="service_anchored",
        perspective="diagnostic",
    )

    topology_ids = result["topology_aware"]["retrieved_ids"]
    connected_ids = {
        case["trace_ids"]["upstream"],
        case["trace_ids"]["target"],
        case["trace_ids"]["dependency"],
    }

    # All three connected trace spans receive the topology boost.
    assert connected_ids.issubset(set(topology_ids))

    # The two unrelated trace records are not topology-connected
    # to the target service.
    unrelated_ids = set(case["trace_ids"]["unrelated"])
    assert unrelated_ids.isdisjoint(set(topology_ids))


def test_service_anchored_query_uses_target_service(fake_retriever):
    case = build_dataset()[0]

    result = evaluate_case(
        case,
        fake_retriever,
        query_track="service_anchored",
        perspective="direct",
    )

    assert case["target_service"] in result["query"]


def test_symptom_only_query_preserves_original_query(fake_retriever):
    case = build_dataset()[0]

    result = evaluate_case(
        case,
        fake_retriever,
        query_track="symptom_only",
        perspective="direct",
    )

    assert result["query"] == case["symptom_query"]


def test_symptom_only_query_does_not_activate_topology_when_unanchored(
    fake_retriever,
):
    case = build_dataset()[0]

    # This fixture's symptom query does not mention its target service.
    assert case["target_service"] not in case["symptom_query"]

    result = evaluate_case(
        case,
        fake_retriever,
        query_track="symptom_only",
        perspective="diagnostic",
    )

    # Without a service-name match, topology must not change ranking.
    assert (
        result["baseline"]["retrieved_ids"]
        == result["topology_aware"]["retrieved_ids"]
    )


def test_evaluation_reports_displaced_useful_non_trace_records(
    fake_retriever,
):
    case = build_dataset()[0]

    result = evaluate_case(
        case,
        fake_retriever,
        query_track="service_anchored",
        perspective="diagnostic",
    )

    evidence_by_id = {
        item.id: item
        for item in case["evidence"]
    }

    for evidence_id in result["displaced_useful_non_trace_ids"]:
        assert evidence_by_id[evidence_id].source_type != "trace"
        assert evidence_id in get_relevant_ids(case, "diagnostic")
        assert evidence_id in result["baseline"]["retrieved_ids"]
        assert evidence_id not in result["topology_aware"]["retrieved_ids"]


def test_aggregate_results_rejects_empty_input():
    with pytest.raises(ValueError, match="empty result set"):
        aggregate_results([])


def test_aggregate_results_calculates_macro_averages():
    results = [
        {
            "baseline": {
                "recall_at_k": 0.4,
                "precision_at_k": 0.2,
                "mrr": 0.5,
            },
            "topology_aware": {
                "recall_at_k": 0.6,
                "precision_at_k": 0.4,
                "mrr": 0.75,
            },
            "delta": {
                "recall_at_k": 0.2,
                "precision_at_k": 0.2,
                "mrr": 0.25,
            },
            "displaced_useful_non_trace_ids": [10],
        },
        {
            "baseline": {
                "recall_at_k": 0.8,
                "precision_at_k": 0.4,
                "mrr": 1.0,
            },
            "topology_aware": {
                "recall_at_k": 0.8,
                "precision_at_k": 0.4,
                "mrr": 1.0,
            },
            "delta": {
                "recall_at_k": 0.0,
                "precision_at_k": 0.0,
                "mrr": 0.0,
            },
            "displaced_useful_non_trace_ids": [],
        },
    ]

    summary = aggregate_results(results)

    assert summary["baseline"]["recall_at_k"] == pytest.approx(0.6)
    assert summary["topology_aware"]["recall_at_k"] == pytest.approx(0.7)
    assert summary["delta"]["recall_at_k"] == pytest.approx(0.1)

    assert summary["recall_outcomes"]["wins"] == 1
    assert summary["recall_outcomes"]["regressions"] == 0
    assert summary["recall_outcomes"]["neutral"] == 1

    assert summary["displacement"]["cases_with_displacement"] == 1
    assert (
        summary["displacement"]["total_displaced_useful_non_trace_records"]
        == 1
    )


def test_benchmark_runs_all_80_comparisons(fake_retriever):
    benchmark = run_benchmark(retriever=fake_retriever)

    assert len(benchmark["results"]) == 80


def test_benchmark_contains_all_four_evaluation_groups(fake_retriever):
    benchmark = run_benchmark(retriever=fake_retriever)

    summaries = benchmark["group_summaries"]

    assert len(summaries) == 4

    expected_groups = {
        "service_anchored_direct",
        "service_anchored_diagnostic",
        "symptom_only_direct",
        "symptom_only_diagnostic",
    }

    assert set(summaries) == expected_groups


def test_each_evaluation_group_contains_20_scenarios(fake_retriever):
    benchmark = run_benchmark(retriever=fake_retriever)

    for group in benchmark["group_summaries"].values():
        assert group["scenario_count"] == 20


def test_benchmark_uses_top_five(fake_retriever):
    benchmark = run_benchmark(retriever=fake_retriever)

    for result in benchmark["results"]:
        assert len(result["baseline"]["retrieved_ids"]) <= TOP_K
        assert len(result["topology_aware"]["retrieved_ids"]) <= TOP_K
