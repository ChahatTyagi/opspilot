
import argparse
import json
import re
import time

from pathlib import Path
from types import SimpleNamespace

from app.incident_context import build_incident_context
from app.ollama_client import OllamaClient
from app.ollama_investigation import (
    generate_ollama_investigation_with_tools,
)
from app.tool_executor import InvestigationToolExecutor

from experiments.fact_grounding_cases import (
    ExpectedFact,
    FactGroundingCase,
    build_fact_grounding_cases,
    validate_fact_grounding_cases,
)


RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_OUTPUT = RESULTS_DIR / "fact_grounding_v5.json"


# =============================================================
# TEXT NORMALIZATION AND EXPECTED-FACT MATCHING
# =============================================================

def normalize_text(value: str) -> str:
    """Normalize text for case-insensitive deterministic matching."""

    return re.sub(r"\s+", " ", value.casefold()).strip()


def matches_expected_fact(
    statement: str,
    expected: ExpectedFact,
) -> bool:
    """
    Check whether a generated statement matches an expected fact.

    All match terms must appear in the generated statement.

    This is deterministic lexical matching, not semantic evaluation.
    """

    normalized = normalize_text(statement)

    return all(
        normalize_text(term) in normalized
        for term in expected.match_terms
    )


# =============================================================
# INDIVIDUAL FACT EVALUATION
# =============================================================

def evaluate_fact(
    *,
    statement: str,
    evidence_ids: list[int],
    case: FactGroundingCase,
    matched_expected: ExpectedFact | None,
) -> dict:
    """
    Evaluate one generated fact against its expected evidence.

    Primary classifications:
        grounded
        incomplete
        citation_error
        contradicted
        unmatched_or_incomplete
    """

    available_ids = {item.id for item in case.evidence}
    cited_ids = set(evidence_ids)

    invalid_ids = sorted(cited_ids - available_ids)

    result = {
        "statement": statement,
        "evidence_ids": evidence_ids,
        "matched_expected_fact": matched_expected is not None,
        "classification": "unmatched_or_incomplete",
        "grounded": False,
        "numeric_and_detail_checks_passed": False,
        "citation_checks_passed": False,
        "invalid_evidence_ids": invalid_ids,
        "failed_checks": [],
    }

    # Do not assume an unmatched statement is a hallucination.
    if matched_expected is None:
        result["failed_checks"].append(
            "No independently labeled expected fact matched this statement. "
            "Its factual correctness cannot be determined by this evaluator."
        )
        return result

    # Check required details such as values, units, and timestamps.
    required_patterns_pass = all(
        re.search(pattern, statement, flags=re.IGNORECASE) is not None
        for pattern in matched_expected.required_patterns
    )

    # Check for explicitly prohibited assertions.
    forbidden_patterns_found = [
        pattern
        for pattern in matched_expected.forbidden_patterns
        if re.search(pattern, statement, flags=re.IGNORECASE)
    ]

    detail_checks_pass = (
        required_patterns_pass
        and not forbidden_patterns_found
    )

    # Check whether the generated fact cites the expected evidence.
    expected_ids = set(matched_expected.supporting_evidence_ids)

    citations_pass = (
        not invalid_ids
        and expected_ids.issubset(cited_ids)
        and bool(cited_ids)
    )

    result["numeric_and_detail_checks_passed"] = detail_checks_pass
    result["citation_checks_passed"] = citations_pass

    if not required_patterns_pass:
        result["failed_checks"].append(
            "One or more required values, units, or details are missing."
        )

    if forbidden_patterns_found:
        result["failed_checks"].append(
            "The statement contains a prohibited or unsupported assertion."
        )

    if invalid_ids:
        result["failed_checks"].append(
            "The statement cites evidence IDs unavailable in this case."
        )

    if not expected_ids.issubset(cited_ids):
        result["failed_checks"].append(
            "The statement does not cite all expected supporting evidence."
        )

    if not cited_ids:
        result["failed_checks"].append(
            "The statement has no evidence citations."
        )

    # Assign one primary classification.
    if forbidden_patterns_found:
        classification = "contradicted"

    elif not required_patterns_pass:
        classification = "incomplete"

    elif not citations_pass:
        classification = "citation_error"

    else:
        classification = "grounded"

    result["classification"] = classification
    result["grounded"] = classification == "grounded"

    return result


