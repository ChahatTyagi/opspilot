
import math
import os

from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from the environment")
    return database_url


def get_llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def get_verifier_model() -> str:
    configured_model = os.getenv("VERIFIER_MODEL")

    if configured_model and configured_model.strip():
        return configured_model.strip()

    if get_llm_provider() == "ollama":
        return get_ollama_model()

    return get_openai_model()


def get_embedding_provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()


def get_ollama_embedding_model() -> str:
    return os.getenv("OLLAMA_EMBEDDING_MODEL", "all-minilm").strip()


def get_openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def get_ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")


def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M").strip()


def get_ollama_timeout() -> float:
    try:
        timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
    except ValueError as exc:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be a valid number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be greater than zero")
    return timeout


def get_ollama_num_predict() -> int:
    try:
        num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "1024"))
    except ValueError as exc:
        raise ValueError("OLLAMA_NUM_PREDICT must be a valid integer") from exc
    if num_predict <= 0:
        raise ValueError("OLLAMA_NUM_PREDICT must be greater than zero")
    return num_predict


def get_ollama_num_ctx() -> int:
    try:
        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    except ValueError as exc:
        raise ValueError("OLLAMA_NUM_CTX must be a valid integer") from exc
    if num_ctx <= 0:
        raise ValueError("OLLAMA_NUM_CTX must be greater than zero")
    return num_ctx


def get_allowed_origins() -> list[str]:
    origins = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip().rstrip("/") for origin in origins.split(",") if origin.strip()]
