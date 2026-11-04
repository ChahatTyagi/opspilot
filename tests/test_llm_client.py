from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.ai_models import (
    AIConfidence,
    AIFact,
    AIHypothesis,
    AIInvestigationResult,
)
from app.llm_client import (
    LLMConfigurationError,
    create_openai_client,
    generate_investigation,
)


def make_result():
    return AIInvestigationResult(
        observed_facts=[
            AIFact(
                statement="Database connection errors were logged.",
                evidence_ids=[10],
            )
        ],
        hypotheses=[
            AIHypothesis(
                explanation="Connection saturation may be involved.",
                supporting_evidence_ids=[10],
                confidence=AIConfidence.MEDIUM,
            )
        ],
        recommended_checks=["Inspect database connection usage."],
        unknowns=["The exact trigger is not yet established."],
    )


def test_create_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.llm_client.get_openai_api_key",
        lambda: None,
    )

    with pytest.raises(LLMConfigurationError):
        create_openai_client()


def test_generate_investigation_returns_parsed_result(monkeypatch):
    expected_result = make_result()
    mock_client = Mock()
    mock_client.responses.parse.return_value = SimpleNamespace(
        output_parsed=expected_result
    )
    monkeypatch.setattr(
        "app.llm_client.get_openai_model",
        lambda: "test-model",
    )

    result = generate_investigation(
        incident_context="Incident 1 evidence: [ID 10] Database errors.",
        client=mock_client,
    )

    assert result is expected_result
    mock_client.responses.parse.assert_called_once()


def test_generate_investigation_sends_structured_output_config(
    monkeypatch,
):
    mock_client = Mock()
    mock_client.responses.parse.return_value = SimpleNamespace(
        output_parsed=make_result()
    )
    monkeypatch.setattr(
        "app.llm_client.get_openai_model",
        lambda: "test-model",
    )

    generate_investigation(
        incident_context="Incident context",
        client=mock_client,
    )

    call_kwargs = mock_client.responses.parse.call_args.kwargs

    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["input"] == "Incident context"
    assert call_kwargs["text_format"] is AIInvestigationResult
    assert call_kwargs["max_output_tokens"] == 1200


def test_generate_investigation_rejects_empty_parsed_response():
    mock_client = Mock()
    mock_client.responses.parse.return_value = SimpleNamespace(
        output_parsed=None
    )

    with pytest.raises(ValueError, match="structured investigation"):
        generate_investigation(
            incident_context="Incident context",
            client=mock_client,
        )
