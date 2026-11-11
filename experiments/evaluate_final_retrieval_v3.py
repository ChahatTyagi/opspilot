
from statistics import mean
from types import SimpleNamespace

from app.investigation_tools import search_incident_evidence
from app.retrieval_service import EvidenceRetriever

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
# 1. Baseline keyword retrieval
# 2. Porter stemming
# 3. Query expansion
# 4. Existing lexical hybrid retrieval
# 5. Ollama semantic retrieval
# 6. Ollama semantic + lexical RRF
# ============================================================


TOP_K = 5
RRF_K = 60

RELEVANCE_PERSPECTIVES = {
    "Direct relevance": DIRECT_RELEVANT_IDS,
    "Diagnostic relevance": DIAGNOSTIC_RELEVANT_IDS,
}


# ============================================================
# DATASET AND LABEL VALIDATION
# ============================================================

def validate_v3_dataset():

    validate_labels()

    scenario_names = set()
    actual_evidence_ids = set()

    for case in FINAL_TEST_CASES:

        name = case["name"]

        if name in scenario_names:
            raise ValueError(
                f"Duplicate scenario name: {name}"
            )

        scenario_names.add(name)

        query = case["query"]

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                f"Invalid query in scenario: {name}"
            )

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

    if actual_evidence_ids != set(EVIDENCE_LABELS):

        missing = actual_evidence_ids - set(EVIDENCE_LABELS)
        unknown = set(EVIDENCE_LABELS) - actual_evidence_ids

        raise ValueError(
            "Dataset and V3 labels do not match. "
            f"Missing: {sorted(missing)}, "
            f"Unknown: {sorted(unknown)}"
        )

    if len(FINAL_TEST_CASES) != 20:
        raise ValueError(
            "V3 benchmark must contain exactly 20 scenarios."
        )

    if len(actual_evidence_ids) != 160:
        raise ValueError(
            "V3 benchmark must contain exactly 160 records."
        )

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

    print(
        "V3 dataset and relevance-label validation passed."
    )


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
# OLLAMA SEMANTIC RETRIEVAL ADAPTER
# ============================================================

def search_with_semantic_retrieval(
    query,
    incident_id,
    evidence_items,
    max_results=5,
    retriever=None,
):
    """
    Adapt EvidenceRetriever output to the benchmark result format.

    A shared retriever is supplied by main() so its embedding
    cache can be reused across scenarios and methods.
    """

    if retriever is None:
        raise ValueError(
            "A shared EvidenceRetriever instance must be supplied."
        )
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        raise ValueError("max_results must be an integer.")
    if max_results <= 0:
        raise ValueError("max_results must be positive")

    scoped_evidence = [
        item
        for item in evidence_items
        if getattr(item, "incident_id", None) == incident_id
    ]

    if not scoped_evidence:
        return []

    results = retriever.retrieve(
        query=query,
        evidence_items=scoped_evidence,
        top_k=max_results,
    )

    return [
        {
            "incident_id": result.chunk.incident_id,
            "evidence_id": result.chunk.evidence_id,
            "source_type": result.chunk.source_type,
            "text": result.chunk.text,
            "score": result.score,
        }
        for result in results
    ]


# ============================================================
# SEMANTIC + LEXICAL RECIPROCAL RANK FUSION
# ============================================================

