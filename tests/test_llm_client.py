from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import json
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
    generate_investigation_with_tools,
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

def make_tool_call(
    *,
    name="search_incident_evidence",
    arguments=None,
    call_id="call_1",
):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=json.dumps(arguments or {"query": "database errors"}),
        call_id=call_id,
    )


def test_generate_investigation_with_tools_returns_final_result(
    monkeypatch,
):
    expected_result = make_result()
    mock_client = Mock()

    tool_call = make_tool_call()
    tool_response = SimpleNamespace(
        id="resp_tool_step",
        output=[tool_call],
    )

    final_response = SimpleNamespace(
        output_parsed=expected_result,
        output=[],
    )

    mock_client.responses.parse.side_effect = [
        tool_response,
        final_response,
    ]

    monkeypatch.setattr(
        "app.llm_client.get_openai_model",
        lambda: "test-model",
    )

    executor = Mock()
    executor.max_calls = 5
    executor.execute.return_value = {
        "ok": True,
        "results": [
            {
                "evidence_id": 10,
                "text": "Database connection errors were logged.",
            }
        ],
    }

    result = generate_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result is expected_result
    assert mock_client.responses.parse.call_count == 2
    executor.execute.assert_called_once_with(
        tool_name="search_incident_evidence",
        arguments={"query": "database errors"},
    )


def test_generate_investigation_with_tools_rejects_invalid_json(
    monkeypatch,
):
    mock_client = Mock()
    mock_client.responses.parse.return_value = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_incident_evidence",
                arguments="{invalid-json",
                call_id="call_1",
            )
        ]
    )

    monkeypatch.setattr(
        "app.llm_client.get_openai_model",
        lambda: "test-model",
    )

    executor = Mock()
    executor.max_calls = 5

    with pytest.raises(ValueError, match="tool arguments"):
        generate_investigation_with_tools(
            incident_context="Incident context",
            executor=executor,
            client=mock_client,
        )

    executor.execute.assert_not_called()


def test_generate_investigation_with_tools_rejects_missing_final_result(
    monkeypatch,
):
    mock_client = Mock()
    mock_client.responses.parse.return_value = SimpleNamespace(
        output=[],
        output_parsed=None,
    )

    monkeypatch.setattr(
        "app.llm_client.get_openai_model",
        lambda: "test-model",
    )

    executor = Mock()

    with pytest.raises(ValueError, match="structured investigation"):
        generate_investigation_with_tools(
            incident_context="Incident context",
            executor=executor,
            client=mock_client,
        )

def test_generate_investigation_with_tools_enforces_call_limit(
    monkeypatch,
):
    mock_client = Mock()

    tool_response = SimpleNamespace(
        id="resp_tool_step",
        output=[
            make_tool_call(
                arguments={"query": "database"},
                call_id="call_1",
            ),
            make_tool_call(
                arguments={"query": "timeout"},
                call_id="call_2",
            ),
            make_tool_call(
                arguments={"query": "connection"},
                call_id="call_3",
            ),
        ],
    )

    mock_client.responses.parse.return_value = tool_response

    monkeypatch.setattr(
        "app.llm_client.get_openai_model",
        lambda: "test-model",
    )

    executor = Mock()
    executor.max_calls = 2
    executor.execute.return_value = {"ok": True, "results": []}

    with pytest.raises(ValueError, match="tool-call limit"):
        generate_investigation_with_tools(
            incident_context="Incident context",
            executor=executor,
            client=mock_client,
        )

    assert executor.execute.call_count == 2
    mock_client.responses.parse.assert_called_once()

def test_generate_investigation_with_tools_rejects_missing_call_id(
    monkeypatch,
):
    mock_client = Mock()
    mock_client.responses.parse.return_value = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_incident_evidence",
                arguments=json.dumps({"query": "database"}),
                # call_id intentionally missing
            )
        ]
    )

    monkeypatch.setattr(
        "app.llm_client.get_openai_model",
        lambda: "test-model",
    )

    executor = Mock()
    executor.max_calls = 5

    with pytest.raises(ValueError, match="Malformed tool call"):
        generate_investigation_with_tools(
            incident_context="Incident context",
            executor=executor,
            client=mock_client,
        )

    executor.execute.assert_not_called()