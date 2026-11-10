
from statistics import mean
from types import SimpleNamespace

from app.investigation_tools import search_incident_evidence

from experiments.evaluate_final_retrieval import (
    search_with_porter_stemming,
    search_with_query_expansion,
    search_with_hybrid_retrieval,
)


# ============================================================
# FINAL RETRIEVAL BENCHMARK V2
#
# 20 scenarios x 8 evidence records = 160 records.
#
# Evidence tuple:
# (evidence_id, source_type, content, is_relevant)
#
# True  = relevant evidence
# False = irrelevant evidence
# ============================================================

FINAL_TEST_CASES = [

    {
        "name": "Checkout failures caused by expired service certificate",
        "query": "Customers cannot complete purchases because the checkout service suddenly refuses connections",
        "evidence": [
            (2001, "log", "TLS negotiation aborted because the certificate presented by the order endpoint passed its validity end date.", True),
            (2002, "log", "The payment workflow could not establish a trusted session with the checkout backend.", True),
            (2003, "config", "The certificate bundle mounted in the checkout deployment was not renewed after its expiration.", True),
            (2004, "metric", "The payment provider authorization latency increased during the same interval.", False),
            (2005, "log", "Several card transactions were declined by the external issuer with insufficient funds.", False),
            (2006, "config", "The checkout service uses a connection pool of twenty database sessions.", False),
            (2007, "metric", "The product catalogue cache recorded a lower hit ratio after the latest release.", False),
            (2008, "log", "The order confirmation email was delivered after a successful purchase.", False),
        ],
    },

    {
        "name": "Application pauses caused by garbage collection",
        "query": "The application periodically freezes and requests take a long time before recovering",
        "evidence": [
            (2011, "metric", "Stop-the-world collection pauses reached several seconds while the managed heap was nearly full.", True),
            (2012, "log", "The runtime repeatedly performed full heap reclamation before request processing resumed.", True),
            (2013, "metric", "Allocation pressure increased sharply and old-generation occupancy failed to fall after collection.", True),
            (2014, "metric", "The database server reported elevated query execution time.", False),
            (2015, "log", "The reverse proxy retried requests after receiving an upstream gateway timeout.", False),
            (2016, "config", "The application container memory limit is set to two gigabytes.", True),
            (2017, "log", "The background image worker completed a batch of thumbnail conversions.", False),
            (2018, "metric", "The message broker recorded a temporary increase in consumer lag.", False),
        ],
    },

    {
        "name": "Login rejection caused by clock skew",
        "query": "Users are unexpectedly signed out and valid sessions are rejected",
        "evidence": [
            (2021, "log", "Token validation rejected credentials because the token issue time was ahead of the verifier clock.", True),
            (2022, "metric", "The authentication nodes showed several minutes of time drift relative to the time source.", True),
            (2023, "config", "Time synchronization was disabled on one identity-service virtual machine.", True),
            (2024, "log", "The password verification component rejected an incorrect user-supplied password.", False),
            (2025, "metric", "The identity database connection pool reached its configured maximum.", False),
            (2026, "config", "Refresh tokens are configured to expire after seven days.", False),
            (2027, "log", "The profile service returned a missing optional avatar field.", False),
            (2028, "metric", "The API gateway recorded normal request throughput.", False),
        ],
    },

    {
        "name": "File upload failure caused by request body limit",
        "query": "Large documents fail to upload even though smaller files work normally",
        "evidence": [
            (2031, "log", "The ingress proxy returned HTTP 413 before forwarding the oversized multipart request.", True),
            (2032, "config", "The reverse proxy client body limit is smaller than the maximum document size accepted by the application.", True),
            (2033, "log", "The upload handler never received the request because the edge proxy rejected its payload.", True),
            (2034, "metric", "Object storage returned elevated latency for completed upload operations.", False),
            (2035, "log", "The document scanner quarantined a file because its antivirus signature matched a known threat.", False),
            (2036, "config", "The upload service stores completed documents in a private bucket.", False),
            (2037, "metric", "The database connection pool remained below its saturation threshold.", False),
            (2038, "log", "The file metadata record was created after a successful small-file upload.", False),
        ],
    },

    {
        "name": "Stale inventory caused by cache invalidation failure",
        "query": "The storefront displays old stock quantities after warehouse updates have completed",
        "evidence": [
            (2041, "log", "Warehouse updates reached the primary store, but the corresponding cache entries were not evicted.", True),
            (2042, "metric", "Inventory reads continued to return cached values older than the latest stock mutation.", True),
            (2043, "log", "The cache invalidation subscriber stopped consuming inventory change notifications.", True),
            (2044, "metric", "The inventory database reported increased write latency during warehouse synchronization.", False),
            (2045, "log", "The product search index refreshed successfully after the catalogue import.", False),
            (2046, "config", "The storefront uses a five-minute cache expiration for product descriptions.", False),
            (2047, "metric", "The warehouse event queue contains a small number of unprocessed messages.", False),
            (2048, "log", "The pricing service recalculated promotional discounts for active products.", False),
        ],
    },

    {
        "name": "Database write stalls caused by checkpoint pressure",
        "query": "Saving records intermittently stalls and write operations become unusually slow",
        "evidence": [
            (2051, "metric", "Database checkpoint writes saturated storage throughput and caused foreground transactions to wait.", True),
            (2052, "log", "The database reported repeated checkpoint completion warnings during periods of heavy write activity.", True),
            (2053, "config", "The checkpoint interval and WAL volume settings cause frequent large flush operations.", True),
            (2054, "metric", "Read replica replay delay increased while the primary database continued accepting writes.", False),
            (2055, "log", "A query planner selected a sequential scan for a large reporting query.", False),
            (2056, "config", "The database uses read committed isolation for application transactions.", False),
            (2057, "metric", "The database connection pool had several idle sessions available.", False),
            (2058, "log", "The nightly backup completed and uploaded its archive to object storage.", False),
        ],
    },

    {
        "name": "Reports missing records because of timezone boundary handling",
        "query": "Daily reports omit transactions that occurred near midnight",
        "evidence": [
            (2061, "log", "The reporting query converted local timestamps to UTC using an incorrect day boundary.", True),
            (2062, "config", "The report scheduler uses local dates while stored transaction timestamps are interpreted as UTC.", True),
            (2063, "log", "Transactions near midnight were assigned to the previous reporting period after timezone conversion.", True),
            (2064, "metric", "The reporting database replica was several seconds behind the primary.", False),
            (2065, "log", "The report export process truncated a CSV file after reaching its configured size limit.", False),
            (2066, "config", "The report service uses pagination with a page size of five hundred rows.", False),
            (2067, "metric", "The email delivery queue accumulated messages during the morning schedule.", False),
            (2068, "log", "The billing service successfully calculated tax for the selected reporting period.", False),
        ],
    },

    {
        "name": "Email delivery delay caused by SMTP greylisting",
        "query": "Password reset and notification emails arrive much later than expected",
        "evidence": [
            (2071, "log", "The remote mail exchanger temporarily deferred delivery with a greylisting response.", True),
            (2072, "metric", "SMTP retry intervals increased the time messages remained in the outbound delivery queue.", True),
            (2073, "log", "The mail transfer agent successfully delivered deferred messages after subsequent retry attempts.", False),
            (2074, "log", "The notification worker failed to authenticate because its SMTP password was invalid.", False),
            (2075, "metric", "The email queue grew because the notification worker deployment had insufficient replicas.", False),
            (2076, "config", "The application uses a branded sender address for password reset messages.", False),
            (2077, "metric", "The user database query latency remained within normal limits.", False),
            (2078, "log", "The account service generated password reset tokens successfully.", False),
        ],
    },

    {
        "name": "API requests rejected by proxy header configuration",
        "query": "Some API clients receive bad gateway responses after requests pass through the edge layer",
        "evidence": [
            (2081, "log", "The upstream server closed the connection after receiving an invalid forwarded host header.", True),
            (2082, "config", "The proxy forwarded duplicate host metadata that the application server rejected.", True),
            (2083, "log", "Gateway failures occurred only on requests routed through the newly changed proxy configuration.", True),
            (2084, "metric", "The API application recorded elevated CPU usage while processing valid requests.", False),
            (2085, "log", "The application returned HTTP 400 because a client omitted a required JSON field.", False),
            (2086, "config", "The edge proxy uses round-robin routing across three application instances.", False),
            (2087, "metric", "The database connection pool remained below its maximum size.", False),
            (2088, "log", "The API health endpoint returned HTTP 200 when accessed directly.", False),
        ],
    },

    {
        "name": "Queue messages repeatedly redelivered",
        "query": "Background tasks run more than once and some jobs appear to repeat indefinitely",
        "evidence": [
            (2091, "log", "Messages were delivered again because consumers did not acknowledge them before the visibility timeout expired.", True),
            (2092, "config", "The broker visibility timeout is shorter than the normal processing duration of long-running tasks.", True),
            (2093, "metric", "The same task identifiers appeared repeatedly in the consumer delivery history.", True),
            (2094, "log", "The dead-letter queue received messages after their configured maximum delivery attempts.", True),
            (2095, "metric", "The consumer group had fewer active workers than the configured target replica count.", False),
            (2096, "config", "The broker retains successfully acknowledged messages for one day.", False),
            (2097, "log", "The scheduler created a new task because its recurring schedule fired as expected.", False),
            (2098, "metric", "The database reported normal transaction commit latency.", False),
        ],
    },

    {
        "name": "DNS responses remain stale after endpoint changes",
        "query": "A service continues connecting to an old server after its endpoint was changed",
        "evidence": [
            (2101, "config", "The resolver retained the previous address because the DNS record time to live had not expired.", True),
            (2102, "log", "Application containers continued using cached hostname results after the service endpoint migration.", True),
            (2103, "metric", "The DNS cache hit rate remained high for an obsolete address during the transition.", False),
            (2104, "log", "The new endpoint refused connections because its application process had not started.", False),
            (2105, "config", "The service discovery record points to the correct new address in the authoritative zone.", False),
            (2106, "metric", "The network interface recorded a rise in packet retransmissions.", False),
            (2107, "log", "The load balancer health check marked one backend as unhealthy.", False),
            (2108, "metric", "The application request count remained stable throughout the migration.", False),
        ],
    },

    {
        "name": "Duplicate charges caused by missing idempotency protection",
        "query": "Customers are charged multiple times when they retry a failed payment",
        "evidence": [
            (2111, "log", "The payment endpoint created a second charge because the retry used a new request identifier.", True),
            (2112, "config", "The payment operation does not persist or enforce an idempotency key across repeated submissions.", True),
            (2113, "log", "A client timeout triggered a retry even though the original charge had already been accepted by the provider.", True),
            (2114, "metric", "The payment provider authorization service showed elevated response latency.", False),
            (2115, "log", "The reconciliation job detected a mismatch between settled transactions and local order states.", False),
            (2116, "config", "The checkout service allows three attempts for declined card authorizations.", False),
            (2117, "metric", "The order database reported a normal transaction commit rate.", False),
            (2118, "log", "A customer received a payment declined response from the card issuer.", False),
        ],
    },

    {
        "name": "Kubernetes pods evicted due to ephemeral storage pressure",
        "query": "Application instances disappear from the cluster during periods of heavy activity",
        "evidence": [
            (2121, "log", "The kubelet evicted application pods after node-local ephemeral storage usage crossed the eviction threshold.", True),
            (2122, "metric", "Container writable layers and temporary files consumed nearly all available node-local storage.", True),
            (2123, "config", "The workload has no suitable ephemeral storage request or limit for its temporary file usage.", True),
            (2124, "log", "The scheduler could not place replacement pods because available CPU capacity was insufficient.", False),
            (2125, "metric", "The cluster recorded repeated container restarts after application process crashes.", False),
            (2126, "config", "The deployment uses a memory request of 512 MiB per replica.", False),
            (2127, "metric", "Persistent volume utilization remained below its configured capacity.", False),
            (2128, "log", "The cluster autoscaler added a worker node after a pending pod alert.", False),
        ],
    },

    {
        "name": "Search results missing because of analyzer mismatch",
        "query": "Documents exist in the catalogue but searches fail to find them",
        "evidence": [
            (2131, "config", "The index was built with a keyword analyzer while queries are processed with a language tokenizer.", True),
            (2132, "log", "Search terms were normalized differently at indexing time and query time, producing incompatible tokens.", True),
            (2133, "log", "The document records are present in the search index but their analyzed terms do not match user input.", True),
            (2134, "metric", "The search cluster rejected requests because its heap usage exceeded the configured threshold.", False),
            (2135, "log", "The indexing worker failed to connect to the broker while consuming catalogue updates.", False),
            (2136, "config", "The search service uses three shards and one replica for each index.", False),
            (2137, "metric", "The catalogue database returned a normal number of matching rows.", False),
            (2138, "log", "The frontend search form submitted an empty query string.", False),
        ],
    },

    {
        "name": "Webhook duplicate processing caused by retry semantics",
        "query": "External partners process the same callback event multiple times",
        "evidence": [
            (2141, "log", "The sender retried a callback after a response timeout even though the receiver had already processed it.", True),
            (2142, "config", "The webhook consumer does not record processed event identifiers to prevent duplicate handling.", True),
            (2143, "log", "Repeated delivery attempts carried the same event identifier and created duplicate downstream actions.", True),
            (2144, "metric", "The webhook endpoint returned elevated HTTP 500 responses during a short outage.", False),
            (2145, "config", "The sender signs webhook payloads using an HMAC secret.", False),
            (2146, "log", "The callback receiver rejected a request with an invalid signature.", False),
            (2147, "metric", "The outbound event queue contained a growing number of undelivered callbacks.", False),
            (2148, "log", "The partner endpoint returned HTTP 200 for the latest callback attempt.", False),
        ],
    },

    {
        "name": "TLS handshake failures caused by certificate name mismatch",
        "query": "Internal service calls fail secure connection setup after a hostname change",
        "evidence": [
            (2151, "log", "The TLS client rejected the peer because the requested hostname was absent from the certificate subject alternative names.", True),
            (2152, "config", "The service certificate was issued for the previous DNS name and does not cover the replacement hostname.", True),
            (2153, "log", "Certificate chain validation succeeded, but endpoint identity verification failed.", True),
            (2154, "metric", "The certificate expiration monitoring alert reported that the certificate remains valid for another month.", False),
            (2155, "log", "The DNS resolver returned NXDOMAIN for an unrelated monitoring hostname.", False),
            (2156, "config", "The client enforces TLS 1.2 or newer for outbound connections.", False),
            (2157, "metric", "The service recorded a rise in HTTP request latency after the hostname migration.", False),
            (2158, "log", "The load balancer successfully established encrypted connections with other backends.", False),
        ],
    },

    {
        "name": "Read-after-write inconsistency caused by replica routing",
        "query": "Users do not see their latest changes immediately after saving them",
        "evidence": [
            (2161, "log", "A subsequent read was routed to a replica that had not yet applied the preceding write.", True),
            (2162, "metric", "The replica replay position lagged behind the primary commit position during the affected requests.", True),
            (2163, "config", "The application routes reads to replicas without session-level read-your-writes consistency.", True),
            (2164, "log", "The primary database rejected an update because the transaction violated a uniqueness constraint.", False),
            (2165, "metric", "The frontend browser cache served an older response for a product description.", False),
            (2166, "config", "The database uses synchronous replication for one standby node.", False),
            (2167, "log", "The application returned a stale value from its local in-memory cache.", False),
            (2168, "metric", "The primary database CPU utilization remained below 40 percent.", False),
        ],
    },

    {
        "name": "Scheduled job drift caused by timezone configuration",
        "query": "Recurring maintenance tasks execute several hours earlier than their configured local schedule",
        "evidence": [
            (2171, "config", "The scheduler interprets configured local wall-clock times as UTC without applying the intended timezone.", True),
            (2172, "log", "A recurring task fired at the UTC equivalent of its configured local time rather than the expected local hour.", True),
            (2173, "config", "The scheduler container does not receive the deployment's configured timezone setting.", True),
            (2174, "log", "The task was delayed because the previous execution had not released its distributed lock.", False),
            (2175, "metric", "The scheduler worker pool reached its maximum number of active jobs.", False),
            (2176, "config", "The maintenance job uses a retry policy with three attempts.", False),
            (2177, "log", "The database backup completed at the expected storage location.", False),
            (2178, "metric", "The host clock remained synchronized with the configured time source.", False),
        ],
    },

    {
        "name": "Object download failures caused by encryption key permissions",
        "query": "Files upload successfully but users cannot open or download them later",
        "evidence": [
            (2181, "log", "The storage service denied decryption because its execution role lacked permission to use the configured key.", True),
            (2182, "config", "The encryption key policy does not grant the application principal decrypt access.", True),
            (2183, "log", "Object retrieval failed during server-side decryption even though the object was present in the bucket.", True),
            (2184, "metric", "The storage bucket recorded an increase in failed multipart upload requests.", False),
            (2185, "log", "The upload service rejected a file because it exceeded the maximum permitted size.", False),
            (2186, "config", "The bucket blocks public access and requires authenticated requests.", False),
            (2187, "metric", "The object storage service reported normal availability.", False),
            (2188, "log", "The metadata database returned the requested document identifier.", False),
        ],
    },

    {
        "name": "Circuit breaker recovery blocked by half-open probe configuration",
        "query": "A dependency recovers but application requests continue failing for an extended period",
        "evidence": [
            (2191, "config", "The circuit breaker is configured with a very long open-state duration before it permits a trial request.", True),
            (2192, "log", "The dependency became healthy, but the breaker did not transition to HALF_OPEN to test recovery.", True),
            (2193, "metric", "No recovery probes were sent to the downstream endpoint while the circuit remained open.", True),
            (2194, "log", "The dependency continued returning connection timeouts after the recovery window.", False),
            (2195, "metric", "The downstream service CPU utilization remained elevated after restart.", False),
            (2196, "config", "The client uses exponential backoff for individual failed HTTP requests.", False),
            (2197, "log", "The load balancer removed one unhealthy dependency instance from rotation.", False),
            (2198, "metric", "The API gateway recorded a temporary increase in request volume.", False),
        ],
    },
]