# =============================================================
# INFORMATION-PRESERVATION EVALUATION
# =============================================================

def evaluate_information_preservation(
    *,
    case: FactGroundingCase,
    investigation,
) -> dict:
    """
    Evaluate whether expected information is fully, partially,
    or not preserved across investigation output fields.

    This metric is separate from observed-fact grounding.

    A complete match requires:
    - All expected match terms.
    - Every required regex pattern.
    - No forbidden regex pattern.

    A partial match contains at least one expected match term
    but does not satisfy all complete-match requirements.

    Matching is deterministic and does not establish semantic correctness.
    """

    output_fields = {
        "observed_facts": [
            fact.statement
            for fact in investigation.observed_facts
        ],
        "reported_information": investigation.reported_information,
        "recommended_checks": investigation.recommended_checks,
        "unknowns": investigation.unknowns,
    }

    preserved_items = [
        {
            "field": field_name,
            "text": str(item),
        }
        for field_name, items in output_fields.items()
        for item in items
        if item is not None
    ]

    expected_results = []

    for index, expected in enumerate(case.expected_facts):
        candidates = []
        complete_matches = []

        for item in preserved_items:
            normalized = normalize_text(item["text"])

            # At least one match term makes this output relevant.
            has_relevant_term = any(
                normalize_text(term) in normalized
                for term in expected.match_terms
            )

            if not has_relevant_term:
                continue

            candidates.append(item)

            # A complete match requires every match term.
            has_all_match_terms = matches_expected_fact(
                item["text"],
                expected,
            )

            # Every required detail must be present.
            has_required_details = all(
                re.search(
                    pattern,
                    item["text"],
                    flags=re.IGNORECASE,
                ) is not None
                for pattern in expected.required_patterns
            )

            # Forbidden patterns invalidate a complete match.
            has_forbidden_content = any(
                re.search(
                    pattern,
                    item["text"],
                    flags=re.IGNORECASE,
                ) is not None
                for pattern in expected.forbidden_patterns
            )

            if (
                has_all_match_terms
                and has_required_details
                and not has_forbidden_content
            ):
                complete_matches.append(item)

        if complete_matches:
            status = "preserved"
            selected_matches = complete_matches

        elif candidates:
            status = "partial"
            selected_matches = candidates

        else:
            status = "missing"
            selected_matches = []

        expected_results.append({
            "expected_fact_index": index,
            "match_terms": list(expected.match_terms),
            "status": status,
            "preserved": status == "preserved",
            "partially_preserved": status == "partial",
            "matched_fields": sorted({
                item["field"] for item in selected_matches
            }),
            "matched_text": [
                item["text"] for item in selected_matches
            ],
            "complete_match_count": len(complete_matches),
            "partial_match_count": (
                len(candidates) if status == "partial" else 0
            ),
        })

    expected_count = len(expected_results)

    preserved_count = sum(
        item["status"] == "preserved"
        for item in expected_results
    )

    partial_count = sum(
        item["status"] == "partial"
        for item in expected_results
    )

    missing_count = sum(
        item["status"] == "missing"
        for item in expected_results
    )

    recall = (
        preserved_count / expected_count
        if expected_count
        else 1.0
    )

    return {
        "expected_information_count": expected_count,
        "preserved_information_count": preserved_count,
        "partially_preserved_information_count": partial_count,
        "missing_information_count": missing_count,
        "information_preservation_recall": round(recall, 4),
        "information_items": expected_results,
    }


# =============================================================
# INVESTIGATION-LEVEL EVALUATION
# =============================================================

