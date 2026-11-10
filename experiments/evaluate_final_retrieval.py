
import re
from statistics import mean
from types import SimpleNamespace

from nltk.stem import PorterStemmer

from app.investigation_tools import search_incident_evidence
from experiments.evaluate_keyword_retrieval import QUERY_EXPANSIONS


# ============================================================
# FINAL TEST DATASET
# 15 new incident scenarios x 8 evidence records = 120 records
#
# Evidence format:
# (evidence_id, source_type, content, is_relevant)
#
# Relevance labels are manually assigned. Do not change them
# to improve a retrieval method's score.
# ============================================================

FINAL_TEST_CASES = [
    {
        "name": "API rate limiting and throttling",
        "query": "API requests are being throttled and clients receive rate limit errors",
        "evidence": [
            (1001, "log", "Gateway returned HTTP 429 after the client exceeded the configured request rate limit.", True),
            (1002, "metric", "Requests per second exceeded the token bucket capacity on the public API.", True),
            (1003, "config", "The API gateway rate limiter is configured for 100 requests per minute per client.", True),
            (1004, "log", "The product catalogue service completed its scheduled data refresh.", False),
            (1005, "metric", "CPU utilization on the reporting worker remained below 35 percent.", False),
            (1006, "log", "A background email notification was delivered successfully.", False),
            (1007, "config", "The frontend static asset cache has a time to live of 30 minutes.", False),
            (1008, "log", "The health endpoint returned HTTP 200 during the monitoring interval.", False),
        ],
    },
    {
        "name": "Database deadlocks and transaction contention",
        "query": "Database transactions are blocked by deadlocks and lock contention",
        "evidence": [
            (1011, "log", "PostgreSQL detected a deadlock while two transactions attempted to update the same account rows.", True),
            (1012, "metric", "Database lock wait duration increased sharply during concurrent order processing.", True),
            (1013, "log", "Transaction aborted because the database could not acquire the required row lock.", True),
            (1014, "log", "The image processing worker generated a thumbnail successfully.", False),
            (1015, "metric", "The application server memory utilization remained stable.", False),
            (1016, "config", "The reverse proxy forwards requests to the application service on port 8080.", False),
            (1017, "log", "A scheduled cleanup task removed expired user sessions.", False),
            (1018, "metric", "The message broker consumer count remained unchanged.", False),
        ],
    },
    {
        "name": "DNS resolution and service discovery failure",
        "query": "Services cannot resolve DNS names and hostname lookups are failing",
        "evidence": [
            (1021, "log", "DNS lookup failed because the resolver returned SERVFAIL for the internal service hostname.", True),
            (1022, "log", "The application could not resolve the database endpoint through the configured DNS server.", True),
            (1023, "metric", "DNS query timeout count increased across application containers.", True),
            (1024, "log", "The payment reconciliation job completed without errors.", False),
            (1025, "config", "The application log retention period is configured for fourteen days.", False),
            (1026, "metric", "Disk utilization on the database host remained below 60 percent.", False),
            (1027, "log", "The user profile endpoint returned a successful response.", False),
            (1028, "config", "The worker process is configured to use four execution threads.", False),
        ],
    },
    {
        "name": "Kubernetes CPU throttling",
        "query": "Kubernetes containers are experiencing CPU throttling due to resource limits",
        "evidence": [
            (1031, "metric", "Container CPU throttled time increased after the workload reached its CPU quota.", True),
            (1032, "config", "The Kubernetes deployment defines a CPU limit of 250 millicores for each application pod.", True),
            (1033, "log", "Request processing slowed while the container repeatedly hit its CPU cgroup quota.", True),
            (1034, "log", "The cluster certificate renewal completed successfully.", False),
            (1035, "metric", "Persistent volume capacity remained available on all worker nodes.", False),
            (1036, "config", "The service uses a ClusterIP type for internal network access.", False),
            (1037, "log", "The scheduled database backup finished successfully.", False),
            (1038, "metric", "The message queue contained fewer than ten pending events.", False),
        ],
    },
    {
        "name": "Event serialization and schema incompatibility",
        "query": "Event consumers fail to deserialize messages because the payload schema changed",
        "evidence": [
            (1041, "log", "Consumer failed to deserialize the event because the payload field type did not match the expected schema.", True),
            (1042, "log", "Schema compatibility validation rejected the newly published event definition.", True),
            (1043, "config", "The consumer expects schema version 2 but the producer is publishing version 3 messages.", True),
            (1044, "metric", "The API gateway recorded a normal request success rate.", False),
            (1045, "log", "The cache refresh process completed without exceptions.", False),
            (1046, "config", "The database connection pool allows a maximum of twenty connections.", False),
            (1047, "metric", "The authentication service response time remained stable.", False),
            (1048, "log", "The nightly report was generated and stored successfully.", False),
        ],
    },
    {
        "name": "Database replication lag",
        "query": "Read replicas are delayed and database replication lag is increasing",
        "evidence": [
            (1051, "metric", "Replication lag on the read replica increased to 45 seconds behind the primary database.", True),
            (1052, "log", "Replica replay delay caused recently committed records to be missing from read queries.", True),
            (1053, "metric", "The replication queue contains an increasing number of unapplied write-ahead log records.", True),
            (1054, "log", "The application successfully refreshed its local configuration.", False),
            (1055, "metric", "The API service maintained its normal request throughput.", False),
            (1056, "config", "The frontend uses a two-minute client-side cache expiration.", False),
            (1057, "log", "The scheduled email digest was sent to all subscribers.", False),
            (1058, "metric", "The object storage bucket reported normal request latency.", False),
        ],
    },
    {
        "name": "Authentication token rotation failure",
        "query": "Requests fail because rotated access tokens and signing keys are rejected",
        "evidence": [
            (1061, "log", "JWT validation failed because the token was signed with a key that is no longer accepted.", True),
            (1062, "log", "Authentication middleware rejected requests after the signing key rotation.", True),
            (1063, "config", "The identity service and API gateway are using different active signing key versions.", True),
            (1064, "metric", "The database connection pool remained below its configured maximum.", False),
            (1065, "log", "The inventory synchronization task completed successfully.", False),
            (1066, "config", "The API gateway uses round-robin load balancing across application instances.", False),
            (1067, "metric", "The background worker CPU usage remained stable.", False),
            (1068, "log", "The monitoring agent successfully collected host metrics.", False),
        ],
    },
    {
        "name": "Object storage permission errors",
        "query": "Application uploads fail because object storage access permissions are denied",
        "evidence": [
            (1071, "log", "Object storage returned AccessDenied when the application attempted to upload a document.", True),
            (1072, "config", "The application service account does not have the required PutObject permission on the bucket.", True),
            (1073, "log", "Upload requests failed because the bucket policy denied the configured IAM principal.", True),
            (1074, "metric", "The database query cache hit ratio remained above 90 percent.", False),
            (1075, "log", "The notification worker delivered the upload confirmation email.", False),
            (1076, "config", "The API server listens on port 8000.", False),
            (1077, "metric", "The Kubernetes node memory utilization remained normal.", False),
            (1078, "log", "The scheduled cleanup removed temporary files from the local directory.", False),
        ],
    },
    {
        "name": "Circuit breaker repeatedly opening",
        "query": "The circuit breaker opens repeatedly because a downstream dependency is failing",
        "evidence": [
            (1081, "log", "Circuit breaker transitioned to OPEN after consecutive failures from the inventory dependency.", True),
            (1082, "metric", "Downstream service error percentage exceeded the circuit breaker's configured failure threshold.", True),
            (1083, "log", "Requests were rejected locally while the circuit breaker remained open.", True),
            (1084, "config", "The application uses JSON structured logging for request events.", False),
            (1085, "metric", "The database storage volume has sufficient free capacity.", False),
            (1086, "log", "The scheduled analytics export completed successfully.", False),
            (1087, "config", "The frontend application uses a 30-second session timeout.", False),
            (1088, "metric", "The message broker consumer group is operating normally.", False),
        ],
    },
    {
        "name": "Webhook delivery and retry failures",
        "query": "Outbound webhooks are failing delivery and retry attempts are exhausted",
        "evidence": [
            (1091, "log", "Webhook delivery returned HTTP 503 and the retry policy scheduled another attempt.", True),
            (1092, "metric", "The webhook delivery queue contains a growing number of pending callbacks.", True),
            (1093, "log", "Webhook events moved to the dead-letter queue after the maximum retry count was reached.", True),
            (1094, "log", "The application completed a successful database migration.", False),
            (1095, "metric", "The API server maintained normal memory consumption.", False),
            (1096, "config", "The frontend uses compressed JavaScript bundles.", False),
            (1097, "log", "A user successfully updated their account profile.", False),
            (1098, "metric", "The DNS resolver reported a normal response time.", False),
        ],
    },
    {
        "name": "Background scheduler and cron execution delay",
        "query": "Scheduled background jobs are delayed and cron tasks are not executing on time",
        "evidence": [
            (1101, "log", "The scheduler skipped a cron execution because the previous scheduled job was still running.", True),
            (1102, "metric", "The background job execution delay increased to twelve minutes beyond the scheduled time.", True),
            (1103, "log", "The task scheduler reported that its worker pool had no available execution slots.", True),
            (1104, "config", "The API gateway has a request body size limit of 10 megabytes.", False),
            (1105, "metric", "The primary database replication delay remained below one second.", False),
            (1106, "log", "The authentication service refreshed its signing key successfully.", False),
            (1107, "config", "The application uses a rolling deployment strategy.", False),
            (1108, "metric", "The object storage upload success rate remained stable.", False),
        ],
    },
    {
        "name": "Search indexing pipeline falling behind",
        "query": "Search index updates are delayed and documents are not being indexed",
        "evidence": [
            (1111, "metric", "The search indexing backlog increased as document updates accumulated faster than indexing throughput.", True),
            (1112, "log", "The indexing worker failed to apply document changes to the search index.", True),
            (1113, "log", "Search queries returned stale results because recent documents had not been indexed.", True),
            (1114, "metric", "The API request success rate remained above its normal threshold.", False),
            (1115, "config", "The database connection pool uses a maximum size of thirty connections.", False),
            (1116, "log", "The daily billing report was generated successfully.", False),
            (1117, "metric", "The application container disk usage remained below 50 percent.", False),
            (1118, "config", "The identity provider uses a five-minute access token lifetime.", False),
        ],
    },
    {
        "name": "Email delivery and SMTP rejection",
        "query": "Email notifications are not delivered because the SMTP server rejects messages",
        "evidence": [
            (1121, "log", "SMTP server rejected outbound email with a 550 relay access denied response.", True),
            (1122, "log", "The notification worker failed to authenticate with the configured SMTP relay.", True),
            (1123, "metric", "The email delivery failure count increased while the outbound mail queue accumulated messages.", True),
            (1124, "config", "The API gateway uses HTTPS for external client connections.", False),
            (1125, "metric", "The database query latency remained within the normal range.", False),
            (1126, "log", "The inventory service refreshed its product catalogue.", False),
            (1127, "config", "The worker process is configured with four concurrent threads.", False),
            (1128, "metric", "The object storage bucket has normal availability.", False),
        ],
    },
    {
        "name": "CDN cache invalidation failure",
        "query": "Users receive stale static content because CDN cache invalidation is failing",
        "evidence": [
            (1131, "log", "CDN invalidation request failed and the previous version of the JavaScript bundle remained cached.", True),
            (1132, "metric", "The edge cache continued serving stale assets after a new frontend release.", True),
            (1133, "config", "The CDN distribution has an excessive cache time to live for versioned static resources.", True),
            (1134, "log", "The database backup process completed successfully.", False),
            (1135, "metric", "The API gateway request rate remained normal.", False),
            (1136, "config", "The authentication service uses rotating refresh tokens.", False),
            (1137, "log", "The background notification task completed successfully.", False),
            (1138, "metric", "The message broker consumer lag remained low.", False),
        ],
    },
    {
        "name": "Connection pool leak in an external service client",
        "query": "Outbound HTTP client connections are leaked and the connection pool is exhausted",
        "evidence": [
            (1141, "metric", "The outbound HTTP connection pool reached its maximum size and no idle connections were available.", True),
            (1142, "log", "Requests timed out while waiting to acquire a connection from the external service client pool.", True),
            (1143, "log", "Connections were not returned to the HTTP client pool after response processing completed.", True),
            (1144, "config", "The application uses structured JSON logs with request identifiers.", False),
            (1145, "metric", "The database replica replay delay remained stable.", False),
            (1146, "log", "The scheduled report export completed successfully.", False),
            (1147, "config", "The frontend uses a content security policy header.", False),
            (1148, "metric", "The Kubernetes pod restart count remained unchanged.", False),
        ],
    },
    {
        "name": "Message consumer group partition imbalance",
        "query": "Event processing is uneven because message broker partitions are assigned imbalanced across consumers",
        "evidence": [
            (1151, "metric", "One consumer instance processes most broker partitions while other consumers remain idle.", True),
            (1152, "log", "Partition reassignment caused a subset of message consumers to stop receiving events.", True),
            (1153, "metric", "Consumer lag differs significantly between partitions in the same consumer group.", True),
            (1154, "log", "The API service completed its readiness check successfully.", False),
            (1155, "config", "The database uses read committed transaction isolation.", False),
            (1156, "metric", "The CDN cache hit ratio remained stable.", False),
            (1157, "log", "The daily cleanup task removed expired records.", False),
            (1158, "config", "The authentication gateway uses HTTPS-only cookies.", False),
        ],
    },
]


