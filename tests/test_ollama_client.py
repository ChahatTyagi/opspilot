
from unittest.mock import Mock

import httpx
import pytest

from app.ollama_client import (
    OllamaClient,
    OllamaRequestError,
)


def make_response(data):
    response = Mock()
    response.json.return_value = data
    response.raise_for_status.return_value = None
    return response


def test_ollama_client_sends_basic_chat_request(monkeypatch):
    mock_post = Mock(
        return_value=make_response(
            {
                "message": {
                    "content": '{"status": "ready"}'
                }
            }
        )
    )

    monkeypatch.setattr(
        "app.ollama_client.httpx.post",
        mock_post,
    )

    client = OllamaClient(
        base_url="http://localhost:11434",
        model="test-model",
    )

    result = client.chat(
        messages=[
            {"role": "user", "content": "Hello"}
        ]
    )

    assert result["message"]["content"] == '{"status": "ready"}'

    call_kwargs = mock_post.call_args.kwargs

    assert mock_post.call_args.args[0] == (
        "http://localhost:11434/api/chat"
    )
    assert call_kwargs["json"]["model"] == "test-model"
    assert call_kwargs["json"]["stream"] is False
    assert call_kwargs["json"]["think"] is False
    assert call_kwargs["json"]["messages"] == [
        {"role": "user", "content": "Hello"}
    ]


def test_ollama_client_includes_tools_and_format(monkeypatch):
    mock_post = Mock(
        return_value=make_response(
            {
                "message": {
                    "content": "",
                    "tool_calls": [],
                }
            }
        )
    )

    monkeypatch.setattr(
        "app.ollama_client.httpx.post",
        mock_post,
    )

    client = OllamaClient()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_incident_evidence",
            },
        }
    ]

    output_format = {
        "type": "object",
        "properties": {
            "status": {"type": "string"}
        },
    }

    client.chat(
        messages=[{"role": "user", "content": "Search"}],
        tools=tools,
        format=output_format,
    )

    payload = mock_post.call_args.kwargs["json"]

    assert payload["tools"] == tools
    assert payload["format"] == output_format


def test_ollama_client_omits_optional_fields(monkeypatch):
    mock_post = Mock(
        return_value=make_response(
            {"message": {"content": "Hello"}}
        )
    )

    monkeypatch.setattr(
        "app.ollama_client.httpx.post",
        mock_post,
    )

    client = OllamaClient()

    client.chat(
        messages=[{"role": "user", "content": "Hello"}]
    )

    payload = mock_post.call_args.kwargs["json"]

    assert "tools" not in payload
    assert "format" not in payload


def test_ollama_client_handles_connection_error(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(
        "app.ollama_client.httpx.post",
        raise_connection_error,
    )

    client = OllamaClient()

    with pytest.raises(
        OllamaRequestError,
        match="communicate with the Ollama server",
    ):
        client.chat(
            messages=[{"role": "user", "content": "Hello"}]
        )


def test_ollama_client_rejects_invalid_response_structure(
    monkeypatch,
):
    mock_post = Mock(
        return_value=make_response(
            {"unexpected": "response"}
        )
    )

    monkeypatch.setattr(
        "app.ollama_client.httpx.post",
        mock_post,
    )

    client = OllamaClient()

    with pytest.raises(
        OllamaRequestError,
        match="unexpected response structure",
    ):
        client.chat(
            messages=[{"role": "user", "content": "Hello"}]
        )
