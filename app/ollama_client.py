
import math

import httpx

from app.config import (
    get_ollama_base_url,
    get_ollama_model,
    get_ollama_num_ctx,
    get_ollama_num_predict,
    get_ollama_timeout,
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
        timeout: float | None = None,
        num_predict: int | None = None,
        num_ctx: int | None = None,
    ):
        self.base_url = (
            base_url or get_ollama_base_url()
        )
        self.model = model or get_ollama_model()

        self.timeout = (
            timeout
            if timeout is not None
            else get_ollama_timeout()
        )

        self.num_predict = (
            num_predict
            if num_predict is not None
            else get_ollama_num_predict()
        )

        self.num_ctx = (
            num_ctx
            if num_ctx is not None
            else get_ollama_num_ctx()
        )

        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """Validate the configuration used by this client."""

        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not math.isfinite(self.timeout)
            or self.timeout <= 0
        ):
            raise ValueError(
                "Ollama timeout must be a finite number greater than zero"
            )

        if (
            isinstance(self.num_predict, bool)
            or not isinstance(self.num_predict, int)
            or self.num_predict <= 0
        ):
            raise ValueError(
                "Ollama num_predict must be a positive integer"
            )

        if (
            isinstance(self.num_ctx, bool)
            or not isinstance(self.num_ctx, int)
            or self.num_ctx <= 0
        ):
            raise ValueError(
                "Ollama num_ctx must be a positive integer"
            )

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
            "options": {
                "num_predict": self.num_predict,
                "num_ctx": self.num_ctx,
            },
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
