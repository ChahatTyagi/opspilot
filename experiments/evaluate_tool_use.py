
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Resolve the project root before importing application modules.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.investigation_service as investigation_service
from app.config import get_embedding_provider, get_llm_provider
from app.incident_context import build_incident_context
from app.ollama_client import OllamaClient
from app.retrieval_service import EvidenceRetriever
from app.tool_executor import InvestigationToolExecutor


DEFAULT_OUTPUT = (
    PROJECT_ROOT / "experiments" / "results" / "tool_use_v1.json"
)


TARGET_CONTEXT_EVIDENCE_CHARS = 1980
PADDING_TEXT = (
    "Routine telemetry reports a completed heartbeat. "
    "No additional actionable diagnostic details were recorded. "
)


@dataclass
class ExpectedFinding:
    name: str
    terms: list[str]
    required_evidence_ids: list[int]


@dataclass
class BenchmarkCase:
    case_id: str
    title: str
    description: str
    incident: Any
    evidence: list[Any]
    hidden_evidence_ids: list[int]
    expected_findings: list[ExpectedFinding]


def make_incident(
    incident_id: int,
    title: str,
    description: str,
    service: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=incident_id,
        title=title,
        description=description,
        service=service,
        environment="production",
        severity="high",
        status="open",
        created_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
    )


def pad_evidence_content(content: str) -> str:
    """Make an evidence record large enough to exercise context limits."""

    remaining = TARGET_CONTEXT_EVIDENCE_CHARS - len(content)

    if remaining <= 0:
        return content[:TARGET_CONTEXT_EVIDENCE_CHARS]

    padding = (PADDING_TEXT * (remaining // len(PADDING_TEXT) + 1))[
        :remaining
    ]

    return content + padding


def make_evidence(
    evidence_id: int,
    incident_id: int,
    content: str,
    minute: int,
    *,
    source_type: str = "log",
    pad: bool = False,
) -> SimpleNamespace:
    if pad:
        content = pad_evidence_content(content)

    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        source_type=source_type,
        content=content,
        created_at=(
            datetime(2026, 11, 18, tzinfo=timezone.utc)
            + timedelta(minutes=minute)
        ),
    )


