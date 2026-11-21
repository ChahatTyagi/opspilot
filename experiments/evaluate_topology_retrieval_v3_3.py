
"""V3.3 robustness evaluation for downstream topology retrieval.

Tests stronger topology boost values and measures:
- Retrieval quality
- Recall wins, regressions, and unchanged rows
- Useful non-trace evidence displaced from semantic Top-K
- Trace evidence promoted into candidate Top-K
- Performance across query-track and relevance groups

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
    0.20,
    0.25,
    0.30,
    0.40,
)

BASELINE = "semantic_only"
CANDIDATE = "downstream_only"
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

    if method not in (BASELINE, CANDIDATE):
        raise ValueError(
            f"method must be {BASELINE} or {CANDIDATE}."
        )

    if method == BASELINE:
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
    boost,
):
    """Evaluate semantic-only and downstream-only for one query."""

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

    for method in (BASELINE, CANDIDATE):
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

    baseline_ids = method_results[BASELINE]["retrieved_ids"]
    candidate_ids = method_results[CANDIDATE]["retrieved_ids"]

    baseline_metrics = method_results[BASELINE]
    candidate_metrics = method_results[CANDIDATE]

    comparisons = {
        "delta": {
            metric: (
                candidate_metrics[metric]
                - baseline_metrics[metric]
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
        "query_track": query_track,
        "perspective": perspective,
        "boost": boost,
        "methods": method_results,
        "comparisons": comparisons,
    }


def aggregate_results(results):
    """Aggregate macro metrics for one boost strength."""

    summary = {}

    for method in (BASELINE, CANDIDATE):
        summary[method] = {
            metric: mean(
                row["methods"][method][metric]
                for row in results
            )
            for metric in METRICS
        }

    return summary


def aggregate_groups(results):
    """Aggregate metrics by query track and relevance perspective."""

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

        summaries[group_name] = {}

        for method in (BASELINE, CANDIDATE):
            summaries[group_name][method] = {
                metric: mean(
                    row["methods"][method][metric]
                    for row in rows
                )
                for metric in METRICS
            }

    return summaries


def compare_against_baseline(results):
    """Count recall wins, regressions, and unchanged rows."""

    wins = 0
    regressions = 0
    unchanged = 0

    for row in results:
        delta = row["comparisons"]["delta"]["recall_at_k"]

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


def displacement_summary(results):
    """Summarize useful non-trace displacement and trace promotion."""

    return {
        "useful_non_trace_displacements": sum(
            len(
                row["comparisons"]["displaced_useful_non_trace_ids"]
            )
            for row in results
        ),
        "promoted_trace_records": sum(
            len(row["comparisons"]["promoted_trace_ids"])
            for row in results
        ),
    }


def run_single_boost(retriever, cases, boost):
    """Evaluate all query/perspective rows for one boost."""

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
        "displacement": displacement_summary(results),
    }


def run_benchmark(retriever=None):
    """Run the complete V3.3 boost robustness experiment."""

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
    """Print overall retrieval quality and displacement."""

    print("\nBOOST ROBUSTNESS RESULTS")
    print("=" * 120)

    print(
        f"{'Boost':>8}"
        f"{'Recall@5':>12}"
        f"{'Precision@5':>15}"
        f"{'MRR':>12}"
        f"{'Wins':>8}"
        f"{'Regressions':>14}"
        f"{'Unchanged':>12}"
        f"{'Displaced':>12}"
        f"{'Promoted':>11}"
    )

    print("-" * 120)

    for experiment in benchmark["experiments"]:
        values = experiment["summary"][CANDIDATE]
        outcomes = experiment["outcomes"]
        displacement = experiment["displacement"]

        print(
            f"{experiment['boost']:>8.3f}"
            f"{values['recall_at_k']:>12.4f}"
            f"{values['precision_at_k']:>15.4f}"
            f"{values['mrr']:>12.4f}"
            f"{outcomes['wins']:>8}"
            f"{outcomes['regressions']:>14}"
            f"{outcomes['unchanged']:>12}"
            f"{displacement['useful_non_trace_displacements']:>12}"
            f"{displacement['promoted_trace_records']:>11}"
        )


def print_group_summary(benchmark):
    """Print downstream-only metrics for all four query groups."""

    print("\nGROUPED DOWNSTREAM-ONLY METRICS")
    print("=" * 95)

    for experiment in benchmark["experiments"]:
        print(f"\nBoost = {experiment['boost']:.3f}")

        for group, methods in experiment["group_summaries"].items():
            values = methods[CANDIDATE]

            print(
                f"  {group:<35}"
                f"Recall={values['recall_at_k']:.4f}  "
                f"Precision={values['precision_at_k']:.4f}  "
                f"MRR={values['mrr']:.4f}"
            )


def main():
    """Run and display the V3.3 experiment."""

    benchmark = run_benchmark()

    print("TOPOLOGY RETRIEVAL V3.3 - BOOST ROBUSTNESS")
    print("=" * 95)
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
