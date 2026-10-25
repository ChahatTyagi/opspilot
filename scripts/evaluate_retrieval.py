import re
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
            ("The new container fails readiness checks because its dependency is unavailable.", True),
            ("Health probes time out before the application finishes starting.", True),
            ("The release notes contain a new section.", False),
            ("The deployment dashboard theme was changed.", False),
            ("The background worker CPU usage is stable.", False),
            ("Database backups completed without errors.", False),
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
    """Experimental reranker; lexical overlap did not improve benchmark metrics.

    This is an evaluation-only experiment, not production retrieval logic.
    The small, hand-labelled benchmark has repeated query text and does not
    establish real-world retrieval performance.
    """
    reranked = []

    for semantic_score, text, relevant in ranked:
        lexical_score = lexical_overlap(query, text)
        combined_score = (
            alpha * semantic_score
            + (1 - alpha) * lexical_score
        )

        reranked.append(
            (combined_score, text, relevant)
        )

    return sorted(
        reranked,
        key=lambda item: item[0],
        reverse=True,
    )
def evaluate_case(embedder, case):
    candidates = case["candidates"]
    texts = [text for text, _ in candidates]
    vectors = embedder.embed_texts([case["query"]] + texts)

    ranked = sorted(
        [
            (
                cosine_similarity(vectors[0], vector),
                text,
                relevant,
            )
            for (text, relevant), vector
            in zip(candidates, vectors[1:])
        ],
        key=lambda item: item[0],
        reverse=True,
    )

    relevant_total = sum(
        relevant for _, _, relevant in ranked
    )

    relevant_top_k = sum(
        relevant for _, _, relevant in ranked[:TOP_K]
    )

    relevant_top_3 = sum(
        relevant for _, _, relevant in ranked[:EVAL_K]
    )

    recall_at_5 = (
        relevant_top_k / relevant_total
        if relevant_total
        else 0.0
    )

    recall_at_3 = (
        relevant_top_3 / relevant_total
        if relevant_total
        else 0.0
    )

    first_relevant_rank = next(
        (
            rank
            for rank, (_, _, relevant) in enumerate(ranked, start=1)
            if relevant
        ),
        None,
    )

    reciprocal_rank = (
        1 / first_relevant_rank
        if first_relevant_rank
        else 0.0
    )

    return ranked, recall_at_5, recall_at_3, reciprocal_rank


def main():
    embedder = LocalEmbedder()

    recalls_at_5 = []
    recalls_at_3 = []
    reciprocal_ranks = []
    experimental_recalls_at_5 = []
    experimental_recalls_at_3 = []
    experimental_reciprocal_ranks = []

    for index, case in enumerate(CASES, start=1):
        (
            ranked,
            recall_at_5,
            recall_at_3,
            reciprocal_rank,
        ) = evaluate_case(embedder, case)

        recalls_at_5.append(recall_at_5)
        recalls_at_3.append(recall_at_3)
        reciprocal_ranks.append(reciprocal_rank)

        experimental_ranked = rerank_with_lexical_overlap(
            case["query"], ranked
        )

        relevant_total = sum(
            relevant for _, _, relevant in experimental_ranked
        )

        experimental_recalls_at_5.append(
            sum(
                relevant
                for _, _, relevant in experimental_ranked[:TOP_K]
            ) / relevant_total if relevant_total else 0.0
        )

        experimental_recalls_at_3.append(
            sum(
                relevant
                for _, _, relevant in experimental_ranked[:EVAL_K]
            ) / relevant_total if relevant_total else 0.0
        )

        first_relevant_rank = next(
            (
                rank
                for rank, (_, _, relevant) in enumerate(
                    experimental_ranked, start=1
                )
                if relevant
            ),
            None,
        )

        experimental_reciprocal_ranks.append(
            1 / first_relevant_rank if first_relevant_rank else 0.0
        )

        print(f"\nCase {index}: {case['query']}")

        print("\nBaseline ranking (semantic only):")
        for rank, (score, text, relevant) in enumerate(
            ranked, start=1
        ):
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
        print(f"Baseline reciprocal rank: {reciprocal_rank:.2f}")

    unique_queries = {case["query"] for case in CASES}

    print("\n=== Baseline results ===")
    print(f"Test cases: {len(CASES)}")
    print(f"Unique query texts: {len(unique_queries)}")
    print(
        f"Mean Recall@{TOP_K}: "
        f"{sum(recalls_at_5) / len(recalls_at_5):.3f}"
    )
    print(
        f"Mean Recall@{EVAL_K}: "
        f"{sum(recalls_at_3) / len(recalls_at_3):.3f}"
    )
    print(f"MRR: {sum(reciprocal_ranks) / len(reciprocal_ranks):.3f}")

    print("\n=== Experimental results ===")
    print(
        f"Mean Recall@{TOP_K}: "
        f"{sum(experimental_recalls_at_5) / len(experimental_recalls_at_5):.3f}"
    )
    print(
        f"Mean Recall@{EVAL_K}: "
        f"{sum(experimental_recalls_at_3) / len(experimental_recalls_at_3):.3f}"
    )
    print(
        f"MRR: "
        f"{sum(experimental_reciprocal_ranks) / len(experimental_reciprocal_ranks):.3f}"
    )


if __name__ == "__main__":
    main()