# ============================================================
# FIXED RETRIEVAL METHODS
# Keep these implementations and QUERY_EXPANSIONS unchanged
# while evaluating this final test dataset.
# ============================================================

STEMMER = PorterStemmer()
TOKEN_PATTERN = re.compile(r"\b[a-z0-9]+\b")


def tokenize(text):
    """Convert text into lowercase alphanumeric word tokens."""
    return TOKEN_PATTERN.findall(text.casefold())


def search_with_porter_stemming(
    query,
    incident_id,
    evidence_items,
    max_results=5,
):
    """Rank evidence using exact Porter-stemmed token overlap."""
    query_stems = {
        STEMMER.stem(token)
        for token in tokenize(query)
    }

    ranked = []

    for evidence in evidence_items:
        if evidence.incident_id != incident_id:
            continue

        evidence_stems = {
            STEMMER.stem(token)
            for token in tokenize(evidence.content)
        }

        matching_stems = query_stems.intersection(evidence_stems)

        if matching_stems:
            ranked.append((len(matching_stems), evidence))

    ranked.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "incident_id": evidence.incident_id,
            "evidence_id": evidence.id,
            "source_type": evidence.source_type,
            "text": evidence.content[:1000],
        }
        for _, evidence in ranked[:max_results]
    ]


def expand_query(query):
    """Append curated synonyms while retaining the original query."""
    expanded_terms = []

    for token in tokenize(query):
        expanded_terms.extend(QUERY_EXPANSIONS.get(token, []))

    if not expanded_terms:
        return query

    return query + " " + " ".join(expanded_terms)


