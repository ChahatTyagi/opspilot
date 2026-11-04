from types import SimpleNamespace

import pytest

from app.tool_executor import InvestigationToolExecutor


def make_evidence(
    evidence_id=10,
    incident_id=42,
    content="Database connection timeout occurred.",
    source_type="log",
):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        content=content,
        source_type=source_type,
    )


@pytest.fixture
def executor():
    return InvestigationToolExecutor(
        incident_id=42,
        evidence_items=[
            make_evidence(
                evidence_id=10,
                content="Database connection timeout occurred.",
            ),
            make_evidence(
                evidence_id=11,
                content="Payment gateway returned HTTP 503.",
            ),
        ],
        max_calls=3,
    )


def test_executor_runs_allowlisted_tool(executor):
    result = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database timeout"},
    )

    assert result["ok"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["evidence_id"] == 10


def test_executor_rejects_unknown_tool(executor):
    result = executor.execute(
        tool_name="run_shell_command",
        arguments={"command": "whoami"},
    )

    assert result["ok"] is False
    assert "Unknown tool" in result["error"]


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        {},
        {"query": "database timeout", "extra": "not allowed"},
        {"query": 123},
    ],
)
def test_executor_rejects_invalid_arguments(executor, arguments):
    result = executor.execute(
        tool_name="search_incident_evidence",
        arguments=arguments,
    )

    assert result["ok"] is False
    assert "argument" in result["error"].lower()


def test_executor_rejects_repeated_identical_call(executor):
    first = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database timeout"},
    )
    second = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database timeout"},
    )

    assert first["ok"] is True
    assert second["ok"] is False
    assert "repeated" in second["error"].lower()


def test_executor_enforces_call_limit():
    executor = InvestigationToolExecutor(
        incident_id=42,
        evidence_items=[make_evidence()],
        max_calls=2,
    )

    first = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database"},
    )
    second = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "timeout"},
    )
    third = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "connection"},
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert third["ok"] is False
    assert "limit" in third["error"].lower()


def test_executor_does_not_expose_internal_exception(executor):
    result = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database timeout"},
    )

    assert result["ok"] is True
    assert "exception" not in result


@pytest.mark.parametrize(
    "max_calls",
    [0, -1, 6, 1.5, True],
)
def test_executor_rejects_invalid_call_limit(max_calls):
    with pytest.raises(ValueError):
        InvestigationToolExecutor(
            incident_id=42,
            evidence_items=[make_evidence()],
            max_calls=max_calls,
        )


def test_executor_rejects_oversized_arguments(executor):
    result = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "x" * 1001},
    )

    assert result["ok"] is False
    assert "size limit" in result["error"].lower()


def test_invalid_request_does_not_consume_call_limit(executor):
    invalid = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database", "unexpected": "value"},
    )
    valid = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database"},
    )

    assert invalid["ok"] is False
    assert valid["ok"] is True
    assert executor.call_count == 1

def test_executor_tracks_only_evidence_returned_by_search(executor):
    result = executor.execute(
        tool_name="search_incident_evidence",
        arguments={"query": "database"},
    )

    assert result["ok"] is True
    assert executor.returned_evidence_ids == {10}