
"""
OpsPilot Topology-Aware Retrieval Benchmark V1.

Compares:
1. Semantic-only retrieval.
2. Semantic retrieval with the existing topology relevance boost.

Both methods use the same EvidenceRetriever, evidence records,
embedding provider, and top-k value. The baseline temporarily
disables only the topology relevance-ID calculation.

Run:
    python -m experiments.evaluate_topology_retrieval_v1
"""

import json
from statistics import mean
from types import SimpleNamespace
from unittest.mock import patch

from app.retrieval_service import EvidenceRetriever


TOP_K = 5


# ============================================================
# SYNTHETIC MULTI-SERVICE INCIDENT DATASET
# ============================================================
#
# Each scenario contains 10 records:
# - 3 connected trace spans: upstream -> target -> dependency
# - 2 unrelated trace spans
# - 3 irrelevant log/config records
# - 2 diagnostically relevant log records
#
# The query explicitly mentions the target service.
# The topology implementation should identify the target and
# its directly connected services.
#
# Relevance labels are diagnostic relevance labels:
# connected traces and supporting diagnostic logs are relevant.
# ============================================================


SCENARIO_SPECS = [
    {
        "name": "Checkout requests failing due to payment dependency",
        "query": "Investigate checkout-api failures and identify the dependency involved",
        "target": "checkout-api",
        "upstream": "api-gateway",
        "dependency": "payment-service",
        "unrelated": "catalog-service",
        "second_unrelated": "email-service",
        "target_log": (
            "checkout-api requests are failing while waiting for "
            "the payment dependency response."
        ),
        "dependency_log": (
            "payment-service reports connection timeouts while "
            "processing authorization requests."
        ),
        "irrelevant_log": (
            "catalog-service completed a routine product refresh."
        ),
        "irrelevant_config": (
            "The email-service notification batch size is configured to 100."
        ),
    },
    {
        "name": "Inventory reads stale after cache dependency failure",
        "query": "Investigate inventory-api failures and its connected services",
        "target": "inventory-api",
        "upstream": "warehouse-gateway",
        "dependency": "cache-service",
        "unrelated": "email-service",
        "second_unrelated": "search-service",
        "target_log": (
            "inventory-api continues returning stale stock values "
            "after warehouse updates."
        ),
        "dependency_log": (
            "cache-service failed to invalidate inventory entries "
            "after receiving update notifications."
        ),
        "irrelevant_log": (
            "email-service successfully delivered a scheduled notification."
        ),
        "irrelevant_config": (
            "The search-service index refresh interval is set to ten minutes."
        ),
    },
    {
        "name": "Authentication failures caused by identity dependency",
        "query": "Investigate auth-service failures and its service dependencies",
        "target": "auth-service",
        "upstream": "edge-proxy",
        "dependency": "identity-database",
        "unrelated": "search-service",
        "second_unrelated": "notification-service",
        "target_log": (
            "auth-service rejected valid sessions while validating "
            "user authentication requests."
        ),
        "dependency_log": (
            "identity-database reported connection acquisition failures "
            "during authentication."
        ),
        "irrelevant_log": (
            "search-service completed a successful index optimization."
        ),
        "irrelevant_config": (
            "The notification-service retry interval is configured to 30 seconds."
        ),
    },
    {
        "name": "Reporting requests failing due to analytics dependency",
        "query": "Investigate report-api failures and the connected analytics service",
        "target": "report-api",
        "upstream": "scheduler-service",
        "dependency": "analytics-database",
        "unrelated": "notification-service",
        "second_unrelated": "catalog-service",
        "target_log": (
            "report-api requests are timing out while generating daily reports."
        ),
        "dependency_log": (
            "analytics-database reports slow queries and exhausted "
            "connections during report generation."
        ),
        "irrelevant_log": (
            "notification-service completed a routine delivery batch."
        ),
        "irrelevant_config": (
            "The catalog-service cache expiration is set to five minutes."
        ),
    },
]


def _trace_record(
    *,
    evidence_id,
    incident_id,
    service_name,
    span_id,
    parent_span_id=None,
    trace_suffix=0,
    status_code=0,
):
    """Build a normalized trace record accepted by app.telemetry."""

    record = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": f"{incident_id + trace_suffix:032x}",
        "span_id": f"{span_id:016x}",
        "parent_span_id": (
            f"{parent_span_id:016x}"
            if parent_span_id is not None
            else None
        ),
        "service_name": service_name,
        "span_name": "request",
        "span_kind": 1,
        "start_time_unix_nano": 1_000_000,
        "end_time_unix_nano": 6_000_000,
        "duration_ms": 5.0,
        "status_code": status_code,
        "status_message": "",
        "attributes": {},
        "events": [],
    }

    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        source_type="trace",
        content=json.dumps(record, separators=(",", ":")),
    )


def _text_record(evidence_id, incident_id, source_type, content):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        source_type=source_type,
        content=content,
    )


