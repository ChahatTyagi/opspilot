
"""Three-way evaluation of semantic, broad-topology, and directional retrieval.

Methods:
1. semantic_only: topology relevance selection disabled
2. topology_v2: existing broad topology-aware selection
3. topology_v3: direction-aware topology selection

All methods share one EvidenceRetriever instance and the same dataset.

This is an isolated experiment. Production retrieval is not modified.
"""

from collections import defaultdict
from statistics import mean
from unittest.mock import patch

from app.retrieval_service import EvidenceRetriever

from experiments.evaluate_topology_retrieval_v2 import (
    METRICS,
    PERSPECTIVES,
    QUERY_TRACKS,
    calculate_metrics,
)

from experiments.topology_retrieval_v2_dataset import (
    TOP_K,
    build_dataset,
    get_relevant_ids,
    validate_dataset,
)

from experiments.topology_retrieval_v3 import (
    directional_topology_relevant_evidence_ids,
)


METHODS = (
    "semantic_only",
    "topology_v2",
    "topology_v3",
)

METRIC_LABELS = {
    "recall_at_k": "Recall@5",
    "precision_at_k": "Precision@5",
    "mrr": "MRR",
}


def retrieve_ids(
    retriever,
    query,
    evidence_items,
    *,
    method,
):
    """Retrieve evidence IDs using the selected topology strategy."""

    if method not in METHODS:
        raise ValueError(
            f"method must be one of {METHODS}."
        )

    if method == "semantic_only":
        with patch(
            "app.retrieval_service._topology_relevant_evidence_ids",
            return_value=set(),
        ):
            results = retriever.retrieve(
                query=query,
                evidence_items=evidence_items,
                top_k=TOP_K,
            )

    elif method == "topology_v2":
        results = retriever.retrieve(
            query=query,
            evidence_items=evidence_items,
            top_k=TOP_K,
        )

    else:
        with patch(
            "app.retrieval_service._topology_relevant_evidence_ids",
            side_effect=directional_topology_relevant_evidence_ids,
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


def validate_retrieved_ids(
    method,
    retrieved_ids,
    scenario_ids,
    scenario_name,
):
    """Reject duplicate and cross-scenario retrieval results."""

    if len(retrieved_ids) != len(set(retrieved_ids)):
        raise ValueError(
            f"{method} returned duplicate evidence IDs "
            f"in {scenario_name}."
        )

    unexpected_ids = set(retrieved_ids) - scenario_ids

    if unexpected_ids:
        raise ValueError(
            f"{method} returned evidence outside {scenario_name}: "
            f"{sorted(unexpected_ids)}"
        )


def find_displaced_useful_non_trace_ids(
    baseline_ids,
    candidate_ids,
    relevant_ids,
    evidence_by_id,
):
    """Find useful non-trace records displaced from baseline Top-K."""

    return sorted(
        evidence_id
        for evidence_id in (
            set(baseline_ids[:TOP_K])
            - set(candidate_ids[:TOP_K])
        )
        if (
            evidence_id in relevant_ids
            and evidence_by_id[evidence_id].source_type != "trace"
        )
    )


def find_promoted_trace_ids(
    baseline_ids,
    candidate_ids,
    evidence_by_id,
):
    """Find trace records newly entering the candidate Top-K."""

    return sorted(
        evidence_id
        for evidence_id in (
            set(candidate_ids[:TOP_K])
            - set(baseline_ids[:TOP_K])
        )
        if evidence_by_id[evidence_id].source_type == "trace"
    )


def evaluate_case(
    case,
    retriever,
    *,
    query_track,
    perspective,
):
    """Evaluate all three methods for one query/perspective combination."""

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

    scenario_ids = {
        item.id for item in evidence
    }

    evidence_by_id = {
        item.id: item for item in evidence
    }

    method_results = {}

    for method in METHODS:
        retrieved_ids = retrieve_ids(
            retriever,
            query,
            evidence,
            method=method,
        )

        validate_retrieved_ids(
            method,
            retrieved_ids,
            scenario_ids,
            case["name"],
        )

        metrics = calculate_metrics(
            retrieved_ids,
            relevant_ids,
        )

        method_results[method] = {
            "retrieved_ids": retrieved_ids,
            **metrics,
        }

    baseline_ids = method_results["semantic_only"]["retrieved_ids"]

    comparisons = {}

    for candidate in ("topology_v2", "topology_v3"):
        candidate_ids = method_results[candidate]["retrieved_ids"]

        comparisons[candidate] = {
            "delta": {
                metric: (
                    method_results[candidate][metric]
                    - method_results["semantic_only"][metric]
                )
                for metric in METRICS
            },
            "displaced_useful_non_trace_ids": (
                find_displaced_useful_non_trace_ids(
                    baseline_ids,
                    candidate_ids,
                    relevant_ids,
                    evidence_by_id,
                )
            ),
            "promoted_trace_ids": find_promoted_trace_ids(
                baseline_ids,
                candidate_ids,
                evidence_by_id,
            ),
        }

    return {
        "scenario": case["name"],
        "incident_id": case["incident_id"],
        "query_track": query_track,
        "perspective": perspective,
        "query": query,
        "methods": method_results,
        "comparisons": comparisons,
    }


def aggregate_method_results(results):
    """Calculate macro metrics independently for every method."""

    summary = {}

    for method in METHODS:
        summary[method] = {
            metric: mean(
                row["methods"][method][metric]
                for row in results
            )
            for metric in METRICS
        }

    return summary


def aggregate_by_group(results):
    """Calculate metrics for each query-track/perspective group."""

    groups = defaultdict(list)

    for row in results:
        key = (
            row["query_track"],
            row["perspective"],
        )
        groups[key].append(row)

    summaries = {}

    for (query_track, perspective), rows in sorted(groups.items()):
        group_name = f"{query_track}__{perspective}"

        summaries[group_name] = {
            method: {
                metric: mean(
                    row["methods"][method][metric]
                    for row in rows
                )
                for metric in METRICS
            }
            for method in METHODS
        }

    return summaries


def compare_outcomes(results, candidate):
    """Count recall wins, regressions, and unchanged evaluation rows."""

    wins = 0
    regressions = 0
    unchanged = 0

    for row in results:
        delta = row["comparisons"][candidate]["delta"]["recall_at_k"]

        if delta > 0:
            wins += 1
        elif delta < 0:
            regressions += 1
        else:
            unchanged += 1

    total = len(results)

    return {
        "wins": wins,
        "regressions": regressions,
        "unchanged": unchanged,
        "win_rate": wins / total,
        "regression_rate": regressions / total,
    }


def displacement_summary(results, candidate):
    """Summarize useful non-trace displacement and trace promotion."""

    displaced = sum(
        len(
            row["comparisons"][candidate][
                "displaced_useful_non_trace_ids"
            ]
        )
        for row in results
    )

    promoted = sum(
        len(
            row["comparisons"][candidate]["promoted_trace_ids"]
        )
        for row in results
    )

    return {
        "useful_non_trace_displacements": displaced,
        "promoted_trace_records": promoted,
    }


def run_benchmark(retriever=None):
    """Run all evaluation rows with one shared retriever instance."""

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

    return {
        "results": results,
        "summary": aggregate_method_results(results),
        "group_summaries": aggregate_by_group(results),
        "outcomes": {
            candidate: compare_outcomes(results, candidate)
            for candidate in ("topology_v2", "topology_v3")
        },
        "displacement": {
            candidate: displacement_summary(results, candidate)
            for candidate in ("topology_v2", "topology_v3")
        },
    }


def print_summary_table(summary):
    """Print overall macro retrieval metrics."""

    print("\nOVERALL MACRO METRICS")
    print("-" * 75)

    print(
        f"{'Method':<18}"
        f"{'Recall@5':>12}"
        f"{'Precision@5':>15}"
        f"{'MRR':>12}"
    )

    print("-" * 75)

    for method in METHODS:
        values = summary[method]

        print(
            f"{method:<18}"
            f"{values['recall_at_k']:>12.4f}"
            f"{values['precision_at_k']:>15.4f}"
            f"{values['mrr']:>12.4f}"
        )


def print_group_summary(group_summaries):
    """Print metrics grouped by query track and relevance perspective."""

    print("\nGROUPED METRICS")
    print("-" * 100)

    for group, methods in group_summaries.items():
        print(f"\n{group}")

        for method in METHODS:
            values = methods[method]

            print(
                f"  {method:<16}"
                f"Recall={values['recall_at_k']:.4f}  "
                f"Precision={values['precision_at_k']:.4f}  "
                f"MRR={values['mrr']:.4f}"
            )


def print_comparison_summary(outcomes, displacement):
    """Print per-row outcomes and displacement for both topology methods."""

    print("\nCOMPARISON AGAINST SEMANTIC-ONLY BASELINE")
    print("-" * 75)

    for candidate in ("topology_v2", "topology_v3"):
        outcome = outcomes[candidate]
        impact = displacement[candidate]

        print(f"\n{candidate}")
        print(f"  Recall wins        : {outcome['wins']}")
        print(f"  Recall regressions : {outcome['regressions']}")
        print(f"  No change          : {outcome['unchanged']}")
        print(f"  Win rate           : {outcome['win_rate']:.1%}")
        print(
            f"  Regression rate    : "
            f"{outcome['regression_rate']:.1%}"
        )
        print(
            "  Useful non-trace records displaced: "
            f"{impact['useful_non_trace_displacements']}"
        )
        print(
            "  Trace records promoted: "
            f"{impact['promoted_trace_records']}"
        )


def main():
    """Run and print the complete three-way experiment."""

    benchmark = run_benchmark()

    print("TOPOLOGY RETRIEVAL V3 — THREE-WAY EVALUATION")
    print("=" * 75)
    print(f"Scenarios       : {len(build_dataset())}")
    print(f"Evaluation rows : {len(benchmark['results'])}")
    print(f"Evidence        : 260 expected")
    print(f"Top-K           : {TOP_K}")
    print("Methods         : semantic-only, topology V2, directional V3")
    print("Production code : unchanged")

    print_summary_table(benchmark["summary"])
    print_group_summary(benchmark["group_summaries"])
    print_comparison_summary(
        benchmark["outcomes"],
        benchmark["displacement"],
    )

    return benchmark


if __name__ == "__main__":
    main()
