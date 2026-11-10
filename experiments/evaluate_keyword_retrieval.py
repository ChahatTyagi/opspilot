
import re
from types import SimpleNamespace
from nltk.stem import PorterStemmer
from app.investigation_tools import search_incident_evidence


CASES = [
    {
        "name": "Database connection pool exhaustion",
        "query": "Why are database connections unavailable after deployment?",
        "evidence": [
            (1, "log", "PostgreSQL connection pool exhausted; all 50 connections are active."),
            (2, "metric", "Database connection acquisition failures increased sharply."),
            (3, "log", "Checkout requests are waiting 30 seconds before failing."),
            (4, "deployment", "checkout-api version 2.8.1 was deployed 10 minutes before failures."),
            (5, "log", "Database backup completed successfully."),
            (6, "metric", "Reporting dashboard CPU utilization is stable."),
            (7, "deployment", "Frontend CSS assets were updated."),
            (8, "trace", "Checkout requests spend most of their time waiting for a database connection."),
        ],
        "relevant_ids": {1, 2, 3, 4, 8},
    },
    {
        "name": "Authentication failures",
        "query": "Why are users unable to log in?",
        "evidence": [
            (11, "log", "Identity provider rejects requests because JWT signatures are invalid."),
            (12, "metric", "HTTP 401 responses increased significantly across login requests."),
            (13, "trace", "Token validation fails before the authentication request reaches the user service."),
            (14, "deployment", "Authentication service signing key configuration changed in the latest release."),
            (15, "log", "User profile images loaded successfully."),
            (16, "metric", "Reporting worker CPU utilization is stable."),
            (17, "deployment", "Login page logo dimensions were updated."),
            (18, "log", "Expired access tokens are rejected by the identity provider."),
        ],
        "relevant_ids": {11, 12, 13, 14, 18},
    },
    {
        "name": "Deployment-related API regression",
        "query": "Why did API errors increase following the latest release?",
        "evidence": [
            (21, "log", "Request handlers began raising NullPointerException after version 4.2.0."),
            (22, "metric", "HTTP 500 error rate increased from 0.2% to 8.5% after deployment."),
            (23, "deployment", "API version 4.2.0 was released shortly before the error spike."),
            (24, "trace", "Requests fail inside the new response serialization component."),
            (25, "log", "Database backups completed without errors."),
            (26, "metric", "Memory usage on the reporting worker is unchanged."),
            (27, "deployment", "Dashboard theme configuration was updated."),
            (28, "log", "Homepage images are loading successfully."),
        ],
        "relevant_ids": {21, 22, 23, 24},
    },
    {
        "name": "Message queue backlog",
        "query": "Why are background jobs accumulating without being processed?",
        "evidence": [
            (31, "metric", "Queue depth increased while worker throughput dropped."),
            (32, "log", "Workers repeatedly fail to acquire messages from Redis."),
            (33, "trace", "Job processing requests spend excessive time waiting for downstream responses."),
            (34, "metric", "Consumer count dropped from 12 workers to 3 workers."),
            (35, "log", "Redis snapshots completed successfully."),
            (36, "deployment", "Admin dashboard layout was redesigned."),
            (37, "metric", "Payment database connection utilization is stable."),
            (38, "log", "Background workers repeatedly retry jobs after request timeouts."),
        ],
        "relevant_ids": {31, 32, 33, 34, 38},
    },
    {
        "name": "High API latency",
        "query": "What is causing the increase in API response times?",
        "evidence": [
            (41, "metric", "P95 latency increased from 180 ms to 2400 ms."),
            (42, "trace", "Most request duration is spent waiting for database queries."),
            (43, "log", "Slow query warnings increased significantly during peak traffic."),
            (44, "metric", "API request throughput remains nearly unchanged."),
            (45, "deployment", "Frontend button animations were modified."),
            (46, "log", "Database backup completed successfully."),
            (47, "metric", "Login page image loading time improved."),
            (48, "trace", "Several checkout requests spend over two seconds executing SQL queries."),
        ],
        "relevant_ids": {41, 42, 43, 44, 48},
    },
    {
        "name": "Memory exhaustion",
        "query": "Why is the application running out of memory and restarting?",
        "evidence": [
            (51, "metric", "Heap utilization increased continuously from 45% to 98%."),
            (52, "log", "Container runtime repeatedly terminated the application with an out-of-memory error."),
            (53, "trace", "Request objects remain referenced after response processing completes."),
            (54, "metric", "Incoming request volume remained stable during memory growth."),
            (55, "log", "Scheduled database backup completed successfully."),
            (56, "deployment", "Documentation website received a typography update."),
            (57, "metric", "Reporting service CPU utilization is unchanged."),
            (58, "log", "Application process restarted after exceeding its configured memory limit."),
        ],
        "relevant_ids": {51, 52, 53, 54, 58},
    },
    {
        "name": "Payment gateway failures",
        "query": "Why are checkout payments failing even though the payment page loads?",
        "evidence": [
            (61, "log", "Payment provider requests fail because outbound connections are refused."),
            (62, "trace", "Checkout API waits for the external payment gateway before returning HTTP 500."),
            (63, "metric", "Payment transaction failure rate increased to 35%."),
            (64, "log", "Payment page assets loaded successfully with HTTP 200."),
            (65, "deployment", "Reporting dashboard colors were changed."),
            (66, "metric", "Authentication service response times are stable."),
            (67, "log", "Payment gateway connection attempts exceed the configured timeout."),
            (68, "deployment", "Frontend CSS was updated without modifying payment API code."),
        ],
        "relevant_ids": {61, 62, 63, 67},
    },
    {
        "name": "Disk space exhaustion",
        "query": "Why is the service unable to write files to disk?",
        "evidence": [
            (71, "log", "Application writes fail with No space left on device."),
            (72, "metric", "Filesystem utilization reached 100% on the application volume."),
            (73, "log", "Temporary diagnostic files have accumulated over several days."),
            (74, "metric", "Available disk capacity decreased continuously."),
            (75, "deployment", "Login page footer text was updated."),
            (76, "log", "Database connection pool is healthy."),
            (77, "metric", "Network packet loss remains near zero."),
            (78, "log", "Log rotation failed because the filesystem has no remaining capacity."),
        ],
        "relevant_ids": {71, 72, 73, 74, 78},
    },
    {
        "name": "Network connectivity failure",
        "query": "Why can the application no longer communicate with the downstream service?",
        "evidence": [
            (81, "log", "Connection attempts to the inventory service fail with connection refused."),
            (82, "trace", "Outbound requests terminate before reaching the downstream application."),
            (83, "metric", "Network connection failure rate increased to 28%."),
            (84, "log", "DNS resolution for inventory.internal intermittently returns no records."),
            (85, "metric", "Database query latency is stable."),
            (86, "deployment", "Dashboard background color was modified."),
            (87, "log", "Database backups completed successfully."),
            (88, "metric", "Packet retransmissions increased significantly on the application network interface."),
        ],
        "relevant_ids": {81, 82, 83, 84, 88},
    },
    {
        "name": "Database query performance degradation",
        "query": "Why are database queries slow even though traffic is low?",
        "evidence": [
            (91, "log", "Queries are waiting for locks held by a long-running transaction."),
            (92, "trace", "Database execution time increased while request volume remained low."),
            (93, "metric", "Active database locks increased sharply."),
            (94, "log", "Query planner switched to a sequential scan after statistics changed."),
            (95, "metric", "Database connection pool utilization remains low and stable."),
            (96, "deployment", "Reporting dashboard layout was updated."),
            (97, "log", "Scheduled database backup completed successfully."),
            (98, "metric", "Database CPU utilization is stable despite increased query duration."),
        ],
        "relevant_ids": {91, 92, 93, 94, 98},
    },
]


