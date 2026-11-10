
import re

from nltk.stem import PorterStemmer

from app.investigation_tools import search_incident_evidence

from experiments.evaluate_keyword_retrieval import (
    CASES as TRAINING_CASES,
    QUERY_EXPANSIONS,
    build_evidence_objects,
    evaluate_case,
    search_stemmed_tokens,
    search_with_query_expansion,
    validate_dataset,
)

from experiments.evaluate_keyword_generalization import (
    HELD_OUT_CASES,
)


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

MAX_RESULTS = 5

TOKEN_PATTERN = re.compile(r"\b[a-z0-9]+\b")

STEMMER = PorterStemmer()


# ---------------------------------------------------------
# TOKENIZATION AND QUERY EXPANSION
# ---------------------------------------------------------

def tokenize(text):
    """Convert text into lowercase alphanumeric tokens."""

    return TOKEN_PATTERN.findall(text.casefold())


def expand_query_tokens(query):
    """
    Return original query tokens together with their
    manually defined synonyms.
    """

    original_tokens = tokenize(query)

    expanded_tokens = set(original_tokens)

    for token in original_tokens:
        related_terms = QUERY_EXPANSIONS.get(token, [])

        for related_term in related_terms:
            expanded_tokens.update(tokenize(related_term))

    return expanded_tokens


def stem_tokens(tokens):
    """Convert tokens into their Porter stem representations."""

    return {
        STEMMER.stem(token)
        for token in tokens
    }


# ---------------------------------------------------------
# HYBRID RETRIEVAL
# ---------------------------------------------------------

def search_hybrid(
    query,
    incident_id,
    evidence_items,
    max_results=MAX_RESULTS,
):
    """
    Experimental hybrid retrieval combining:

    1. Manually defined query expansion.
    2. Porter stemming.
    3. Exact matching between normalized stems.

    Production retrieval remains unchanged.
    """

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query must be a non-empty string.")

    if len(query) > 500:
        raise ValueError("Query cannot exceed 500 characters.")

    if (
        not isinstance(max_results, int)
        or isinstance(max_results, bool)
        or not 1 <= max_results <= 10
    ):
        raise ValueError("max_results must be between 1 and 10.")

    # Step 1: Expand the original query.
    expanded_tokens = expand_query_tokens(query)

    # Step 2: Normalize expanded query vocabulary using stemming.
    query_stems = stem_tokens(expanded_tokens)

    matches = []

    # Step 3: Search evidence belonging to this incident only.
    for item in evidence_items:

        if item.incident_id != incident_id:
            continue

        content = item.content or ""

        evidence_tokens = tokenize(content)

        # Step 4: Apply the same normalization to evidence.
        evidence_stems = stem_tokens(evidence_tokens)

        # Step 5: Calculate the number of matching unique stems.
        matching_stems = query_stems & evidence_stems

        if not matching_stems:
            continue

        matches.append(
            {
                "incident_id": item.incident_id,
                "evidence_id": item.id,
                "source_type": item.source_type,
                "text": content[:1000],
                "match_count": len(matching_stems),
            }
        )

    # Step 6: Rank by matching stem count.
    # Python's sort is stable, so original evidence order
    # is preserved when two records have equal scores.
    matches.sort(
        key=lambda result: result["match_count"],
        reverse=True,
    )

    # Step 7: Return the same result structure as other methods.
    return [
        {
            "incident_id": result["incident_id"],
            "evidence_id": result["evidence_id"],
            "source_type": result["source_type"],
            "text": result["text"],
        }
        for result in matches[:max_results]
    ]


# ---------------------------------------------------------
# DATASET VALIDATION
# ---------------------------------------------------------

def validate_datasets():
    """Validate both datasets and ensure their scenarios differ."""

    validate_dataset(TRAINING_CASES)
    validate_dataset(HELD_OUT_CASES)

    training_names = {
        case["name"]
        for case in TRAINING_CASES
    }

    held_out_names = {
        case["name"]
        for case in HELD_OUT_CASES
    }

    overlapping_names = training_names & held_out_names

    if overlapping_names:
        raise ValueError(
            "Training and held-out datasets contain overlapping "
            f"scenario names: {sorted(overlapping_names)}"
        )

    print("Dataset validation successful.")
    print(
        f"Training scenarios: {len(TRAINING_CASES)}"
    )
    print(
        f"Training evidence records: "
        f"{sum(len(case['evidence']) for case in TRAINING_CASES)}"
    )
    print(
        f"Held-out scenarios: {len(HELD_OUT_CASES)}"
    )
    print(
        f"Held-out evidence records: "
        f"{sum(len(case['evidence']) for case in HELD_OUT_CASES)}"
    )


