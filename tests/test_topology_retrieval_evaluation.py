
import pytest

from app.retrieval_service import EvidenceRetriever

from experiments.evaluate_topology_retrieval_v1 import (
    TOP_K,
    aggregate_results,
    build_dataset,
    calculate_metrics,
    evaluate_case,
    validate_dataset,
)


class ConstantFakeEmbedder:
    """Give every text the same vector to isolate topology effects."""

    def embed_texts(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_dataset_validation_passes():
    assert validate_dataset() is True


def test_dataset_has_unique_evidence_ids():
    cases = build_dataset()

    evidence_ids = [
        item.id
        for case in cases
        for item in case["evidence"]
    ]

    assert len(evidence_ids) == len(set(evidence_ids))


def test_every_scenario_contains_relevant_and_irrelevant_evidence():
    for case in build_dataset():
        scenario_ids = {
            item.id
            for item in case["evidence"]
        }

        assert case["relevant_ids"]
        assert case["relevant_ids"].issubset(scenario_ids)
        assert scenario_ids - case["relevant_ids"]


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


def test_calculate_metrics_rejects_duplicate_results():
    with pytest.raises(ValueError, match="must be unique"):
        calculate_metrics(
            retrieved_ids=[1, 1, 2],
            relevant_ids={1, 2},
        )


def test_calculate_metrics_rejects_empty_relevant_set():
    with pytest.raises(ValueError, match="cannot be empty"):
        calculate_metrics(
            retrieved_ids=[1, 2, 3],
            relevant_ids=set(),
        )


def test_topology_aware_retrieval_promotes_connected_trace_evidence():
    case = build_dataset()[0]

    retriever = EvidenceRetriever(
        embedder=ConstantFakeEmbedder()
    )

    result = evaluate_case(case, retriever)

    baseline = result["baseline"]
    topology = result["topology_aware"]

    # With identical semantic vectors, the baseline preserves
    # original evidence order. Its first five records are irrelevant.
    assert baseline["precision_at_k"] == pytest.approx(0.0)

    # Topology promotes the three connected trace records.
    assert topology["precision_at_k"] == pytest.approx(3 / TOP_K)

    assert topology["retrieved_ids"][:3] == [
        3006,
        3007,
        3008,
    ]

    assert (
        result["delta"]["precision_at_k"]
        > 0
    )


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
        },
        {
            "baseline": {
                "recall_at_k": 0.8,
                "precision_at_k": 0.4,
                "mrr": 1.0,
            },
            "topology_aware": {
                "recall_at_k": 1.0,
                "precision_at_k": 0.6,
                "mrr": 1.0,
            },
        },
    ]

    summary = aggregate_results(results)

    assert summary["baseline"]["recall_at_k"] == pytest.approx(0.6)
    assert summary["topology_aware"]["recall_at_k"] == pytest.approx(0.8)

    assert summary["delta"]["recall_at_k"] == pytest.approx(0.2)
    assert summary["delta"]["precision_at_k"] == pytest.approx(0.2)
    assert summary["delta"]["mrr"] == pytest.approx(0.125)


def test_aggregate_results_rejects_empty_results():
    with pytest.raises(ValueError, match="empty result set"):
        aggregate_results([])