def build_evidence_objects(case, incident_id):
    """Convert dataset records into production-compatible evidence objects."""

    return [
        SimpleNamespace(
            id=evidence_id,
            incident_id=incident_id,
            source_type=source_type,
            content=content,
        )
        for evidence_id, source_type, content in case["evidence"]
    ]


def validate_dataset(cases):
    """Validate the manually labelled evaluation dataset."""

    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset must be a non-empty list.")

    seen_names = set()
    all_evidence_ids = set()

    for case in cases:
        name = case.get("name")
        query = case.get("query")
        evidence = case.get("evidence")
        relevant_ids = case.get("relevant_ids")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every case must have a name.")

        if name in seen_names:
            raise ValueError(f"Duplicate case name: {name}")

        seen_names.add(name)

        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"Invalid query in case: {name}")

        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"Missing evidence in case: {name}")

        evidence_ids = set()

        for record in evidence:
            if not isinstance(record, tuple) or len(record) != 3:
                raise ValueError(f"Invalid evidence record in case: {name}")

            evidence_id, source_type, content = record

            if not isinstance(evidence_id, int) or isinstance(evidence_id, bool):
                raise ValueError(f"Invalid evidence ID in case: {name}")

            if evidence_id in evidence_ids or evidence_id in all_evidence_ids:
                raise ValueError(f"Duplicate evidence ID: {evidence_id}")

            evidence_ids.add(evidence_id)
            all_evidence_ids.add(evidence_id)

            if not isinstance(source_type, str) or not source_type.strip():
                raise ValueError(f"Invalid source type in case: {name}")

            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"Invalid evidence content in case: {name}")

        if not isinstance(relevant_ids, set) or not relevant_ids:
            raise ValueError(f"Relevant IDs must be a non-empty set: {name}")

        if not relevant_ids.issubset(evidence_ids):
            raise ValueError(f"Unknown relevant evidence ID in case: {name}")


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at",
    "be", "because", "been", "being", "but", "by",
    "can", "could",
    "did", "do", "does",
    "even",
    "for", "from",
    "had", "has", "have", "how",
    "i", "if", "in", "into", "is", "it",
    "may", "might", "must",
    "no", "not",
    "of", "on", "or",
    "should", "so",
    "than", "that", "the", "their", "then",
    "there", "these", "they", "this", "those", "to",
    "was", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would",
}


