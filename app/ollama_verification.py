import json
from typing import Any, Sequence

from pydantic import ValidationError

from app.ai_models import (
    AIHypothesis,
    AIInvestigationResult,
    AIHypothesisVerificationResult,
)
from app.config import get_verifier_model
from app.evidence_validation import validate_hypothesis_verification
from app.ollama_client import OllamaClient
from app.verification_prompts import (
    HYPOTHESIS_VERIFICATION_INSTRUCTIONS,
)


_CORRECTIVE_RETRY_INSTRUCTIONS = """

CORRECTIVE RETRY REQUIREMENTS

Your previous response did not pass deterministic validation. Re-evaluate
this same single hypothesis using only the evidence supplied in the user
payload. Return exactly one assessment with hypothesis_index 0.

If and only if you return SUPPORTED, evidence_ids MUST contain at least one
integer ID copied exactly from the cited_evidence list. Never leave that
list empty for SUPPORTED. Every ID explicitly named in the rationale must
also appear in evidence_ids. Do not invent IDs. If the evidence does not
support the proposed cause, choose INSUFFICIENT instead of manufacturing
supporting citations. Return only the required JSON structure.
"""


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

    return {"hypotheses": verification_hypotheses}


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
        return AIHypothesisVerificationResult.model_validate_json(content)
    except (ValueError, ValidationError) as exc:
        raise ValueError(
            "Ollama returned an invalid structured verification result."
        ) from exc


def _validate_single_assessment(
    *,
    hypothesis: AIHypothesis,
    verification: AIHypothesisVerificationResult,
) -> None:
    """Run the same strict evidence validation used by the service."""

    # The per-hypothesis request uses local index zero. Build a minimal
    # investigation object so the production validator can enforce all
    # evidence-ID and rationale consistency rules without duplicating them.
    single_hypothesis_result = AIInvestigationResult.model_construct(
        observed_facts=[],
        hypotheses=[hypothesis],
        reported_information=[],
        recommended_checks=[],
        unknowns=[],
    )

    cited_ids = set(hypothesis.supporting_evidence_ids)

    validate_hypothesis_verification(
        result=single_hypothesis_result,
        verification=verification,
        valid_evidence_ids=cited_ids,
    )


def _request_assessment(
    *,
    client: OllamaClient,
    messages: list[dict],
) -> AIHypothesisVerificationResult:
    response = client.chat(
        messages=messages,
        format=AIHypothesisVerificationResult.model_json_schema(),
    )
    return _parse_verification_response(response)


def verify_ollama_hypotheses(
    *,
    hypotheses: Sequence[AIHypothesis],
    evidence: Sequence[Any],
    client: OllamaClient | None = None,
) -> AIHypothesisVerificationResult:
    """Verify each hypothesis independently, with one validation retry.

    Each request receives exactly one hypothesis and only that hypothesis's
    cited evidence. If the model output is structurally or semantically
    invalid, one corrective retry is made for that same hypothesis. The
    retry is validated identically. A second invalid response raises and
    lets the investigation service apply its existing fail-closed policy.
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

        user_message = {
            "role": "user",
            "content": json.dumps(verification_input),
        }
        messages = [
            {
                "role": "system",
                "content": HYPOTHESIS_VERIFICATION_INSTRUCTIONS,
            },
            user_message,
        ]

        first_error: Exception | None = None
        assessment = None

        # First attempt, followed by exactly one corrective retry for
        # invalid model output. Transport errors are not retried here.
        try:
            verification_result = _request_assessment(
                client=client,
                messages=messages,
            )

            if len(verification_result.assessments) != 1:
                raise ValueError(
                    "Verifier must return exactly one assessment "
                    f"for hypothesis {original_index}."
                )

            assessment = verification_result.assessments[0]

            if assessment.hypothesis_index != 0:
                raise ValueError(
                    "Verifier returned an incorrect local hypothesis index "
                    f"for hypothesis {original_index}."
                )

            _validate_single_assessment(
                hypothesis=hypothesis,
                verification=verification_result,
            )

        except ValueError as exc:
            first_error = exc

        if first_error is not None:
            retry_messages = [
                {
                    "role": "system",
                    "content": (
                        HYPOTHESIS_VERIFICATION_INSTRUCTIONS
                        + _CORRECTIVE_RETRY_INSTRUCTIONS
                        + f"\nValidation failure to correct: {first_error}"
                    ),
                },
                user_message,
            ]

            try:
                retry_result = _request_assessment(
                    client=client,
                    messages=retry_messages,
                )

                if len(retry_result.assessments) != 1:
                    raise ValueError(
                        "Verifier must return exactly one assessment "
                        f"for hypothesis {original_index} after retry."
                    )

                retry_assessment = retry_result.assessments[0]

                if retry_assessment.hypothesis_index != 0:
                    raise ValueError(
                        "Verifier returned an incorrect local hypothesis "
                        f"index for hypothesis {original_index} after retry."
                    )

                _validate_single_assessment(
                    hypothesis=hypothesis,
                    verification=retry_result,
                )

                assessment = retry_assessment

            except ValueError as retry_error:
                raise ValueError(
                    "Ollama verifier returned an invalid assessment "
                    "after one corrective retry."
                ) from retry_error

        # The model sees one hypothesis, so its local index is zero.
        # Restore the original index deterministically in Python.
        restored_assessment = assessment.model_copy(
            update={"hypothesis_index": original_index}
        )
        all_assessments.append(restored_assessment)

    return AIHypothesisVerificationResult(assessments=all_assessments)