def search_with_query_expansion(
    query,
    incident_id,
    evidence_items,
    max_results=5,
):
    """Use the existing production keyword search with expanded terms."""
    expanded_query = expand_query(query)

    return search_incident_evidence(
        expanded_query,
        incident_id,
        evidence_items,
        max_results=max_results,
    )


def search_with_hybrid_retrieval(
    query,
    incident_id,
    evidence_items,
    max_results=5,
):
    """Expand query vocabulary, then rank using stemmed exact tokens."""
    expanded_query = expand_query(query)

    query_stems = {
        STEMMER.stem(token)
        for token in tokenize(expanded_query)
    }

    ranked = []

    for evidence in evidence_items:
        if evidence.incident_id != incident_id:
            continue

        evidence_stems = {
            STEMMER.stem(token)
            for token in tokenize(evidence.content)
        }

        matching_stems = query_stems.intersection(evidence_stems)

        if matching_stems:
            ranked.append((len(matching_stems), evidence))

    ranked.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "incident_id": evidence.incident_id,
            "evidence_id": evidence.id,
            "source_type": evidence.source_type,
            "text": evidence.content[:1000],
        }
        for _, evidence in ranked[:max_results]
    ]


# ============================================================
# DATASET VALIDATION
# ============================================================

def validate_dataset(cases):
    """Check scenario names, IDs, evidence records and labels."""
    scenario_names = set()
    evidence_ids = set()

    for case in cases:
        assert case["name"] not in scenario_names, (
            f"Duplicate scenario name: {case['name']}"
        )
        scenario_names.add(case["name"])

        assert isinstance(case["query"], str) and case["query"].strip(), (
            f"Empty query in scenario: {case['name']}"
        )

        assert len(case["evidence"]) == 8, (
            f"{case['name']} must contain exactly 8 evidence records."
        )

        relevant_count = 0

        for record in case["evidence"]:
            assert len(record) == 4, (
                f"Invalid evidence tuple in {case['name']}: {record}"
            )

            evidence_id, source_type, content, is_relevant = record

            assert evidence_id not in evidence_ids, (
                f"Duplicate evidence ID: {evidence_id}"
            )
            evidence_ids.add(evidence_id)

            assert isinstance(source_type, str) and source_type.strip()
            assert isinstance(content, str) and content.strip()
            assert isinstance(is_relevant, bool)

            if is_relevant:
                relevant_count += 1

        assert relevant_count > 0, (
            f"No relevant evidence labelled in {case['name']}"
        )


