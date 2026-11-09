from app.config import get_openai_api_key, get_openai_model
from app.config import (
    get_llm_provider,
    get_ollama_base_url,
    get_ollama_model,
)

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

def test_llm_provider_defaults_to_openai(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    assert get_llm_provider() == "openai"


def test_llm_provider_can_be_set_to_ollama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    assert get_llm_provider() == "ollama"


def test_llm_provider_is_normalized(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", " OLLAMA ")

    assert get_llm_provider() == "ollama"


def test_ollama_base_url_has_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    assert get_ollama_base_url() == "http://localhost:11434"


def test_ollama_base_url_removes_trailing_slash(monkeypatch):
    monkeypatch.setenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434/",
    )

    assert get_ollama_base_url() == "http://localhost:11434"


def test_ollama_model_has_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    assert get_ollama_model() == "qwen3.5:9b-q4_K_M"


def test_ollama_model_can_be_configured(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model")

    assert get_ollama_model() == "custom-model"