def build_cases() -> dict[str, BenchmarkCase]:
    # TU-01: All useful evidence is visible. Searching is unnecessary.
    incident = make_incident(
        9101,
        "Payment authorization latency",
        "Payment authorization requests are intermittently slow.",
        "payment-api",
    )

    evidence = [
        make_evidence(
            1101,
            9101,
            (
                "Payment API logs show authorization requests "
                "succeeded, but response latency increased to "
                "4.8 seconds during the incident window."
            ),
            1,
        ),
        make_evidence(
            1102,
            9101,
            (
                "Payment gateway metrics show upstream response "
                "latency increased to 4.5 seconds. No increase in "
                "authorization rejection rate was observed."
            ),
            2,
            source_type="metric",
        ),
    ]

    tu01 = BenchmarkCase(
        case_id="TU-01",
        title="Visible evidence",
        description=(
            "The relevant evidence is already present in the initial "
            "context. The model should not need a search."
        ),
        incident=incident,
        evidence=evidence,
        hidden_evidence_ids=[],
        expected_findings=[
            ExpectedFinding(
                name="Elevated payment authorization latency",
                terms=["authorization", "latency", "4.8 seconds"],
                required_evidence_ids=[1101],
            ),
        ],
    )

    # TU-02: The decisive database evidence is hidden by the context limit.
    incident = make_incident(
        9102,
        "Checkout requests failing",
        "Checkout requests are intermittently returning server errors.",
        "checkout-api",
    )

    evidence = []

    for index in range(5):
        evidence.append(
            make_evidence(
                2101 + index,
                9102,
                (
                    f"Checkout application telemetry record {index + 1}. "
                    "Request volume is elevated. Application instances "
                    "remain healthy. HTTP 500 responses are observed "
                    "intermittently. No confirmed database failure "
                    "is recorded in this log."
                ),
                index + 1,
                pad=True,
            )
        )

    evidence.append(
        make_evidence(
            2106,
            9102,
            (
                "CRITICAL DATABASE INCIDENT: PostgreSQL connection "
                "pool exhausted. All 50 connections are active. "
                "Connection acquisition failures increased sharply "
                "after deployment version checkout-api-2.8.1. "
                "Connection acquisition timeout is 30 seconds. "
                "Investigate a possible connection leak."
            ),
            6,
            pad=True,
        )
    )

    tu02 = BenchmarkCase(
        case_id="TU-02",
        title="Hidden root cause",
        description=(
            "The initial context contains symptoms but not the "
            "decisive database evidence."
        ),
        incident=incident,
        evidence=evidence,
        hidden_evidence_ids=[2106],
        expected_findings=[
            ExpectedFinding(
                name="PostgreSQL connection pool exhaustion",
                terms=[
                    "postgresql",
                    "connection pool",
                    "50 connections",
                ],
                required_evidence_ids=[2106],
            ),
        ],
    )

    # TU-03: Visible clues are plausible but do not establish the cause.
    incident = make_incident(
        9103,
        "Catalog service response degradation",
        "Catalog requests are slow and intermittently timing out.",
        "catalog-api",
    )

    evidence = [
        make_evidence(
            3101,
            9103,
            (
                "Catalog API request latency increased during the "
                "incident. Request volume is within the expected range."
            ),
            1,
            pad=True,
        ),
        make_evidence(
            3102,
            9103,
            (
                "Catalog application CPU utilization increased to "
                "68 percent. CPU throttling was not observed."
            ),
            2,
            source_type="metric",
            pad=True,
        ),
        make_evidence(
            3103,
            9103,
            (
                "Catalog database query latency is close to its "
                "normal baseline. No database connection errors "
                "were recorded."
            ),
            3,
            pad=True,
        ),
        make_evidence(
            3104,
            9103,
            (
                "Catalog API cache hit rate decreased slightly. "
                "Cache misses increased but remained within the "
                "historical range."
            ),
            4,
            source_type="metric",
            pad=True,
        ),
        make_evidence(
            3105,
            9103,
            (
                "No recent infrastructure restart or node failure "
                "was recorded for the catalog service."
            ),
            5,
            pad=True,
        ),
        make_evidence(
            3106,
            9103,
            (
                "Redis cache configuration audit: the maxmemory-policy "
                "was changed from volatile-lru to noeviction shortly "
                "before the incident. Redis evictions stopped, and "
                "memory pressure increased. The configuration change "
                "is a strong lead for the cache degradation."
            ),
            6,
            source_type="audit",
            pad=True,
        ),
    ]

    tu03 = BenchmarkCase(
        case_id="TU-03",
        title="Distractors and decisive evidence",
        description=(
            "The visible evidence contains plausible but inconclusive "
            "clues. The decisive Redis configuration audit is hidden."
        ),
        incident=incident,
        evidence=evidence,
        hidden_evidence_ids=[3106],
        expected_findings=[
            ExpectedFinding(
                name="Redis eviction policy changed",
                terms=["redis", "noeviction", "volatile-lru"],
                required_evidence_ids=[3106],
            ),
        ],
    )

    # TU-04: Two hidden records are needed to connect deployment and code.
    incident = make_incident(
        9104,
        "Checkout database connection exhaustion",
        "Checkout requests are timing out after a recent release.",
        "checkout-api",
    )

    evidence = [
        make_evidence(
            4101,
            9104,
            (
                "Checkout API database query latency increased "
                "during the incident window."
            ),
            1,
            pad=True,
        ),
        make_evidence(
            4102,
            9104,
            (
                "Checkout requests are being retried more frequently. "
                "The retry count increased after the release."
            ),
            2,
            pad=True,
        ),
        make_evidence(
            4103,
            9104,
            (
                "Database CPU utilization is 54 percent. The database "
                "is reachable and no storage saturation is reported."
            ),
            3,
            source_type="metric",
            pad=True,
        ),
        make_evidence(
            4104,
            9104,
            (
                "Checkout API instances report intermittent failures "
                "while acquiring database connections."
            ),
            4,
            pad=True,
        ),
        make_evidence(
            4105,
            9104,
            (
                "The connection pool is configured with a maximum "
                "of 20 connections. The configured acquisition "
                "timeout is 30 seconds."
            ),
            5,
            source_type="config",
            pad=True,
        ),
        make_evidence(
            4106,
            9104,
            (
                "Deployment audit: checkout-api version 2.9.1 was "
                "released at 14:05 UTC. The release included a new "
                "database retry handler."
            ),
            6,
            source_type="audit",
            pad=True,
        ),
        make_evidence(
            4107,
            9104,
            (
                "Code review evidence for checkout-api 2.9.1: the "
                "new database retry handler opens SQLAlchemy sessions "
                "but does not close them on the retry failure path. "
                "Sessions can remain checked out from the connection "
                "pool after failed retries."
            ),
            7,
            source_type="code_review",
            pad=True,
        ),
    ]

    tu04 = BenchmarkCase(
        case_id="TU-04",
        title="Multi-source investigation",
        description=(
            "The deployment audit and code review evidence are both "
            "hidden. The model needs both records to connect the "
            "release with the connection leak."
        ),
        incident=incident,
        evidence=evidence,
        hidden_evidence_ids=[4106, 4107],
        expected_findings=[
            ExpectedFinding(
                name="Release introduced a database session leak",
                terms=[
                    "2.9.1",
                    "retry handler",
                    "sessions",
                    "close",
                ],
                required_evidence_ids=[4106, 4107],
            ),
        ],
    )

    return {
        case.case_id: case
        for case in [tu01, tu02, tu03, tu04]
    }