def build_dataset():
    """
    Build deterministic benchmark scenarios.

    Evidence IDs are globally unique across all scenarios.
    Every scenario contains exactly 10 records.
    """

    cases = []

    for index, spec in enumerate(SCENARIO_SPECS):
        incident_id = 7001 + index
        base_id = 3000 + (index * 100)

        upstream_id = base_id + 6
        target_id = base_id + 7
        dependency_id = base_id + 8

        evidence = [
            # Two unrelated traces appear first deliberately.
            # They provide a useful ranking test when semantic
            # scores are tied or similar.
            _trace_record(
                evidence_id=base_id + 1,
                incident_id=incident_id,
                service_name=spec["unrelated"],
                span_id=base_id + 1,
                trace_suffix=1000,
            ),
            _trace_record(
                evidence_id=base_id + 2,
                incident_id=incident_id,
                service_name=spec["second_unrelated"],
                span_id=base_id + 2,
                trace_suffix=2000,
            ),

            # Irrelevant non-trace evidence.
            _text_record(
                base_id + 3,
                incident_id,
                "log",
                spec["irrelevant_log"],
            ),
            _text_record(
                base_id + 4,
                incident_id,
                "config",
                spec["irrelevant_config"],
            ),
            _text_record(
                base_id + 5,
                incident_id,
                "metric",
                "Unrelated background workload remained within normal limits.",
            ),

            # Connected trace chain:
            # upstream -> target -> dependency
            _trace_record(
                evidence_id=upstream_id,
                incident_id=incident_id,
                service_name=spec["upstream"],
                span_id=upstream_id,
            ),
            _trace_record(
                evidence_id=target_id,
                incident_id=incident_id,
                service_name=spec["target"],
                span_id=target_id,
                parent_span_id=upstream_id,
            ),
            _trace_record(
                evidence_id=dependency_id,
                incident_id=incident_id,
                service_name=spec["dependency"],
                span_id=dependency_id,
                parent_span_id=target_id,
                status_code=2,
            ),

            # Relevant diagnostic logs.
            _text_record(
                base_id + 9,
                incident_id,
                "log",
                spec["target_log"],
            ),
            _text_record(
                base_id + 10,
                incident_id,
                "log",
                spec["dependency_log"],
            ),
        ]

        relevant_ids = {
            upstream_id,
            target_id,
            dependency_id,
            base_id + 9,
            base_id + 10,
        }

        cases.append(
            {
                "name": spec["name"],
                "query": spec["query"],
                "incident_id": incident_id,
                "evidence": evidence,
                "relevant_ids": relevant_ids,
            }
        )

    return cases


# ============================================================
# DATASET VALIDATION
# ============================================================


def validate_dataset(cases=None):
    if cases is None:
        cases = build_dataset()

    if len(cases) != len(SCENARIO_SPECS):
        raise ValueError("Unexpected number of benchmark scenarios.")

    all_ids = set()

    for case in cases:
        if not case["name"].strip():
            raise ValueError("Scenario name cannot be empty.")

        if not case["query"].strip():
            raise ValueError(
                f"Empty query in scenario: {case['name']}"
            )

        evidence = case["evidence"]

        if not 8 <= len(evidence) <= 10:
            raise ValueError(
                f"{case['name']} must contain 8-10 evidence records."
            )

        scenario_ids = set()

        for item in evidence:
            evidence_id = item.id

            if (
                not isinstance(evidence_id, int)
                or isinstance(evidence_id, bool)
            ):
                raise ValueError("Evidence IDs must be integers.")

            if evidence_id in scenario_ids or evidence_id in all_ids:
                raise ValueError(
                    f"Duplicate evidence ID: {evidence_id}"
                )

            scenario_ids.add(evidence_id)
            all_ids.add(evidence_id)

            if item.incident_id != case["incident_id"]:
                raise ValueError(
                    f"Incorrect incident ID for evidence {evidence_id}."
                )

            if not isinstance(item.content, str) or not item.content.strip():
                raise ValueError(
                    f"Empty content for evidence {evidence_id}."
                )

        if not case["relevant_ids"]:
            raise ValueError(
                f"No relevant evidence in {case['name']}."
            )

        if not case["relevant_ids"].issubset(scenario_ids):
            raise ValueError(
                f"Unknown relevant evidence ID in {case['name']}."
            )

    return True


# ============================================================
# METRIC CALCULATION
# ============================================================


def calculate_metrics(retrieved_ids, relevant_ids, top_k=TOP_K):
    """
    Calculate Recall@K, Precision@K, and reciprocal rank.

    Precision@K uses K as the denominator, even if fewer than
    K results are returned.
    """

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

    recall = len(retrieved_relevant) / len(relevant_ids)
    precision = len(retrieved_relevant) / top_k

    reciprocal_rank = 0.0

    for rank, evidence_id in enumerate(
        retrieved_ids[:top_k],
        start=1,
    ):
        if evidence_id in relevant_ids:
            reciprocal_rank = 1.0 / rank
            break

    return {
        "recall_at_k": recall,
        "precision_at_k": precision,
        "mrr": reciprocal_rank,
        "relevant_retrieved": len(retrieved_relevant),
        "relevant_total": len(relevant_ids),
    }