# ============================================================
# EVALUATION
# ============================================================

def build_evidence_objects(case, incident_id):
    """Convert dataset tuples into objects expected by retrieval."""
    return [
        SimpleNamespace(
            id=evidence_id,
            incident_id=incident_id,
            source_type=source_type,
            content=content,
        )
        for evidence_id, source_type, content, _ in case["evidence"]
    ]


def evaluate_case(case, incident_id, search_function):
    """Calculate retrieval metrics for one scenario."""
    evidence_items = build_evidence_objects(case, incident_id)

    relevant_ids = {
        evidence_id
        for evidence_id, _, _, is_relevant in case["evidence"]
        if is_relevant
    }

    retrieved = search_function(
        case["query"],
        incident_id,
        evidence_items,
        max_results=5,
    )

    retrieved_ids = [
        item["evidence_id"]
        for item in retrieved
    ]

    retrieved_relevant = [
        evidence_id
        for evidence_id in retrieved_ids
        if evidence_id in relevant_ids
    ]

    missed_ids = sorted(relevant_ids - set(retrieved_ids))

    irrelevant_ids = [
        evidence_id
        for evidence_id in retrieved_ids
        if evidence_id not in relevant_ids
    ]

    recall_at_5 = (
        len(retrieved_relevant) / len(relevant_ids)
        if relevant_ids
        else 0.0
    )

    # Precision@5 uses a fixed denominator of 5.
    precision_at_5 = len(retrieved_relevant) / 5

    # This reports precision among only the items actually returned.
    precision_returned = (
        len(retrieved_relevant) / len(retrieved_ids)
        if retrieved_ids
        else 0.0
    )

    reciprocal_rank = 0.0

    for rank, evidence_id in enumerate(retrieved_ids, start=1):
        if evidence_id in relevant_ids:
            reciprocal_rank = 1 / rank
            break

    return {
        "retrieved_ids": retrieved_ids,
        "missed_ids": missed_ids,
        "irrelevant_ids": irrelevant_ids,
        "recall_at_5": recall_at_5,
        "precision_at_5": precision_at_5,
        "precision_returned": precision_returned,
        "mrr": reciprocal_rank,
    }


