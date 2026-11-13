
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
    OLLAMA_TOOLS,
    generate_ollama_investigation_with_tools,
)
from app.investigation_prompts import INVESTIGATION_INSTRUCTIONS


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


def make_tool_response(query="database errors"):
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "search_incident_evidence",
                        "arguments": {
                            "query": query
                        },
                    }
                }
            ],
        }
    }


def make_multiple_tool_response(*queries):
    """Create one assistant response containing multiple tool calls."""
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "search_incident_evidence",
                        "arguments": {"query": query},
                    }
                }
                for query in queries
            ],
        }
    }


def make_evidence_result(evidence_id=10):
    return {
        "ok": True,
        "results": [
            {
                "evidence_id": evidence_id,
                "text": "Database connection errors were logged.",
            }
        ],
        "new_evidence_ids": [evidence_id],
    }


def make_final_response(result):
    return {
        "message": {
            "role": "assistant",
            "content": result.model_dump_json(),
        }
    }


def extract_tool_results(messages):
    """Extract tool-result messages from a conversation."""
    return [
        message
        for message in messages
        if message.get("role") == "tool"
    ]


def test_ollama_returns_structured_result_after_tool_search():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response(),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 5
    executor.execute.return_value = make_evidence_result()

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert mock_client.chat.call_count == 2

    executor.execute.assert_called_once_with(
        tool_name="search_incident_evidence",
        arguments={"query": "database errors"},
    )


def test_ollama_sends_tool_results_back_to_model():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response(),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 5
    executor.execute.return_value = make_evidence_result()

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
    assert tool_result["new_evidence_ids"] == [10]


def test_ollama_passes_duplicate_evidence_feedback():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response(),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 5
    executor.execute.return_value = {
        "ok": True,
        "results": [
            {"evidence_id": 10}
        ],
        "new_evidence_ids": [],
    }

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result

    final_call_messages = (
        mock_client.chat.call_args_list[1].kwargs["messages"]
    )

    tool_result = json.loads(
        final_call_messages[-1]["content"]
    )

    assert tool_result["new_evidence_ids"] == []


def test_ollama_stops_after_search_returns_only_duplicate_evidence():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response("database errors"),
        make_tool_response("connection pool timeout"),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 5
    executor.execute.side_effect = [
        {
            "ok": True,
            "results": [{"evidence_id": 10}],
            "new_evidence_ids": [10],
        },
        {
            "ok": True,
            "results": [{"evidence_id": 10}],
            "new_evidence_ids": [],
        },
    ]

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert executor.execute.call_count == 2
    assert mock_client.chat.call_count == 3

    final_call_messages = (
        mock_client.chat.call_args_list[2].kwargs["messages"]
    )

    second_tool_result = json.loads(
        final_call_messages[-1]["content"]
    )

    assert second_tool_result["results"][0]["evidence_id"] == 10
    assert second_tool_result["new_evidence_ids"] == []


def test_ollama_continues_after_search_returns_no_results():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response("missing database information"),
        make_tool_response("database connection errors"),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 5
    executor.execute.side_effect = [
        {
            "ok": True,
            "results": [],
            "new_evidence_ids": [],
        },
        make_evidence_result(),
    ]

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert executor.execute.call_count == 2
    assert mock_client.chat.call_count == 3


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


def test_ollama_investigation_completes_after_tool_call_limit():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_multiple_tool_response(
            "database",
            "timeout",
            "connection",
        ),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 2
    executor.execute.return_value = {
        "ok": True,
        "results": [],
        "new_evidence_ids": [],
    }

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert executor.execute.call_count == 2
    assert mock_client.chat.call_count == 2


