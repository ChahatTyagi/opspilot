
import math

import httpx

from app.config import (
    get_ollama_base_url,
    get_ollama_embedding_model,
    get_ollama_timeout,
)
from app.ollama_client import OllamaRequestError


class OllamaEmbedder:
    """Generate text embeddings using Ollama's embedding API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (
            base_url or get_ollama_base_url()
        )
        self.model = (
            model or get_ollama_embedding_model()
        )
        self.timeout = (
            timeout
            if timeout is not None
            else get_ollama_timeout()
        )

        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """Validate embedding client configuration."""

        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ValueError("Ollama base URL must not be empty")

        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Ollama embedding model must not be empty")

        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not math.isfinite(self.timeout)
            or self.timeout <= 0
        ):
            raise ValueError(
                "Ollama timeout must be a finite number greater than zero"
            )

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Convert non-empty text strings into embedding vectors."""

        if not texts:
            return []

        if any(
            not isinstance(text, str) or not text.strip()
            for text in texts
        ):
            raise ValueError(
                "texts must contain only non-empty strings"
            )

        payload = {
            "model": self.model,
            "input": texts,
        }

        try:
            response = httpx.post(
                f"{self.base_url}/api/embed",
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
            or not isinstance(data.get("embeddings"), list)
        ):
            raise OllamaRequestError(
                "Ollama returned an unexpected embedding response structure"
            )

        embeddings = data["embeddings"]

        if len(embeddings) != len(texts):
            raise OllamaRequestError(
                "Ollama returned an incorrect number of embeddings"
            )

        validated_embeddings = []
        expected_dimensions = None

        for vector in embeddings:
            if not isinstance(vector, list) or not vector:
                raise OllamaRequestError(
                    "Ollama returned an invalid embedding vector"
                )

            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise OllamaRequestError(
                    "Ollama returned non-numeric embedding values"
                )

            if expected_dimensions is None:
                expected_dimensions = len(vector)
            elif len(vector) != expected_dimensions:
                raise OllamaRequestError(
                    "Ollama returned embeddings with inconsistent dimensions"
                )

            validated_embeddings.append(
                [float(value) for value in vector]
            )

        return validated_embeddings
