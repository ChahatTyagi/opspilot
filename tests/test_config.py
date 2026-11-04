from app.config import get_openai_api_key, get_openai_model


def test_openai_api_key_is_optional(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert get_openai_api_key() is None


def test_openai_api_key_is_returned_when_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert get_openai_api_key() == "test-key"


def test_openai_model_has_default(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    assert get_openai_model() == "gpt-4.1-mini"


def test_openai_model_can_be_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    assert get_openai_model() == "test-model"
