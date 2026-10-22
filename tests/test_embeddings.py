
import numpy as np
import pytest

from app.embeddings import LocalEmbedder


class FakeModel:
    def __init__(self):
        self.received_texts = None
        self.received_options = None

    def encode(self, texts, **kwargs):
        self.received_texts = texts
        self.received_options = kwargs
        return np.array([[0.6, 0.8] for _ in texts])


def test_embed_texts_returns_vectors():
    embedder = LocalEmbedder()
    fake_model = FakeModel()
    embedder._model = fake_model

    result = embedder.embed_texts(["Database timeout"])

    assert result == [[0.6, 0.8]]
    assert fake_model.received_texts == ["Database timeout"]


def test_embed_texts_processes_multiple_texts():
    embedder = LocalEmbedder()
    fake_model = FakeModel()
    embedder._model = fake_model

    result = embedder.embed_texts(
        ["Database timeout", "Payment service unavailable"]
    )

    assert len(result) == 2
    assert all(len(vector) == 2 for vector in result)


def test_empty_list_returns_without_loading_model():
    embedder = LocalEmbedder()

    assert embedder.embed_texts([]) == []
    assert embedder._model is None


@pytest.mark.parametrize("texts", [[""], ["   "], ["valid text", ""]])
def test_blank_text_is_rejected(texts):
    embedder = LocalEmbedder()

    with pytest.raises(ValueError, match="non-empty strings"):
        embedder.embed_texts(texts)

    assert embedder._model is None
