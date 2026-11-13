
import json
from typing import Any, Sequence

from pydantic import ValidationError

from app.ai_models import (
    AIHypothesis,
    AIHypothesisVerificationResult,
)
from app.config import get_verifier_model
from app.ollama_client import OllamaClient
from app.verification_prompts import (
    HYPOTHESIS_VERIFICATION_INSTRUCTIONS,
)


def build_verification_input(
    *,
    hypotheses: Sequence[AIHypothesis],
    evidence: Sequence[Any],
) -> dict:
    """Build verifier input containing each hypothesis's cited evidence."""

    evidence_by_id = {}

    for item in evidence:
        evidence_id = item.id

        if evidence_id in evidence_by_id:
            raise ValueError(
                f"Duplicate evidence record ID: {evidence_id}"
            )

        evidence_by_id[evidence_id] = item

    verification_hypotheses = []

    for index, hypothesis in enumerate(hypotheses):
        cited_evidence = []

        for evidence_id in hypothesis.supporting_evidence_ids:
            item = evidence_by_id.get(evidence_id)

            if item is None:
                raise ValueError(
                    f"Hypothesis {index} cites evidence ID "
                    f"{evidence_id}, but its content is unavailable."
                )

            cited_evidence.append({
                "evidence_id": item.id,
                "source_type": item.source_type,
                "content": item.content,
            })

        verification_hypotheses.append({
            "hypothesis_index": index,
            "explanation": hypothesis.explanation,
            "confidence": hypothesis.confidence.value,
            "cited_evidence": cited_evidence,
        })

    return {
        "hypotheses": verification_hypotheses,
    }


def _parse_verification_response(
    response: dict,
) -> AIHypothesisVerificationResult:
    """Parse and validate the structured Ollama verifier response."""

    message = response.get("message")

    if not isinstance(message, dict):
        raise ValueError(
            "Ollama returned a malformed verification response."
        )

    content = message.get("content")

    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "Ollama did not return a structured verification result."
        )

    try:
        return AIHypothesisVerificationResult.model_validate_json(
            content
        )
    except (ValueError, ValidationError) as exc:
        raise ValueError(
            "Ollama returned an invalid structured verification result."
        ) from exc


def verify_ollama_hypotheses(
    *,
    hypotheses: Sequence[AIHypothesis],
    evidence: Sequence[Any],
    client: OllamaClient | None = None,
) -> AIHypothesisVerificationResult:
    """
    Independently verify each hypothesis in a separate Ollama request.

    Each request receives exactly one hypothesis and only that
    hypothesis's cited evidence.

    The original hypothesis index is restored by Python after
    the model returns its assessment.
    """

    if not hypotheses:
        return AIHypothesisVerificationResult(assessments=[])

    if client is None:
        client = OllamaClient(model=get_verifier_model())

    all_assessments = []

    for original_index, hypothesis in enumerate(hypotheses):

        verification_input = build_verification_input(
            hypotheses=[hypothesis],
            evidence=evidence,
        )

        messages = [
            {
                "role": "system",
                "content": HYPOTHESIS_VERIFICATION_INSTRUCTIONS,
            },
            {
                "role": "user",
                "content": json.dumps(verification_input),
            },
        ]

        response = client.chat(
            messages=messages,
            format=AIHypothesisVerificationResult.model_json_schema(),
        )

        verification_result = _parse_verification_response(response)

        if len(verification_result.assessments) != 1:
            raise ValueError(
                f"Verifier must return exactly one assessment "
                f"for hypothesis {original_index}."
            )

        assessment = verification_result.assessments[0]

        if assessment.hypothesis_index != 0:
            raise ValueError(
                "Verifier returned an incorrect local hypothesis index "
                f"for hypothesis {original_index}."
            )

        # The model sees one hypothesis, so its local index is 0.
        # Restore the original index deterministically in Python.
        restored_assessment = assessment.model_copy(
            update={
                "hypothesis_index": original_index,
            }
        )

        all_assessments.append(restored_assessment)

    return AIHypothesisVerificationResult(
        assessments=all_assessments
    )