class BenchmarkLoggingExecutor(InvestigationToolExecutor):
    """Capture the searches made during one benchmark investigation."""

    instances: list[BenchmarkLoggingExecutor] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool_attempts: list[dict[str, Any]] = []
        type(self).instances.append(self)

    def execute(self, *, tool_name, arguments):
        attempt = {
            "tool_name": tool_name,
            "arguments": arguments,
            "ok": None,
            "returned_evidence_ids": [],
            "new_evidence_ids": [],
            "error": None,
        }

        try:
            result = super().execute(
                tool_name=tool_name,
                arguments=arguments,
            )

            attempt["ok"] = result.get("ok") is True
            attempt["returned_evidence_ids"] = [
                item.get("evidence_id")
                for item in result.get("results", [])
                if isinstance(item, dict)
                and item.get("evidence_id") is not None
            ]
            attempt["new_evidence_ids"] = list(
                result.get("new_evidence_ids", [])
            )

            self.tool_attempts.append(attempt)
            return result

        except Exception as exc:
            attempt["error"] = (
                f"{type(exc).__name__}: {exc}"
            )
            self.tool_attempts.append(attempt)
            raise


def prepare_case(case: BenchmarkCase) -> dict[str, Any]:
    """Check that the context builder hides the intended evidence."""

    context = build_incident_context(
        case.incident,
        case.evidence,
    )

    context_data = json.loads(context)

    initial_ids = [
        item["evidence_id"]
        for item in context_data["evidence"]
    ]

    all_ids = {item.id for item in case.evidence}
    hidden_ids = set(case.hidden_evidence_ids)

    if not hidden_ids.issubset(all_ids):
        raise ValueError(
            f"{case.case_id}: hidden evidence IDs are not in the "
            "incident evidence collection."
        )

    visible_hidden_ids = hidden_ids.intersection(initial_ids)

    if visible_hidden_ids:
        raise ValueError(
            f"{case.case_id}: expected hidden evidence appeared "
            f"in initial context: {sorted(visible_hidden_ids)}"
        )

    if not hidden_ids and len(initial_ids) != len(all_ids):
        raise ValueError(
            f"{case.case_id}: visible-evidence case unexpectedly "
            "lost evidence from its initial context."
        )

    return {
        "incident_context": context,
        "initial_context_evidence_ids": initial_ids,
        "hidden_evidence_ids": sorted(hidden_ids),
        "excluded_from_initial_context_ids": sorted(
            all_ids - set(initial_ids)
        ),
        "context_characters": len(context),
    }


