import re

from math import isfinite
from numbers import Real

from app.embeddings import LocalEmbedder
from app.retrieval import cosine_similarity
CASES = [
    {
        "query": "Why is the payment service failing?",
        "candidates": [
            ("Payment requests time out connecting to PostgreSQL.", True),
            ("Database connection pool exhausted.", True),
            ("The payment page CSS was updated.", False),
            ("PostgreSQL backups completed successfully.", False),
            ("The reporting dashboard color changed.", False),
            ("The checkout button animation is slow.", False),
        ],
    },
    {
        "query": "Why are users receiving authentication errors?",
        "candidates": [
            ("The identity provider rejects expired access tokens.", True),
            ("The authentication API returns HTTP 401 after token validation.", True),
            ("The login page logo was resized.", False),
            ("CPU utilization increased on the reporting worker.", False),
            ("The access-token documentation was updated.", False),
            ("The user profile page loads slowly.", False),
        ],
    },
    {
        "query": "What caused the sudden increase in API latency?",
        "candidates": [
            ("P95 response time increased after the latest deployment.", True),
            ("Database queries are taking longer than usual.", True),
            ("The dashboard background color changed.", False),
            ("The login page logo was resized.", False),
            ("API documentation was updated after deployment.", False),
            ("The homepage image is taking longer to load.", False),
        ],
    },
    {
        "query": "Why are database requests timing out?",
        "candidates": [
            ("Database connection pool exhausted under high load.", True),
            ("Queries are waiting for database locks.", True),
            ("The database monitoring dashboard changed color.", False),
            ("Database backup completed without errors.", False),
            ("The database team's documentation was revised.", False),
            ("The homepage layout caused a visual regression.", False),
        ],
    },
    {
        "query": "Why did login start failing after deployment?",
        "candidates": [
            ("The deployment changed the JWT signing key configuration.", True),
            ("Authentication requests return HTTP 401 after the release.", True),
            ("The login page layout changed in the release.", False),
            ("The deployment updated the footer copyright year.", False),
            ("Image assets are missing from the homepage.", False),
            ("The reporting service CPU usage increased.", False),
        ],
    },
    {
        "query": "Why did error rates increase after the release?",
        "candidates": [
            ("The new release introduced exceptions in request processing.", True),
            ("HTTP 500 responses increased after deployment.", True),
            ("The release changed the dashboard theme.", False),
            ("The deployment notes contain a new section.", False),
            ("A background worker's CPU usage is unchanged.", False),
            ("The homepage font was updated in the release.", False),
        ],
    },
    {
        "query": "Why did login start failing after deployment?",
        "candidates": [
            ("The deployment changed the JWT signing key configuration.", True),
            ("The login page layout changed in the release.", False),
            ("The identity provider rejects invalid JWT signatures.", True),
            ("The deployment updated the footer copyright year.", False),
            ("Authentication requests return HTTP 401 after the release.", True),
            ("The homepage image assets are missing.", False),
        ],
    },
    {
        "query": "Why are background jobs stuck in the queue?",
        "candidates": [
            ("Workers cannot acquire messages from the Redis queue.", True),
            ("Queue depth has increased while worker throughput dropped.", True),
            ("The admin dashboard layout changed.", False),
            ("Redis snapshots completed successfully.", False),
            ("The job documentation was updated.", False),
            ("The payment service database pool is exhausted.", False),
        ],
    },
    {
        "query": "Why is memory usage growing continuously?",
        "candidates": [
            ("The service retains request objects after each response.", True),
            ("Heap usage increases steadily without corresponding traffic growth.", True),
            ("The monitoring dashboard uses a new font.", False),
            ("A scheduled database backup completed.", False),
            ("The service API documentation was revised.", False),
            ("The login endpoint returned HTTP 401 errors.", False),
        ],
    },
    {
        "query": "Why are deployment health checks failing?",
        "candidates": [
            (
                "The new container fails readiness checks because its dependency is unavailable.",
                True,
            ),
            (
                "Health probes time out before the application finishes starting.",
                True,
            ),
            ("The release notes contain a new section.", False),
            ("The deployment dashboard theme was changed.", False),
            ("The background worker CPU usage is stable.", False),
            ("Database backups completed without errors.", False),
        ],
    },
    {
        "query": "Why are database queries slow despite low traffic?",
        "candidates": [
            (
                "Database queries are waiting on locks held by a long-running transaction.",
                True,
            ),
            (
                "The query planner switched to a sequential scan after a statistics change.",
                True,
            ),
            ("Database connection pool utilization is low and stable.", False),
            ("The database dashboard theme was updated.", False),
            ("The payment service returned HTTP 401 errors.", False),
            ("A scheduled database backup completed successfully.", False),
        ],
    },
    {
        "query": "Why are background jobs being processed more slowly?",
        "candidates": [
            ("Queue depth is increasing while worker throughput has fallen.", True),
            (
                "Workers are repeatedly retrying jobs after downstream requests time out.",
                True,
            ),
            (
                "The admin dashboard shows a higher number of queued jobs due to a display change.",
                False,
            ),
            ("Redis snapshots completed successfully.", False),
            ("The login service is rejecting expired access tokens.", False),
            ("The job documentation was revised.", False),
        ],
    },
    {
        "query": "Why is the service restarting repeatedly after deployment?",
        "candidates": [
            (
                "The new container exits because a required environment variable is missing.",
                True,
            ),
            (
                "The process exceeds its memory limit and is repeatedly killed by the container runtime.",
                True,
            ),
            ("The release notes contain a new section.", False),
            ("The readiness probe succeeds consistently after startup.", False),
            ("The reporting dashboard font was changed.", False),
            ("Database backups completed without errors.", False),
        ],
    },
    {
        "query": "Why are checkout requests failing while the payment page loads?",
        "candidates": [
            (
                "The checkout API returns HTTP 500 when the payment provider request times out.",
                True,
            ),
            (
                "Payment requests fail because the downstream provider rejects connections.",
                True,
            ),
            ("The payment page CSS changed without affecting API requests.", False),
            ("The reporting service has stable response times.", False),
            ("The login page logo was resized.", False),
            ("The checkout button animation is slow, but requests succeed.", False),
        ],
    },
]