def evaluate_dataset(cases, search_function):
    """Evaluate a retrieval method across all scenarios."""
    results = []

    for index, case in enumerate(cases, start=1):
        incident_id = f"final-test-{index:02d}"

        result = evaluate_case(
            case,
            incident_id,
            search_function,
        )

        results.append({
            "name": case["name"],
            **result,
        })

    return results


# ============================================================
# REPORTING
# ============================================================

def macro_average(results, metric):
    """Calculate the unweighted average across scenarios."""
    return mean(result[metric] for result in results)


def print_comparison_table(method_results):
    """Print aggregate metrics for all retrieval methods."""
    print("\n" + "=" * 100)
    print("FINAL TEST DATASET: AGGREGATE RETRIEVAL RESULTS")
    print("=" * 100)

    print(
        f"{'Method':<25}"
        f"{'Recall@5':>12}"
        f"{'Precision@5':>15}"
        f"{'Precision Returned':>22}"
        f"{'MRR':>10}"
    )

    print("-" * 100)

    for method_name, results in method_results.items():
        print(
            f"{method_name:<25}"
            f"{macro_average(results, 'recall_at_5'):>12.3f}"
            f"{macro_average(results, 'precision_at_5'):>15.3f}"
            f"{macro_average(results, 'precision_returned'):>22.3f}"
            f"{macro_average(results, 'mrr'):>10.3f}"
        )

    print("=" * 100)


