
from statistics import mean
from types import SimpleNamespace

from app.investigation_tools import search_incident_evidence

from experiments.evaluate_final_retrieval import (
    search_with_porter_stemming,
    search_with_query_expansion,
    search_with_hybrid_retrieval,
)

from experiments.evaluate_final_retrieval_v2 import FINAL_TEST_CASES

from experiments.retrieval_v3_labels import (
    EVIDENCE_LABELS,
    DIRECT_RELEVANT_IDS,
    DIAGNOSTIC_RELEVANT_IDS,
    validate_labels,
)


# ============================================================
# OPSPILOT FINAL RETRIEVAL BENCHMARK V3
#
# Dataset:
# 20 scenarios x 8 evidence records = 160 records.
#
# Evaluation perspectives:
# 1. Direct relevance
# 2. Diagnostic relevance
#
# Retrieval methods:
# 1. Baseline
# 2. Porter stemming
# 3. Query expansion
# 4. Hybrid retrieval
#
# V1 and V2 remain unchanged.
# ============================================================


TOP_K = 5

RELEVANCE_PERSPECTIVES = {
    "Direct relevance": DIRECT_RELEVANT_IDS,
    "Diagnostic relevance": DIAGNOSTIC_RELEVANT_IDS,
}


# ============================================================
# DATASET AND LABEL VALIDATION
# ============================================================

def validate_v3_dataset():

    # Validate all manually assigned V3 relevance labels.
    validate_labels()

    scenario_names = set()
    actual_evidence_ids = set()

    for case in FINAL_TEST_CASES:

        name = case["name"]

        if name in scenario_names:
            raise ValueError(f"Duplicate scenario name: {name}")

        scenario_names.add(name)

        query = case["query"]

        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"Invalid query in scenario: {name}")

        evidence_records = case["evidence"]

        if not 8 <= len(evidence_records) <= 10:
            raise ValueError(
                f"{name} must contain 8-10 evidence records."
            )

        for record in evidence_records:

            if len(record) != 4:
                raise ValueError(
                    f"Invalid evidence tuple in scenario: {name}"
                )

            evidence_id, source_type, content, old_relevance = record

            if evidence_id in actual_evidence_ids:
                raise ValueError(
                    f"Duplicate evidence ID: {evidence_id}"
                )

            actual_evidence_ids.add(evidence_id)

            if not isinstance(source_type, str) or not source_type.strip():
                raise ValueError(
                    f"Invalid source type for evidence {evidence_id}"
                )

            if not isinstance(content, str) or not content.strip():
                raise ValueError(
                    f"Invalid content for evidence {evidence_id}"
                )

            if not isinstance(old_relevance, bool):
                raise ValueError(
                    f"Invalid original relevance value for {evidence_id}"
                )

    # Ensure the dataset and V3 classification file contain
    # exactly the same evidence IDs.
    if actual_evidence_ids != set(EVIDENCE_LABELS):
        missing = actual_evidence_ids - set(EVIDENCE_LABELS)
        unknown = set(EVIDENCE_LABELS) - actual_evidence_ids

        raise ValueError(
            f"Dataset and V3 labels do not match. "
            f"Missing: {sorted(missing)}, "
            f"Unknown: {sorted(unknown)}"
        )

    if len(FINAL_TEST_CASES) != 20:
        raise ValueError("V3 benchmark must contain exactly 20 scenarios.")

    if len(actual_evidence_ids) != 160:
        raise ValueError("V3 benchmark must contain exactly 160 records.")

    # Each scenario must have at least one relevant record
    # under both evaluation perspectives.
    for case in FINAL_TEST_CASES:

        case_ids = {
            evidence[0]
            for evidence in case["evidence"]
        }

        for perspective, relevant_ids in RELEVANCE_PERSPECTIVES.items():

            scenario_relevant = case_ids.intersection(relevant_ids)

            if not scenario_relevant:
                raise ValueError(
                    f"No relevant evidence in {case['name']} "
                    f"under {perspective}."
                )

    print("V3 dataset and relevance-label validation passed.")


# ============================================================
# EVIDENCE OBJECT CREATION
# ============================================================

def build_evidence_objects(case, incident_id):

    return [
        SimpleNamespace(
            id=evidence_id,
            incident_id=incident_id,
            source_type=source_type,
            content=content,
        )
        for evidence_id, source_type, content, _ in case["evidence"]
    ]


# ============================================================
# METRIC CALCULATION
# ============================================================


def evaluate_case(case, incident_id, search_function, relevant_ids):

    evidence_items = build_evidence_objects(case, incident_id)

    # Restrict relevance labels to evidence in this scenario only.
    scenario_evidence_ids = {
        evidence_id
        for evidence_id, _, _, _ in case["evidence"]
    }

    scenario_relevant_ids = (
        scenario_evidence_ids.intersection(relevant_ids)
    )

    # Retrieve the top K evidence records.
    retrieved = search_function(
        case["query"],
        incident_id,
        evidence_items,
        max_results=TOP_K,
    )

    retrieved_ids = [
        item["evidence_id"]
        for item in retrieved
    ]

    # Relevant records retrieved by the search method.
    retrieved_relevant = [
        evidence_id
        for evidence_id in retrieved_ids
        if evidence_id in scenario_relevant_ids
    ]

    # Relevant records in this scenario that were not retrieved.
    missed_ids = sorted(
        scenario_relevant_ids - set(retrieved_ids)
    )

    # Retrieved records irrelevant under this perspective.
    irrelevant_ids = [
        evidence_id
        for evidence_id in retrieved_ids
        if evidence_id not in scenario_relevant_ids
    ]

    # Recall@5.
    recall_at_5 = (
        len(retrieved_relevant) / len(scenario_relevant_ids)
    )

    # Precision@5.
    precision_at_5 = (
        len(retrieved_relevant) / TOP_K
    )

    # Precision Returned.
    precision_returned = (
        len(retrieved_relevant) / len(retrieved_ids)
        if retrieved_ids
        else 0.0
    )

    # Reciprocal rank of the first relevant result.
    reciprocal_rank = 0.0

    for rank, evidence_id in enumerate(retrieved_ids, start=1):

        if evidence_id in scenario_relevant_ids:
            reciprocal_rank = 1 / rank
            break

    return {
        "retrieved_ids": retrieved_ids,
        "missed_ids": missed_ids,
        "irrelevant_ids": irrelevant_ids,
        "retrieved_relevant": retrieved_relevant,
        "recall_at_5": recall_at_5,
        "precision_at_5": precision_at_5,
        "precision_returned": precision_returned,
        "mrr": reciprocal_rank,
    }


