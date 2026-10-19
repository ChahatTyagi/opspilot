
from types import SimpleNamespace

from app.analyzer import analyze_evidence, normalize_error


def make_evidence(
    evidence_id: int,
    source_type: str,
    content: str,
):
    return SimpleNamespace(
        id=evidence_id,
        source_type=source_type,
        content=content,
    )


def test_groups_repeated_error_patterns():
    evidence = [
        make_evidence(
            1,
            "log",
            "ERROR database connection failed for request 123",
        ),
        make_evidence(
            2,
            "log",
            "ERROR database connection failed for request 456",
        ),
    ]

    result = analyze_evidence(7, evidence)

    assert result.incident_id == 7
    assert result.logs_analyzed == 2
    assert result.error_lines_detected == 2
    assert len(result.recurring_patterns) == 1
    assert result.recurring_patterns[0].occurrences == 2
    assert result.recurring_patterns[0].evidence_ids == [1, 2]


def test_ignores_non_log_evidence():
    evidence = [
        make_evidence(1, "note", "ERROR something failed"),
        make_evidence(2, "deployment", "Deployment failed"),
    ]

    result = analyze_evidence(7, evidence)

    assert result.logs_analyzed == 0
    assert result.error_lines_detected == 0
    assert result.recurring_patterns == []


def test_no_recurring_pattern_for_single_error():
    evidence = [
        make_evidence(1, "log", "ERROR request failed"),
    ]

    result = analyze_evidence(7, evidence)

    assert result.error_lines_detected == 1
    assert result.recurring_patterns == []


def test_empty_evidence_returns_valid_analysis():
    result = analyze_evidence(7, [])

    assert result.logs_analyzed == 0
    assert result.error_lines_detected == 0
    assert result.recurring_patterns == []
    assert result.findings


def test_normalization_replaces_variable_numbers():
    first = normalize_error("ERROR request 123 failed")
    second = normalize_error("ERROR request 456 failed")

    assert first == second

def test_filters_generic_recurring_errors():
    evidence = [
        make_evidence(1, "log", "ERROR something failed"),
        make_evidence(2, "log", "ERROR something failed"),
    ]

    result = analyze_evidence(7, evidence)

    assert result.error_lines_detected == 2
    assert result.recurring_patterns == []


def test_keeps_specific_recurring_database_errors():
    evidence = [
        make_evidence(
            1,
            "log",
            "ERROR database connection failed for request 123",
        ),
        make_evidence(
            2,
            "log",
            "ERROR database connection failed for request 456",
        ),
    ]

    result = analyze_evidence(7, evidence)

    assert len(result.recurring_patterns) == 1
    assert result.recurring_patterns[0].occurrences == 2
    assert result.recurring_patterns[0].evidence_ids == [1, 2]

def test_evidence_ids_are_unique_when_log_repeats_pattern():
    evidence = [
        make_evidence(
            1,
            "log",
            (
                "ERROR database connection failed for request 123\n"
                "ERROR database connection failed for request 456"
            ),
        ),
        make_evidence(
            2,
            "log",
            "ERROR database connection failed for request 789",
        ),
    ]

    result = analyze_evidence(7, evidence)

    assert len(result.recurring_patterns) == 1
    pattern = result.recurring_patterns[0]
    assert pattern.occurrences == 3
    assert pattern.evidence_ids == [1, 2]