# ============================================================
# DATASET VALIDATION
# ============================================================

def validate_dataset(cases):
    scenario_names = set()
    evidence_ids = set()
    relevant_counts = set()

    for case in cases:
        name = case["name"]

        assert name not in scenario_names, f"Duplicate scenario: {name}"
        scenario_names.add(name)

        assert isinstance(case["query"], str) and case["query"].strip(), (
            f"Invalid query in {name}"
        )

        assert 8 <= len(case["evidence"]) <= 10, (
            f"{name} must have 8-10 evidence records"
        )

        relevant_count = 0

        for record in case["evidence"]:
            assert len(record) == 4, f"Invalid evidence tuple in {name}"

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

        assert 2 <= relevant_count <= 4, (
            f"{name} must have between 2 and 4 relevant records; "
            f"found {relevant_count}"
        )

        relevant_counts.add(relevant_count)

    assert len(relevant_counts) > 1, (
        "The dataset should vary the number of relevant records."
    )


# ============================================================
# EVALUATION
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


def evaluate_case(case, incident_id, search_function):
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

    recall_at_5 = len(retrieved_relevant) / len(relevant_ids)
    precision_at_5 = len(retrieved_relevant) / 5

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
    results = []

    for index, case in enumerate(cases, start=1):
        incident_id = f"final-v2-{index:02d}"

        results.append({
            "name": case["name"],
            **evaluate_case(case, incident_id, search_function),
        })

    return results


