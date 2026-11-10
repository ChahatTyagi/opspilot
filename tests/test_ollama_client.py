
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

    monkeypatch.setattr(
        "app.ollama_client.get_ollama_num_predict",
        lambda: 1024,
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
    assert call_kwargs["json"]["options"] == {
        "num_predict": 1024,
        "num_ctx": 8192,
    }


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

    assert "options" in payload
    assert "num_predict" in payload["options"]


def test_ollama_client_allows_explicit_num_predict(monkeypatch):
    monkeypatch.setattr(
        "app.ollama_client.get_ollama_num_predict",
        lambda: 1024,
    )

    mock_post = Mock(
        return_value=make_response(
            {"message": {"content": "Hello"}}
        )
    )

    monkeypatch.setattr(
        "app.ollama_client.httpx.post",
        mock_post,
    )

    client = OllamaClient(num_predict=512)

    client.chat(
        messages=[{"role": "user", "content": "Hello"}]
    )

    payload = mock_post.call_args.kwargs["json"]

    assert payload["options"]["num_predict"] == 512


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


def test_ollama_client_uses_configured_timeout(monkeypatch):
    monkeypatch.setattr(
        "app.ollama_client.get_ollama_timeout",
        lambda: 300.0,
    )

    client = OllamaClient()

    assert client.timeout == 300.0


def test_ollama_client_allows_explicit_timeout(monkeypatch):
    monkeypatch.setattr(
        "app.ollama_client.get_ollama_timeout",
        lambda: 300.0,
    )

    client = OllamaClient(timeout=60.0)

    assert client.timeout == 60.0


def test_ollama_client_uses_configured_num_predict(monkeypatch):
    monkeypatch.setattr(
        "app.ollama_client.get_ollama_num_predict",
        lambda: 1536,
    )

    client = OllamaClient()

    assert client.num_predict == 1536


def test_ollama_client_uses_configured_num_ctx(monkeypatch):
    monkeypatch.setattr(
        "app.ollama_client.get_ollama_num_ctx",
        lambda: 8192,
    )

    client = OllamaClient()

    assert client.num_ctx == 8192


def test_ollama_client_allows_explicit_num_ctx(monkeypatch):
    monkeypatch.setattr(
        "app.ollama_client.get_ollama_num_ctx",
        lambda: 8192,
    )

    client = OllamaClient(num_ctx=4096)

    assert client.num_ctx == 4096


# Constructor validation tests


@pytest.mark.parametrize(
    "timeout",
    [0, -1, float("nan"), float("inf"), float("-inf"), True],
)
def test_ollama_client_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="timeout"):
        OllamaClient(timeout=timeout)


@pytest.mark.parametrize(
    "num_predict",
    [0, -1, 1.5, True, "1024"],
)
def test_ollama_client_rejects_invalid_num_predict(num_predict):
    with pytest.raises(ValueError, match="num_predict"):
        OllamaClient(num_predict=num_predict)


@pytest.mark.parametrize(
    "num_ctx",
    [0, -1, 1.5, True, "8192"],
)
def test_ollama_client_rejects_invalid_num_ctx(num_ctx):
    with pytest.raises(ValueError, match="num_ctx"):
        OllamaClient(num_ctx=num_ctx)
