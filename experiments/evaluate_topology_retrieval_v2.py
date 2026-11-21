
"""
OpsPilot Topology-Aware Retrieval Benchmark V2.

Compares semantic-only retrieval with the existing topology-aware
retrieval over the V2 dataset.

Evaluation dimensions:
- 20 scenarios
- Service-anchored and symptom-only query tracks
- DIRECT and DIAGNOSTIC relevance perspectives
- Recall@5, Precision@5, and MRR
- Per-scenario changes and useful non-trace evidence displacement

The only baseline intervention is temporarily disabling
_topology_relevant_evidence_ids. Production code is not modified.

Run:
    python -m experiments.evaluate_topology_retrieval_v2
"""

from collections import defaultdict
from statistics import mean
from unittest.mock import patch

from app.retrieval_service import EvidenceRetriever

from experiments.topology_retrieval_v2_dataset import (
    TOP_K,
    build_dataset,
    get_relevant_ids,
    validate_dataset,
)


QUERY_TRACKS = ("service_anchored", "symptom_only")
PERSPECTIVES = ("direct", "diagnostic")
METRICS = ("recall_at_k", "precision_at_k", "mrr")


# ============================================================
# METRIC CALCULATION
# ============================================================


def calculate_metrics(retrieved_ids, relevant_ids, top_k=TOP_K):
    """Calculate Recall@K, Precision@K, and reciprocal rank."""

    if top_k <= 0:
        raise ValueError("top_k must be positive.")

    if len(retrieved_ids) != len(set(retrieved_ids)):
        raise ValueError("Retrieved evidence IDs must be unique.")

    if not relevant_ids:
        raise ValueError("Relevant evidence IDs cannot be empty.")

    retrieved_relevant = [
        evidence_id
        for evidence_id in retrieved_ids[:top_k]
        if evidence_id in relevant_ids
    ]

    reciprocal_rank = 0.0

    for rank, evidence_id in enumerate(retrieved_ids[:top_k], start=1):
        if evidence_id in relevant_ids:
            reciprocal_rank = 1.0 / rank
            break

    return {
        "recall_at_k": len(retrieved_relevant) / len(relevant_ids),
        "precision_at_k": len(retrieved_relevant) / top_k,
        "mrr": reciprocal_rank,
        "relevant_retrieved": len(retrieved_relevant),
        "relevant_total": len(relevant_ids),
    }


# ============================================================
# RETRIEVAL
# ============================================================


def retrieve_ids(
    retriever,
    query,
    evidence_items,
    *,
    topology_enabled,
):
    """
    Retrieve evidence IDs using the same retriever.

    The baseline temporarily disables only topology relevance
    detection. Embedding, chunking, and semantic ranking remain
    unchanged.
    """

    if topology_enabled:
        results = retriever.retrieve(
            query=query,
            evidence_items=evidence_items,
            top_k=TOP_K,
        )
    else:
        with patch(
            "app.retrieval_service._topology_relevant_evidence_ids",
            return_value=set(),
        ):
            results = retriever.retrieve(
                query=query,
                evidence_items=evidence_items,
                top_k=TOP_K,
            )

    return [
        result.chunk.evidence_id
        for result in results
    ]


