
"""
OpsPilot Topology-Aware Retrieval Benchmark V2 dataset.

This module extends the existing V3 benchmark without modifying it.

Original evidence:
    20 scenarios x 8 records = 160 records.
    Original V3 relevance labels are imported unchanged.

Synthetic topology evidence:
    20 scenarios x 5 trace records = 100 records.

Per scenario:
    1 DIRECT trace span
    1 CONTRIBUTING trace span
    1 connected IRRELEVANT trace span
    2 unrelated IRRELEVANT trace spans

The trace relevance labels are assigned independently of topology.
"""

import json
from types import SimpleNamespace

from experiments.evaluate_final_retrieval_v2 import FINAL_TEST_CASES
from experiments.retrieval_v3_labels import (
    EVIDENCE_LABELS,
    DIRECT_RELEVANT_IDS,
    DIAGNOSTIC_RELEVANT_IDS,
    validate_labels,
)


TOP_K = 5

TRACE_LABELS = {
    "DIRECT",
    "CONTRIBUTING",
    "CORROBORATING",
    "DIFFERENTIAL",
    "IRRELEVANT",
}

# Synthetic service names and trace descriptions.
# These are benchmark fixtures, not claims about production services.
SCENARIO_TRACE_SPECS = [
    {
        "target": "checkout-api",
        "upstream": "edge-proxy",
        "dependency": "payment-gateway",
        "unrelated": ["notification-api", "catalog-worker"],
        "direct_span": "certificate_validation",
        "direct_message": "TLS certificate expired during payment gateway connection",
        "target_span": "checkout_request",
        "target_message": "Checkout request failed while establishing a secure payment connection",
    },
    {
        "target": "catalog-api",
        "upstream": "edge-proxy",
        "dependency": "product-cache",
        "unrelated": ["report-worker", "email-service"],
        "direct_span": "heap_reclamation",
        "direct_message": "Full garbage collection caused a multi-second stop-the-world pause",
        "target_span": "catalog_request",
        "target_message": "Catalog request latency increased during runtime pause",
    },
    {
        "target": "identity-service",
        "upstream": "auth-gateway",
        "dependency": "token-store",
        "unrelated": ["scheduler-api", "catalog-worker"],
        "direct_span": "token_clock_validation",
        "direct_message": "Token issue timestamp was ahead of the identity verifier clock",
        "target_span": "login_request",
        "target_message": "Valid login session rejected during token validation",
    },
    {
        "target": "upload-api",
        "upstream": "edge-proxy",
        "dependency": "object-storage",
        "unrelated": ["document-worker", "billing-api"],
        "direct_span": "request_body_rejection",
        "direct_message": "Ingress rejected oversized multipart request with HTTP 413",
        "target_span": "upload_request",
        "target_message": "Large document upload failed before application handler execution",
    },
    {
        "target": "inventory-api",
        "upstream": "warehouse-api",
        "dependency": "stock-cache",
        "unrelated": ["search-api", "notification-worker"],
        "direct_span": "cache_invalidation",
        "direct_message": "Inventory cache entry remained present after stock mutation event",
        "target_span": "inventory_read",
        "target_message": "Inventory response returned a value older than the latest warehouse update",
    },
    {
        "target": "orders-db",
        "upstream": "order-api",
        "dependency": "storage-layer",
        "unrelated": ["analytics-db", "identity-service"],
        "direct_span": "checkpoint_flush",
        "direct_message": "Checkpoint flush saturated storage and blocked foreground writes",
        "target_span": "order_write",
        "target_message": "Order transaction waited for database checkpoint storage activity",
    },
    {
        "target": "reporting-api",
        "upstream": "scheduler-api",
        "dependency": "transaction-db",
        "unrelated": ["billing-api", "notification-worker"],
        "direct_span": "timezone_conversion",
        "direct_message": "Reporting timestamp conversion assigned midnight transaction to incorrect day",
        "target_span": "report_generation",
        "target_message": "Daily report omitted transactions near the local midnight boundary",
    },
    {
        "target": "notification-worker",
        "upstream": "account-api",
        "dependency": "smtp-relay",
        "unrelated": ["email-template-api", "catalog-worker"],
        "direct_span": "smtp_greylisting",
        "direct_message": "Remote SMTP exchanger deferred message delivery with greylisting response",
        "target_span": "notification_delivery",
        "target_message": "Notification remained queued while waiting for SMTP retry",
    },
    {
        "target": "customer-api",
        "upstream": "edge-proxy",
        "dependency": "customer-db",
        "unrelated": ["admin-api", "search-api"],
        "direct_span": "forwarded_host_validation",
        "direct_message": "Application rejected duplicate forwarded host metadata from proxy",
        "target_span": "customer_request",
        "target_message": "Customer API request failed after passing through edge proxy",
    },
    {
        "target": "task-worker",
        "upstream": "event-broker",
        "dependency": "task-db",
        "unrelated": ["email-worker", "report-worker"],
        "direct_span": "visibility_timeout",
        "direct_message": "Task message was redelivered after visibility timeout expired before acknowledgement",
        "target_span": "task_execution",
        "target_message": "Background task identifier appeared repeatedly in worker execution history",
    },
    {
        "target": "service-discovery",
        "upstream": "edge-proxy",
        "dependency": "dns-resolver",
        "unrelated": ["monitoring-agent", "catalog-worker"],
        "direct_span": "dns_cache_lookup",
        "direct_message": "Resolver returned cached address after endpoint migration",
        "target_span": "service_connection",
        "target_message": "Service connection continued using the previous endpoint address",
    },
    {
        "target": "payment-api",
        "upstream": "checkout-api",
        "dependency": "payment-provider",
        "unrelated": ["billing-reconciliation", "notification-worker"],
        "direct_span": "charge_creation",
        "direct_message": "Payment retry created a second charge because request idempotency key was not enforced",
        "target_span": "payment_request",
        "target_message": "Repeated payment submission created duplicate downstream charge attempts",
    },
    {
        "target": "media-worker",
        "upstream": "job-scheduler",
        "dependency": "node-runtime",
        "unrelated": ["backup-worker", "report-worker"],
        "direct_span": "pod_eviction",
        "direct_message": "Kubelet evicted worker pod after ephemeral storage crossed node threshold",
        "target_span": "media_processing",
        "target_message": "Media processing worker disappeared during temporary file activity",
    },
    {
        "target": "search-api",
        "upstream": "catalog-api",
        "dependency": "search-index",
        "unrelated": ["recommendation-api", "notification-worker"],
        "direct_span": "analyzer_tokenization",
        "direct_message": "Indexed and queried terms used incompatible analyzer tokenization",
        "target_span": "search_request",
        "target_message": "Search request returned no matching documents despite indexed records",
    },
    {
        "target": "webhook-consumer",
        "upstream": "event-gateway",
        "dependency": "partner-api",
        "unrelated": ["notification-worker", "catalog-worker"],
        "direct_span": "event_deduplication",
        "direct_message": "Repeated webhook event identifier was processed without deduplication",
        "target_span": "webhook_processing",
        "target_message": "Webhook callback was processed more than once after sender retry",
    },
    {
        "target": "internal-api",
        "upstream": "service-mesh",
        "dependency": "certificate-authority",
        "unrelated": ["external-api", "search-api"],
        "direct_span": "hostname_verification",
        "direct_message": "TLS peer certificate did not contain requested hostname in subject alternative names",
        "target_span": "internal_request",
        "target_message": "Internal service request failed during secure connection establishment",
    },
    {
        "target": "customer-db",
        "upstream": "customer-api",
        "dependency": "read-replica",
        "unrelated": ["analytics-db", "billing-api"],
        "direct_span": "replica_read",
        "direct_message": "Read request reached replica before preceding primary write was replayed",
        "target_span": "customer_read",
        "target_message": "Customer read returned stale state immediately after a successful write",
    },
    {
        "target": "maintenance-scheduler",
        "upstream": "control-api",
        "dependency": "job-worker",
        "unrelated": ["report-scheduler", "notification-worker"],
        "direct_span": "schedule_timezone",
        "direct_message": "Scheduler interpreted configured local wall-clock time as UTC",
        "target_span": "maintenance_job",
        "target_message": "Recurring maintenance job executed earlier than its configured local schedule",
    },
    {
        "target": "file-storage-api",
        "upstream": "document-api",
        "dependency": "key-manager",
        "unrelated": ["backup-storage", "catalog-worker"],
        "direct_span": "decryption_authorization",
        "direct_message": "Storage execution role lacked permission to decrypt object with configured key",
        "target_span": "file_download",
        "target_message": "File download failed during server-side decryption although object existed",
    },
    {
        "target": "recommendation-api",
        "upstream": "edge-proxy",
        "dependency": "recommendation-engine",
        "unrelated": ["search-api", "notification-worker"],
        "direct_span": "circuit_breaker_probe",
        "direct_message": "Circuit breaker remained open and did not send a half-open recovery probe",
        "target_span": "recommendation_request",
        "target_message": "Recommendation requests continued failing after downstream recovery",
    },
]


