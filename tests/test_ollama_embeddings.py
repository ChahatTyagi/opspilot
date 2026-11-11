
from unittest.mock import Mock

import httpx
import pytest

from app.ollama_client import OllamaRequestError
from app.ollama_embeddings import OllamaEmbedder


def make_response(data):
    response = Mock()
    response.json.return_value = data
    response.raise_for_status.return_value = None
    return response


def test_ollama_embedder_sends_embedding_request(monkeypatch):
    expected_embeddings = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]

    mock_post = Mock(
        return_value=make_response(
            {"embeddings": expected_embeddings}
        )
    )

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        mock_post,
    )

    embedder = OllamaEmbedder(
        base_url="http://localhost:11434",
        model="all-minilm",
        timeout=60,
    )

    texts = [
        "Database connection pool exhausted",
        "Database connection limit reached",
    ]

    result = embedder.embed_texts(texts)

    assert result == expected_embeddings

    call_kwargs = mock_post.call_args.kwargs

    assert mock_post.call_args.args[0] == (
        "http://localhost:11434/api/embed"
    )
    assert call_kwargs["json"] == {
        "model": "all-minilm",
        "input": texts,
    }
    assert call_kwargs["timeout"] == 60


def test_ollama_embedder_returns_empty_list_without_request(
    monkeypatch,
):
    mock_post = Mock()

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        mock_post,
    )

    embedder = OllamaEmbedder()

    assert embedder.embed_texts([]) == []
    mock_post.assert_not_called()


@pytest.mark.parametrize(
    "texts",
    [
        [""],
        ["   "],
        ["valid text", ""],
        [123],
        [None],
    ],
)
def test_ollama_embedder_rejects_invalid_texts(texts):
    embedder = OllamaEmbedder()

    with pytest.raises(
        ValueError,
        match="non-empty strings",
    ):
        embedder.embed_texts(texts)


def test_ollama_embedder_handles_connection_error(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        raise_connection_error,
    )

    embedder = OllamaEmbedder()

    with pytest.raises(
        OllamaRequestError,
        match="communicate with the Ollama server",
    ):
        embedder.embed_texts(["Database timeout"])


def test_ollama_embedder_handles_invalid_json(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("Invalid JSON")

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        Mock(return_value=response),
    )

    embedder = OllamaEmbedder()

    with pytest.raises(
        OllamaRequestError,
        match="invalid JSON",
    ):
        embedder.embed_texts(["Database timeout"])


def test_ollama_embedder_rejects_invalid_response_structure(
    monkeypatch,
):
    mock_post = Mock(
        return_value=make_response(
            {"unexpected": "response"}
        )
    )

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        mock_post,
    )

    embedder = OllamaEmbedder()

    with pytest.raises(
        OllamaRequestError,
        match="unexpected embedding response structure",
    ):
        embedder.embed_texts(["Database timeout"])


def test_ollama_embedder_rejects_wrong_embedding_count(
    monkeypatch,
):
    mock_post = Mock(
        return_value=make_response(
            {"embeddings": [[0.1, 0.2]]}
        )
    )

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        mock_post,
    )

    embedder = OllamaEmbedder()

    with pytest.raises(
        OllamaRequestError,
        match="incorrect number of embeddings",
    ):
        embedder.embed_texts(
            ["First text", "Second text"]
        )


@pytest.mark.parametrize(
    "embeddings",
    [
        [[]],
        ["not a vector"],
        [[0.1, "invalid"]],
        [[0.1, float("nan")]],
        [[0.1, float("inf")]],
        [[True, 0.2]],
    ],
)
def test_ollama_embedder_rejects_invalid_vectors(
    monkeypatch,
    embeddings,
):
    mock_post = Mock(
        return_value=make_response(
            {"embeddings": embeddings}
        )
    )

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        mock_post,
    )

    embedder = OllamaEmbedder()

    with pytest.raises(OllamaRequestError):
        embedder.embed_texts(["Database timeout"])


def test_ollama_embedder_rejects_inconsistent_dimensions(
    monkeypatch,
):
    mock_post = Mock(
        return_value=make_response(
            {
                "embeddings": [
                    [0.1, 0.2],
                    [0.3, 0.4, 0.5],
                ]
            }
        )
    )

    monkeypatch.setattr(
        "app.ollama_embeddings.httpx.post",
        mock_post,
    )

    embedder = OllamaEmbedder()

    with pytest.raises(
        OllamaRequestError,
        match="inconsistent dimensions",
    ):
        embedder.embed_texts(
            ["First text", "Second text"]
        )


@pytest.mark.parametrize(
    "timeout",
    [
        0,
        -1,
        float("nan"),
        float("inf"),
        True,
    ],
)
def test_ollama_embedder_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="timeout"):
        OllamaEmbedder(timeout=timeout)