def evaluate_investigation(
    *,
    case: FactGroundingCase,
    investigation,
) -> dict:
    """Evaluate observed facts and information preservation separately."""

    expected_facts = list(case.expected_facts)

    information_preservation = evaluate_information_preservation(
        case=case,
        investigation=investigation,
    )

    # These sets track unique expected facts, not generated statements.
    matched_expected_indexes = set()
    grounded_expected_indexes = set()

    evaluated_facts = []

    for fact in investigation.observed_facts:
        matched_expected = None
        matched_index = None

        # Allow multiple generated statements to match the same
        # independently labeled expected fact.
        for index, expected in enumerate(expected_facts):
            if matches_expected_fact(fact.statement, expected):
                matched_expected = expected
                matched_index = index
                break

        # The first match is not a repeat; subsequent matches are.
        is_repeated_match = (
            matched_index in matched_expected_indexes
            if matched_index is not None
            else False
        )

        if matched_index is not None:
            matched_expected_indexes.add(matched_index)

        evaluated = evaluate_fact(
            statement=fact.statement,
            evidence_ids=fact.evidence_ids,
            case=case,
            matched_expected=matched_expected,
        )

        evaluated["matched_expected_fact_index"] = matched_index
        evaluated["is_repeated_match"] = is_repeated_match

        # A unique expected fact counts as grounded if at least one
        # generated statement matching it passes every grounding check.
        if (
            matched_index is not None
            and evaluated["classification"] == "grounded"
        ):
            grounded_expected_indexes.add(matched_index)

        evaluated_facts.append(evaluated)

    expected_count = len(expected_facts)
    generated_count = len(evaluated_facts)

    matched_count = len(matched_expected_indexes)
    grounded_expected_count = len(grounded_expected_indexes)

    repeated_match_count = sum(
        fact["is_repeated_match"]
        for fact in evaluated_facts
    )

    # These are statement-level counts.
    grounded_count = sum(
        fact["classification"] == "grounded"
        for fact in evaluated_facts
    )

    incomplete_count = sum(
        fact["classification"] == "incomplete"
        for fact in evaluated_facts
    )

    citation_error_count = sum(
        fact["classification"] == "citation_error"
        for fact in evaluated_facts
    )

    contradicted_count = sum(
        fact["classification"] == "contradicted"
        for fact in evaluated_facts
    )

    unmatched_count = sum(
        fact["classification"] == "unmatched_or_incomplete"
        for fact in evaluated_facts
    )

    # A fact can fail both detail and citation checks.
    detail_check_failure_count = sum(
        fact["matched_expected_fact"]
        and not fact["numeric_and_detail_checks_passed"]
        for fact in evaluated_facts
    )

    citation_check_failure_count = sum(
        fact["matched_expected_fact"]
        and not fact["citation_checks_passed"]
        for fact in evaluated_facts
    )

    # Statement-level grounded precision.
    if generated_count:
        grounded_precision = grounded_count / generated_count
    else:
        grounded_precision = (
            1.0 if expected_count == 0 else 0.0
        )

    # Unique expected facts matched by at least one generated statement.
    if expected_count:
        fact_match_recall = matched_count / expected_count
    else:
        fact_match_recall = (
            1.0 if generated_count == 0 else 0.0
        )

    # Unique expected facts with at least one fully grounded statement.
    if expected_count:
        grounded_recall = grounded_expected_count / expected_count
    else:
        grounded_recall = (
            1.0 if generated_count == 0 else 0.0
        )

    all_citations = [
        evidence_id
        for fact in evaluated_facts
        for evidence_id in fact["evidence_ids"]
    ]

    available_ids = {item.id for item in case.evidence}

    invalid_citation_count = sum(
        evidence_id not in available_ids
        for evidence_id in all_citations
    )

    return {
        "case_id": case.case_id,
        "title": case.title,

        "expected_fact_count": expected_count,
        "generated_fact_count": generated_count,
        "matched_expected_fact_count": matched_count,
        "grounded_expected_fact_count": grounded_expected_count,
        "repeated_match_count": repeated_match_count,

        "grounded_fact_count": grounded_count,
        "incomplete_fact_count": incomplete_count,
        "citation_error_fact_count": citation_error_count,
        "contradicted_fact_count": contradicted_count,
        "unmatched_fact_count": unmatched_count,

        "detail_check_failure_count": detail_check_failure_count,
        "citation_check_failure_count": citation_check_failure_count,
        "invalid_citation_count": invalid_citation_count,

        "grounded_fact_precision": round(grounded_precision, 4),
        "fact_match_recall": round(fact_match_recall, 4),
        "grounded_fact_recall": round(grounded_recall, 4),

        "information_preservation": information_preservation,

        "facts": evaluated_facts,
    }