def search_with_semantic_lexical_rrf(
    query,
    incident_id,
    evidence_items,
    max_results=5,
    retriever=None,
    rrf_k=RRF_K,
):
    """
    Combine semantic and lexical rankings using
    Reciprocal Rank Fusion (RRF).

    RRF formula:

        RRF(d) = sum(1 / (k + rank))

    Each evidence record receives a contribution from
    every ranking in which it appears.

    The semantic and lexical scores are never directly
    combined because they use different scoring scales.
    """

    if retriever is None:
        raise ValueError(
            "A semantic retriever is required."
        )

    if (
        not isinstance(max_results, int)
        or isinstance(max_results, bool)
        or max_results <= 0
    ):
        raise ValueError(
            "max_results must be a positive integer."
        )

    if (
        not isinstance(rrf_k, int)
        or isinstance(rrf_k, bool)
        or rrf_k <= 0
    ):
        raise ValueError(
            "rrf_k must be a positive integer."
        )

    # --------------------------------------------------------
    # STEP 1: Restrict candidates to the current incident.
    # --------------------------------------------------------

    scoped_evidence = [
        item
        for item in evidence_items
        if getattr(item, "incident_id", None) == incident_id
    ]

    if not scoped_evidence:
        return []

    # Build an evidence lookup and preserve original order.
    evidence_by_id = {}

    for item in scoped_evidence:

        if item.id in evidence_by_id:
            raise ValueError(
                f"Duplicate candidate evidence ID: {item.id}"
            )

        evidence_by_id[item.id] = item

    evidence_order = {
        evidence_id: index
        for index, evidence_id in enumerate(evidence_by_id)
    }

    # --------------------------------------------------------
    # STEP 2: Retrieve the complete semantic ranking.
    # --------------------------------------------------------

    candidate_count = len(scoped_evidence)

    semantic_results = search_with_semantic_retrieval(
        query=query,
        incident_id=incident_id,
        evidence_items=scoped_evidence,
        max_results=candidate_count,
        retriever=retriever,
    )

    # --------------------------------------------------------
    # STEP 3: Retrieve the complete lexical ranking.
    #
    # This reuses the existing query-expansion +
    # Porter-stemming hybrid implementation.
    # --------------------------------------------------------

    lexical_results = search_with_hybrid_retrieval(
        query=query,
        incident_id=incident_id,
        evidence_items=scoped_evidence,
        max_results=candidate_count,
    )

    # --------------------------------------------------------
    # STEP 4: Validate and fuse the two rankings.
    # --------------------------------------------------------

    rrf_scores = {}

    rankings = (
        semantic_results,
        lexical_results,
    )

    for ranking in rankings:

        seen_ids = set()

        for rank, result in enumerate(ranking, start=1):

            evidence_id = result.get("evidence_id")

            if evidence_id not in evidence_by_id:
                raise ValueError(
                    "Retrieval returned evidence outside "
                    "the requested incident."
                )

            if evidence_id in seen_ids:
                raise ValueError(
                    "Retrieval returned duplicate evidence IDs."
                )

            if result.get("incident_id") != incident_id:
                raise ValueError(
                    "Retrieval returned an incorrect incident ID."
                )

            seen_ids.add(evidence_id)

            contribution = 1.0 / (rrf_k + rank)

            rrf_scores[evidence_id] = (
                rrf_scores.get(evidence_id, 0.0)
                + contribution
            )

    # --------------------------------------------------------
    # STEP 5: Sort by fused score.
    #
    # Original evidence order is used as a deterministic
    # tie-breaker.
    # --------------------------------------------------------

    ranked_ids = sorted(
        rrf_scores,
        key=lambda evidence_id: (
            -rrf_scores[evidence_id],
            evidence_order[evidence_id],
        ),
    )

    # --------------------------------------------------------
    # STEP 6: Return the final top-k results.
    # --------------------------------------------------------

    return [
        {
            "incident_id": evidence_by_id[evidence_id].incident_id,
            "evidence_id": evidence_id,
            "source_type": evidence_by_id[evidence_id].source_type,
            "text": evidence_by_id[evidence_id].content[:1000],
            "rrf_score": rrf_scores[evidence_id],
        }
        for evidence_id in ranked_ids[:max_results]
    ]


# ============================================================
# METRIC CALCULATION
# ============================================================

def evaluate_case(
    case,
    incident_id,
    search_function,
    relevant_ids,
):

    evidence_items = build_evidence_objects(
        case,
        incident_id,
    )

    scenario_evidence_ids = {
        evidence_id
        for evidence_id, _, _, _ in case["evidence"]
    }

    scenario_relevant_ids = (
        scenario_evidence_ids.intersection(relevant_ids)
    )

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

    # Prevent duplicate IDs from artificially affecting metrics.
    if len(retrieved_ids) != len(set(retrieved_ids)):
        raise ValueError(
            f"Retrieval method returned duplicate evidence IDs "
            f"for scenario: {case['name']}"
        )

    # Prevent results from another scenario affecting evaluation.
    unexpected_ids = set(retrieved_ids) - scenario_evidence_ids

    if unexpected_ids:
        raise ValueError(
            f"Retrieval returned evidence outside scenario "
            f"{case['name']}: {sorted(unexpected_ids)}"
        )

    retrieved_relevant = [
        evidence_id
        for evidence_id in retrieved_ids
        if evidence_id in scenario_relevant_ids
    ]

    missed_ids = sorted(
        scenario_relevant_ids - set(retrieved_ids)
    )

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
    # Unfilled positions count as non-relevant.
    precision_at_5 = (
        len(retrieved_relevant) / TOP_K
    )

    # Precision among results actually returned.
    precision_returned = (
        len(retrieved_relevant) / len(retrieved_ids)
        if retrieved_ids
        else 0.0
    )

    # Reciprocal rank of the first relevant result.
    reciprocal_rank = 0.0

    for rank, evidence_id in enumerate(
        retrieved_ids,
        start=1,
    ):

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

def evaluate_dataset(
    cases,
    search_function,
    relevant_ids,
):

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