TOP_K = 5
EVAL_K = 3


def lexical_overlap(query: str, text: str) -> float:
    """Measure the proportion of query terms present in the text."""
    query_terms = set(re.findall(r"\b[a-z0-9]+\b", query.lower()))
    text_terms = set(re.findall(r"\b[a-z0-9]+\b", text.lower()))

    if not query_terms:
        return 0.0

    return len(query_terms & text_terms) / len(query_terms)


def rerank_with_lexical_overlap(query, ranked, alpha=0.8):
    """Evaluation-only reranker; benchmark results are not production evidence."""
    reranked = []

    for semantic_score, text, relevant in ranked:
        lexical_score = lexical_overlap(query, text)
        combined_score = alpha * semantic_score + (1 - alpha) * lexical_score
        reranked.append((combined_score, text, relevant))

    return sorted(reranked, key=lambda item: item[0], reverse=True)


def validate_case(case):
    if not isinstance(case, dict):
        raise ValueError("Evaluation case must be a dictionary")

    query = case.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Evaluation case query must be a non-empty string")

    candidates = case.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("Evaluation case candidates must be a list")

    seen_texts = set()

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, tuple) or len(candidate) != 2:
            raise ValueError(
                f"Candidate {index} must be a (text, relevant) tuple"
            )

        text, relevant = candidate

        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"Candidate {index} text must be a non-empty string"
            )

        if not isinstance(relevant, bool):
            raise ValueError(
                f"Candidate {index} relevance label must be a boolean"
            )

        normalized_text = " ".join(text.lower().split())

        if normalized_text in seen_texts:
            raise ValueError(
                f"Candidate {index} duplicates earlier candidate text"
            )

        seen_texts.add(normalized_text)


def validate_cases(cases):
    if not isinstance(cases, list):
        raise ValueError("Evaluation cases must be a list")

    for case in cases:
        validate_case(case)