# =============================================================
# SYNTHETIC INCIDENT CONSTRUCTION
# =============================================================

def build_synthetic_objects(
    case: FactGroundingCase,
) -> tuple[SimpleNamespace, list[SimpleNamespace]]:
    """Create in-memory objects compatible with production components."""

    incident_id = int(case.case_id.split("-")[1])

    incident = SimpleNamespace(
        id=incident_id,
        title=case.title,
        description=case.description,
        service=case.service,
        environment=case.environment,
        severity=case.severity,
        status="open",
        created_at=None,
    )

    evidence_items = [
        SimpleNamespace(
            id=item.id,
            incident_id=incident_id,
            source_type=item.source_type,
            content=item.content,
            created_at=None,
        )
        for item in case.evidence
    ]

    return incident, evidence_items


# =============================================================
# PRODUCTION INVESTIGATOR EXECUTION
# =============================================================

def run_case(
    *,
    case: FactGroundingCase,
    client: OllamaClient,
) -> dict:
    """
    Run the real production investigator on one synthetic incident.

    Uses the production incident context builder, Ollama investigator,
    and evidence-search executor.
    """

    incident, evidence_items = build_synthetic_objects(case)

    incident_context = build_incident_context(
        incident,
        evidence_items,
    )

    executor = InvestigationToolExecutor(
        incident_id=incident.id,
        evidence_items=evidence_items,
    )

    started_at = time.perf_counter()

    investigation = generate_ollama_investigation_with_tools(
        incident_context=incident_context,
        executor=executor,
        client=client,
    )

    latency_seconds = time.perf_counter() - started_at

    evaluation = evaluate_investigation(
        case=case,
        investigation=investigation,
    )

    evaluation["status"] = "success"
    evaluation["latency_seconds"] = round(latency_seconds, 3)
    evaluation["tool_calls"] = executor.call_count

    # Keep the complete structured output for manual inspection.
    evaluation["investigation"] = investigation.model_dump(mode="json")

    return evaluation


# =============================================================
# AGGREGATE BENCHMARK METRICS
# =============================================================

