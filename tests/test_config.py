
import pytest

from app.config import (
    get_llm_provider,
    get_openai_api_key,
    get_openai_model,
    get_ollama_base_url,
    get_ollama_model,
    get_ollama_timeout,
    get_ollama_num_predict,
    get_ollama_num_ctx,
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


# Ollama timeout tests

def test_ollama_timeout_has_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_TIMEOUT_SECONDS", raising=False)

    assert get_ollama_timeout() == 300.0


def test_ollama_timeout_can_be_configured(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45.5")

    assert get_ollama_timeout() == 45.5


@pytest.mark.parametrize(
    "value",
    ["abc", "0", "-1", "nan", "inf", "-inf"],
)
def test_ollama_timeout_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError):
        get_ollama_timeout()


# Ollama output token limit tests

def test_ollama_num_predict_has_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_NUM_PREDICT", raising=False)

    assert get_ollama_num_predict() == 1024


def test_ollama_num_predict_can_be_configured(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "2048")

    assert get_ollama_num_predict() == 2048


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_ollama_num_predict_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", value)

    with pytest.raises(ValueError):
        get_ollama_num_predict()


# Ollama context window tests

def test_ollama_num_ctx_has_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

    assert get_ollama_num_ctx() == 8192


def test_ollama_num_ctx_can_be_configured(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")

    assert get_ollama_num_ctx() == 4096


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_ollama_num_ctx_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("OLLAMA_NUM_CTX", value)

    with pytest.raises(ValueError):
        get_ollama_num_ctx()
