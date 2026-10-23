
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
]

TOP_K = 5


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

    relevant_total = sum(relevant for _, _, relevant in ranked)
    relevant_top_k = sum(
        relevant for _, _, relevant in ranked[:TOP_K]
    )

    first_relevant_rank = next(
        (
            rank
            for rank, (_, _, relevant) in enumerate(ranked, start=1)
            if relevant
        ),
        None,
    )

    recall = (
        relevant_top_k / relevant_total
        if relevant_total
        else 0.0
    )
    reciprocal_rank = (
        1 / first_relevant_rank
        if first_relevant_rank
        else 0.0
    )

    return ranked, recall, reciprocal_rank


def main():
    embedder = LocalEmbedder()
    recalls = []
    reciprocal_ranks = []

    for index, case in enumerate(CASES, start=1):
        ranked, recall, reciprocal_rank = evaluate_case(
            embedder, case
        )

        recalls.append(recall)
        reciprocal_ranks.append(reciprocal_rank)

        print(f"\nCase {index}: {case['query']}")
        for rank, (score, text, relevant) in enumerate(ranked, start=1):
            label = "RELEVANT" if relevant else "NOT RELEVANT"
            print(f"{rank}. {score:.4f} [{label}] {text}")

        print(f"Recall@{TOP_K}: {recall:.2f}")
        print(f"Reciprocal rank: {reciprocal_rank:.2f}")

    unique_queries = {
        case["query"] for case in CASES
    }

    print("\n=== Overall results ===")
    print(f"Test cases: {len(CASES)}")
    print(f"Unique query texts: {len(unique_queries)}")
    print(f"Mean Recall@{TOP_K}: {sum(recalls) / len(recalls):.3f}")
    print(f"MRR: {sum(reciprocal_ranks) / len(reciprocal_ranks):.3f}")


if __name__ == "__main__":
    main()