def reciprocal_rank(ranked):
    """Return the reciprocal rank of the first relevant result."""
    first_relevant_rank = next(
        (
            rank
            for rank, (_, _, relevant) in enumerate(ranked, start=1)
            if relevant
        ),
        None,
    )

    return 1 / first_relevant_rank if first_relevant_rank else 0.0

def validate_embedding_vectors(vectors):
    """Validate embedding vector structure, dimensions, and values."""
    error_message = "invalid embedding vectors"

    if not isinstance(vectors, (list, tuple)) or not vectors:
        raise ValueError(error_message)

    expected_dimensions = None

    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or not vector:
            raise ValueError(error_message)

        if expected_dimensions is None:
            expected_dimensions = len(vector)
        elif len(vector) != expected_dimensions:
            raise ValueError(error_message)

        for value in vector:
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not isfinite(value)
            ):
                raise ValueError(error_message)
def evaluate_case(embedder, case):
    validate_case(case)

    candidates = case["candidates"]
    texts = [text for text, _ in candidates]
    texts_to_embed = [case["query"]] + texts
    vectors = embedder.embed_texts(texts_to_embed)
    if len(vectors) != len(texts_to_embed):
        raise ValueError(
            "embedder must return one vector per input text"
        )
    validate_embedding_vectors(vectors)

    ranked = sorted(
        [
            (cosine_similarity(vectors[0], vector), text, relevant)
            for (text, relevant), vector in zip(candidates, vectors[1:])
        ],
        key=lambda item: item[0],
        reverse=True,
    )

    relevant_total = sum(relevant for _, _, relevant in ranked)
    relevant_top_k = sum(relevant for _, _, relevant in ranked[:TOP_K])
    relevant_top_3 = sum(relevant for _, _, relevant in ranked[:EVAL_K])

    recall_at_5 = (
        relevant_top_k / relevant_total if relevant_total else 0.0
    )
    recall_at_3 = (
        relevant_top_3 / relevant_total if relevant_total else 0.0
    )
    reciprocal_rank_score = reciprocal_rank(ranked)

    return ranked, recall_at_5, recall_at_3, reciprocal_rank_score


def mean_metric(values):
    """Return the case-weighted mean of evaluation metrics."""
    return sum(values) / len(values) if values else 0.0


def metric_delta(baseline, experimental):
    """Return experimental metric minus baseline metric."""
    return experimental - baseline

def classify_outcome(deltas):
    """Classify metric changes as improved, regressed, mixed, or unchanged."""
    has_improvement = any(delta > 0 for delta in deltas.values())
    has_regression = any(delta < 0 for delta in deltas.values())

    if has_improvement and has_regression:
        return "mixed"
    if has_improvement:
        return "improved"
    if has_regression:
        return "regressed"
    return "unchanged"
def compare_rankings(baseline_ranked, experimental_ranked):
    """Compare two rankings using Recall@5, Recall@3, and MRR."""

    def calculate_metrics(ranked):
        relevant_total = sum(
            1 for _, _, relevant in ranked if relevant
        )

        relevant_at_5 = sum(
            1 for _, _, relevant in ranked[:TOP_K] if relevant
        )

        relevant_at_3 = sum(
            1 for _, _, relevant in ranked[:EVAL_K] if relevant
        )

        recall_at_5 = (
            relevant_at_5 / relevant_total
            if relevant_total
            else 0.0
        )

        recall_at_3 = (
            relevant_at_3 / relevant_total
            if relevant_total
            else 0.0
        )

        mrr = reciprocal_rank(ranked)

        return {
            "recall_at_5": recall_at_5,
            "recall_at_3": recall_at_3,
            "mrr": mrr,
        }

    baseline_metrics = calculate_metrics(baseline_ranked)
    experimental_metrics = calculate_metrics(experimental_ranked)

    deltas = {
        metric: metric_delta(
            baseline_metrics[metric],
            experimental_metrics[metric],
        )
        for metric in baseline_metrics
    }

    outcome = classify_outcome(deltas)
    return {
        "baseline": baseline_metrics,
        "experimental": experimental_metrics,
        "deltas": deltas,
        "outcome": outcome,
    }

