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


def get_openai_api_key() -> str | None:
    """Return the OpenAI API key if configured."""
    return os.getenv("OPENAI_API_KEY")


def get_openai_model() -> str:
    """Return the configured model name."""
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

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