# ============================================================
# REPORTING
# ============================================================

def macro_average(results, metric):
    return mean(result[metric] for result in results)


def print_comparison_table(method_results):
    print("\n" + "=" * 105)
    print("FINAL RETRIEVAL BENCHMARK V2: AGGREGATE RESULTS")
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


def print_scenario_results(method_results):
    print("\n" + "=" * 105)
    print("PER-SCENARIO RECALL@5")
    print("=" * 105)

    method_names = list(method_results)

    print(f"{'Scenario':<62}", end="")

    for method_name in method_names:
        print(f"{method_name[:12]:>13}", end="")

    print()
    print("-" * 105)

    for index, case in enumerate(FINAL_TEST_CASES):
        print(f"{case['name']:<62}", end="")

        for method_name in method_names:
            score = method_results[method_name][index]["recall_at_5"]
            print(f"{score:>13.3f}", end="")

        print()

    print("=" * 105)


def print_method_diagnostics(method_results):
    print("\n" + "=" * 105)
    print("PER-METHOD RETRIEVAL DIAGNOSTICS")
    print("=" * 105)

    for method_name, results in method_results.items():
        print(f"\n--- {method_name} ---")

        for result in results:
            if result["missed_ids"] or result["irrelevant_ids"]:
                print(f"\nScenario: {result['name']}")
                print(f"Retrieved : {result['retrieved_ids']}")
                print(f"Missed    : {result['missed_ids']}")
                print(f"Irrelevant: {result['irrelevant_ids']}")


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

    relevant_counts = sorted({
        sum(1 for _, _, _, relevant in case["evidence"] if relevant)
        for case in FINAL_TEST_CASES
    })

    print("Final V2 benchmark validation passed.")
    print(f"Scenarios          : {len(FINAL_TEST_CASES)}")
    print(f"Evidence records   : {total_evidence}")
    print(f"Relevant records   : {total_relevant}")
    print(f"Non-relevant       : {total_evidence - total_relevant}")
    print(f"Relevant counts    : {relevant_counts}")

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
    print_method_diagnostics(method_results)


if __name__ == "__main__":
    main()
