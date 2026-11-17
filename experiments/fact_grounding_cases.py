
from dataclasses import dataclass
import re
from typing import Sequence


@dataclass(frozen=True)
class EvidenceCase:
    id: int
    source_type: str
    content: str


@dataclass(frozen=True)
class ExpectedFact:
    match_terms: tuple[str, ...]
    required_patterns: tuple[str, ...]
    supporting_evidence_ids: tuple[int, ...]
    forbidden_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactGroundingCase:
    case_id: str
    title: str
    description: str
    service: str
    environment: str
    severity: str
    evidence: tuple[EvidenceCase, ...]
    expected_facts: tuple[ExpectedFact, ...]


def build_fact_grounding_cases() -> Sequence[FactGroundingCase]:
    """Return the manually labeled Fact Grounding evaluation dataset."""

    return (
        # FG-01: Payment failure rate
        FactGroundingCase(
            case_id="FG-01",
            title="Payment failure rate increased",
            description="The payment service is experiencing failures.",
            service="payment-service",
            environment="production",
            severity="high",
            evidence=(
                EvidenceCase(
                    1001,
                    "application_log",
                    "Payment failure rate increased from 2% to 8% "
                    "between 10:00 and 10:15 UTC.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("payment", "failure"),
                    required_patterns=(r"2\s*%", r"8\s*%"),
                    supporting_evidence_ids=(1001,),
                ),
            ),
        ),

        # FG-02: API latency and normal baseline
        FactGroundingCase(
            case_id="FG-02",
            title="High API latency",
            description="The API is responding more slowly than usual.",
            service="api-gateway",
            environment="production",
            severity="medium",
            evidence=(
                EvidenceCase(
                    1002,
                    "metrics",
                    "API gateway p95 latency reached 500 ms "
                    "at 11:20 UTC. The normal p95 latency is 120 ms.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("latency", "500"),
                    required_patterns=(r"\b500\s*(ms|milliseconds)\b",),
                    supporting_evidence_ids=(1002,),
                ),
                ExpectedFact(
                    match_terms=("normal", "latency", "120"),
                    required_patterns=(r"\b120\s*(ms|milliseconds)\b",),
                    supporting_evidence_ids=(1002,),
                ),
            ),
        ),

        # FG-03: No database connection failures
        FactGroundingCase(
            case_id="FG-03",
            title="Database connection monitoring",
            description="The database connection monitor reported its status.",
            service="database-service",
            environment="production",
            severity="low",
            evidence=(
                EvidenceCase(
                    1003,
                    "monitoring_log",
                    "No database connection failures were recorded "
                    "during the 15-minute monitoring window.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("database", "connection"),
                    required_patterns=(
                        r"\bno\b|\bzero\b",
                        r"\bfailures?\b",
                    ),
                    supporting_evidence_ids=(1003,),
                    forbidden_patterns=(
                        r"^(?!.*\b(?:no|zero)\b).*"
                        r"\b(?:database\s+)?connection\s+failures?\s+"
                        r"(?:occurred|were recorded|were detected)\b",
                        r"^(?!.*\b(?:no|zero)\b).*"
                        r"\bdatabase\s+failures?\s+"
                        r"(?:occurred|were recorded|were detected)\b",
                    ),
                ),
            ),
        ),

        # FG-04: Worker restart timestamp
        FactGroundingCase(
            case_id="FG-04",
            title="Worker restart recorded",
            description="A worker restart was reported.",
            service="background-worker",
            environment="production",
            severity="medium",
            evidence=(
                EvidenceCase(
                    1004,
                    "system_log",
                    "Worker process restarted at 10:42 UTC "
                    "after receiving a termination signal.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("worker", "restarted"),
                    required_patterns=(r"10:42\s*UTC",),
                    supporting_evidence_ids=(1004,),
                ),
            ),
        ),

        # FG-05: Recommendation versus confirmed action
        FactGroundingCase(
            case_id="FG-05",
            title="Suggested service restart",
            description="An investigation note contains a suggested action.",
            service="notification-service",
            environment="production",
            severity="low",
            evidence=(
                EvidenceCase(
                    1005,
                    "investigation_note",
                    "Recommendation: consider restarting the "
                    "notification service if the issue persists. "
                    "No restart has been confirmed.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("notification", "restart"),
                    required_patterns=(
                        r"consider|recommend|suggest",
                        r"if the issue persists|if .* persists",
                    ),
                    supporting_evidence_ids=(1005,),
                    forbidden_patterns=(
                        r"\b(?:was|has been|had been|is)\s+restarted\b",
                        r"\brestart(?:ed)?\s+(?:was|has been)\s+confirmed\b",
                    ),
                ),
                ExpectedFact(
                    match_terms=("restart", "confirmed"),
                    required_patterns=(
                        r"\bno restart has been confirmed\b"
                        r"|\brestart has not been confirmed\b",
                    ),
                    supporting_evidence_ids=(1005,),
                ),
            ),
        ),

        # FG-06: Deployment followed by errors
        FactGroundingCase(
            case_id="FG-06",
            title="Deployment followed by errors",
            description="Errors were reported shortly after deployment.",
            service="order-service",
            environment="production",
            severity="high",
            evidence=(
                EvidenceCase(
                    1006,
                    "deployment_log",
                    "Version 2.4.1 deployment completed at 10:00 UTC.",
                ),
                EvidenceCase(
                    1007,
                    "application_log",
                    "Order processing errors first appeared at "
                    "10:03 UTC.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("deployment",),
                    required_patterns=(
                        r"2\.4\.1",
                        r"10:00\s*UTC",
                    ),
                    supporting_evidence_ids=(1006,),
                ),
                ExpectedFact(
                    match_terms=("order", "errors"),
                    required_patterns=(r"10:03\s*UTC",),
                    supporting_evidence_ids=(1007,),
                ),
            ),
        ),

        # FG-07: Queue depth and retries
        FactGroundingCase(
            case_id="FG-07",
            title="Queue retries and depth",
            description="The message queue experienced increased activity.",
            service="message-queue",
            environment="production",
            severity="medium",
            evidence=(
                EvidenceCase(
                    1008,
                    "metrics",
                    "Queue depth reached 1200 messages. "
                    "The consumer recorded 3 retry attempts "
                    "for the affected message.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("queue", "depth"),
                    required_patterns=(r"\b1200\b",),
                    supporting_evidence_ids=(1008,),
                ),
                ExpectedFact(
                    match_terms=("retry",),
                    required_patterns=(r"\b3\b",),
                    supporting_evidence_ids=(1008,),
                ),
            ),
        ),

        # FG-08: Timeout and suspected cache involvement
        FactGroundingCase(
            case_id="FG-08",
            title="Timeout with suspected cache involvement",
            description="An intermittent timeout was reported.",
            service="catalog-service",
            environment="production",
            severity="medium",
            evidence=(
                EvidenceCase(
                    1009,
                    "application_log",
                    "A request timeout occurred at 14:05 UTC. "
                    "The investigation note says the cache may be "
                    "involved, but this has not been confirmed.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("timeout",),
                    required_patterns=(r"14:05\s*UTC",),
                    supporting_evidence_ids=(1009,),
                    forbidden_patterns=(
                        r"\bcache caused\b",
                        r"\bcache failure caused\b",
                    ),
                ),
            ),
        ),

        # FG-09: HTTP 503 responses
        FactGroundingCase(
            case_id="FG-09",
            title="HTTP 503 responses",
            description="The API returned service unavailable responses.",
            service="public-api",
            environment="production",
            severity="high",
            evidence=(
                EvidenceCase(
                    1010,
                    "metrics",
                    "The API returned 17 HTTP 503 responses "
                    "during the five-minute interval from "
                    "15:00 to 15:05 UTC.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("503",),
                    required_patterns=(
                        r"\b17\b",
                        r"five[- ]minute|5[- ]minute",
                    ),
                    supporting_evidence_ids=(1010,),
                ),
            ),
        ),

        # FG-10: Disk utilization and warning threshold
        FactGroundingCase(
            case_id="FG-10",
            title="Disk utilization threshold",
            description="Disk utilization crossed its warning threshold.",
            service="storage-node",
            environment="production",
            severity="high",
            evidence=(
                EvidenceCase(
                    1011,
                    "monitoring_log",
                    "Disk utilization reached 92%. "
                    "The configured warning threshold is 90%.",
                ),
            ),
            expected_facts=(
                ExpectedFact(
                    match_terms=("disk", "utilization"),
                    required_patterns=(r"92\s*%",),
                    supporting_evidence_ids=(1011,),
                ),
                ExpectedFact(
                    match_terms=("warning", "threshold"),
                    required_patterns=(r"90\s*%",),
                    supporting_evidence_ids=(1011,),
                ),
            ),
        ),
    )