def print_scenario_results(method_results):
    """Show per-scenario recall so weak areas are visible."""
    print("\n" + "=" * 100)
    print("PER-SCENARIO RECALL@5")
    print("=" * 100)

    method_names = list(method_results.keys())

    print(f"{'Scenario':<48}", end="")

    for method_name in method_names:
        print(f"{method_name[:12]:>14}", end="")

    print()
    print("-" * 100)

    for index, case in enumerate(FINAL_TEST_CASES):
        print(f"{case['name']:<48}", end="")

        for method_name in method_names:
            score = method_results[method_name][index]["recall_at_5"]
            print(f"{score:>14.3f}", end="")

        print()

    print("=" * 100)


def print_hybrid_diagnostics(method_results):
    """Show what the hybrid method missed or retrieved incorrectly."""
    hybrid_results = method_results["Hybrid"]

    print("\n" + "=" * 100)
    print("HYBRID RETRIEVAL: FINAL TEST DIAGNOSTICS")
    print("=" * 100)

    for result in hybrid_results:
        print(f"\nScenario: {result['name']}")
        print(f"Retrieved IDs : {result['retrieved_ids']}")
        print(f"Missed IDs    : {result['missed_ids']}")
        print(f"Irrelevant IDs: {result['irrelevant_ids']}")
        print(f"Recall@5      : {result['recall_at_5']:.3f}")


# ============================================================
# MAIN
# ============================================================

def main():
    validate_dataset(FINAL_TEST_CASES)

    total_evidence = sum(
        len(case["evidence"])
        for case in FINAL_TEST_CASES
    )

    total_relevant = sum(
        sum(1 for _, _, _, relevant in case["evidence"] if relevant)
        for case in FINAL_TEST_CASES
    )

    print("Final retrieval benchmark validation passed.")
    print(f"Scenarios         : {len(FINAL_TEST_CASES)}")
    print(f"Evidence records  : {total_evidence}")
    print(f"Relevant records  : {total_relevant}")
    print(f"Non-relevant      : {total_evidence - total_relevant}")

    methods = {
        "Baseline": search_incident_evidence,
        "Porter stemming": search_with_porter_stemming,
        "Query expansion": search_with_query_expansion,
        "Hybrid": search_with_hybrid_retrieval,
    }

    method_results = {}

    for method_name, search_function in methods.items():
        print(f"\nEvaluating: {method_name}")

        method_results[method_name] = evaluate_dataset(
            FINAL_TEST_CASES,
            search_function,
        )

    print_comparison_table(method_results)
    print_scenario_results(method_results)
    print_hybrid_diagnostics(method_results)


if __name__ == "__main__":
    main()
