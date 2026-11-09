
import os

from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing from the environment"
        )

    return database_url


def get_llm_provider() -> str:
    """Return the configured LLM provider."""
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def get_openai_api_key() -> str | None:
    """Return the OpenAI API key if configured."""
    return os.getenv("OPENAI_API_KEY")


def get_openai_model() -> str:
    """Return the configured OpenAI model."""
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def get_ollama_base_url() -> str:
    """Return the Ollama server URL."""
    return os.getenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434",
    ).strip().rstrip("/")


def get_ollama_model() -> str:
    """Return the configured Ollama model."""
    return os.getenv(
        "OLLAMA_MODEL",
        "qwen3.5:9b-q4_K_M",
    ).strip()


def get_allowed_origins() -> list[str]:
    """Return the frontend origins allowed to access the API."""
    origins = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )

    return [
        origin.strip().rstrip("/")
        for origin in origins.split(",")
        if origin.strip()
    ]