QUERY_EXPANSIONS = {
    "login": ["authentication", "auth", "sign-in"],
    "users": ["accounts", "customers"],
    "unable": ["failure", "failed", "unavailable"],
    "jobs": ["tasks", "workers", "queue"],
    "accumulating": ["backlog", "pending", "queued"],
    "processed": ["processing", "throughput"],
    "response": ["latency", "duration"],
    "times": ["latency", "duration"],
    "memory": ["heap", "ram", "out-of-memory"],
    "restarting": ["restart", "terminated", "crash"],
    "payments": ["transactions", "gateway", "provider"],
    "write": ["writes", "filesystem", "storage"],
    "disk": ["filesystem", "storage", "volume"],
    "communicate": ["connect", "connection", "connectivity"],
    "downstream": ["dependency", "service"],
    "queries": ["sql", "database", "locks"],
    "slow": ["latency", "performance"],
    "deployment": ["release", "version"],
    "connections": ["connection"],
    "failing": ["failure", "failed"],
}


def search_without_stop_words(
    query,
    incident_id,
    evidence_items,
    max_results=5,
):
    """Experimental search using production keyword matching without stop words."""

    filtered_terms = [
        term
        for term in query.casefold().split()
        if term not in STOP_WORDS
    ]

    filtered_query = " ".join(filtered_terms)

    return search_incident_evidence(
        query=filtered_query,
        incident_id=incident_id,
        evidence_items=evidence_items,
        max_results=max_results,
    )


def search_with_query_expansion(
    query,
    incident_id,
    evidence_items,
    max_results=5,
):
    """Experimental search using manually defined query expansions."""

    original_terms = re.findall(
        r"\b[a-z0-9]+\b",
        query.casefold(),
    )

    expanded_terms = set(original_terms)

    for term in original_terms:
        related_terms = QUERY_EXPANSIONS.get(term, [])
        expanded_terms.update(related_terms)

    
    additional_terms = expanded_terms - set(original_terms)
    expanded_query = query + " " + " ".join(sorted(additional_terms))

    return search_incident_evidence(
        query=expanded_query,
        incident_id=incident_id,
        evidence_items=evidence_items,
        max_results=max_results,
    )