def validate_fact_grounding_cases(
    cases: Sequence[FactGroundingCase],
) -> None:
    """Validate the manually labeled benchmark before model execution."""

    if len(cases) != 10:
        raise ValueError(
            "Fact Grounding dataset must contain exactly 10 cases."
        )

    case_ids = [case.case_id for case in cases]

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Duplicate benchmark case IDs found.")

    evidence_ids = []

    for case in cases:
        if not case.case_id.strip():
            raise ValueError("Benchmark case ID cannot be empty.")

        if not case.title.strip() or not case.description.strip():
            raise ValueError(
                f"{case.case_id} has empty incident information."
            )

        if not case.service.strip():
            raise ValueError(
                f"{case.case_id} has an empty service name."
            )

        if not case.environment.strip() or not case.severity.strip():
            raise ValueError(
                f"{case.case_id} has empty environment or severity."
            )

        if not case.evidence:
            raise ValueError(
                f"{case.case_id} must contain at least one evidence record."
            )

        if not case.expected_facts:
            raise ValueError(
                f"{case.case_id} must contain at least one expected fact."
            )

        local_ids = [item.id for item in case.evidence]

        if len(local_ids) != len(set(local_ids)):
            raise ValueError(
                f"{case.case_id} contains duplicate evidence IDs."
            )

        for item in case.evidence:
            if item.id <= 0:
                raise ValueError(
                    f"{case.case_id} has an invalid evidence ID."
                )

            if not item.source_type.strip() or not item.content.strip():
                raise ValueError(
                    f"{case.case_id} has empty evidence information."
                )

        evidence_ids.extend(local_ids)
        available_ids = set(local_ids)

        for expected in case.expected_facts:
            if not expected.match_terms:
                raise ValueError(
                    f"{case.case_id} has an expected fact without match terms."
                )

            if any(not term.strip() for term in expected.match_terms):
                raise ValueError(
                    f"{case.case_id} has an empty expected-fact match term."
                )

            if not expected.supporting_evidence_ids:
                raise ValueError(
                    f"{case.case_id} has an expected fact without evidence IDs."
                )

            if len(expected.supporting_evidence_ids) != len(
                set(expected.supporting_evidence_ids)
            ):
                raise ValueError(
                    f"{case.case_id} has duplicate expected evidence IDs."
                )

            if not set(expected.supporting_evidence_ids).issubset(
                available_ids
            ):
                raise ValueError(
                    f"{case.case_id} references unavailable expected evidence."
                )

            patterns = (
                expected.required_patterns
                + expected.forbidden_patterns
            )

            for pattern in patterns:
                if not pattern.strip():
                    raise ValueError(
                        f"{case.case_id} contains an empty regex pattern."
                    )

                try:
                    re.compile(pattern, flags=re.IGNORECASE)
                except re.error as exc:
                    raise ValueError(
                        f"{case.case_id} contains an invalid regex "
                        f"pattern {pattern!r}: {exc}"
                    ) from exc

    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError(
            "Evidence IDs must be unique across the dataset."
        )