def test_ollama_returns_result_for_every_tool_call_after_limit():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_multiple_tool_response(
            "database",
            "timeout",
            "connection",
            "deployment",
        ),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 2
    executor.execute.return_value = {
        "ok": True,
        "results": [],
        "new_evidence_ids": [],
    }

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert executor.execute.call_count == 2

    final_messages = (
        mock_client.chat.call_args_list[1].kwargs["messages"]
    )

    assistant_message = next(
        message
        for message in final_messages
        if message.get("role") == "assistant"
        and message.get("tool_calls")
    )

    tool_results = extract_tool_results(final_messages)

    assert len(assistant_message["tool_calls"]) == 4
    assert len(tool_results) == 4

    first_two_results = [
        json.loads(message["content"])
        for message in tool_results[:2]
    ]

    last_two_results = [
        json.loads(message["content"])
        for message in tool_results[2:]
    ]

    assert all(result["ok"] is True for result in first_two_results)
    assert all(result["ok"] is False for result in last_two_results)

    assert all(
        "limit" in result["error"].lower()
        for result in last_two_results
    )


def test_ollama_returns_result_for_remaining_calls_after_duplicate_evidence():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.side_effect = [
        make_tool_response("initial database search"),
        make_multiple_tool_response(
            "database timeout",
            "connection errors",
            "deployment failures",
        ),
        make_final_response(expected_result),
    ]

    executor = Mock()
    executor.max_calls = 5

    executor.execute.side_effect = [
        make_evidence_result(10),
        {
            "ok": True,
            "results": [{"evidence_id": 10}],
            "new_evidence_ids": [],
        },
    ]

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert executor.execute.call_count == 2

    final_messages = (
        mock_client.chat.call_args_list[2].kwargs["messages"]
    )

    assistant_message = [
        message
        for message in final_messages
        if message.get("role") == "assistant"
        and message.get("tool_calls")
    ][-1]

    tool_results = extract_tool_results(final_messages)

    assert len(assistant_message["tool_calls"]) == 3
    assert len(tool_results) == 4

    duplicate_result = json.loads(tool_results[-3]["content"])

    assert duplicate_result["ok"] is True
    assert duplicate_result["new_evidence_ids"] == []

    skipped_results = [
        json.loads(message["content"])
        for message in tool_results[-2:]
    ]

    assert all(result["ok"] is False for result in skipped_results)

    assert all(
        "Search stopped" in result["error"]
        for result in skipped_results
    )


def test_ollama_investigation_rejects_invalid_final_json():
    mock_client = Mock()
    mock_client.chat.return_value = {
        "message": {
            "content": "This is not JSON",
        }
    }

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

    assert mock_client.chat.call_count == 1


def test_ollama_uses_structured_first_response_without_reconstruction():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.return_value = make_final_response(expected_result)

    executor = Mock()
    executor.max_calls = 5

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result
    assert mock_client.chat.call_count == 1
    executor.execute.assert_not_called()


def test_ollama_first_call_includes_tools_and_json_schema():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.return_value = make_final_response(expected_result)

    executor = Mock()
    executor.max_calls = 5

    generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    first_call = mock_client.chat.call_args

    assert first_call.kwargs["tools"] == OLLAMA_TOOLS
    assert (
        first_call.kwargs["format"]
        == AIInvestigationResult.model_json_schema()
    )


def test_ollama_uses_shared_investigation_instructions():
    expected_result = make_result()

    mock_client = Mock()
    mock_client.chat.return_value = make_final_response(expected_result)

    executor = Mock()
    executor.max_calls = 5

    result = generate_ollama_investigation_with_tools(
        incident_context="Incident context",
        executor=executor,
        client=mock_client,
    )

    assert result == expected_result

    first_call_messages = (
        mock_client.chat.call_args_list[0].kwargs["messages"]
    )

    assert first_call_messages[0]["role"] == "system"
    assert (
        first_call_messages[0]["content"]
        == INVESTIGATION_INSTRUCTIONS
    )


def test_shared_instructions_include_evidence_search_strategy():
    assert "9. EVIDENCE SEARCH STRATEGY" in INVESTIGATION_INSTRUCTIONS

    assert (
        "search for additional relevant evidence"
        in INVESTIGATION_INSTRUCTIONS
    )

    assert (
        "Use targeted search queries"
        in INVESTIGATION_INSTRUCTIONS
    )

    assert (
        "Never treat search queries, tool-call decisions, or"
        in INVESTIGATION_INSTRUCTIONS
    )
