
import json
from unittest.mock import Mock

import pytest

from app.ai_models import (
    AIConfidence,
    AIFact,
    AIHypothesis,
    AIInvestigationResult,
)
from app.ollama_investigation import (
    generate_ollama_investigation_with_tools,
)
from app.tool_executor import InvestigationToolExecutor


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
        recommended_checks=[
            "Inspect database connection usage."
        ],
        unknowns=[
            "The exact trigger is not yet established."
        ],
    )


def make_tool_response():
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "search_incident_evidence",
                        "arguments": {
                            "query": "database errors"
                        },
                    }
                }
            ],
        }
    }


def test_ollama_investigation_returns_structured_result():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response(),
        {
            "message": {
                "role": "assistant",
                "content": "Search completed.",
            }
        },
        {
            "message": {
                "role": "assistant",
                "content": expected_result.model_dump_json(),
            }
        },
    ]

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

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert mock_client.chat.call_count == 3

    executor.execute.assert_called_once_with(
        tool_name="search_incident_evidence",
        arguments={"query": "database errors"},
    )


def test_ollama_investigation_sends_tool_results_back():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response(),
        {
            "message": {
                "role": "assistant",
                "content": "Search completed.",
            }
        },
        {
            "message": {
                "role": "assistant",
                "content": expected_result.model_dump_json(),
            }
        },
    ]

    executor = Mock()
    executor.max_calls = 5
    executor.execute.return_value = {
        "ok": True,
        "results": [{"evidence_id": 10}],
    }

    generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    second_call_messages = (
        mock_client.chat.call_args_list[1].kwargs["messages"]
    )

    assert second_call_messages[-1]["role"] == "tool"
    assert (
        second_call_messages[-1]["tool_name"]
        == "search_incident_evidence"
    )

    tool_result = json.loads(
        second_call_messages[-1]["content"]
    )

    assert tool_result["ok"] is True
    assert tool_result["results"][0]["evidence_id"] == 10


def test_ollama_investigation_rejects_malformed_tool_call():
    mock_client = Mock()
    mock_client.chat.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "search_incident_evidence",
                        "arguments": "not-an-object",
                    }
                }
            ],
        }
    }

    executor = Mock()
    executor.max_calls = 5

    with pytest.raises(ValueError, match="Malformed Ollama tool call"):
        generate_ollama_investigation_with_tools(
            incident_context="Incident context",
            executor=executor,
            client=mock_client,
        )

    executor.execute.assert_not_called()


def test_ollama_investigation_enforces_tool_call_limit():
    mock_client = Mock()
    mock_client.chat.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "search_incident_evidence",
                        "arguments": {"query": "database"},
                    }
                },
                {
                    "function": {
                        "name": "search_incident_evidence",
                        "arguments": {"query": "timeout"},
                    }
                },
                {
                    "function": {
                        "name": "search_incident_evidence",
                        "arguments": {"query": "connection"},
                    }
                },
            ],
        }
    }

    executor = Mock()
    executor.max_calls = 2
    executor.execute.return_value = {"ok": True, "results": []}

    with pytest.raises(ValueError, match="tool-call limit"):
        generate_ollama_investigation_with_tools(
            incident_context="Incident context",
            executor=executor,
            client=mock_client,
        )

    assert executor.execute.call_count == 2
    mock_client.chat.assert_called_once()


def test_ollama_investigation_rejects_invalid_final_json():
    mock_client = Mock()
    mock_client.chat.side_effect = [
        {
            "message": {
                "content": "No more tools needed.",
            }
        },
        {
            "message": {
                "content": "This is not JSON",
            }
        },
    ]

    executor = Mock()
    executor.max_calls = 5

    with pytest.raises(
        ValueError,
        match="invalid structured investigation",
    ):
        generate_ollama_investigation_with_tools(
            incident_context="Incident context",
            executor=executor,
            client=mock_client,
        )
