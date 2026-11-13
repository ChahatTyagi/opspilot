
"""Evaluate OpsPilot's independent causal hypothesis verifier.

Run from the repository root:
    python -m experiments.evaluate_hypothesis_verifier

Run repeated trials:
    python -m experiments.evaluate_hypothesis_verifier --runs 3

Run a smaller initial smoke test:
    python -m experiments.evaluate_hypothesis_verifier --limit 3

The benchmark calls the production Ollama verifier and then applies the
production hypothesis-evidence validation rules to each assessment.
It does not exercise the complete investigation pipeline.

IMPORTANT:
    --limit selects the first N cases, not a balanced sample.
    Use it only for smoke tests, not for reporting final accuracy.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ai_models import (
    AIConfidence,
    AIHypothesis,
    AIHypothesisVerdict,
    AIInvestigationResult,
)
from app.config import get_verifier_model
from app.evidence_validation import validate_hypothesis_verification
from app.ollama_verification import verify_ollama_hypotheses


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "hypothesis_verifier_benchmark_v3.json"
)

VERDICTS = (
    AIHypothesisVerdict.SUPPORTED.value,
    AIHypothesisVerdict.INSUFFICIENT.value,
    AIHypothesisVerdict.CONTRADICTED.value,
)


# ---------------------------------------------------------------------
# Benchmark data structures
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkEvidence:
    """Evidence object compatible with the production verifier."""

    id: int
    source_type: str
    content: str


@dataclass(frozen=True)
class BenchmarkCase:
    """One manually labeled causal hypothesis scenario."""

    case_id: str
    category: str
    description: str
    hypothesis: str
    expected_verdict: str
    evidence: tuple[BenchmarkEvidence, ...]
    expected_evidence_ids: tuple[int, ...]


@dataclass
class CaseResult:
    """Result of one model evaluation."""

    run_number: int
    case_id: str
    category: str
    description: str
    hypothesis: str
    expected_verdict: str
    actual_verdict: str | None
    expected_evidence_ids: list[int]
    actual_evidence_ids: list[int]
    rationale: str | None
    verdict_correct: bool
    evidence_exact_match: bool
    evidence_precision: float | None
    evidence_recall: float | None
    latency_seconds: float
    error: str | None
    production_validation_passed: bool | None
    production_validation_error: str | None
    production_usable_verdict: str | None
    production_usable_verdict_correct: bool | None


# ---------------------------------------------------------------------
# Labeled benchmark dataset
# ---------------------------------------------------------------------

def build_benchmark_cases() -> list[BenchmarkCase]:
    """Return 24 manually labeled synthetic scenarios.

    Each case contains only the evidence cited by its hypothesis.
    Expected evidence IDs identify the items that justify the expected
    verdict. For INSUFFICIENT cases, this set is normally empty.
    """

    cases = [

        # =============================================================
        # SUPPORTED: 8 cases
        # =============================================================

        BenchmarkCase(
            case_id="SUP-01",
            category="connection_pool_saturation",
            description="Connection pool reaches capacity during timeouts.",
            hypothesis=(
                "Database connection pool saturation caused API request "
                "timeouts."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    101, "metric",
                    "During the incident, active database connections "
                    "reached the configured maximum of 100. The maximum "
                    "remained reached for 4 consecutive minutes."
                ),
                BenchmarkEvidence(
                    102, "log",
                    "API requests failed during the same interval with "
                    "the error: timeout waiting to acquire a database "
                    "connection from the application pool."
                ),
            ),
            expected_evidence_ids=(101, 102),
        ),

        BenchmarkCase(
            case_id="SUP-02",
            category="cpu_throttling",
            description="Container CPU throttling coincides with latency.",
            hypothesis=(
                "Container CPU throttling contributed to increased "
                "API request latency."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    111, "metric",
                    "During the latency incident, the API container "
                    "experienced CPU throttling in 42% of measurement "
                    "periods. The configured CPU limit was reached "
                    "repeatedly."
                ),
                BenchmarkEvidence(
                    112, "metric",
                    "API p95 latency increased from 180 ms to 2.4 seconds "
                    "during the same five-minute interval."
                ),
            ),
            expected_evidence_ids=(111, 112),
        ),

        BenchmarkCase(
            case_id="SUP-03",
            category="consumer_failure",
            description="Consumer crash explains message backlog.",
            hypothesis=(
                "The inventory consumer crash caused messages to "
                "accumulate in the inventory processing queue."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    121, "log",
                    "Inventory consumer process exited unexpectedly at "
                    "14:02:11 after an unhandled exception. No consumer "
                    "restart was recorded for the next six minutes."
                ),
                BenchmarkEvidence(
                    122, "metric",
                    "Inventory queue depth increased from 120 to 18,400 "
                    "messages between 14:02 and 14:08."
                ),
            ),
            expected_evidence_ids=(121, 122),
        ),

        BenchmarkCase(
            case_id="SUP-04",
            category="dns_failure",
            description="DNS resolution failures affect upstream calls.",
            hypothesis=(
                "DNS resolution failures caused the checkout service "
                "to fail when contacting the payment service."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    131, "log",
                    "Checkout service repeatedly logged "
                    "getaddrinfo EAI_AGAIN payment.internal while "
                    "attempting to resolve the payment service."
                ),
                BenchmarkEvidence(
                    132, "trace",
                    "Distributed traces show checkout requests failing "
                    "at the payment-service hostname resolution step. "
                    "No HTTP request reached the payment service."
                ),
            ),
            expected_evidence_ids=(131, 132),
        ),

        BenchmarkCase(
            case_id="SUP-05",
            category="database_lock_contention",
            description="Database lock waits align with slow transactions.",
            hypothesis=(
                "Database lock contention contributed to the increase "
                "in transaction latency."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    141, "metric",
                    "Database lock-wait time increased from 5 ms to "
                    "1,850 ms per transaction during the incident."
                ),
                BenchmarkEvidence(
                    142, "log",
                    "Transaction logs repeatedly report lock wait "
                    "timeouts involving the orders table during the "
                    "same period as the latency increase."
                ),
            ),
            expected_evidence_ids=(141, 142),
        ),

        BenchmarkCase(
            case_id="SUP-06",
            category="memory_exhaustion",
            description="OOM kills precede worker request failures.",
            hypothesis=(
                "Memory exhaustion caused API workers to terminate, "
                "contributing to failed requests."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    151, "log",
                    "The operating system recorded an OOM kill for "
                    "api-worker-3 at 09:31:07."
                ),
                BenchmarkEvidence(
                    152, "metric",
                    "Available container memory reached zero immediately "
                    "before the worker termination. The worker restarted "
                    "after the termination."
                ),
            ),
            expected_evidence_ids=(151, 152),
        ),

        BenchmarkCase(
            case_id="SUP-07",
            category="disk_io_pressure",
            description="Storage latency affects database query latency.",
            hypothesis=(
                "Elevated storage I/O latency contributed to slow "
                "database query execution."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    161, "metric",
                    "Database volume I/O await time increased from "
                    "3 ms to 920 ms during the incident. Disk utilization "
                    "remained near 100%."
                ),
                BenchmarkEvidence(
                    162, "metric",
                    "Database query latency increased during the same "
                    "measurement interval. Database CPU utilization "
                    "remained below 40%."
                ),
            ),
            expected_evidence_ids=(161, 162),
        ),

        BenchmarkCase(
            case_id="SUP-08",
            category="deployment_regression",
            description="A deployed version introduces a specific error.",
            hypothesis=(
                "The latest checkout deployment introduced a regression "
                "that caused payment requests to fail."
            ),
            expected_verdict="supported",
            evidence=(
                BenchmarkEvidence(
                    171, "deployment",
                    "Checkout version 2.8.1 was deployed at 16:00. "
                    "The previous version was 2.8.0."
                ),
                BenchmarkEvidence(
                    172, "log",
                    "Immediately after deployment, checkout requests "
                    "began failing with a new serialization exception "
                    "in the payment request adapter. The same error "
                    "does not appear in the preceding version's logs."
                ),
            ),
            expected_evidence_ids=(171, 172),
        ),

        # =============================================================
        # INSUFFICIENT: 8 cases
        # =============================================================

        BenchmarkCase(
            case_id="INS-01",
            category="symptom_only",
            description="Timeouts exist, but no cause is established.",
            hypothesis=(
                "Database connection pool exhaustion caused API "
                "timeouts."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    201, "log",
                    "API requests returned timeout errors during the "
                    "incident."
                ),
                BenchmarkEvidence(
                    202, "metric",
                    "API p95 latency increased from 200 ms to 1.8 seconds."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-02",
            category="component_mismatch",
            description="Evidence concerns another service.",
            hypothesis=(
                "The checkout service's CPU saturation caused its "
                "request failures."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    211, "metric",
                    "The analytics worker CPU utilization reached 98%. "
                    "The measurement belongs to the analytics service."
                ),
                BenchmarkEvidence(
                    212, "log",
                    "Checkout requests failed with HTTP 500 errors."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-03",
            category="temporal_mismatch",
            description="Evidence occurs after the incident.",
            hypothesis=(
                "A database restart caused the API outage at 10:00."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    221, "log",
                    "Database restart completed successfully at 10:45. "
                    "The API outage occurred between 10:00 and 10:10."
                ),
                BenchmarkEvidence(
                    222, "log",
                    "API requests failed between 10:00 and 10:10."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-04",
            category="recommendation_as_evidence",
            description="A recommendation is not proof of a failure.",
            hypothesis=(
                "The Redis cache outage caused the API latency increase."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    231, "note",
                    "Recommendation: investigate Redis availability "
                    "and consider restarting the cache if necessary."
                ),
                BenchmarkEvidence(
                    232, "metric",
                    "API p95 latency increased to 2.1 seconds."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-05",
            category="possible_failure_mode",
            description="A technically possible cause has no observation.",
            hypothesis=(
                "A memory leak in the API service caused the incident."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    241, "log",
                    "API requests intermittently returned HTTP 503."
                ),
                BenchmarkEvidence(
                    242, "metric",
                    "Memory usage was not collected for the affected "
                    "service during the incident."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-06",
            category="measurement_scope",
            description="A metric does not identify the relevant instance.",
            hypothesis=(
                "The production API instance ran out of memory and "
                "caused the outage."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    251, "metric",
                    "Average memory utilization across all development "
                    "containers was 96%. No production-instance "
                    "measurement is included."
                ),
                BenchmarkEvidence(
                    252, "log",
                    "Production API requests returned HTTP 503."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-07",
            category="correlation_without_causation",
            description="Two events coincide without a causal connection.",
            hypothesis=(
                "The marketing campaign caused database latency "
                "by increasing checkout traffic."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    261, "note",
                    "The marketing campaign began at 12:00."
                ),
                BenchmarkEvidence(
                    262, "metric",
                    "Database latency increased at approximately 12:00. "
                    "No checkout traffic volume or database workload "
                    "measurements are available."
                ),
            ),
            expected_evidence_ids=(),
        ),

        BenchmarkCase(
            case_id="INS-08",
            category="conflicting_monitoring",
            description="Conflicting measurements do not establish cause.",
            hypothesis=(
                "Database CPU saturation caused the checkout outage."
            ),
            expected_verdict="insufficient",
            evidence=(
                BenchmarkEvidence(
                    271, "metric",
                    "Monitoring source A reports database CPU utilization "
                    "of 98% during the incident."
                ),
                BenchmarkEvidence(
                    272, "metric",
                    "Monitoring source B reports database CPU utilization "
                    "of 34% over the same labeled interval. The sources "
                    "have not been reconciled."
                ),
            ),
            expected_evidence_ids=(),
        ),

        # =============================================================
        # CONTRADICTED: 8 cases
        # =============================================================

        BenchmarkCase(
            case_id="CON-01",
            category="healthy_connection_pool",
            description="Connection pool remains far below capacity.",
            hypothesis=(
                "Database connection pool exhaustion caused the API "
                "timeouts."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    301, "metric",
                    "During the entire API timeout interval, active "
                    "database connections remained between 18 and 24 "
                    "against a configured maximum of 100. No pool "
                    "acquisition failures were recorded."
                ),
                BenchmarkEvidence(
                    302, "log",
                    "API requests failed with upstream gateway timeout "
                    "errors."
                ),
            ),
            expected_evidence_ids=(301,),
        ),

        BenchmarkCase(
            case_id="CON-02",
            category="no_cpu_throttling",
            description="The relevant container has no CPU throttling.",
            hypothesis=(
                "CPU throttling caused the API container's latency spike."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    311, "metric",
                    "The affected API container recorded zero CPU "
                    "throttled periods throughout the incident. Its "
                    "CPU usage remained below 45% of its configured limit."
                ),
                BenchmarkEvidence(
                    312, "metric",
                    "API p95 latency increased to 2.7 seconds."
                ),
            ),
            expected_evidence_ids=(311,),
        ),

        BenchmarkCase(
            case_id="CON-03",
            category="consumer_healthy",
            description=(
                "Consumer remained healthy while queue depth stayed "
                "at its normal baseline."
            ),
            hypothesis=(
                "An inventory consumer crash caused the inventory "
                "queue backlog."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    321, "metric",
                    "The inventory consumer maintained its configured "
                    "replica count and processed messages continuously "
                    "throughout the incident."
                ),
                BenchmarkEvidence(
                    322, "metric",
                    "Inventory queue depth remained between 80 and 110 "
                    "messages, matching its normal baseline."
                ),
            ),
            expected_evidence_ids=(321, 322),
        ),

        BenchmarkCase(
            case_id="CON-04",
            category="dns_healthy",
            description="DNS resolution succeeds throughout the incident.",
            hypothesis=(
                "DNS resolution failures caused checkout requests "
                "to fail."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    331, "metric",
                    "DNS probes from the affected checkout instances "
                    "successfully resolved payment.internal on every "
                    "attempt during the outage."
                ),
                BenchmarkEvidence(
                    332, "trace",
                    "Failed checkout traces show successful DNS "
                    "resolution followed by an HTTP 503 response "
                    "from the payment service."
                ),
            ),
            expected_evidence_ids=(331, 332),
        ),

        BenchmarkCase(
            case_id="CON-05",
            category="no_database_lock_contention",
            description="No lock waits occur during the relevant interval.",
            hypothesis=(
                "Database lock contention caused the orders "
                "transaction latency increase."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    341, "metric",
                    "Database lock-wait duration remained zero throughout "
                    "the incident. No blocked transactions were observed."
                ),
                BenchmarkEvidence(
                    342, "metric",
                    "Orders transaction latency increased from 40 ms "
                    "to 1.2 seconds."
                ),
            ),
            expected_evidence_ids=(341,),
        ),

        BenchmarkCase(
            case_id="CON-06",
            category="memory_healthy",
            description="Memory measurements rule out memory exhaustion.",
            hypothesis=(
                "Memory exhaustion caused the production API workers "
                "to terminate."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    351, "metric",
                    "Production API container memory utilization "
                    "remained between 38% and 52% during the incident. "
                    "No OOM events or worker terminations were recorded."
                ),
                BenchmarkEvidence(
                    352, "log",
                    "API requests failed with HTTP 502 responses."
                ),
            ),
            expected_evidence_ids=(351,),
        ),

        BenchmarkCase(
            case_id="CON-07",
            category="storage_healthy",
            description="Storage measurements contradict disk I/O pressure.",
            hypothesis=(
                "Database disk I/O saturation caused slow query execution."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    361, "metric",
                    "Database volume utilization remained below 20%, "
                    "and I/O await time remained below 4 ms throughout "
                    "the incident."
                ),
                BenchmarkEvidence(
                    362, "metric",
                    "Database query latency increased from 30 ms "
                    "to 1.5 seconds."
                ),
            ),
            expected_evidence_ids=(361,),
        ),

        BenchmarkCase(
            case_id="CON-08",
            category="no_deployment",
            description="Deployment history rules out the proposed release.",
            hypothesis=(
                "A new checkout deployment introduced the regression "
                "responsible for the incident."
            ),
            expected_verdict="contradicted",
            evidence=(
                BenchmarkEvidence(
                    371, "deployment",
                    "Deployment history confirms checkout version "
                    "2.8.0 remained deployed throughout the incident. "
                    "No deployment, rollback, or configuration change "
                    "occurred during the relevant period."
                ),
                BenchmarkEvidence(
                    372, "log",
                    "Checkout requests failed with HTTP 500 responses."
                ),
            ),
            expected_evidence_ids=(371,),
        ),
    ]

    if len(cases) != 24:
        raise ValueError(
            f"Expected 24 benchmark cases, found {len(cases)}."
        )

    verdict_counts = {
        verdict: sum(
            case.expected_verdict == verdict for case in cases
        )
        for verdict in VERDICTS
    }

    if verdict_counts != {
        "supported": 8,
        "insufficient": 8,
        "contradicted": 8,
    }:
        raise ValueError(
            f"Benchmark verdict distribution is incorrect: "
            f"{verdict_counts}"
        )

    validate_benchmark_cases(cases)

    return cases


def validate_benchmark_cases(
    cases: list[BenchmarkCase],
) -> None:
    """Catch mistakes in the manually labeled benchmark dataset."""

    seen_case_ids: set[str] = set()

    for case in cases:
        if case.case_id in seen_case_ids:
            raise ValueError(
                f"Duplicate benchmark case ID: {case.case_id}"
            )

        seen_case_ids.add(case.case_id)

        if case.expected_verdict not in VERDICTS:
            raise ValueError(
                f"Invalid expected verdict in {case.case_id}."
            )

        if not case.hypothesis.strip():
            raise ValueError(
                f"Empty hypothesis in {case.case_id}."
            )

        evidence_ids = [item.id for item in case.evidence]

        if not evidence_ids:
            raise ValueError(
                f"No evidence provided in {case.case_id}."
            )

        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(
                f"Duplicate evidence IDs in {case.case_id}."
            )

        if not set(case.expected_evidence_ids).issubset(
            set(evidence_ids)
        ):
            raise ValueError(
                f"Expected evidence IDs are not present in "
                f"{case.case_id}."
            )

        if (
            case.expected_verdict == "supported"
            and not case.expected_evidence_ids
        ):
            raise ValueError(
                f"Supported case {case.case_id} needs expected "
                f"supporting evidence IDs."
            )

        if (
            case.expected_verdict == "insufficient"
            and case.expected_evidence_ids
        ):
            raise ValueError(
                f"Insufficient case {case.case_id} should not have "
                f"expected supporting evidence IDs in this dataset."
            )

        if (
            case.expected_verdict == "contradicted"
            and not case.expected_evidence_ids
        ):
            raise ValueError(
                f"Contradicted case {case.case_id} needs expected "
                f"contradicting evidence IDs."
            )

        if any(
            not item.content.strip()
            for item in case.evidence
        ):
            raise ValueError(
                f"Empty evidence content in {case.case_id}."
            )


# ---------------------------------------------------------------------
# Individual evaluation
# ---------------------------------------------------------------------

def evaluate_case(
    case: BenchmarkCase,
    run_number: int,
) -> CaseResult:
    """Call the actual production verifier for one benchmark case."""

    hypothesis = AIHypothesis(
        explanation=case.hypothesis,
        supporting_evidence_ids=[
            item.id for item in case.evidence
        ],
        confidence=AIConfidence.MEDIUM,
    )

    start = time.perf_counter()

    try:
        verification = verify_ollama_hypotheses(
            hypotheses=[hypothesis],
            evidence=list(case.evidence),
        )

        latency = time.perf_counter() - start

        if len(verification.assessments) != 1:
            raise ValueError(
                "Expected exactly one assessment, received "
                f"{len(verification.assessments)}."
            )

        assessment = verification.assessments[0]

        if assessment.hypothesis_index != 0:
            raise ValueError(
                "Unexpected hypothesis index: "
                f"{assessment.hypothesis_index}."
            )

        actual_verdict = assessment.verdict.value

        if actual_verdict not in VERDICTS:
            raise ValueError(
                f"Unexpected verdict: {actual_verdict}."
            )

        actual_ids = list(assessment.evidence_ids)
        expected_ids = list(case.expected_evidence_ids)

        expected_set = set(expected_ids)
        actual_set = set(actual_ids)

        intersection = expected_set.intersection(actual_set)

        if actual_ids:
            precision = len(intersection) / len(actual_ids)
        else:
            precision = (
                1.0 if not expected_ids else 0.0
            )

        if expected_ids:
            recall = len(intersection) / len(expected_ids)
        else:
            recall = (
                1.0 if not actual_ids else 0.0
            )

        # Preserve the raw model verdict even if production validation
        # rejects the assessment. This separates model classification
        # quality from whether OpsPilot can safely use the result.
        production_validation_error = None

        try:
            validate_hypothesis_verification(
                result=AIInvestigationResult(
                    hypotheses=[hypothesis],
                ),
                verification=verification,
                valid_evidence_ids={
                    item.id for item in case.evidence
                },
            )
            production_validation_passed = True
            production_usable_verdict = actual_verdict
            production_usable_verdict_correct = (
                actual_verdict == case.expected_verdict
            )
        except ValueError as validation_exc:
            production_validation_passed = False
            production_validation_error = (
                f"{type(validation_exc).__name__}: "
                f"{validation_exc}"
            )
            production_usable_verdict = None
            # A rejected assessment cannot count as a production-usable
            # correct verdict, even when its raw classification was right.
            production_usable_verdict_correct = False

        return CaseResult(
            run_number=run_number,
            case_id=case.case_id,
            category=case.category,
            description=case.description,
            hypothesis=case.hypothesis,
            expected_verdict=case.expected_verdict,
            actual_verdict=actual_verdict,
            expected_evidence_ids=expected_ids,
            actual_evidence_ids=actual_ids,
            rationale=assessment.rationale,
            verdict_correct=(
                actual_verdict == case.expected_verdict
            ),
            evidence_exact_match=(
                actual_set == expected_set
            ),
            evidence_precision=precision,
            evidence_recall=recall,
            latency_seconds=round(latency, 3),
            error=None,
            production_validation_passed=(
                production_validation_passed
            ),
            production_validation_error=(
                production_validation_error
            ),
            production_usable_verdict=production_usable_verdict,
            production_usable_verdict_correct=(
                production_usable_verdict_correct
            ),
        )

    except Exception as exc:
        latency = time.perf_counter() - start

        return CaseResult(
            run_number=run_number,
            case_id=case.case_id,
            category=case.category,
            description=case.description,
            hypothesis=case.hypothesis,
            expected_verdict=case.expected_verdict,
            actual_verdict=None,
            expected_evidence_ids=list(
                case.expected_evidence_ids
            ),
            actual_evidence_ids=[],
            rationale=None,
            verdict_correct=False,
            evidence_exact_match=False,
            evidence_precision=None,
            evidence_recall=None,
            latency_seconds=round(latency, 3),
            error=f"{type(exc).__name__}: {exc}",
            production_validation_passed=None,
            production_validation_error=None,
            production_usable_verdict=None,
            production_usable_verdict_correct=None,
        )


# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------

def calculate_percent(
    numerator: int,
    denominator: int,
) -> float | None:
    if denominator == 0:
        return None

    return round(
        numerator / denominator * 100,
        2,
    )


def calculate_metrics(
    results: list[CaseResult],
) -> dict[str, Any]:
    """Calculate verdict, safety, citation and latency metrics."""

    total_evaluations = len(results)

    unique_case_ids = {
        result.case_id
        for result in results
    }

    successful = [
        result
        for result in results
        if result.actual_verdict is not None
    ]

    failures = total_evaluations - len(successful)

    correct = sum(
        result.verdict_correct
        for result in successful
    )

    confusion_matrix = {
        expected: {
            actual: 0
            for actual in VERDICTS
        }
        for expected in VERDICTS
    }

    for result in successful:
        confusion_matrix[
            result.expected_verdict
        ][result.actual_verdict] += 1

    non_supported = [
        result
        for result in successful
        if result.expected_verdict in (
            "insufficient",
            "contradicted",
        )
    ]

    false_supported = sum(
        result.actual_verdict == "supported"
        for result in non_supported
    )

    supported_cases = [
        result
        for result in successful
        if result.expected_verdict == "supported"
    ]

    rejected_supported = sum(
        result.actual_verdict != "supported"
        for result in supported_cases
    )

    citation_results = [
        result
        for result in successful
        if result.expected_verdict in (
            "supported",
            "contradicted",
        )
    ]

    citation_precision_values = [
        result.evidence_precision
        for result in citation_results
        if result.evidence_precision is not None
    ]

    citation_recall_values = [
        result.evidence_recall
        for result in citation_results
        if result.evidence_recall is not None
    ]

    insufficient_results = [
        result
        for result in successful
        if result.expected_verdict == "insufficient"
    ]

    unnecessary_insufficient_citations = sum(
        bool(result.actual_evidence_ids)
        for result in insufficient_results
    )

    validation_evaluated = [
        result
        for result in successful
        if result.production_validation_passed is not None
    ]

    validation_accepted = [
        result
        for result in validation_evaluated
        if result.production_validation_passed
    ]

    production_usable_correct = sum(
        result.production_usable_verdict_correct is True
        for result in validation_evaluated
    )

    latencies = [
        result.latency_seconds
        for result in results
    ]

    sorted_latencies = sorted(latencies)

    if sorted_latencies:
        p95_index = max(
            0,
            math.ceil(0.95 * len(sorted_latencies)) - 1,
        )
        p95_latency = sorted_latencies[p95_index]
    else:
        p95_latency = None

    def mean(values: list[float]) -> float | None:
        if not values:
            return None

        return round(statistics.mean(values), 3)

    return {
        "unique_benchmark_cases": len(unique_case_ids),
        "total_evaluations": total_evaluations,
        "successful_evaluations": len(successful),
        "failed_evaluations": failures,
        "execution_success_rate_percent": calculate_percent(
            len(successful),
            total_evaluations,
        ),
        "verdict_accuracy_percent": calculate_percent(
            correct,
            len(successful),
        ),
        "correct_verdicts": correct,
        "confusion_matrix": confusion_matrix,

        "false_supported": {
            "count": false_supported,
            "denominator": len(non_supported),
            "rate_percent": calculate_percent(
                false_supported,
                len(non_supported),
            ),
        },

        "supported_hypothesis_rejection": {
            "count": rejected_supported,
            "denominator": len(supported_cases),
            "rate_percent": calculate_percent(
                rejected_supported,
                len(supported_cases),
            ),
        },

        "production_validation": {
            "evaluated_assessments": len(validation_evaluated),
            "accepted_assessments": len(validation_accepted),
            "rejected_assessments": (
                len(validation_evaluated) - len(validation_accepted)
            ),
            "acceptance_rate_percent": calculate_percent(
                len(validation_accepted),
                len(validation_evaluated),
            ),
            "production_usable_verdict_accuracy_percent": (
                calculate_percent(
                    production_usable_correct,
                    len(validation_evaluated),
                )
            ),
            "production_usable_correct_verdicts": (
                production_usable_correct
            ),
            "production_usable_accuracy_denominator": (
                len(validation_evaluated)
            ),
        },

        "evidence_citations": {
            "averaging_method": "macro_mean_of_case_level_scores",
            "mean_case_level_precision_percent": (
                calculate_percent(
                    sum(citation_precision_values),
                    len(citation_precision_values),
                )
                if citation_precision_values
                else None
            ),
            "mean_case_level_recall_percent": (
                calculate_percent(
                    sum(citation_recall_values),
                    len(citation_recall_values),
                )
                if citation_recall_values
                else None
            ),
            "exact_match_count": sum(
                result.evidence_exact_match
                for result in citation_results
            ),
            "evaluated_cases": len(citation_results),
            "insufficient_cases_with_unnecessary_citations": (
                unnecessary_insufficient_citations
            ),
            "evaluated_insufficient_cases": len(
                insufficient_results
            ),
        },

        "latency_seconds": {
            "mean": mean(latencies),
            "median": (
                round(statistics.median(latencies), 3)
                if latencies
                else None
            ),
            "p95": (
                round(p95_latency, 3)
                if p95_latency is not None
                else None
            ),
            "minimum": (
                round(min(latencies), 3)
                if latencies
                else None
            ),
            "maximum": (
                round(max(latencies), 3)
                if latencies
                else None
            ),
        },
    }


# ---------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------

def print_report(
    model: str,
    runs: int,
    metrics: dict[str, Any],
    results: list[CaseResult],
) -> None:

    print("\n" + "=" * 68)
    print("OPSPILOT HYPOTHESIS VERIFIER BENCHMARK")
    print("=" * 68)

    print(f"Model: {model}")
    print(f"Runs per case: {runs}")
    print(
        "Unique benchmark cases:",
        metrics["unique_benchmark_cases"],
    )
    print(
        "Total evaluations:",
        metrics["total_evaluations"],
    )

    print("\nEXECUTION")
    print("-" * 68)
    print(
        "Successful evaluations:",
        metrics["successful_evaluations"],
    )
    print(
        "Failed evaluations:",
        metrics["failed_evaluations"],
    )
    print(
        "Execution success rate:",
        f"{metrics['execution_success_rate_percent']}%",
    )

    print("\nVERDICT PERFORMANCE")
    print("-" * 68)
    print(
        "Accuracy:",
        f"{metrics['verdict_accuracy_percent']}%",
    )

    print("\nConfusion matrix")
    print(
        f"{'Expected':<18}"
        f"{'SUPPORTED':>14}"
        f"{'INSUFFICIENT':>16}"
        f"{'CONTRADICTED':>16}"
    )

    for expected, row in metrics["confusion_matrix"].items():
        print(
            f"{expected:<18}"
            f"{row['supported']:>14}"
            f"{row['insufficient']:>16}"
            f"{row['contradicted']:>16}"
        )

    false_supported = metrics["false_supported"]

    print("\nSAFETY METRICS")
    print("-" * 68)
    print(
        "False SUPPORTED decisions:",
        f"{false_supported['count']}/"
        f"{false_supported['denominator']}",
    )
    print(
        "False SUPPORTED rate:",
        f"{false_supported['rate_percent']}%",
    )

    rejection = metrics["supported_hypothesis_rejection"]

    print(
        "Supported hypotheses incorrectly rejected:",
        f"{rejection['count']}/"
        f"{rejection['denominator']}",
    )
    print(
        "Supported rejection rate:",
        f"{rejection['rate_percent']}%",
    )

    production_validation = metrics["production_validation"]

    print("\\nPRODUCTION VALIDATION")
    print("-" * 68)
    print(
        "Assessments accepted:",
        f"{production_validation['accepted_assessments']}/"
        f"{production_validation['evaluated_assessments']}",
    )
    print(
        "Assessments rejected:",
        production_validation["rejected_assessments"],
    )
    print(
        "Production validation acceptance rate:",
        f"{production_validation['acceptance_rate_percent']}%",
    )
    print(
        "Production-usable verdict accuracy:",
        f"{production_validation['production_usable_verdict_accuracy_percent']}%",
    )

    citations = metrics["evidence_citations"]

    print("\nEVIDENCE CITATION METRICS")
    print("-" * 68)
    print(
        "Averaging method:",
        citations["averaging_method"],
    )
    print(
        "Mean case-level citation precision:",
        f"{citations['mean_case_level_precision_percent']}%",
    )
    print(
        "Mean case-level citation recall:",
        f"{citations['mean_case_level_recall_percent']}%",
    )
    print(
        "Exact citation matches:",
        f"{citations['exact_match_count']}/"
        f"{citations['evaluated_cases']}",
    )
    print(
        "INSUFFICIENT cases with unnecessary citations:",
        f"{citations['insufficient_cases_with_unnecessary_citations']}/"
        f"{citations['evaluated_insufficient_cases']}",
    )

    latency = metrics["latency_seconds"]

    print("\nLATENCY")
    print("-" * 68)
    print(f"Mean:   {latency['mean']} seconds")
    print(f"Median: {latency['median']} seconds")
    print(f"P95:    {latency['p95']} seconds")
    print(f"Min:    {latency['minimum']} seconds")
    print(f"Max:    {latency['maximum']} seconds")

    print("\nINCORRECT VERDICTS AND FAILURES")
    print("-" * 68)

    problem_cases = [
        result
        for result in results
        if (
            not result.verdict_correct
            or result.production_validation_passed is False
            or result.error is not None
        )
    ]

    if not problem_cases:
        print(
            "No incorrect verdicts, production-validation rejections, "
            "or failed evaluations."
        )
    else:
        for result in problem_cases:
            print(
                f"\nRun {result.run_number} | "
                f"{result.case_id} | "
                f"Expected: {result.expected_verdict} | "
                f"Actual: {result.actual_verdict}"
            )

            if result.error:
                print("Error:", result.error)

            if result.production_validation_error:
                print(
                    "Production validation rejected assessment:",
                    result.production_validation_error,
                )

            if result.rationale:
                print("Rationale:", result.rationale)

    print("\n" + "=" * 68)


# ---------------------------------------------------------------------
# Command-line arguments
# ---------------------------------------------------------------------

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate OpsPilot's independent Ollama hypothesis verifier."
        )
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help=(
            "Number of repetitions per benchmark case "
            "(default: 1)."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Evaluate only the first N cases. "
            "For smoke tests only; this is not a balanced sample."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Path to the JSON results file. "
            "Defaults to the versioned v3 output file."
        ),
    )

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------


def main() -> None:
    args = parse_arguments()

    if args.runs < 1:
        raise SystemExit("--runs must be at least 1.")

    # Resolve and check the output path BEFORE any model evaluations.
    output_path = args.output.resolve()

    if output_path.exists():
        raise SystemExit(
            "Output file already exists; refusing to overwrite it:\n"
            f"{output_path}\n\n"
            "Choose another path using --output."
        )

    cases = build_benchmark_cases()

    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1.")

        if args.limit > len(cases):
            raise SystemExit(
                f"--limit cannot exceed {len(cases)} benchmark cases."
            )

        cases = cases[:args.limit]

    model = get_verifier_model()

    total_evaluations = len(cases) * args.runs

    print("=" * 68)
    print("Starting OpsPilot hypothesis verifier benchmark")
    print(f"Verifier model: {model}")
    print(f"Unique benchmark cases: {len(cases)}")
    print(f"Runs per case: {args.runs}")
    print(f"Total model evaluations: {total_evaluations}")

    if args.limit is not None:
        print(
            "WARNING: --limit selects the first N cases only. "
            "Do not use this run for final benchmark accuracy."
        )

    print("=" * 68)

    all_results: list[CaseResult] = []

    for run_number in range(1, args.runs + 1):
        print(
            f"\nStarting run {run_number}/{args.runs}"
        )

        for case_number, case in enumerate(cases, start=1):
            print(
                f"[Run {run_number}/{args.runs}] "
                f"[Case {case_number}/{len(cases)}] "
                f"{case.case_id}: {case.category}",
                flush=True,
            )

            result = evaluate_case(
                case=case,
                run_number=run_number,
            )

            all_results.append(result)

            if result.error:
                print(
                    f"  FAILED after {result.latency_seconds}s: "
                    f"{result.error}",
                    flush=True,
                )
            else:
                if result.production_validation_passed is False:
                    status = (
                        "INVALID"
                        if result.verdict_correct
                        else "MISMATCH + INVALID"
                    )
                else:
                    status = (
                        "PASS"
                        if result.verdict_correct
                        else "MISMATCH"
                    )

                print(
                    f"  {status} | "
                    f"Expected: {result.expected_verdict} | "
                    f"Actual: {result.actual_verdict} | "
                    f"Latency: {result.latency_seconds}s",
                    flush=True,
                )

    metrics = calculate_metrics(all_results)

    report = {
        "benchmark": "OpsPilot Hypothesis Verifier",
        "benchmark_version": 3,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "model": model,
        "runs_per_case": args.runs,
        "case_count": len(cases),
        "evaluation_count": len(all_results),
        "metrics": metrics,
        "results": [
            asdict(result)
            for result in all_results
        ],
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Exclusive creation prevents overwriting a file that appeared
    # after the initial existence check.
    try:
        with output_path.open(
            "x",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                report,
                output_file,
                indent=2,
                ensure_ascii=False,
            )

    except FileExistsError:
        raise SystemExit(
            "Output file appeared during benchmark execution; "
            "refusing to overwrite it:\n"
            f"{output_path}\n\n"
            "Choose another path using --output."
        )

    print_report(
        model=model,
        runs=args.runs,
        metrics=metrics,
        results=all_results,
    )

    print(
        f"\nDetailed JSON report saved to:\n{output_path}"
    )


if __name__ == "__main__":
    main()