# ============================================================
# RETRIEVAL COMPARISON
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

    When topology_enabled=False, temporarily replace only the
    topology relevance-ID calculation with an empty result.
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


def evaluate_case(case, retriever):
    evidence = case["evidence"]
    query = case["query"]

    # Baseline: semantic retrieval only.
    baseline_ids = retrieve_ids(
        retriever,
        query,
        evidence,
        topology_enabled=False,
    )

    # Proposed: semantic retrieval + topology relevance boost.
    topology_ids = retrieve_ids(
        retriever,
        query,
        evidence,
        topology_enabled=True,
    )

    scenario_ids = {
        item.id
        for item in evidence
    }

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
        case["relevant_ids"],
    )

    topology_metrics = calculate_metrics(
        topology_ids,
        case["relevant_ids"],
    )

    return {
        "scenario": case["name"],
        "baseline": {
            "retrieved_ids": baseline_ids,
            **baseline_metrics,
        },
        "topology_aware": {
            "retrieved_ids": topology_ids,
            **topology_metrics,
        },
        "delta": {
            metric: (
                topology_metrics[metric] - baseline_metrics[metric]
            )
            for metric in (
                "recall_at_k",
                "precision_at_k",
                "mrr",
            )
        },
    }


# ============================================================
# AGGREGATION AND REPORTING
# ============================================================


def aggregate_results(results):
    if not results:
        raise ValueError("Cannot aggregate an empty result set.")

    metrics = (
        "recall_at_k",
        "precision_at_k",
        "mrr",
    )

    summary = {}

    for method in ("baseline", "topology_aware"):
        summary[method] = {
            metric: mean(
                result[method][metric]
                for result in results
            )
            for metric in metrics
        }

    summary["delta"] = {
        metric: (
            summary["topology_aware"][metric]
            - summary["baseline"][metric]
        )
        for metric in metrics
    }

    return summary



def print_report(results, summary):
    width = 88

    print("\n" + "=" * width)
    print("OPSPILOT - TOPOLOGY-AWARE RETRIEVAL BENCHMARK V1")
    print("=" * width)

    print(f"\nScenarios evaluated : {len(results)}")
    print(f"Top K               : {TOP_K}")
    print("Baseline            : Semantic-only retrieval")
    print("Proposed            : Semantic + topology boost")

    print("\n" + "-" * width)
    print("AGGREGATE MACRO-AVERAGE METRICS")
    print("-" * width)

    print(
        f"{'Metric':<20}"
        f"{'Semantic only':>20}"
        f"{'Topology aware':>20}"
        f"{'Improvement':>20}"
    )

    print("-" * width)

    for metric, label in (
        ("recall_at_k", "Recall@5"),
        ("precision_at_k", "Precision@5"),
        ("mrr", "MRR"),
    ):
        baseline = summary["baseline"][metric]
        proposed = summary["topology_aware"][metric]
        delta = summary["delta"][metric]

        print(
            f"{label:<20}"
            f"{baseline:>20.4f}"
            f"{proposed:>20.4f}"
            f"{delta:>+20.4f}"
        )

    print("\n" + "-" * width)
    print("PER-SCENARIO RESULTS")
    print("-" * width)

    for result in results:
        baseline = result["baseline"]
        proposed = result["topology_aware"]
        delta = result["delta"]

        print(f"\n{result['scenario']}")

        print(
            "  Semantic only : "
            f"Recall={baseline['recall_at_k']:.3f}, "
            f"Precision={baseline['precision_at_k']:.3f}, "
            f"MRR={baseline['mrr']:.3f}"
        )

        print(
            "  Topology aware: "
            f"Recall={proposed['recall_at_k']:.3f}, "
            f"Precision={proposed['precision_at_k']:.3f}, "
            f"MRR={proposed['mrr']:.3f}"
        )

        print(
            "  Change        : "
            f"Recall={delta['recall_at_k']:+.3f}, "
            f"Precision={delta['precision_at_k']:+.3f}, "
            f"MRR={delta['mrr']:+.3f}"
        )

        print(f"  Baseline IDs  : {baseline['retrieved_ids']}")
        print(f"  Topology IDs  : {proposed['retrieved_ids']}")

    print("\n" + "=" * width)
    print("Benchmark completed.")
    print("=" * width)



# ============================================================
# MAIN
# ============================================================


def run_benchmark(retriever=None):
    cases = build_dataset()
    validate_dataset(cases)

    if retriever is None:
        retriever = EvidenceRetriever()

    results = [
        evaluate_case(case, retriever)
        for case in cases
    ]

    summary = aggregate_results(results)

    return {
        "results": results,
        "summary": summary,
    }


def main():
    print("Validating topology benchmark dataset...")

    validate_dataset()

    print("Dataset validation passed.")
    print("Initializing configured embedding provider...")

    benchmark = run_benchmark()

    print_report(
        benchmark["results"],
        benchmark["summary"],
    )


if __name__ == "__main__":
    main()
