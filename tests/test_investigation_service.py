
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.ai_models import (
    AIConfidence,
    AIFact,
    AIHypothesis,
    AIInvestigationResult,
)
from app.investigation_service import (
    UnsupportedLLMProviderError,
    run_ai_investigation,
)


@pytest.fixture(autouse=True)
def use_openai_provider_by_default(monkeypatch):
    monkeypatch.setattr(
        "app.investigation_service.get_llm_provider",
        lambda: "openai",
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
    evidence_id=10,
    content="Database timeout",
    incident_id=42,
):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
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

    def fake_generate_investigation_with_tools(
        *,
        incident_context,
        executor,
        client,
    ):
        captured["context"] = json.loads(incident_context)
        captured["executor"] = executor
        captured["client"] = client
        return expected_result

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        fake_generate_investigation_with_tools,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
        client=mock_client,
    )

    assert result is expected_result
    assert captured["context"]["incident"]["id"] == 42
    assert captured["context"]["evidence"][0]["evidence_id"] == 10
    assert captured["executor"].incident_id == 42
    assert captured["client"] is mock_client


def test_run_ai_investigation_rejects_unknown_evidence_reference(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        lambda **kwargs: make_result(evidence_ids=[999]),
    )

    with pytest.raises(ValueError, match="999"):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[make_evidence()],
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
        "app.investigation_service.generate_investigation_with_tools",
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
    generator = Mock(return_value=make_result(evidence_ids=[10]))

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        generator,
    )

    with pytest.raises(ValueError, match="belong to incident"):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[
                make_evidence(
                    evidence_id=10,
                    incident_id=999,
                )
            ],
        )

    generator.assert_not_called()


def test_run_ai_investigation_accepts_evidence_returned_by_search_tool(
    monkeypatch,
):
    evidence = [
        make_evidence(
            evidence_id=index,
            content="x" * 2_000,
        )
        for index in range(1, 19)
    ]

    evidence.append(
        make_evidence(
            evidence_id=19,
            content="needle database timeout evidence",
        )
    )

    def fake_generate_investigation_with_tools(
        *,
        incident_context,
        executor,
        client,
    ):
        search_result = executor.execute(
            tool_name="search_incident_evidence",
            arguments={"query": "needle"},
        )

        assert search_result["ok"] is True
        assert any(
            item["evidence_id"] == 19
            for item in search_result["results"]
        )

        return make_result(evidence_ids=[19])

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        fake_generate_investigation_with_tools,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=evidence,
    )

    assert result.observed_facts[0].evidence_ids == [19]


def test_run_ai_investigation_rejects_evidence_not_returned_by_search(
    monkeypatch,
):
    evidence = [
        make_evidence(
            evidence_id=index,
            content="x" * 2_000,
        )
        for index in range(1, 19)
    ]

    evidence.append(
        make_evidence(
            evidence_id=19,
            content="unrelated evidence",
        )
    )

    def fake_generate_investigation_with_tools(
        *,
        incident_context,
        executor,
        client,
    ):
        search_result = executor.execute(
            tool_name="search_incident_evidence",
            arguments={"query": "missing-keyword"},
        )

        assert search_result["ok"] is True
        assert all(
            item["evidence_id"] != 19
            for item in search_result["results"]
        )

        return make_result(evidence_ids=[19])

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        fake_generate_investigation_with_tools,
    )

    with pytest.raises(ValueError, match="19"):
        run_ai_investigation(
            incident=make_incident(),
            evidence=evidence,
        )


def test_run_ai_investigation_uses_ollama_when_configured(monkeypatch):
    expected_result = make_result()
    mock_client = Mock()
    captured = {}

    monkeypatch.setattr(
        "app.investigation_service.get_llm_provider",
        lambda: "ollama",
    )

    def fake_ollama_generator(
        *,
        incident_context,
        executor,
        client,
    ):
        captured["context"] = json.loads(incident_context)
        captured["executor"] = executor
        captured["client"] = client
        return expected_result

    ollama_generator = Mock(side_effect=fake_ollama_generator)

    monkeypatch.setattr(
        "app.investigation_service.generate_ollama_investigation_with_tools",
        ollama_generator,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
        client=mock_client,
    )

    assert result is expected_result
    assert captured["context"]["incident"]["id"] == 42
    assert captured["executor"].incident_id == 42
    assert captured["client"] is mock_client
    ollama_generator.assert_called_once()


def test_run_ai_investigation_validates_ollama_evidence_references(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.investigation_service.get_llm_provider",
        lambda: "ollama",
    )

    monkeypatch.setattr(
        "app.investigation_service.generate_ollama_investigation_with_tools",
        lambda **kwargs: make_result(evidence_ids=[999]),
    )

    with pytest.raises(ValueError, match="999"):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[make_evidence(evidence_id=10)],
        )


def test_run_ai_investigation_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr(
        "app.investigation_service.get_llm_provider",
        lambda: "unsupported-provider",
    )

    with pytest.raises(
        UnsupportedLLMProviderError,
        match="Unsupported LLM provider",
    ):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[make_evidence()],
        )