# ============================================================
# DATASET EVALUATION
# ============================================================

def evaluate_dataset(cases, search_function, relevant_ids):

    results = []

    for index, case in enumerate(cases, start=1):

        incident_id = f"final-v3-{index:02d}"

        result = evaluate_case(
            case,
            incident_id,
            search_function,
            relevant_ids,
        )

        results.append({
            "name": case["name"],
            **result,
        })

    return results


# ============================================================
# AGGREGATE METRICS
# ============================================================

def macro_average(results, metric):

    return mean(
        result[metric]
        for result in results
    )


# ============================================================
# AGGREGATE COMPARISON REPORT
# ============================================================

def print_comparison_table(method_results, perspective):

    print("\n" + "=" * 105)
    print(f"V3 AGGREGATE RESULTS - {perspective.upper()}")
    print("=" * 105)

    print(
        f"{'Method':<25}"
        f"{'Recall@5':>12}"
        f"{'Precision@5':>15}"
        f"{'Precision Returned':>22}"
        f"{'MRR':>10}"
    )

    print("-" * 105)

    for method_name, results in method_results.items():

        print(
            f"{method_name:<25}"
            f"{macro_average(results, 'recall_at_5'):>12.3f}"
            f"{macro_average(results, 'precision_at_5'):>15.3f}"
            f"{macro_average(results, 'precision_returned'):>22.3f}"
            f"{macro_average(results, 'mrr'):>10.3f}"
        )

    print("=" * 105)


# ============================================================
# PER-SCENARIO RESULTS
# ============================================================

def print_scenario_results(method_results, perspective):

    print("\n" + "=" * 120)
    print(f"PER-SCENARIO RECALL@5 - {perspective.upper()}")
    print("=" * 120)

    method_names = list(method_results)

    print(f"{'Scenario':<65}", end="")

    for method_name in method_names:
        print(f"{method_name[:12]:>13}", end="")

    print()
    print("-" * 120)

    for index, case in enumerate(FINAL_TEST_CASES):

        print(f"{case['name']:<65}", end="")

        for method_name in method_names:

            score = method_results[method_name][index]["recall_at_5"]

            print(f"{score:>13.3f}", end="")

        print()

    print("=" * 120)


# ============================================================
# RETRIEVAL DIAGNOSTICS
# ============================================================

def print_method_diagnostics(method_results, perspective):

    print("\n" + "=" * 105)
    print(f"RETRIEVAL DIAGNOSTICS - {perspective.upper()}")
    print("=" * 105)

    for method_name, results in method_results.items():

        print(f"\n--- {method_name} ---")

        for result in results:

            if result["missed_ids"] or result["irrelevant_ids"]:

                print(f"\nScenario: {result['name']}")
                print(f"Retrieved : {result['retrieved_ids']}")
                print(f"Relevant  : {result['retrieved_relevant']}")
                print(f"Missed    : {result['missed_ids']}")
                print(f"Irrelevant: {result['irrelevant_ids']}")


# ============================================================
# MAIN
# ============================================================

def main():

    validate_v3_dataset()

    total_evidence = sum(
        len(case["evidence"])
        for case in FINAL_TEST_CASES
    )

    print("\n" + "=" * 75)
    print("OPSPILOT FINAL RETRIEVAL BENCHMARK V3")
    print("=" * 75)

    print(f"Scenarios          : {len(FINAL_TEST_CASES)}")
    print(f"Evidence records   : {total_evidence}")
    print(f"Direct relevant    : {len(DIRECT_RELEVANT_IDS)}")
    print(f"Diagnostic relevant: {len(DIAGNOSTIC_RELEVANT_IDS)}")

    # All retrieval methods use the same dataset and evidence objects.
    methods = {
        "Baseline": search_incident_evidence,
        "Porter stemming": search_with_porter_stemming,
        "Query expansion": search_with_query_expansion,
        "Hybrid": search_with_hybrid_retrieval,
    }

    # Run both relevance perspectives independently.
    for perspective, relevant_ids in RELEVANCE_PERSPECTIVES.items():

        print("\n\n")
        print("#" * 105)
        print(f"EVALUATION PERSPECTIVE: {perspective.upper()}")
        print("#" * 105)

        method_results = {}

        for method_name, search_function in methods.items():

            print(f"\nEvaluating {method_name}...")

            method_results[method_name] = evaluate_dataset(
                FINAL_TEST_CASES,
                search_function,
                relevant_ids,
            )

        print_comparison_table(
            method_results,
            perspective,
        )

        print_scenario_results(
            method_results,
            perspective,
        )

        print_method_diagnostics(
            method_results,
            perspective,
        )

    print("\n" + "=" * 75)
    print("V3 RETRIEVAL BENCHMARK COMPLETED")
    print("=" * 75)


if __name__ == "__main__":
    main()