def search_exact_tokens(
    query,
    incident_id,
    evidence_items,
    max_results=5,
):
    """Experimental search using exact word matching."""

    query_terms = set(
        re.findall(r"\b[a-z0-9]+\b", query.casefold())
    )

    matches = []

    for item in evidence_items:
        if item.incident_id != incident_id:
            continue

        evidence_terms = set(
            re.findall(
                r"\b[a-z0-9]+\b",
                (item.content or "").casefold(),
            )
        )

        matching_terms = query_terms & evidence_terms

        if not matching_terms:
            continue

        matches.append(
            {
                "incident_id": item.incident_id,
                "evidence_id": item.id,
                "source_type": item.source_type,
                "text": (item.content or "")[:1000],
                "match_count": len(matching_terms),
            }
        )

    matches.sort(
        key=lambda result: result["match_count"],
        reverse=True,
    )

    return [
        {
            "incident_id": result["incident_id"],
            "evidence_id": result["evidence_id"],
            "source_type": result["source_type"],
            "text": result["text"],
        }
        for result in matches[:max_results]
    ]


def search_stemmed_tokens(
    query,
    incident_id,
    evidence_items,
    max_results=5,
):
    """Experimental search using Porter stemming and exact stem matching."""

    stemmer = PorterStemmer()

    query_tokens = re.findall(r"\b[a-z0-9]+\b", query.casefold())
    query_stems = {
        stemmer.stem(token)
        for token in query_tokens
    }

    matches = []

    for item in evidence_items:
        if item.incident_id != incident_id:
            continue

        evidence_tokens = re.findall(
            r"\b[a-z0-9]+\b",
            (item.content or "").casefold(),
        )

        evidence_stems = {
            stemmer.stem(token)
            for token in evidence_tokens
        }

        matching_stems = query_stems & evidence_stems

        if not matching_stems:
            continue

        matches.append(
            {
                "incident_id": item.incident_id,
                "evidence_id": item.id,
                "source_type": item.source_type,
                "text": (item.content or "")[:1000],
                "match_count": len(matching_stems),
            }
        )

    matches.sort(
        key=lambda result: result["match_count"],
        reverse=True,
    )

    return [
        {
            "incident_id": result["incident_id"],
            "evidence_id": result["evidence_id"],
            "source_type": result["source_type"],
            "text": result["text"],
        }
        for result in matches[:max_results]
    ]

def get_keyword_matches(query, case, evidence_ids):
    """Show which query terms match selected evidence records."""

    query_terms = set(query.casefold().split())

    evidence_by_id = {
        evidence_id: content
        for evidence_id, source_type, content in case["evidence"]
    }

    matches = {}

    for evidence_id in evidence_ids:
        content = evidence_by_id[evidence_id].casefold()

        matching_terms = sorted(
            term
            for term in query_terms
            if term in content
        )

        matches[evidence_id] = matching_terms

    return matches



def evaluate_case(case, incident_id, search_function):
    """Evaluate keyword search for one incident scenario."""

    evidence_objects = build_evidence_objects(case, incident_id)

    results = search_function(
        query=case["query"],
        incident_id=incident_id,
        evidence_items=evidence_objects,
        max_results=5,
    )

    retrieved_ids = [
        result["evidence_id"]
        for result in results
    ]

    relevant_ids = case["relevant_ids"]

    relevant_retrieved = sum(
        evidence_id in relevant_ids
        for evidence_id in retrieved_ids
    )

    missed_ids = sorted(relevant_ids - set(retrieved_ids))

    irrelevant_ids = [
        evidence_id
        for evidence_id in retrieved_ids
        if evidence_id not in relevant_ids
    ]

    # Fixed-cutoff precision: denominator is always 5.
    precision_at_5 = relevant_retrieved / 5

    # Precision among the results actually returned.
    precision_returned = (
        relevant_retrieved / len(retrieved_ids)
        if retrieved_ids
        else 0.0
    )

    recall_at_5 = relevant_retrieved / len(relevant_ids)

    first_relevant_rank = next(
        (
            rank
            for rank, evidence_id in enumerate(retrieved_ids, start=1)
            if evidence_id in relevant_ids
        ),
        None,
    )

    reciprocal_rank_score = (
        1 / first_relevant_rank
        if first_relevant_rank is not None
        else 0.0
    )

    return {
        "name": case["name"],
        "query": case["query"],
        "retrieved_ids": retrieved_ids,
        "relevant_retrieved": relevant_retrieved,
        "total_relevant": len(relevant_ids),
        "missed_ids": missed_ids,
        "irrelevant_ids": irrelevant_ids,
        "recall_at_5": recall_at_5,
        "precision_at_5": precision_at_5,
        "precision_returned": precision_returned,
        "mrr": reciprocal_rank_score,
    }


