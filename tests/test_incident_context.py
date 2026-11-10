import pytest
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.incident_context import (
    MAX_CONTEXT_CHARS,
    MAX_EVIDENCE_CHARS,
    build_incident_context,
)


def make_incident():
    return SimpleNamespace(
        id=42,
        title="Checkout errors",
        description="Checkout requests are failing.",
        service="checkout",
        environment="production",
        severity="high",
        status="open",
        created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )


def make_evidence(
    evidence_id=1,
    content="Connection timeout",
    source_type="log",
    created_at=None,
):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=42,
        source_type=source_type,
        content=content,
        created_at=created_at
        or datetime(2026, 11, 4, tzinfo=timezone.utc),
    )


def test_context_includes_incident_metadata_and_evidence():
    context = build_incident_context(
        make_incident(),
        [make_evidence(evidence_id=7)],
    )

    parsed = json.loads(context)

    assert parsed["incident"]["id"] == 42
    assert parsed["incident"]["service"] == "checkout"
    assert parsed["evidence"][0]["evidence_id"] == 7
    assert parsed["evidence"][0]["source_type"] == "log"
    assert "untrusted data" in parsed["evidence_notice"]


def test_context_with_no_evidence_is_valid():
    context = build_incident_context(make_incident(), [])

    parsed = json.loads(context)

    assert parsed["evidence"] == []


def test_long_evidence_content_is_truncated():
    evidence = make_evidence(content="x" * (MAX_EVIDENCE_CHARS + 500))

    context = build_incident_context(make_incident(), [evidence])
    parsed = json.loads(context)

    content = parsed["evidence"][0]["content"]

    assert len(content) <= MAX_EVIDENCE_CHARS + 40
    assert "[Evidence content truncated]" in content


def test_context_preserves_evidence_order():
    evidence = [
        make_evidence(evidence_id=1, content="first"),
        make_evidence(evidence_id=2, content="second"),
        make_evidence(evidence_id=3, content="third"),
    ]

    context = build_incident_context(make_incident(), evidence)
    parsed = json.loads(context)

    ids = [item["evidence_id"] for item in parsed["evidence"]]

    assert ids == [1, 2, 3]


def test_total_context_size_is_bounded():
    evidence = [
        make_evidence(
            evidence_id=index,
            content="x" * MAX_EVIDENCE_CHARS,
        )
        for index in range(1, 20)
    ]

    context = build_incident_context(make_incident(), evidence)

    assert len(context) <= MAX_CONTEXT_CHARS
    json.loads(context)

def test_raises_if_incident_metadata_exceeds_context_limit():
    incident = make_incident()
    incident.description = "x" * (MAX_CONTEXT_CHARS + 1)

    with pytest.raises(
        ValueError,
        match="exceeds the maximum context size",
    ):
        build_incident_context(incident, [])

def test_context_notice_distinguishes_observations_from_suggestions():
    context = build_incident_context(
        make_incident(),
        [
            make_evidence(
                evidence_id=919,
                content=(
                    "PostgreSQL connection pool exhausted. "
                    "All 50 connections are active. "
                    "Investigate possible connection leak."
                ),
            )
        ],
    )

    parsed = json.loads(context)
    notice = parsed["evidence_notice"]

    assert "recommendations" in notice
    assert "suspicions" in notice
    assert "suggested actions" in notice
    assert "does not prove" in notice
    assert "every relevant directly supported" in notice