def score_investigation(
    case: BenchmarkCase,
    investigation: Any,
    executor: BenchmarkLoggingExecutor | None,
) -> dict[str, Any]:
    """Score retrieval, evidence citations, and expected findings."""

    observed_facts = [
        {
            "statement": fact.statement,
            "evidence_ids": list(fact.evidence_ids),
        }
        for fact in investigation.observed_facts
    ]

    hypotheses = [
        {
            "explanation": hypothesis.explanation,
            "evidence_ids": list(
                hypothesis.supporting_evidence_ids
            ),
            "confidence": hypothesis.confidence.value,
        }
        for hypothesis in investigation.hypotheses
    ]

    all_cited_ids = {
        evidence_id
        for fact in observed_facts
        for evidence_id in fact["evidence_ids"]
    }

    all_cited_ids.update(
        evidence_id
        for hypothesis in hypotheses
        for evidence_id in hypothesis["evidence_ids"]
    )

    all_valid_ids = {item.id for item in case.evidence}
    invalid_cited_ids = sorted(all_cited_ids - all_valid_ids)

    attempts = (
        executor.tool_attempts
        if executor is not None
        else []
    )

    returned_ids = {
        evidence_id
        for attempt in attempts
        for evidence_id in attempt["returned_evidence_ids"]
    }

    new_ids = {
        evidence_id
        for attempt in attempts
        for evidence_id in attempt["new_evidence_ids"]
    }

    hidden_ids = set(case.hidden_evidence_ids)

    finding_results = []

    for finding in case.expected_findings:
        matching_facts = []

        for fact in observed_facts:
            statement = fact["statement"].casefold()

            if all(
                term.casefold() in statement
                for term in finding.terms
            ):
                matching_facts.append(fact)

        matching_citations = {
            evidence_id
            for fact in matching_facts
            for evidence_id in fact["evidence_ids"]
        }

        required_ids = set(finding.required_evidence_ids)

        finding_results.append(
            {
                "name": finding.name,
                "matched_in_observed_fact": bool(matching_facts),
                "required_evidence_ids": sorted(required_ids),
                "cited_required_evidence_ids": sorted(
                    required_ids.intersection(matching_citations)
                ),
                "all_required_evidence_cited": (
                    required_ids.issubset(matching_citations)
                ),
            }
        )

    return {
        "observed_facts": observed_facts,
        "hypotheses": hypotheses,
        "reported_information": investigation.reported_information,
        "recommended_checks": investigation.recommended_checks,
        "unknowns": investigation.unknowns,
        "tool_invocations": len(attempts),
        "accepted_executor_calls": (
            executor.call_count if executor is not None else 0
        ),
        "successful_searches": sum(
            attempt["ok"] is True for attempt in attempts
        ),
        "searches_returning_new_evidence": sum(
            bool(attempt["new_evidence_ids"])
            for attempt in attempts
        ),
        "searches_without_new_evidence": sum(
            not attempt["new_evidence_ids"]
            for attempt in attempts
        ),
        "search_queries": [
            attempt["arguments"].get("query")
            for attempt in attempts
            if isinstance(attempt["arguments"], dict)
        ],
        "tool_attempt_details": attempts,
        "returned_evidence_ids": sorted(returned_ids),
        "new_evidence_ids": sorted(new_ids),
        "hidden_evidence_retrieved_ids": sorted(
            hidden_ids.intersection(returned_ids)
        ),
        "hidden_evidence_retrieval_recall": (
            round(
                len(hidden_ids.intersection(returned_ids))
                / len(hidden_ids),
                4,
            )
            if hidden_ids
            else None
        ),
        "hidden_evidence_cited_ids": sorted(
            hidden_ids.intersection(all_cited_ids)
        ),
        "hidden_evidence_citation_recall": (
            round(
                len(hidden_ids.intersection(all_cited_ids))
                / len(hidden_ids),
                4,
            )
            if hidden_ids
            else None
        ),
        "all_cited_evidence_ids": sorted(all_cited_ids),
        "invalid_cited_evidence_ids": invalid_cited_ids,
        "expected_findings": finding_results,
        "expected_findings_matched": sum(
            item["matched_in_observed_fact"]
            for item in finding_results
        ),
        "expected_findings_fully_grounded": sum(
            item["matched_in_observed_fact"]
            and item["all_required_evidence_cited"]
            for item in finding_results
        ),
        "expected_findings_total": len(finding_results),
    }