def print_comparison_table(
    method_results,
    perspective,
):

    print("\n" + "=" * 115)

    print(
        f"V3 AGGREGATE RESULTS - {perspective.upper()}"
    )

    print("=" * 115)

    print(
        f"{'Method':<32}"
        f"{'Recall@5':>12}"
        f"{'Precision@5':>15}"
        f"{'Precision Returned':>22}"
        f"{'MRR':>10}"
    )

    print("-" * 115)

    for method_name, results in method_results.items():

        print(
            f"{method_name:<32}"
            f"{macro_average(results, 'recall_at_5'):>12.3f}"
            f"{macro_average(results, 'precision_at_5'):>15.3f}"
            f"{macro_average(results, 'precision_returned'):>22.3f}"
            f"{macro_average(results, 'mrr'):>10.3f}"
        )

    print("=" * 115)


# ============================================================
# PER-SCENARIO RESULTS
# ============================================================

def print_scenario_results(
    method_results,
    perspective,
):

    print("\n" + "=" * 150)

    print(
        f"PER-SCENARIO RECALL@5 - {perspective.upper()}"
    )

    print("=" * 150)

    method_names = list(method_results)

    print(
        f"{'Scenario':<65}",
        end="",
    )

    for method_name in method_names:
        print(
            f"{method_name[:16]:>18}",
            end="",
        )

    print()
    print("-" * 150)

    for index, case in enumerate(FINAL_TEST_CASES):

        print(
            f"{case['name']:<65}",
            end="",
        )

        for method_name in method_names:

            score = method_results[method_name][index][
                "recall_at_5"
            ]

            print(
                f"{score:>18.3f}",
                end="",
            )

        print()

    print("=" * 150)


# ============================================================
# RETRIEVAL DIAGNOSTICS
# ============================================================

def print_method_diagnostics(
    method_results,
    perspective,
):

    print("\n" + "=" * 110)

    print(
        f"RETRIEVAL DIAGNOSTICS - {perspective.upper()}"
    )

    print("=" * 110)

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

    print("\n" + "=" * 85)
    print("OPSPILOT FINAL RETRIEVAL BENCHMARK V3")
    print("=" * 85)

    print(
        f"Scenarios          : {len(FINAL_TEST_CASES)}"
    )

    print(
        f"Evidence records   : {total_evidence}"
    )

    print(
        f"Direct relevant    : {len(DIRECT_RELEVANT_IDS)}"
    )

    print(
        f"Diagnostic relevant: {len(DIAGNOSTIC_RELEVANT_IDS)}"
    )

    # One shared semantic retriever.
    # It uses the embedding provider configured in .env.
    semantic_retriever = EvidenceRetriever()

    # --------------------------------------------------------
    # RETRIEVAL METHODS
    # --------------------------------------------------------

    methods = {

        "Baseline": search_incident_evidence,

        "Porter stemming": search_with_porter_stemming,

        "Query expansion": search_with_query_expansion,

        "Hybrid": search_with_hybrid_retrieval,

        "Ollama semantic": (
            lambda query, incident_id, evidence_items, max_results=5:
            search_with_semantic_retrieval(
                query,
                incident_id,
                evidence_items,
                max_results=max_results,
                retriever=semantic_retriever,
            )
        ),

        "Semantic + Lexical RRF": (
            lambda query, incident_id, evidence_items, max_results=5:
            search_with_semantic_lexical_rrf(
                query,
                incident_id,
                evidence_items,
                max_results=max_results,
                retriever=semantic_retriever,
                rrf_k=RRF_K,
            )
        ),
    }

    # --------------------------------------------------------
    # EVALUATE BOTH RELEVANCE PERSPECTIVES
    # --------------------------------------------------------

    for perspective, relevant_ids in RELEVANCE_PERSPECTIVES.items():

        print("\n\n")

        print("#" * 115)

        print(
            f"EVALUATION PERSPECTIVE: {perspective.upper()}"
        )

        print("#" * 115)

        method_results = {}

        for method_name, search_function in methods.items():

            print(
                f"\nEvaluating {method_name}..."
            )

            method_results[method_name] = evaluate_dataset(
                FINAL_TEST_CASES,
                search_function,
                relevant_ids,
            )

        # Aggregate comparison.
        print_comparison_table(
            method_results,
            perspective,
        )

        # Per-scenario comparison.
        print_scenario_results(
            method_results,
            perspective,
        )

        # Missed and irrelevant evidence.
        print_method_diagnostics(
            method_results,
            perspective,
        )

    print("\n" + "=" * 85)
    print("V3 RETRIEVAL BENCHMARK COMPLETED")
    print("=" * 85)


if __name__ == "__main__":
    main()