def calculate_overall_metrics(results: list[dict]) -> dict:
    """Calculate aggregate metrics across successful benchmark cases."""

    successful = [
        result
        for result in results
        if result["status"] == "success"
    ]

    failed = len(results) - len(successful)

    def total(field: str) -> int:
        return sum(
            result.get(field, 0)
            for result in successful
        )

    expected_count = total("expected_fact_count")
    generated_count = total("generated_fact_count")
    matched_count = total("matched_expected_fact_count")

    grounded_count = total("grounded_fact_count")
    grounded_expected_count = total("grounded_expected_fact_count")
    repeated_match_count = total("repeated_match_count")

    incomplete_count = total("incomplete_fact_count")
    citation_error_count = total("citation_error_fact_count")
    contradicted_count = total("contradicted_fact_count")
    unmatched_count = total("unmatched_fact_count")

    detail_failures = total("detail_check_failure_count")
    citation_failures = total("citation_check_failure_count")
    invalid_citations = total("invalid_citation_count")

    # Aggregate information-preservation results.
    expected_information = sum(
        result["information_preservation"]["expected_information_count"]
        for result in successful
    )

    preserved_information = sum(
        result["information_preservation"]["preserved_information_count"]
        for result in successful
    )

    partially_preserved_information = sum(
        result["information_preservation"][
            "partially_preserved_information_count"
        ]
        for result in successful
    )

    missing_information = sum(
        result["information_preservation"]["missing_information_count"]
        for result in successful
    )

    information_preservation_recall = (
        preserved_information / expected_information
        if expected_information
        else 0.0
    )

    # Statement-level grounded precision.
    grounded_precision = (
        grounded_count / generated_count
        if generated_count
        else 0.0
    )

    # Unique expected-fact matching recall.
    fact_match_recall = (
        matched_count / expected_count
        if expected_count
        else 0.0
    )

    # Unique expected facts with at least one grounded statement.
    grounded_recall = (
        grounded_expected_count / expected_count
        if expected_count
        else 0.0
    )

    latencies = [
        result["latency_seconds"]
        for result in successful
        if result.get("latency_seconds") is not None
    ]

    return {
        "total_cases": len(results),
        "successful_cases": len(successful),
        "failed_cases": failed,

        "expected_facts": expected_count,
        "generated_facts": generated_count,
        "matched_expected_facts": matched_count,
        "grounded_expected_facts": grounded_expected_count,
        "repeated_matches": repeated_match_count,

        "grounded_facts": grounded_count,
        "incomplete_facts": incomplete_count,
        "citation_error_facts": citation_error_count,
        "contradicted_facts": contradicted_count,
        "unmatched_facts": unmatched_count,

        "detail_check_failures": detail_failures,
        "citation_check_failures": citation_failures,
        "invalid_citations": invalid_citations,

        "grounded_fact_precision": round(grounded_precision, 4),
        "fact_match_recall": round(fact_match_recall, 4),
        "grounded_fact_recall": round(grounded_recall, 4),

        "expected_information": expected_information,
        "preserved_information": preserved_information,
        "partially_preserved_information": (
            partially_preserved_information
        ),
        "missing_information": missing_information,
        "information_preservation_recall": round(
            information_preservation_recall, 4
        ),

        "mean_latency_seconds": (
            round(sum(latencies) / len(latencies), 3)
            if latencies
            else None
        ),
    }


# =============================================================
# COMMAND-LINE ARGUMENTS
# =============================================================

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run OpsPilot Fact Grounding Evaluation v5."
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the JSON benchmark report.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases for a preliminary check.",
    )

    return parser.parse_args()


# =============================================================
# MAIN BENCHMARK EXECUTION
# =============================================================

