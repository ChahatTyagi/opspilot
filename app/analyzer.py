
import re
from collections import defaultdict

from pydantic import BaseModel, Field


ERROR_MARKER = re.compile(
    r"\b(error|exception|traceback|fatal|failed|failure)\b",
    re.IGNORECASE,
)

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

TIMESTAMP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)

NUMBER_PATTERN = re.compile(r"\b\d+\b")


class ErrorPattern(BaseModel):
    pattern: str
    occurrences: int = Field(ge=1)
    evidence_ids: list[int]


class EvidenceAnalysis(BaseModel):
    incident_id: int
    logs_analyzed: int
    error_lines_detected: int
    recurring_patterns: list[ErrorPattern]
    findings: list[str]


def normalize_error(line: str) -> str:
    """Normalize changing values to help group similar error messages."""
    normalized = UUID_PATTERN.sub("<UUID>", line)
    normalized = TIMESTAMP_PATTERN.sub("<TIMESTAMP>", normalized)
    normalized = NUMBER_PATTERN.sub("<N>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:500]


def analyze_evidence(incident_id: int, evidence: list) -> EvidenceAnalysis:
    """Group recurring error patterns found in log evidence."""
    logs = [
        item for item in evidence
        if item.source_type == "log"
    ]

    groups = defaultdict(list)
    error_lines_detected = 0

    for item in logs:
        for line in item.content.splitlines():
            line = line.strip()

            if not line or not ERROR_MARKER.search(line):
                continue

            error_lines_detected += 1
            pattern = normalize_error(line)
            groups[pattern].append(item.id)

    recurring_patterns = [
        ErrorPattern(
            pattern=pattern,
            occurrences=len(evidence_ids),
            evidence_ids=sorted(set(evidence_ids)),
        )
        for pattern, evidence_ids in groups.items()
        if len(evidence_ids) >= 2
    ]

    recurring_patterns.sort(
        key=lambda item: (-item.occurrences, item.pattern)
    )

    if recurring_patterns:
        findings = [
            f"Found {len(recurring_patterns)} recurring error pattern(s)."
        ]
    elif error_lines_detected:
        findings = [
            "Error-like log lines were detected, but no recurring "
            "patterns were found."
        ]
    else:
        findings = [
            "No error-like log lines were detected in the available logs."
        ]

    return EvidenceAnalysis(
        incident_id=incident_id,
        logs_analyzed=len(logs),
        error_lines_detected=error_lines_detected,
        recurring_patterns=recurring_patterns,
        findings=findings,
    )
