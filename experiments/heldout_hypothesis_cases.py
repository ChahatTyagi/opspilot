
"""Independent held-out cases for OpsPilot's hypothesis verifier.

These cases must not be used for prompt tuning.
They are evaluated separately from the original 24-case benchmark.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkEvidence:
    id: int
    source_type: str
    content: str


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    description: str
    hypothesis: str
    expected_verdict: str
    evidence: tuple[BenchmarkEvidence, ...]
    expected_evidence_ids: tuple[int, ...]


def build_heldout_cases() -> list[BenchmarkCase]:
    """Return 12 independently labeled held-out scenarios."""

    cases = [

        # =========================================================
        # SUPPORTED: 4 cases
        # =========================================================

        BenchmarkCase(
            case_id="SUP-09",
            category="message_acknowledgement_failure",
            description="Failed acknowledgements cause message redelivery.",
            hypothesis=(
                "Message acknowledgement failures caused messages "
                "to be repeatedly redelivered and the number of "
                "unacknowledged messages to increase."
            ),

            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    901,
                    "log",
                    "The inventory consumer successfully processed "
                    "messages, but acknowledgement requests were "
                    "rejected by the broker with an authorization "
                    "error beginning at 10:04. The consumer process "
                    "remained running."
                ),
                BenchmarkEvidence(
                    902,
                    "metric",
                    "Immediately after acknowledgement failures "
                    "began, the broker recorded repeated deliveries "
                    "of the same message IDs. Unacknowledged "
                    "messages increased from 40 to 12,600 over "
                    "six minutes."
                ),
            ),
            expected_evidence_ids=(901, 902),
        ),

        BenchmarkCase(
            case_id="SUP-10",
            category="cache_stampede",
            description="Simultaneous cache misses overload the database.",
            hypothesis=(
                "A cache stampede caused increased database query "
                "load and checkout request latency."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    911,
                    "metric",
                    "At 14:20, a frequently accessed product cache "
                    "key expired. Cache misses for that key increased "
                    "from 2 per second to 1,400 per second as "
                    "concurrent requests attempted to reload it."
                ),
                BenchmarkEvidence(
                    912,
                    "trace",
                    "Distributed traces for the affected checkout "
                    "requests show concurrent cache misses followed "
                    "by repeated database queries for the same "
                    "product records. Database query volume and "
                    "checkout latency increased during this interval."
                ),
            ),
            expected_evidence_ids=(911, 912),
        ),

        BenchmarkCase(
            case_id="SUP-11",
            category="tls_certificate_expiration",
            description="An expired upstream certificate breaks handshakes.",
            hypothesis=(
                "The upstream service's expired TLS certificate "
                "caused payment requests to fail."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    921,
                    "certificate",
                    "The payment provider certificate presented "
                    "by api.payments.internal expired at 14:00 UTC. "
                    "The affected application continued connecting "
                    "to this exact hostname after expiration."
                ),
                BenchmarkEvidence(
                    922,
                    "log",
                    "Beginning at 14:01 UTC, payment requests to "
                    "api.payments.internal failed TLS handshakes "
                    "with certificate verification errors stating "
                    "that the certificate had expired. Requests "
                    "to other upstream services continued succeeding."
                ),
            ),
            expected_evidence_ids=(921, 922),
        ),

        BenchmarkCase(
            case_id="SUP-12",
            category="worker_thread_exhaustion",
            description="Blocked workers exhaust the request thread pool.",
            hypothesis=(
                "Worker thread exhaustion caused API requests "
                "to time out while waiting for an available worker."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    931,
                    "metric",
                    "The API worker pool is configured for 64 "
                    "threads. During the incident, all 64 threads "
                    "were occupied, and the number of available "
                    "workers remained zero for five minutes."
                ),
                BenchmarkEvidence(
                    932,
                    "trace",
                    "Request traces show all occupied worker threads "
                    "blocked while waiting for responses from the "
                    "same downstream inventory service. New incoming "
                    "requests timed out while waiting in the worker "
                    "queue. The downstream response delay preceded "
                    "the worker pool exhaustion."
                ),
            ),
            expected_evidence_ids=(931, 932),
        ),

        # =========================================================
        # INSUFFICIENT: 4 cases
        # =========================================================

        BenchmarkCase(
            case_id="INS-09",
            category="unmapped_instance_metric",
            description="High CPU is observed on an instance with no request mapping.",
            hypothesis=(
                "CPU saturation on api-12 caused checkout failures."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    941,
                    "metric",
                    "Instance api-12 reported CPU utilization "
                    "of 99% during the checkout incident."
                ),
                BenchmarkEvidence(
                    942,
                    "trace",
                    "Checkout requests failed during the incident, "
                    "but the available traces do not identify which "
                    "API instance handled those requests. No evidence "
                    "maps the failing requests to api-12."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-10",
            category="cache_metric_without_request_link",
            description="A cache hit-rate decline lacks a causal link.",
            hypothesis=(
                "The decline in cache hit rate caused the checkout "
                "request failures."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    951,
                    "metric",
                    "The cluster-wide product cache hit rate "
                    "declined from 94% to 71% during the incident."
                ),
                BenchmarkEvidence(
                    952,
                    "log",
                    "Checkout requests returned intermittent "
                    "HTTP 500 responses during the same period. "
                    "No request-level cache traces, database "
                    "query measurements, or cache error records "
                    "are available."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-11",
            category="certificate_event_without_failure_trace",
            description="Certificate renewal overlaps with errors.",
            hypothesis=(
                "The certificate renewal process caused the "
                "checkout service outage."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    961,
                    "event",
                    "The certificate renewal job ran at 16:00 UTC "
                    "and reported successful completion."
                ),
                BenchmarkEvidence(
                    962,
                    "metric",
                    "Checkout error rate increased between "
                    "15:55 and 16:10 UTC. No TLS handshake "
                    "failures, certificate validation errors, "
                    "or affected connection records were captured."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-12",
            category="replica_lag_without_request_mapping",
            description="Replica lag is observed without request mapping.",
            hypothesis=(
                "Database replica lag caused checkout requests "
                "to return stale data."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    971,
                    "metric",
                    "The read replica experienced replication "
                    "lag of approximately 18 seconds during "
                    "the checkout incident."
                ),
                BenchmarkEvidence(
                    972,
                    "trace",
                    "Checkout requests returned inconsistent "
                    "product information. Available traces do "
                    "not identify whether the affected reads "
                    "were served by the primary database or "
                    "the read replica."
                ),
            ),
            expected_evidence_ids=(),
        ),

        # =========================================================
        # CONTRADICTED: 4 cases
        # =========================================================

        BenchmarkCase(
            case_id="CON-09",
            category="consumer_remained_healthy",
            description="Consumer health contradicts a crash hypothesis.",
            hypothesis=(
                "The inventory consumer crashed and caused "
                "the inventory queue backlog."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    981,
                    "metric",
                    "The inventory consumer process maintained "
                    "continuous uptime throughout the incident. "
                    "Its health checks succeeded every five seconds, "
                    "and no process restart or crash was recorded."
                ),
                BenchmarkEvidence(
                    982,
                    "metric",
                    "The inventory consumer continued processing "
                    "and acknowledging messages at its normal "
                    "baseline rate throughout the relevant interval."
                ),
            ),
            expected_evidence_ids=(981, 982),
        ),

        BenchmarkCase(
            case_id="CON-10",
            category="tls_certificate_valid",
            description="Valid certificate and successful handshakes.",
            hypothesis=(
                "An expired TLS certificate caused payment "
                "requests to fail."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    991,
                    "certificate",
                    "The certificate presented by the payment "
                    "provider remained valid until 30 days after "
                    "the incident. Its validity period covered "
                    "the entire incident."
                ),
                BenchmarkEvidence(
                    992,
                    "log",
                    "TLS handshake logs for the affected payment "
                    "hostname show successful certificate "
                    "verification throughout the incident. "
                    "No certificate expiration or validation "
                    "errors were recorded."
                ),
            ),
            expected_evidence_ids=(991, 992),
        ),

        BenchmarkCase(
            case_id="CON-11",
            category="cache_capacity_available",
            description="Cache memory metrics rule out memory exhaustion.",
            hypothesis=(
                "Cache memory exhaustion caused the product "
                "lookup failures."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    1001,
                    "metric",
                    "The cache cluster used 38% of its configured "
                    "memory capacity throughout the incident. "
                    "Memory usage remained below the configured "
                    "eviction threshold."
                ),
                BenchmarkEvidence(
                    1002,
                    "metric",
                    "The cache recorded zero memory-pressure "
                    "evictions and no allocation failures during "
                    "the incident."
                ),
            ),
            expected_evidence_ids=(1001, 1002),
        ),

        BenchmarkCase(
            case_id="CON-12",
            category="worker_pool_not_exhausted",
            description="Worker and queue metrics rule out exhaustion.",
            hypothesis=(
                "API worker thread exhaustion caused incoming "
                "requests to time out."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    1011,
                    "metric",
                    "The API worker pool supports 64 concurrent "
                    "threads. During the entire incident, active "
                    "worker usage remained between 18 and 26, "
                    "with at least 38 workers available."
                ),
                BenchmarkEvidence(
                    1012,
                    "metric",
                    "The API worker queue remained empty throughout "
                    "the incident. No requests timed out while "
                    "waiting for an available worker."
                ),
            ),
            expected_evidence_ids=(1011, 1012),
        ),
    ]

    validate_heldout_cases(cases)
    return cases


def validate_heldout_cases(
    cases: list[BenchmarkCase],
) -> None:
    """Validate held-out labels, evidence and dataset balance."""

    if len(cases) != 12:
        raise ValueError(
            f"Expected 12 held-out cases, received {len(cases)}."
        )

    seen_case_ids: set[str] = set()
    seen_evidence_ids: set[int] = set()

    verdict_counts = {
        "supported": 0,
        "insufficient": 0,
        "contradicted": 0,
    }

    for case in cases:
        if case.case_id in seen_case_ids:
            raise ValueError(
                f"Duplicate case ID: {case.case_id}"
            )

        seen_case_ids.add(case.case_id)

        if case.expected_verdict not in verdict_counts:
            raise ValueError(
                f"Invalid verdict in {case.case_id}."
            )

        verdict_counts[case.expected_verdict] += 1

        if not case.hypothesis.strip():
            raise ValueError(
                f"Empty hypothesis in {case.case_id}."
            )

        if not case.evidence:
            raise ValueError(
                f"No evidence in {case.case_id}."
            )

        evidence_ids = [item.id for item in case.evidence]

        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(
                f"Duplicate evidence IDs in {case.case_id}."
            )

        overlap = seen_evidence_ids.intersection(evidence_ids)

        if overlap:
            raise ValueError(
                f"Evidence IDs reused in {case.case_id}: {overlap}"
            )

        seen_evidence_ids.update(evidence_ids)

        if not set(case.expected_evidence_ids).issubset(
            set(evidence_ids)
        ):
            raise ValueError(
                f"Expected evidence IDs missing in {case.case_id}."
            )

        if (
            case.expected_verdict == "supported"
            and not case.expected_evidence_ids
        ):
            raise ValueError(
                f"{case.case_id} needs supporting evidence IDs."
            )

        if (
            case.expected_verdict == "insufficient"
            and case.expected_evidence_ids
        ):
            raise ValueError(
                f"{case.case_id} must not have expected evidence IDs."
            )

        if (
            case.expected_verdict == "contradicted"
            and not case.expected_evidence_ids
        ):
            raise ValueError(
                f"{case.case_id} needs contradicting evidence IDs."
            )

        for item in case.evidence:
            if not item.content.strip():
                raise ValueError(
                    f"Empty evidence content in {case.case_id}."
                )

    if verdict_counts != {
        "supported": 4,
        "insufficient": 4,
        "contradicted": 4,
    }:
        raise ValueError(
            f"Incorrect verdict distribution: {verdict_counts}"
        )