def run_case(
    case: BenchmarkCase,
    *,
    client: OllamaClient,
    evidence_retriever: EvidenceRetriever,
) -> dict[str, Any]:
    """Run one case through the production investigation service."""

    prepared = prepare_case(case)

    BenchmarkLoggingExecutor.instances.clear()

    original_executor = (
        investigation_service.InvestigationToolExecutor
    )

    investigation_service.InvestigationToolExecutor = (
        BenchmarkLoggingExecutor
    )

    started_at = time.perf_counter()

    try:
        investigation = investigation_service.run_ai_investigation(
            incident=case.incident,
            evidence=case.evidence,
            client=client,
            evidence_retriever=evidence_retriever,
        )

        latency = time.perf_counter() - started_at

        executor = (
            BenchmarkLoggingExecutor.instances[-1]
            if BenchmarkLoggingExecutor.instances
            else None
        )

        evaluation = score_investigation(
            case,
            investigation,
            executor,
        )

        return {
            "case_id": case.case_id,
            "title": case.title,
            "description": case.description,
            "status": "success",
            **prepared,
            "latency_seconds": round(latency, 3),
            "evaluation": evaluation,
            "investigation": investigation.model_dump(
                mode="json"
            ),
        }

    except Exception as exc:
        latency = time.perf_counter() - started_at

        executor = (
            BenchmarkLoggingExecutor.instances[-1]
            if BenchmarkLoggingExecutor.instances
            else None
        )

        return {
            "case_id": case.case_id,
            "title": case.title,
            "description": case.description,
            "status": "failed",
            **prepared,
            "latency_seconds": round(latency, 3),
            "error": f"{type(exc).__name__}: {exc}",
            "tool_attempt_details": (
                executor.tool_attempts
                if executor is not None
                else []
            ),
        }

    finally:
        investigation_service.InvestigationToolExecutor = (
            original_executor
        )


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [
        result
        for result in results
        if result["status"] == "success"
    ]

    evaluations = [
        result["evaluation"]
        for result in successful
    ]

    total_hidden = sum(
        len(result["hidden_evidence_ids"])
        for result in successful
    )

    retrieved_hidden = sum(
        len(item["hidden_evidence_retrieved_ids"])
        for item in evaluations
    )

    cited_hidden = sum(
        len(item["hidden_evidence_cited_ids"])
        for item in evaluations
    )

    expected_findings = sum(
        item["expected_findings_total"]
        for item in evaluations
    )

    matched_findings = sum(
        item["expected_findings_matched"]
        for item in evaluations
    )

    grounded_findings = sum(
        item["expected_findings_fully_grounded"]
        for item in evaluations
    )

    total_tool_invocations = sum(
        item["tool_invocations"]
        for item in evaluations
    )

    return {
        "total_cases": len(results),
        "successful_cases": len(successful),
        "failed_cases": len(results) - len(successful),
        "total_tool_invocations": total_tool_invocations,
        "total_successful_searches": sum(
            item["successful_searches"]
            for item in evaluations
        ),
        "total_searches_returning_new_evidence": sum(
            item["searches_returning_new_evidence"]
            for item in evaluations
        ),
        "hidden_evidence_expected": total_hidden,
        "hidden_evidence_retrieved": retrieved_hidden,
        "hidden_evidence_cited": cited_hidden,
        "hidden_evidence_retrieval_recall": (
            round(retrieved_hidden / total_hidden, 4)
            if total_hidden
            else None
        ),
        "hidden_evidence_citation_recall": (
            round(cited_hidden / total_hidden, 4)
            if total_hidden
            else None
        ),
        "expected_findings": expected_findings,
        "expected_findings_matched": matched_findings,
        "expected_findings_fully_grounded": grounded_findings,
        "expected_finding_match_rate": (
            round(matched_findings / expected_findings, 4)
            if expected_findings
            else None
        ),
        "expected_finding_grounding_rate": (
            round(grounded_findings / expected_findings, 4)
            if expected_findings
            else None
        ),
        "mean_latency_seconds": (
            round(
                sum(
                    result["latency_seconds"]
                    for result in successful
                )
                / len(successful),
                3,
            )
            if successful
            else None
        ),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Ollama tool selection and semantic evidence "
            "retrieval in OpsPilot investigations."
        )
    )

    parser.add_argument(
        "--case",
        choices=["TU-01", "TU-02", "TU-03", "TU-04"],
        help="Run only one benchmark case.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the JSON result file.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing output file.",
    )

    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate scenario construction without calling Ollama.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    llm_provider = get_llm_provider()
    embedding_provider = get_embedding_provider()

    if llm_provider != "ollama":
        raise RuntimeError(
            "This benchmark requires LLM_PROVIDER=ollama. "
            f"Current provider: {llm_provider}"
        )

    if embedding_provider != "ollama":
        raise RuntimeError(
            "This benchmark requires EMBEDDING_PROVIDER=ollama. "
            f"Current provider: {embedding_provider}"
        )

    cases = build_cases()

    selected_cases = (
        [cases[args.case]]
        if args.case
        else list(cases.values())
    )

    print("OpsPilot tool-use benchmark")
    print("===========================")
    print("LLM provider:", llm_provider)
    print("Embedding provider:", embedding_provider)
    print("Cases selected:", len(selected_cases))

    preflight_results = []

    for case in selected_cases:
        prepared = prepare_case(case)

        preflight_results.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "initial_context_evidence_ids": (
                    prepared["initial_context_evidence_ids"]
                ),
                "hidden_evidence_ids": (
                    prepared["hidden_evidence_ids"]
                ),
                "excluded_from_initial_context_ids": (
                    prepared["excluded_from_initial_context_ids"]
                ),
                "context_characters": (
                    prepared["context_characters"]
                ),
            }
        )

    print("\nPreflight:")
    print(json.dumps(preflight_results, indent=2))

    if args.preflight_only:
        print("\nPreflight completed. No model calls were made.")
        return

    output_path = args.output

    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path

    if output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}\n"
            "Choose another --output path or pass --overwrite."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("\nInitializing Ollama client and semantic retriever...")

    client = OllamaClient()
    evidence_retriever = EvidenceRetriever()

    results = []

    for index, case in enumerate(selected_cases, start=1):
        print(
            f"\n[{index}/{len(selected_cases)}] "
            f"Running {case.case_id}: {case.title}"
        )

        result = run_case(
            case,
            client=client,
            evidence_retriever=evidence_retriever,
        )

        results.append(result)

        if result["status"] == "success":
            evaluation = result["evaluation"]

            print("Status: SUCCESS")
            print(
                "Tool invocations:",
                evaluation["tool_invocations"],
            )
            print(
                "Successful searches:",
                evaluation["successful_searches"],
            )
            print(
                "Retrieved hidden evidence:",
                evaluation["hidden_evidence_retrieved_ids"],
            )
            print(
                "Cited hidden evidence:",
                evaluation["hidden_evidence_cited_ids"],
            )
            print(
                "Expected findings grounded:",
                (
                    evaluation["expected_findings_fully_grounded"],
                    evaluation["expected_findings_total"],
                ),
            )
            print(
                "Latency:",
                result["latency_seconds"],
                "seconds",
            )
        else:
            print("Status: FAILED")
            print("Error:", result["error"])

    summary = build_summary(results)

    output = {
        "benchmark": "OpsPilot Tool-Use Evaluation",
        "version": "tool_use_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "llm_provider": llm_provider,
            "embedding_provider": embedding_provider,
            "llm_model": "configured Ollama model",
            "embedding_model": "configured Ollama embedding model",
            "retrieval_mode": "EvidenceRetriever semantic retrieval",
        },
        "summary": summary,
        "cases": results,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("\nBenchmark summary")
    print("=================")
    print(json.dumps(summary, indent=2))
    print("\nResults saved to:", output_path)


if __name__ == "__main__":
    main()