# ---------------------------------------------------------
# EVALUATION
# ---------------------------------------------------------

SEARCH_METHODS = {
    "Baseline": search_incident_evidence,
    "Porter stemming": search_stemmed_tokens,
    "Query expansion": search_with_query_expansion,
    "Hybrid": search_hybrid,
}


def evaluate_dataset(dataset, dataset_name):
    """Evaluate all retrieval methods on one dataset."""

    print("\n")
    print("=" * 76)
    print(f"{dataset_name.upper()} EVALUATION")
    print("=" * 76)

    dataset_results = {}

    for method_name, search_function in SEARCH_METHODS.items():

        print(f"\n{'-' * 76}")
        print(f"METHOD: {method_name.upper()}")
        print(f"{'-' * 76}")

        case_results = []

        for index, case in enumerate(dataset, start=1):

            result = evaluate_case(
                case=case,
                incident_id=index,
                search_function=search_function,
            )

            case_results.append(result)

            print(f"\nCase {index}: {result['name']}")
            print(f"Query: {result['query']}")
            print(f"Retrieved IDs: {result['retrieved_ids']}")
            print(f"Missed relevant IDs: {result['missed_ids']}")
            print(
                f"Irrelevant retrieved IDs: "
                f"{result['irrelevant_ids']}"
            )
            print(
                f"Recall@5: {result['recall_at_5']:.3f}"
            )
            print(
                f"Precision@5: {result['precision_at_5']:.3f}"
            )
            print(
                f"Precision (returned): "
                f"{result['precision_returned']:.3f}"
            )
            print(f"MRR: {result['mrr']:.3f}")

        case_count = len(case_results)

        if case_count == 0:
            raise ValueError(
                f"{dataset_name} cannot be empty."
            )

        # Macro-average: every scenario contributes equally.
        summary = {
            "recall": sum(
                result["recall_at_5"]
                for result in case_results
            ) / case_count,

            "precision": sum(
                result["precision_at_5"]
                for result in case_results
            ) / case_count,

            "precision_returned": sum(
                result["precision_returned"]
                for result in case_results
            ) / case_count,

            "mrr": sum(
                result["mrr"]
                for result in case_results
            ) / case_count,
        }

        dataset_results[method_name] = summary

        print(f"\n{method_name} SUMMARY")
        print(f"Mean Recall@5: {summary['recall']:.3f}")
        print(f"Mean Precision@5: {summary['precision']:.3f}")
        print(
            "Mean Precision (returned): "
            f"{summary['precision_returned']:.3f}"
        )
        print(f"Mean MRR: {summary['mrr']:.3f}")

    return dataset_results


# ---------------------------------------------------------
# COMPARISON TABLE
# ---------------------------------------------------------

def print_comparison(results, dataset_name):
    """Display a side-by-side comparison of retrieval methods."""

    print("\n")
    print("=" * 100)
    print(f"{dataset_name.upper()} — SIDE-BY-SIDE COMPARISON")
    print("=" * 100)

    headers = [
        "Metric",
        "Baseline",
        "Porter stem",
        "Query expand",
        "Hybrid",
    ]

    print(
        f"{headers[0]:<24}"
        f"{headers[1]:>15}"
        f"{headers[2]:>15}"
        f"{headers[3]:>15}"
        f"{headers[4]:>15}"
    )

    print("-" * 84)

    metrics = [
        ("Recall@5", "recall"),
        ("Precision@5", "precision"),
        ("Precision (returned)", "precision_returned"),
        ("MRR", "mrr"),
    ]

    for metric_name, metric_key in metrics:

        print(
            f"{metric_name:<24}"
            f"{results['Baseline'][metric_key]:>15.3f}"
            f"{results['Porter stemming'][metric_key]:>15.3f}"
            f"{results['Query expansion'][metric_key]:>15.3f}"
            f"{results['Hybrid'][metric_key]:>15.3f}"
        )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    validate_datasets()

    training_results = evaluate_dataset(
        dataset=TRAINING_CASES,
        dataset_name="Training",
    )

    print_comparison(
        results=training_results,
        dataset_name="Training",
    )

    held_out_results = evaluate_dataset(
        dataset=HELD_OUT_CASES,
        dataset_name="Held-out validation",
    )

    print_comparison(
        results=held_out_results,
        dataset_name="Held-out validation",
    )

    print("\n")
    print("=" * 76)
    print("EXPERIMENT COMPLETED")
    print("=" * 76)

    print(
        "\nImportant: Held-out results are validation results, "
        "not results from a completely untouched final test set."
    )


if __name__ == "__main__":
    main()
