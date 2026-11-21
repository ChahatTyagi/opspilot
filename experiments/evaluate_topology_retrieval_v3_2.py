
"""V3.2 boost-strength sensitivity evaluation.

Tests downstream-only topology retrieval at multiple boost strengths.

Production retrieval code is not modified.
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

from experiments.evaluate_topology_retrieval_v3_1 import (
    topology_ids_for_method,
    validate_retrieved_ids,
)


BOOST_STRENGTHS = (
    0.00,
    0.025,
    0.05,
    0.075,
    0.10,
    0.15,
    0.20,
)

BASELINE = "semantic_only"
STRATEGY = "downstream_only"


def retrieve_ids(
    retriever,
    query,
    evidence_items,
    *,
    boost,
    method,
):
    """Retrieve evidence using an isolated boost configuration."""

    if method not in ("semantic_only", "downstream_only"):
        raise ValueError(
            "method must be semantic_only or downstream_only."
        )

    if method == "semantic_only":
        selected_ids = set()
    else:
        selected_ids = topology_ids_for_method(
            query=query,
            evidence_items=evidence_items,
            method=STRATEGY,
        )

    with (
        patch(
            "app.retrieval_service._topology_relevant_evidence_ids",
            return_value=selected_ids,
        ),
        patch(
            "app.retrieval_service.TOPOLOGY_RELEVANCE_BOOST",
            boost,
        ),
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
    boost,
):
    """Evaluate semantic-only and downstream-only retrieval."""

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

    method_results = {}

    for method in ("semantic_only", "downstream_only"):
        retrieved_ids = retrieve_ids(
            retriever,
            query,
            evidence,
            boost=boost,
            method=method,
        )

        validate_retrieved_ids(
            method,
            retrieved_ids,
            scenario_ids,
            case["name"],
        )

        method_results[method] = {
            "retrieved_ids": retrieved_ids,
            **calculate_metrics(
                retrieved_ids,
                relevant_ids,
            ),
        }

    return {
        "scenario": case["name"],
        "query_track": query_track,
        "perspective": perspective,
        "boost": boost,
        "methods": method_results,
    }


def aggregate_results(results):
    """Aggregate macro metrics for one boost strength."""

    summary = {}

    for method in ("semantic_only", "downstream_only"):
        summary[method] = {
            metric: mean(
                row["methods"][method][metric]
                for row in results
            )
            for metric in METRICS
        }

    return summary


def aggregate_groups(results):
    """Aggregate metrics by query track and perspective."""

    groups = defaultdict(list)

    for row in results:
        key = (
            row["query_track"],
            row["perspective"],
        )
        groups[key].append(row)

    summaries = {}

    for (query_track, perspective), rows in sorted(groups.items()):
        name = f"{query_track}__{perspective}"

        summaries[name] = {}

        for method in ("semantic_only", "downstream_only"):
            summaries[name][method] = {
                metric: mean(
                    row["methods"][method][metric]
                    for row in rows
                )
                for metric in METRICS
            }

    return summaries


def compare_against_baseline(results):
    """Compare downstream-only ranking with semantic-only ranking."""

    wins = 0
    regressions = 0
    unchanged = 0

    for row in results:
        baseline = row["methods"]["semantic_only"]
        candidate = row["methods"]["downstream_only"]

        delta = (
            candidate["recall_at_k"]
            - baseline["recall_at_k"]
        )

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


def run_single_boost(retriever, cases, boost):
    """Evaluate all 80 rows for one boost strength."""

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
                        boost=boost,
                    )
                )

    expected_rows = (
        len(cases)
        * len(QUERY_TRACKS)
        * len(PERSPECTIVES)
    )

    if len(results) != expected_rows:
        raise ValueError(
            f"Expected {expected_rows} rows, got {len(results)}."
        )

    return {
        "boost": boost,
        "results": results,
        "summary": aggregate_results(results),
        "group_summaries": aggregate_groups(results),
        "outcomes": compare_against_baseline(results),
    }


def run_benchmark(retriever=None):
    """Run the complete boost-strength sensitivity experiment."""

    cases = build_dataset()
    validate_dataset(cases)

    if retriever is None:
        retriever = EvidenceRetriever()

    experiments = []

    for boost in BOOST_STRENGTHS:
        experiments.append(
            run_single_boost(
                retriever,
                cases,
                boost,
            )
        )

    return {
        "experiments": experiments,
        "scenario_count": len(cases),
        "evidence_count": sum(
            len(case["evidence"])
            for case in cases
        ),
    }


def print_summary(benchmark):
    """Print overall metrics for each boost strength."""

    print("\nBOOST-STRENGTH SENSITIVITY")
    print("=" * 105)

    print(
        f"{'Boost':>8}"
        f"{'Recall@5':>12}"
        f"{'Precision@5':>15}"
        f"{'MRR':>12}"
        f"{'Wins':>9}"
        f"{'Regressions':>14}"
        f"{'Unchanged':>12}"
    )

    print("-" * 105)

    for experiment in benchmark["experiments"]:
        values = experiment["summary"]["downstream_only"]
        outcomes = experiment["outcomes"]

        print(
            f"{experiment['boost']:>8.3f}"
            f"{values['recall_at_k']:>12.4f}"
            f"{values['precision_at_k']:>15.4f}"
            f"{values['mrr']:>12.4f}"
            f"{outcomes['wins']:>9}"
            f"{outcomes['regressions']:>14}"
            f"{outcomes['unchanged']:>12}"
        )


def print_group_summary(benchmark):
    """Print downstream-only results for each evaluation group."""

    print("\nGROUPED DOWNSTREAM-ONLY METRICS")
    print("=" * 90)

    for experiment in benchmark["experiments"]:
        print(f"\nBoost = {experiment['boost']:.3f}")

        for group, methods in experiment["group_summaries"].items():
            values = methods["downstream_only"]

            print(
                f"  {group:<35}"
                f"Recall={values['recall_at_k']:.4f}  "
                f"Precision={values['precision_at_k']:.4f}  "
                f"MRR={values['mrr']:.4f}"
            )


def main():
    """Run and display the V3.2 experiment."""

    benchmark = run_benchmark()

    print("TOPOLOGY RETRIEVAL V3.2 — BOOST SENSITIVITY")
    print("=" * 90)
    print(f"Scenarios       : {benchmark['scenario_count']}")
    print(f"Evidence        : {benchmark['evidence_count']}")
    print(f"Top-K           : {TOP_K}")
    print(f"Boost strengths : {BOOST_STRENGTHS}")
    print(f"Strategy        : {STRATEGY}")
    print("Production code : unchanged")

    print_summary(benchmark)
    print_group_summary(benchmark)

    return benchmark


if __name__ == "__main__":
    main()