def test_run_ai_investigation_rejects_blank_observed_fact(
    monkeypatch,
):
    result = make_result()
    result.observed_facts[0].statement = "   "

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        lambda **kwargs: result,
    )

    with pytest.raises(ValueError, match="blank observed fact"):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[make_evidence()],
        )


def test_run_ai_investigation_rejects_blank_recommended_check(
    monkeypatch,
):
    result = make_result()
    result.recommended_checks = ["   "]

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        lambda **kwargs: result,
    )

    with pytest.raises(
        ValueError,
        match="blank entry in recommended_checks",
    ):
        run_ai_investigation(
            incident=make_incident(),
            evidence=[make_evidence()],
        )


def test_run_ai_investigation_retries_when_supported_hypothesis_has_no_checks(
    monkeypatch,
):
    first_result = make_result()
    first_result.hypotheses = [
        AIHypothesis(
            explanation="Connection pool saturation may be involved.",
            supporting_evidence_ids=[10],
            confidence=AIConfidence.LOW,
        )
    ]

    retry_result = make_result()
    retry_result.recommended_checks = [
        "Inspect connection utilization and waiting requests over time."
    ]

    generator = Mock(return_value=first_result)
    refiner = Mock(return_value=retry_result)

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        generator,
    )
    monkeypatch.setattr(
        "app.investigation_service.refine_investigation_recommendations",
        refiner,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
    )

    assert result is not first_result
    assert result is not retry_result
    assert result.recommended_checks == retry_result.recommended_checks

    # The original findings must remain unchanged.
    assert result.observed_facts == first_result.observed_facts
    assert result.hypotheses == first_result.hypotheses
    assert result.unknowns == first_result.unknowns

    generator.assert_called_once()
    refiner.assert_called_once()


def test_run_ai_investigation_does_not_retry_when_checks_exist(
    monkeypatch,
):
    expected_result = make_result()
    expected_result.recommended_checks = ["Inspect request latency."]

    generator = Mock(return_value=expected_result)
    refiner = Mock()

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        generator,
    )
    monkeypatch.setattr(
        "app.investigation_service.refine_investigation_recommendations",
        refiner,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
    )

    assert result is expected_result
    generator.assert_called_once()
    refiner.assert_not_called()


def test_run_ai_investigation_does_not_retry_without_supported_hypothesis(
    monkeypatch,
):
    result_without_hypothesis = make_result()
    result_without_hypothesis.hypotheses = []
    result_without_hypothesis.recommended_checks = []

    generator = Mock(return_value=result_without_hypothesis)
    refiner = Mock()

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        generator,
    )
    monkeypatch.setattr(
        "app.investigation_service.refine_investigation_recommendations",
        refiner,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
    )

    assert result is result_without_hypothesis
    generator.assert_called_once()
    refiner.assert_not_called()


def test_run_ai_investigation_keeps_first_result_when_retry_has_no_checks(
    monkeypatch,
):
    first_result = make_result()
    first_result.hypotheses = [
        AIHypothesis(
            explanation="Connection pool saturation may be involved.",
            supporting_evidence_ids=[10],
            confidence=AIConfidence.LOW,
        )
    ]

    retry_result = make_result()
    retry_result.recommended_checks = []

    generator = Mock(return_value=first_result)
    refiner = Mock(return_value=retry_result)

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        generator,
    )
    monkeypatch.setattr(
        "app.investigation_service.refine_investigation_recommendations",
        refiner,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
    )

    assert result is first_result
    generator.assert_called_once()
    refiner.assert_called_once()



def test_run_ai_investigation_keeps_first_result_when_refinement_fails(
    monkeypatch,
):
    first_result = make_result()
    first_result.hypotheses = [
        AIHypothesis(
            explanation="Connection pool saturation may be involved.",
            supporting_evidence_ids=[10],
            confidence=AIConfidence.LOW,
        )
    ]

    generator = Mock(return_value=first_result)
    refiner = Mock(side_effect=RuntimeError("Model request timed out"))

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        generator,
    )
    monkeypatch.setattr(
        "app.investigation_service.refine_investigation_recommendations",
        refiner,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
    )

    assert result is first_result
    assert result.recommended_checks == []

    generator.assert_called_once()
    refiner.assert_called_once()


def test_run_ai_investigation_rejects_invalid_refinement_evidence(
    monkeypatch,
):
    first_result = make_result()
    first_result.hypotheses = [
        AIHypothesis(
            explanation="Connection pool saturation may be involved.",
            supporting_evidence_ids=[10],
            confidence=AIConfidence.LOW,
        )
    ]

    invalid_refinement = make_result(evidence_ids=[999])
    invalid_refinement.recommended_checks = [
        "Inspect connection utilization over time."
    ]

    generator = Mock(return_value=first_result)
    refiner = Mock(return_value=invalid_refinement)

    monkeypatch.setattr(
        "app.investigation_service.generate_investigation_with_tools",
        generator,
    )
    monkeypatch.setattr(
        "app.investigation_service.refine_investigation_recommendations",
        refiner,
    )

    result = run_ai_investigation(
        incident=make_incident(),
        evidence=[make_evidence()],
    )

    assert result is first_result
    assert result.recommended_checks == []

    generator.assert_called_once()
    refiner.assert_called_once()