def _trace_record(
    *,
    evidence_id,
    incident_id,
    trace_id,
    service_name,
    span_id,
    parent_span_id=None,
    span_name="request",
    status_code=0,
    status_message="",
):
    """Create a normalized trace record accepted by app.telemetry."""

    record = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": f"{trace_id:032x}",
        "span_id": f"{span_id:016x}",
        "parent_span_id": (
            f"{parent_span_id:016x}"
            if parent_span_id is not None
            else None
        ),
        "service_name": service_name,
        "span_name": span_name,
        "span_kind": 1,
        "start_time_unix_nano": 1_000_000,
        "end_time_unix_nano": 6_000_000,
        "duration_ms": 5.0,
        "status_code": status_code,
        "status_message": status_message,
        "attributes": {},
        "events": [],
    }

    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        source_type="trace",
        content=json.dumps(record, separators=(",", ":")),
    )


def _text_record(evidence_id, incident_id, source_type, content):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        source_type=source_type,
        content=content,
    )


def build_dataset():
    """
    Build 20 cases containing original V3 evidence plus 5 trace records.

    Original V3 records and labels are reused without modification.
    Synthetic trace IDs start at 22001.
    """

    if len(FINAL_TEST_CASES) != 20:
        raise ValueError("Expected exactly 20 original V3 scenarios.")

    if len(SCENARIO_TRACE_SPECS) != len(FINAL_TEST_CASES):
        raise ValueError("Every V3 scenario must have one topology spec.")

    cases = []

    for index, (original_case, spec) in enumerate(
        zip(FINAL_TEST_CASES, SCENARIO_TRACE_SPECS)
    ):
        incident_id = 9001 + index
        base_id = 22001 + (index * 10)

        upstream_id = base_id
        target_id = base_id + 1
        dependency_id = base_id + 2
        unrelated_one_id = base_id + 3
        unrelated_two_id = base_id + 4

        trace_id = 800000 + index

        # Original evidence is copied into objects for the retriever.
        original_evidence = [
            _text_record(
                evidence_id,
                incident_id,
                source_type,
                content,
            )
            for evidence_id, source_type, content, _ in original_case["evidence"]
        ]

        # Connected trace chain:
        # upstream -> target -> dependency
        connected_traces = [
            _trace_record(
                evidence_id=upstream_id,
                incident_id=incident_id,
                trace_id=trace_id,
                service_name=spec["upstream"],
                span_id=1,
                span_name="incoming_request",
            ),
            _trace_record(
                evidence_id=target_id,
                incident_id=incident_id,
                trace_id=trace_id,
                service_name=spec["target"],
                span_id=2,
                parent_span_id=1,
                span_name=spec["target_span"],
                status_code=2,
                status_message=spec["target_message"],
            ),
            _trace_record(
                evidence_id=dependency_id,
                incident_id=incident_id,
                trace_id=trace_id,
                service_name=spec["dependency"],
                span_id=3,
                parent_span_id=2,
                span_name=spec["direct_span"],
                status_code=2,
                status_message=spec["direct_message"],
            ),
        ]

        # Separate traces deliberately have no connection to the target.
        unrelated_traces = [
            _trace_record(
                evidence_id=unrelated_one_id,
                incident_id=incident_id,
                trace_id=trace_id + 1000,
                service_name=spec["unrelated"][0],
                span_id=4,
                span_name="routine_background_operation",
            ),
            _trace_record(
                evidence_id=unrelated_two_id,
                incident_id=incident_id,
                trace_id=trace_id + 2000,
                service_name=spec["unrelated"][1],
                span_id=5,
                span_name="scheduled_maintenance",
            ),
        ]

        trace_evidence = connected_traces + unrelated_traces
        evidence = original_evidence + trace_evidence

        trace_labels = {
            upstream_id: "IRRELEVANT",
            target_id: "CONTRIBUTING",
            dependency_id: "DIRECT",
            unrelated_one_id: "IRRELEVANT",
            unrelated_two_id: "IRRELEVANT",
        }

        labels = {
            evidence_id: EVIDENCE_LABELS[evidence_id]
            for evidence_id, _, _, _ in original_case["evidence"]
        }
        labels.update(trace_labels)

        service_anchored_query = (
            f"{original_case['query']} "
            f"Investigate service {spec['target']} and its dependencies."
        )

        cases.append(
            {
                "name": original_case["name"],
                "incident_id": incident_id,
                "symptom_query": original_case["query"],
                "service_anchored_query": service_anchored_query,
                "target_service": spec["target"],
                "connected_services": [
                    spec["upstream"],
                    spec["target"],
                    spec["dependency"],
                ],
                "unrelated_services": list(spec["unrelated"]),
                "evidence": evidence,
                "labels": labels,
                "trace_ids": {
                    "upstream": upstream_id,
                    "target": target_id,
                    "dependency": dependency_id,
                    "unrelated": [
                        unrelated_one_id,
                        unrelated_two_id,
                    ],
                },
            }
        )

    return cases


