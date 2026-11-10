
from experiments.evaluate_keyword_retrieval import (
    CASES as TRAINING_CASES,
    STOP_WORDS,
    QUERY_EXPANSIONS,
    build_evidence_objects,
    evaluate_case,
    search_without_stop_words,
    search_exact_tokens,
    search_stemmed_tokens,
    search_with_query_expansion,
    validate_dataset,
)
from app.investigation_tools import search_incident_evidence


# Separate scenarios that were not used to design QUERY_EXPANSIONS.
HELD_OUT_CASES = [
    {
        "name": "Cache eviction and hit-rate degradation",
        "query": "Why are cached product lookups becoming slower?",
        "evidence": [
            (101, "metric", "Cache hit ratio dropped from 96% to 41% over twenty minutes."),
            (102, "log", "Redis eviction events increased sharply after the cache reached its memory limit."),
            (103, "trace", "Product lookup requests repeatedly fetch records from the primary database."),
            (104, "metric", "Database read operations increased by 70% during the same period."),
            (105, "log", "The nightly database backup completed successfully."),
            (106, "deployment", "The product catalogue page received a visual redesign."),
            (107, "metric", "Payment service CPU utilization remained stable."),
            (108, "trace", "Requests spend additional time waiting for cache population to complete."),
        ],
        "relevant_ids": {101, 102, 103, 104, 108},
    },
    {
        "name": "TLS certificate expiration",
        "query": "Why are external clients unable to establish secure connections?",
        "evidence": [
            (111, "log", "TLS handshake failed because the presented certificate has expired."),
            (112, "metric", "Failed HTTPS connection attempts increased across external integrations."),
            (113, "log", "Certificate validation rejected the server identity during negotiation."),
            (114, "deployment", "A new certificate was not installed before the previous certificate expired."),
            (115, "metric", "Internal CPU and memory utilization remained within normal limits."),
            (116, "log", "The reporting dashboard loaded successfully over HTTPS."),
            (117, "deployment", "A footer style was changed on the public website."),
            (118, "trace", "Outbound requests terminate during SSL verification."),
        ],
        "relevant_ids": {111, 112, 113, 114, 118},
    },
    {
        "name": "Kubernetes pod scheduling failures",
        "query": "Why are application replicas remaining pending instead of starting?",
        "evidence": [
            (121, "metric", "Four application pods remain in Pending state."),
            (122, "log", "The scheduler cannot place pods because available CPU requests exceed node capacity."),
            (123, "event", "Pod scheduling failed with an insufficient memory resource warning."),
            (124, "metric", "Cluster node utilization is above 95% for CPU."),
            (125, "log", "The container registry completed an image cleanup successfully."),
            (126, "deployment", "The documentation service received a new theme."),
            (127, "trace", "Service startup probes have not executed because containers were never scheduled."),
            (128, "metric", "The database connection pool remains healthy."),
        ],
        "relevant_ids": {121, 122, 123, 124, 127},
    },
    {
        "name": "Message broker authentication rejection",
        "query": "Why can event producers no longer publish messages to the broker?",
        "evidence": [
            (131, "log", "Kafka rejected producer requests because SASL authentication credentials were invalid."),
            (132, "metric", "Producer authorization errors increased after credential rotation."),
            (133, "deployment", "The broker password was rotated without updating the producer secret."),
            (134, "trace", "Publish operations terminate during broker authentication."),
            (135, "log", "Consumer lag remained low for the events already accepted."),
            (136, "metric", "The analytics database disk utilization is stable."),
            (137, "deployment", "The monitoring dashboard layout was updated."),
            (138, "log", "Producer retries continue after receiving authentication failure responses."),
        ],
        "relevant_ids": {131, 132, 133, 134, 138},
    },
    {
        "name": "Object storage upload failures",
        "query": "Why are file uploads being rejected by cloud storage?",
        "evidence": [
            (141, "log", "Object storage returned AccessDenied for upload requests."),
            (142, "metric", "Upload failure rate increased immediately after an IAM policy update."),
            (143, "deployment", "The application role lost permission to perform PutObject operations."),
            (144, "trace", "Upload requests fail during authorization before object data is transferred."),
            (145, "metric", "Available storage capacity remains above 60%."),
            (146, "log", "Existing file downloads continue to succeed."),
            (147, "deployment", "The file browser interface received a colour update."),
            (148, "trace", "The storage SDK reports an authorization exception for new uploads."),
        ],
        "relevant_ids": {141, 142, 143, 144, 148},
    },
]


def main():
    validate_dataset(HELD_OUT_CASES)

    # Guard against accidental reuse of the original scenarios.
    training_names = {case["name"] for case in TRAINING_CASES}
    held_out_names = {case["name"] for case in HELD_OUT_CASES}

    if training_names & held_out_names:
        raise ValueError("Held-out scenarios overlap with training scenarios.")

    search_methods = {
        "Baseline": search_incident_evidence,
        "Stop-word removal": search_without_stop_words,
        "Exact token matching": search_exact_tokens,
        "Porter stemming": search_stemmed_tokens,
        "Query expansion": search_with_query_expansion,
    }

    all_results = {}

    print("Held-out dataset validation successful.")
    print(f"Training scenarios: {len(TRAINING_CASES)}")
    print(f"Held-out scenarios: {len(HELD_OUT_CASES)}")
    print(
        "Held-out evidence records:",
        sum(len(case["evidence"]) for case in HELD_OUT_CASES),
    )

    for method_name, search_function in search_methods.items():
        results = []

        print(f"\n========== {method_name.upper()} ==========")

        for index, case in enumerate(HELD_OUT_CASES, start=1):
            # IDs are independent of the original training scenarios.
            incident_id = 100 + index

            result = evaluate_case(
                case,
                incident_id,
                search_function,
            )

            results.append(result)

            print(f"\nCase {index}: {result['name']}")
            print(f"Retrieved IDs: {result['retrieved_ids']}")
            print(f"Missed relevant IDs: {result['missed_ids']}")
            print(f"Irrelevant retrieved IDs: {result['irrelevant_ids']}")
            print(f"Recall@5: {result['recall_at_5']:.3f}")
            print(f"Precision@5: {result['precision_at_5']:.3f}")
            print(f"MRR: {result['mrr']:.3f}")

        all_results[method_name] = results

        mean_recall = sum(
            result["recall_at_5"] for result in results
        ) / len(results)

        mean_precision = sum(
            result["precision_at_5"] for result in results
        ) / len(results)

        mean_mrr = sum(
            result["mrr"] for result in results
        ) / len(results)

        print(f"\n{method_name} summary:")
        print(f"Mean Recall@5: {mean_recall:.3f}")
        print(f"Mean Precision@5: {mean_precision:.3f}")
        print(f"Mean MRR: {mean_mrr:.3f}")

    print("\n========== HELD-OUT COMPARISON ==========")
    print(
        f"{'Metric':<20}"
        f"{'Baseline':>12}"
        f"{'Stop-word':>12}"
        f"{'Exact':>12}"
        f"{'Stemming':>12}"
        f"{'Expansion':>12}"
    )

    for metric, key in [
        ("Recall@5", "recall_at_5"),
        ("Precision@5", "precision_at_5"),
        ("MRR", "mrr"),
    ]:
        print(
            f"{metric:<20}"
            + "".join(
                f"{sum(r[key] for r in all_results[name]) / len(all_results[name]):>12.3f}"
                for name in search_methods
            )
        )


if __name__ == "__main__":
    main()