def evaluate_case(
    case,
    retriever,
    *,
    query_track,
    perspective,
):
    """Compare both retrieval methods for one evaluation combination."""

    if query_track not in QUERY_TRACKS:
        raise ValueError(
            f"query_track must be one of {QUERY_TRACKS}."
        )

    if perspective not in PERSPECTIVES:
        raise ValueError(
            f"perspective must be one of {PERSPECTIVES}."
        )

    query_key = (
        "service_anchored_query"
        if query_track == "service_anchored"
        else "symptom_query"
    )

    query = case[query_key]
    evidence = case["evidence"]
    relevant_ids = get_relevant_ids(case, perspective)

    baseline_ids = retrieve_ids(
        retriever,
        query,
        evidence,
        topology_enabled=False,
    )

    topology_ids = retrieve_ids(
        retriever,
        query,
        evidence,
        topology_enabled=True,
    )

    scenario_ids = {item.id for item in evidence}

    for method_name, retrieved_ids in (
        ("semantic_only", baseline_ids),
        ("topology_aware", topology_ids),
    ):
        if len(retrieved_ids) != len(set(retrieved_ids)):
            raise ValueError(
                f"{method_name} returned duplicate evidence IDs "
                f"in {case['name']}."
            )

        unexpected_ids = set(retrieved_ids) - scenario_ids

        if unexpected_ids:
            raise ValueError(
                f"{method_name} returned evidence outside "
                f"{case['name']}: {sorted(unexpected_ids)}"
            )

    baseline_metrics = calculate_metrics(
        baseline_ids,
        relevant_ids,
    )

    topology_metrics = calculate_metrics(
        topology_ids,
        relevant_ids,
    )

    delta = {
        metric: topology_metrics[metric] - baseline_metrics[metric]
        for metric in METRICS
    }

    evidence_by_id = {
        item.id: item
        for item in evidence
    }

    # Relevant non-trace evidence that was in the baseline Top-5
    # but disappeared from the topology-aware Top-5.
    displaced_useful_non_trace_ids = sorted(
        evidence_id
        for evidence_id in (
            set(baseline_ids[:TOP_K]) - set(topology_ids[:TOP_K])
        )
        if (
            evidence_id in relevant_ids
            and evidence_by_id[evidence_id].source_type != "trace"
        )
    )

    promoted_trace_ids = sorted(
        evidence_id
        for evidence_id in (
            set(topology_ids[:TOP_K]) - set(baseline_ids[:TOP_K])
        )
        if evidence_by_id[evidence_id].source_type == "trace"
    )

    return {
        "scenario": case["name"],
        "incident_id": case["incident_id"],
        "query_track": query_track,
        "perspective": perspective,
        "query": query,
        "baseline": {
            "retrieved_ids": baseline_ids,
            **baseline_metrics,
        },
        "topology_aware": {
            "retrieved_ids": topology_ids,
            **topology_metrics,
        },
        "delta": delta,
        "displaced_useful_non_trace_ids": (
            displaced_useful_non_trace_ids
        ),
        "promoted_trace_ids": promoted_trace_ids,
    }


# ============================================================
# AGGREGATION
# ============================================================


def aggregate_results(results):
    """Calculate macro averages and outcome rates."""

    if not results:
        raise ValueError("Cannot aggregate an empty result set.")

    summary = {}

    for method in ("baseline", "topology_aware"):
        summary[method] = {
            metric: mean(
                result[method][metric]
                for result in results
            )
            for metric in METRICS
        }

    summary["delta"] = {
        metric: (
            summary["topology_aware"][metric]
            - summary["baseline"][metric]
        )
        for metric in METRICS
    }

    recall_deltas = [
        result["delta"]["recall_at_k"]
        for result in results
    ]

    wins = sum(delta > 0 for delta in recall_deltas)
    regressions = sum(delta < 0 for delta in recall_deltas)
    neutral = sum(delta == 0 for delta in recall_deltas)

    summary["recall_outcomes"] = {
        "wins": wins,
        "regressions": regressions,
        "neutral": neutral,
        "win_rate": wins / len(results),
        "regression_rate": regressions / len(results),
        "neutral_rate": neutral / len(results),
    }

    summary["displacement"] = {
        "cases_with_displacement": sum(
            bool(result["displaced_useful_non_trace_ids"])
            for result in results
        ),
        "total_displaced_useful_non_trace_records": sum(
            len(result["displaced_useful_non_trace_ids"])
            for result in results
        ),
    }

    return summary


def aggregate_by_track_and_perspective(results):
    """Produce separate summaries for each query/perspective pair."""

    grouped = defaultdict(list)

    for result in results:
        key = (
            result["query_track"],
            result["perspective"],
        )
        grouped[key].append(result)

    summaries = {}

    for (query_track, perspective), group_results in sorted(
        grouped.items()
    ):
        summaries[f"{query_track}_{perspective}"] = {
            "scenario_count": len(group_results),
            **aggregate_results(group_results),
        }

    return summaries


# ============================================================
# REPORTING
# ============================================================


def _format_metric(value):
    return f"{value:.4f}"


def print_summary_table(title, summary):
    print("\n" + "=" * 94)
    print(title)
    print("=" * 94)

    print(
        f"{'Metric':<20}"
        f"{'Semantic only':>20}"
        f"{'Topology aware':>20}"
        f"{'Change':>20}"
    )

    print("-" * 80)

    for metric, label in (
        ("recall_at_k", "Recall@5"),
        ("precision_at_k", "Precision@5"),
        ("mrr", "MRR"),
    ):
        baseline = summary["baseline"][metric]
        topology = summary["topology_aware"][metric]
        delta = summary["delta"][metric]

        print(
            f"{label:<20}"
            f"{_format_metric(baseline):>20}"
            f"{_format_metric(topology):>20}"
            f"{delta:>+20.4f}"
        )