def get_relevant_ids(case, perspective):
    """Return independently assigned relevant evidence IDs."""

    if perspective == "direct":
        relevant_labels = {"DIRECT"}
    elif perspective == "diagnostic":
        relevant_labels = {
            "DIRECT",
            "CONTRIBUTING",
            "CORROBORATING",
            "DIFFERENTIAL",
        }
    else:
        raise ValueError(
            "perspective must be either 'direct' or 'diagnostic'."
        )

    return {
        evidence_id
        for evidence_id, label in case["labels"].items()
        if label in relevant_labels
    }


def validate_dataset(cases=None):
    """Validate V3 preservation, synthetic traces, labels, and topology."""

    validate_labels()

    if cases is None:
        cases = build_dataset()

    if len(cases) != 20:
        raise ValueError("V2 must contain exactly 20 scenarios.")

    all_evidence_ids = set()
    total_trace_records = 0

    for case in cases:
        name = case["name"]
        evidence = case["evidence"]
        labels = case["labels"]

        if not case["symptom_query"].strip():
            raise ValueError(f"Empty symptom query in {name}.")

        if not case["service_anchored_query"].strip():
            raise ValueError(f"Empty service-anchored query in {name}.")

        if case["target_service"] not in case["service_anchored_query"]:
            raise ValueError(
                f"Target service missing from anchored query in {name}."
            )

        scenario_ids = set()

        for item in evidence:
            if not isinstance(item.id, int) or isinstance(item.id, bool):
                raise ValueError("Evidence IDs must be integers.")

            if item.id in scenario_ids or item.id in all_evidence_ids:
                raise ValueError(f"Duplicate evidence ID: {item.id}")

            scenario_ids.add(item.id)
            all_evidence_ids.add(item.id)

            if item.incident_id != case["incident_id"]:
                raise ValueError(
                    f"Incorrect incident ID for evidence {item.id}."
                )

            if not isinstance(item.content, str) or not item.content.strip():
                raise ValueError(f"Empty evidence content: {item.id}.")

            if item.source_type == "trace":
                total_trace_records += 1

                try:
                    record = json.loads(item.content)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid trace JSON for evidence {item.id}."
                    ) from exc

                if record.get("schema_version") != 1:
                    raise ValueError(f"Invalid trace schema for {item.id}.")

                if record.get("signal") != "trace":
                    raise ValueError(f"Invalid trace signal for {item.id}.")

                if not record.get("service_name"):
                    raise ValueError(f"Missing service name for {item.id}.")

        if set(labels) != scenario_ids:
            raise ValueError(
                f"Label IDs do not match evidence IDs in {name}."
            )

        if set(labels.values()) - TRACE_LABELS:
            raise ValueError(f"Invalid relevance label in {name}.")

        # Original 8 V3 records must retain their exact labels.
        original_ids = {
            evidence_id
            for evidence_id, _, _, _ in next(
                case_data
                for case_data in FINAL_TEST_CASES
                if case_data["name"] == name
            )["evidence"]
        }

        for evidence_id in original_ids:
            if labels[evidence_id] != EVIDENCE_LABELS[evidence_id]:
                raise ValueError(
                    f"Original V3 label changed for evidence {evidence_id}."
                )

        # Exactly five synthetic traces per scenario.
        trace_items = [
            item for item in evidence if item.source_type == "trace"
        ]

        if len(trace_items) != 5:
            raise ValueError(
                f"{name} must contain exactly 5 synthetic traces."
            )

        # Topology must not define relevance automatically.
        trace_labels = {
            evidence_id: labels[evidence_id]
            for evidence_id in case["trace_ids"].values()
            if isinstance(evidence_id, int)
        }

        if trace_labels.get(case["trace_ids"]["upstream"]) != "IRRELEVANT":
            raise ValueError("Routine connected upstream trace must be irrelevant.")

        if trace_labels.get(case["trace_ids"]["target"]) != "CONTRIBUTING":
            raise ValueError("Target symptom trace must be contributing.")

        if trace_labels.get(case["trace_ids"]["dependency"]) != "DIRECT":
            raise ValueError("Root-cause dependency trace must be direct.")

        if any(
            labels[evidence_id] != "IRRELEVANT"
            for evidence_id in case["trace_ids"]["unrelated"]
        ):
            raise ValueError("Unrelated service traces must be irrelevant.")

        if not get_relevant_ids(case, "direct"):
            raise ValueError(f"No direct evidence in {name}.")

        if not get_relevant_ids(case, "diagnostic"):
            raise ValueError(f"No diagnostic evidence in {name}.")

    if len(all_evidence_ids) != 260:
        raise ValueError(
            f"Expected 260 total evidence records, got {len(all_evidence_ids)}."
        )

    if total_trace_records != 100:
        raise ValueError(
            f"Expected 100 trace records, got {total_trace_records}."
        )

    # Every original V3 evidence ID must still exist.
    original_ids = set(EVIDENCE_LABELS)

    if not original_ids.issubset(all_evidence_ids):
        raise ValueError("Some original V3 evidence records are missing.")

    return True


if __name__ == "__main__":
    dataset = build_dataset()
    validate_dataset(dataset)

    print("Topology retrieval V2 dataset validation passed.")
    print(f"Scenarios          : {len(dataset)}")
    print("Original evidence  : 160")
    print("Synthetic traces   : 100")
    print("Total evidence     : 260")
    print("Trace records      : 5 per scenario")
    print("V3 labels          : preserved")