def main():
    args = parse_arguments()

    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1.")

    cases = build_fact_grounding_cases()
    validate_fact_grounding_cases(cases)

    if args.limit is not None:
        cases = cases[:args.limit]

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Refuse to overwrite a previous benchmark result.
    if output_path.exists():
        raise SystemExit(
            f"Output already exists: {output_path}\n"
            "Choose another --output path to preserve the previous report."
        )

    client = OllamaClient()

    print("=" * 65)
    print("OPSPILOT FACT GROUNDING EVALUATION V5")
    print("=" * 65)
    print(f"Model: {client.model}")
    print(f"Cases: {len(cases)}")
    print(f"Expected facts: {sum(len(c.expected_facts) for c in cases)}")
    print(f"Output: {output_path}")
    print()

    results = []

    for index, case in enumerate(cases, start=1):
        print(
            f"[{index}/{len(cases)}] Running {case.case_id}: "
            f"{case.title}"
        )

        try:
            result = run_case(
                case=case,
                client=client,
            )

            preservation = result["information_preservation"]

            print(
                f"  Generated: {result['generated_fact_count']} | "
                f"Grounded statements: {result['grounded_fact_count']} | "
                f"Grounded expected facts: "
                f"{result['grounded_expected_fact_count']} | "
                f"Repeated matches: {result['repeated_match_count']} | "
                f"Incomplete: {result['incomplete_fact_count']} | "
                f"Citation errors: {result['citation_error_fact_count']} | "
                f"Contradicted: {result['contradicted_fact_count']} | "
                f"Unmatched: {result['unmatched_fact_count']} | "
                f"Information preserved: "
                f"{preservation['preserved_information_count']}/"
                f"{preservation['expected_information_count']} | "
                f"Partial: "
                f"{preservation['partially_preserved_information_count']} | "
                f"Missing: "
                f"{preservation['missing_information_count']} | "
                f"Latency: {result['latency_seconds']:.2f}s"
            )

        except Exception as exc:
            result = {
                "case_id": case.case_id,
                "title": case.title,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

            print(f"  FAILED: {result['error']}")

        results.append(result)
        print()

    metrics = calculate_overall_metrics(results)

    report = {
        "benchmark": "OpsPilot Fact Grounding Evaluation v5",
        "model": client.model,
        "dataset_version": "v3",
        "evaluation_method": (
            "Observed facts are evaluated using deterministic matching "
            "against manually labeled expected facts, required and forbidden "
            "regex checks, and evidence citation validation. Multiple "
            "generated statements may match the same expected fact. "
            "Grounded recall counts unique expected facts with at least one "
            "fully grounded generated statement, while grounded precision "
            "is calculated over generated statements. Repeated matches are "
            "reported separately. Information preservation is evaluated "
            "separately across observed_facts, reported_information, "
            "recommended_checks, and unknowns. Each expected information "
            "item is classified as preserved, partial, or missing. A "
            "preserved item must contain all expected match terms, all "
            "required regex details, and no forbidden pattern. A partial "
            "item contains at least one relevant match term but does not "
            "satisfy all complete-match requirements. Preservation recall "
            "counts only fully preserved information. Unmatched statements "
            "are not automatically classified as hallucinations. Both "
            "evaluators use deterministic lexical matching and are not "
            "semantic judges."
        ),
        "results": results,
        "metrics": metrics,
    }

    # Exclusive creation prevents accidental replacement.
    with output_path.open("x", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )

    print("=" * 65)
    print("FACT GROUNDING V5 SUMMARY")
    print("=" * 65)

    print(f"Successful cases: {metrics['successful_cases']}")
    print(f"Failed cases: {metrics['failed_cases']}")
    print(f"Expected facts: {metrics['expected_facts']}")
    print(f"Generated facts: {metrics['generated_facts']}")
    print(f"Matched expected facts: {metrics['matched_expected_facts']}")
    print(f"Grounded expected facts: {metrics['grounded_expected_facts']}")
    print(f"Grounded statements: {metrics['grounded_facts']}")
    print(f"Repeated matches: {metrics['repeated_matches']}")
    print(f"Incomplete facts: {metrics['incomplete_facts']}")
    print(f"Citation errors: {metrics['citation_error_facts']}")
    print(f"Contradicted facts: {metrics['contradicted_facts']}")
    print(f"Unmatched facts: {metrics['unmatched_facts']}")

    print()
    print(
        "Grounded fact precision: "
        f"{metrics['grounded_fact_precision']:.2%}"
    )
    print(
        "Expected-fact match recall: "
        f"{metrics['fact_match_recall']:.2%}"
    )
    print(
        "Grounded fact recall: "
        f"{metrics['grounded_fact_recall']:.2%}"
    )

    print()
    print(f"Expected information: {metrics['expected_information']}")
    print(f"Preserved information: {metrics['preserved_information']}")
    print(
        "Partially preserved information: "
        f"{metrics['partially_preserved_information']}"
    )
    print(f"Missing information: {metrics['missing_information']}")
    print(
        "Information preservation recall: "
        f"{metrics['information_preservation_recall']:.2%}"
    )

    print()
    print(f"Invalid citations: {metrics['invalid_citations']}")
    print(f"Mean latency: {metrics['mean_latency_seconds']} seconds")
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