def print_report(benchmark):
    results = benchmark["results"]
    summary = benchmark["summary"]
    grouped = benchmark["group_summaries"]

    print("\n" + "=" * 94)
    print("OPSPILOT - TOPOLOGY-AWARE RETRIEVAL BENCHMARK V2")
    print("=" * 94)

    print(f"\nScenarios evaluated : {len(build_dataset())}")
    print(f"Evaluation rows     : {len(results)}")
    print(f"Evidence records    : 260")
    print(f"Top K               : {TOP_K}")
    print("Baseline            : Semantic-only retrieval")
    print("Proposed            : Semantic + existing topology boost")
    print("Embedding provider  : Same configured provider for both methods")

    print_summary_table(
        "OVERALL MACRO-AVERAGE RESULTS",
        summary,
    )

    print("\n" + "-" * 94)
    print("RECALL OUTCOMES")
    print("-" * 94)

    outcomes = summary["recall_outcomes"]

    print(f"Topology wins       : {outcomes['wins']}")
    print(f"Topology regressions: {outcomes['regressions']}")
    print(f"No change           : {outcomes['neutral']}")
    print(f"Win rate            : {outcomes['win_rate']:.1%}")
    print(f"Regression rate     : {outcomes['regression_rate']:.1%}")

    displacement = summary["displacement"]

    print("\n" + "-" * 94)
    print("USEFUL NON-TRACE EVIDENCE DISPLACEMENT")
    print("-" * 94)

    print(
        "Evaluation rows with displacement : "
        f"{displacement['cases_with_displacement']}"
    )
    print(
        "Useful non-trace records displaced : "
        f"{displacement['total_displaced_useful_non_trace_records']}"
    )

    for group_name, group_summary in grouped.items():
        print_summary_table(
            f"QUERY TRACK / RELEVANCE PERSPECTIVE: {group_name.upper()}",
            group_summary,
        )

    print("\n" + "=" * 94)
    print("PER-SCENARIO RESULTS")
    print("=" * 94)

    for result in results:
        baseline = result["baseline"]
        topology = result["topology_aware"]
        delta = result["delta"]

        print(
            f"\n{result['scenario']} | "
            f"{result['query_track']} | "
            f"{result['perspective']}"
        )

        print(
            f"  Recall@5    : "
            f"{baseline['recall_at_k']:.3f} -> "
            f"{topology['recall_at_k']:.3f} "
            f"({delta['recall_at_k']:+.3f})"
        )

        print(
            f"  Precision@5 : "
            f"{baseline['precision_at_k']:.3f} -> "
            f"{topology['precision_at_k']:.3f} "
            f"({delta['precision_at_k']:+.3f})"
        )

        print(
            f"  MRR         : "
            f"{baseline['mrr']:.3f} -> "
            f"{topology['mrr']:.3f} "
            f"({delta['mrr']:+.3f})"
        )

        if result["promoted_trace_ids"]:
            print(
                "  Promoted traces                  : "
                f"{result['promoted_trace_ids']}"
            )

        if result["displaced_useful_non_trace_ids"]:
            print(
                "  Displaced useful non-trace records: "
                f"{result['displaced_useful_non_trace_ids']}"
            )

    print("\n" + "=" * 94)
    print("Benchmark completed.")
    print("=" * 94)


# ============================================================
# BENCHMARK EXECUTION
# ============================================================


def run_benchmark(retriever=None):
    """Run all 80 comparisons with one shared retriever instance."""

    cases = build_dataset()
    validate_dataset(cases)

    if retriever is None:
        retriever = EvidenceRetriever()

    results = []

    for case in cases:
        for query_track in QUERY_TRACKS:
            for perspective in PERSPECTIVES:
                results.append(
                    evaluate_case(
                        case,
                        retriever,
                        query_track=query_track,
                        perspective=perspective,
                    )
                )

    expected_rows = (
        len(cases)
        * len(QUERY_TRACKS)
        * len(PERSPECTIVES)
    )

    if len(results) != expected_rows:
        raise ValueError(
            f"Expected {expected_rows} evaluation rows, "
            f"got {len(results)}."
        )

    summary = aggregate_results(results)
    group_summaries = aggregate_by_track_and_perspective(results)

    return {
        "results": results,
        "summary": summary,
        "group_summaries": group_summaries,
    }


def main():
    print("Validating V2 dataset...")
    validate_dataset()
    print("Dataset validation passed.")

    print("Initializing configured embedding provider...")
    print(
        "Running 20 scenarios x 2 query tracks x "
        "2 relevance perspectives..."
    )

    benchmark = run_benchmark()
    print_report(benchmark)


if __name__ == "__main__":
    main()