def main():
    validate_dataset(CASES)

    print("Dataset validation successful.")
    print(f"Incident scenarios: {len(CASES)}")
    print(
        "Total evidence records: "
        f"{sum(len(case['evidence']) for case in CASES)}"
    )

    search_methods = {
        "Baseline": search_incident_evidence,
        "Stop-word removal": search_without_stop_words,
        "Exact token matching": search_exact_tokens,
        "Porter stemming": search_stemmed_tokens,
        "Query expansion": search_with_query_expansion,
    }

    all_results = {}

    for method_name, search_function in search_methods.items():
        results = []

        print(f"\n========== {method_name.upper()} ==========")

        for index, case in enumerate(CASES, start=1):
            result = evaluate_case(
                case,
                incident_id=index,
                search_function=search_function,
            )

            results.append(result)

            print(f"\nCase {index}: {result['name']}")
            print(f"Retrieved IDs: {result['retrieved_ids']}")
            print(f"Missed relevant IDs: {result['missed_ids']}")
            print(f"Irrelevant retrieved IDs: {result['irrelevant_ids']}")
            print(f"Recall@5: {result['recall_at_5']:.3f}")
            print(f"Precision@5: {result['precision_at_5']:.3f}")
            print(
                "Precision (returned): "
                f"{result['precision_returned']:.3f}"
            )
            print(f"MRR: {result['mrr']:.3f}")

        case_count = len(results)

        mean_recall = sum(
            result["recall_at_5"] for result in results
        ) / case_count

        mean_precision = sum(
            result["precision_at_5"] for result in results
        ) / case_count

        mean_precision_returned = sum(
            result["precision_returned"] for result in results
        ) / case_count

        mean_mrr = sum(
            result["mrr"] for result in results
        ) / case_count

        all_results[method_name] = {
            "recall": mean_recall,
            "precision": mean_precision,
            "precision_returned": mean_precision_returned,
            "mrr": mean_mrr,
        }

        print(f"\n{method_name} summary:")
        print(f"Mean Recall@5: {mean_recall:.3f}")
        print(f"Mean Precision@5: {mean_precision:.3f}")
        print(
            "Mean Precision (returned): "
            f"{mean_precision_returned:.3f}"
        )
        print(f"Mean MRR: {mean_mrr:.3f}")

    # Compare all retrieval methods.
    print("\n========== SIDE-BY-SIDE COMPARISON ==========")

    print(
        f"{'Metric':<24}"
        f"{'Baseline':>12}"
        f"{'Stop-word':>14}"
        f"{'Exact tokens':>14}"
        f"{'Porter stem':>14}"
        f"{'Query expand':>14}"
    )

    print("-" * 92)

    for metric, key in [
        ("Recall@5", "recall"),
        ("Precision@5", "precision"),
        ("Precision (returned)", "precision_returned"),
        ("MRR", "mrr"),
    ]:
        print(
            f"{metric:<24}"
            f"{all_results['Baseline'][key]:>12.3f}"
            f"{all_results['Stop-word removal'][key]:>14.3f}"
            f"{all_results['Exact token matching'][key]:>14.3f}"
            f"{all_results['Porter stemming'][key]:>14.3f}"
            f"{all_results['Query expansion'][key]:>14.3f}"
        )


if __name__ == "__main__":
    main()
