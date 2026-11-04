import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.ai_models import (
    AIConfidence,
    AIFact,
    AIInvestigationResult,
)
from app.investigation_service import run_ai_investigation


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


def make_evidence(evidence_id=10, content="Database timeout"):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=42,
        source_type="log",
        content=content,
        created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )


def make_result(evidence_ids=None):
    return AIInvestigationResult(
        observed_facts=[
            AIFact(
                statement="Database timeout errors were observed.",
                evidence_ids=evidence_ids or [10],
            )
        ],
        hypotheses=[],
        recommended_checks=[],
        unknowns=[],
    )


def test_run_ai_investigation_builds_context_and_validates_result(
    monkeypatch,
):
    expected_result = make_result()
    mock_client = Mock()
    captured = {}

    def fake_generate_investigation(*, incident_context, client):
        captured["context"] = json.loads(incident_context)
        captured["client"] = client
        return expected_result

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation",
        fake_generate_investigation,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
        client=mock_client,
    )

    assert result is expected_result
    assert captured["context"]["incident"]["id"] == 42
    assert captured["context"]["evidence"][0]["evidence_id"] == 10
    assert captured["client"] is mock_client


def test_run_ai_investigation_rejects_unknown_evidence_reference(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.investigation_service.generate_investigation",
        lambda **kwargs: make_result(evidence_ids=[999]),
    )

    with pytest.raises(ValueError, match="999"):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[make_evidence(evidence_id=10)],
        )


def test_run_ai_investigation_rejects_evidence_omitted_from_context(
    monkeypatch,
):
    evidence = [
        make_evidence(
            evidence_id=index,
            content="x" * 2_000,
        )
        for index in range(1, 20)
    ]

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation",
        lambda **kwargs: make_result(evidence_ids=[19]),
    )

    with pytest.raises(ValueError):
        run_ai_investigation(
            incident=make_incident(),
            evidence=evidence,
        )

def test_run_ai_investigation_rejects_evidence_from_another_incident(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.investigation_service.generate_investigation",
        lambda **kwargs: make_result(evidence_ids=[10]),
    )

    with pytest.raises(ValueError, match="belong to incident"):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[
                SimpleNamespace(
                    id=10,
                    incident_id=999,
                    source_type="log",
                    content="Database timeout",
                    created_at=datetime(
                        2026, 11, 4, tzinfo=timezone.utc
                    ),
                )
            ],
        )