
import httpx

from app.config import (
    get_ollama_base_url,
    get_ollama_model,
)


class OllamaRequestError(RuntimeError):
    """Raised when communication with Ollama fails."""


class OllamaClient:
    """Small HTTP client for communicating with Ollama."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
    ):
        self.base_url = (
            base_url or get_ollama_base_url()
        )
        self.model = model or get_ollama_model()
        self.timeout = timeout

    def chat(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None = None,
        format: dict | None = None,
    ) -> dict:
        """Send a non-streaming chat request to Ollama."""

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
        }

        if tools is not None:
            payload["tools"] = tools

        if format is not None:
            payload["format"] = format

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )

            response.raise_for_status()
            data = response.json()

        except httpx.HTTPError as exc:
            raise OllamaRequestError(
                "Could not communicate with the Ollama server"
            ) from exc

        except ValueError as exc:
            raise OllamaRequestError(
                "Ollama returned an invalid JSON response"
            ) from exc

        if (
            not isinstance(data, dict)
            or not isinstance(data.get("message"), dict)
        ):
            raise OllamaRequestError(
                "Ollama returned an unexpected response structure"
            )

        return data