def main():
    validate_cases(CASES)
    embedder = LocalEmbedder()

    baseline_results = []
    experimental_results = []

    unique_queries = {case["query"] for case in CASES}

    for index, case in enumerate(CASES, start=1):
        (
            ranked,
            recall_at_5,
            recall_at_3,
            reciprocal_rank_score,
        ) = evaluate_case(embedder, case)

        experimental_ranked = rerank_with_lexical_overlap(
            case["query"], ranked
        )

        comparison = compare_rankings(ranked, experimental_ranked)

        baseline_results.append(comparison["baseline"])
        experimental_results.append(comparison["experimental"])

        print(f"\nCase {index}: {case['query']}")

        print("\nBaseline ranking (semantic only):")
        for rank, (score, text, relevant) in enumerate(ranked, start=1):
            label = "RELEVANT" if relevant else "NOT RELEVANT"
            print(f"{rank}. {score:.4f} [{label}] {text}")

        print("\nExperimental ranking (semantic + lexical):")
        for rank, (score, text, relevant) in enumerate(
            experimental_ranked, start=1
        ):
            label = "RELEVANT" if relevant else "NOT RELEVANT"
            print(f"{rank}. {score:.4f} [{label}] {text}")

        print(f"\nBaseline Recall@{TOP_K}: {recall_at_5:.2f}")
        print(f"Baseline Recall@{EVAL_K}: {recall_at_3:.2f}")
        print(f"Baseline reciprocal rank: {reciprocal_rank_score:.2f}")

    baseline_metrics = {
        "recall_at_5": mean_metric(
            [result["recall_at_5"] for result in baseline_results]
        ),
        "recall_at_3": mean_metric(
            [result["recall_at_3"] for result in baseline_results]
        ),
        "mrr": mean_metric(
            [result["mrr"] for result in baseline_results]
        ),
    }

    experimental_metrics = {
        "recall_at_5": mean_metric(
            [result["recall_at_5"] for result in experimental_results]
        ),
        "recall_at_3": mean_metric(
            [result["recall_at_3"] for result in experimental_results]
        ),
        "mrr": mean_metric(
            [result["mrr"] for result in experimental_results]
        ),
    }

    deltas = {
        metric: metric_delta(
            baseline_metrics[metric],
            experimental_metrics[metric],
        )
        for metric in baseline_metrics
    }

    outcome = classify_outcome(deltas)

    print("\n=== Baseline results ===")
    print(f"Test cases: {len(CASES)}")
    print(f"Unique query texts: {len(unique_queries)}")
    print(f"Mean Recall@{TOP_K}: {baseline_metrics['recall_at_5']:.3f}")
    print(f"Mean Recall@{EVAL_K}: {baseline_metrics['recall_at_3']:.3f}")
    print(f"MRR: {baseline_metrics['mrr']:.3f}")

    print("\n=== Experimental results ===")
    print(
        f"Mean Recall@{TOP_K}: "
        f"{experimental_metrics['recall_at_5']:.3f}"
    )
    print(
        f"Mean Recall@{EVAL_K}: "
        f"{experimental_metrics['recall_at_3']:.3f}"
    )
    print(f"MRR: {experimental_metrics['mrr']:.3f}")

    print("\n=== Experimental change ===")
    print(
        f"Recall@{TOP_K}: {baseline_metrics['recall_at_5']:.3f} -> "
        f"{experimental_metrics['recall_at_5']:.3f} "
        f"({deltas['recall_at_5']:+.3f})"
    )
    print(
        f"Recall@{EVAL_K}: {baseline_metrics['recall_at_3']:.3f} -> "
        f"{experimental_metrics['recall_at_3']:.3f} "
        f"({deltas['recall_at_3']:+.3f})"
    )
    print(
        f"MRR: {baseline_metrics['mrr']:.3f} -> "
        f"{experimental_metrics['mrr']:.3f} "
        f"({deltas['mrr']:+.3f})"
    )
    print(f"Overall outcome: {outcome}")


if __name__ == "__main__":
    main()