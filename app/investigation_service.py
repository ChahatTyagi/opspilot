
import json
from typing import Any, Sequence

from openai import OpenAI

from app.ai_models import AIInvestigationResult
from app.config import get_llm_provider
from app.evidence_validation import (
    validate_evidence_references,
    validate_hypothesis_verification,
    validate_investigation_quality,
)
from app.incident_context import build_incident_context
from app.llm_client import (
    generate_investigation_with_tools,
    refine_investigation_recommendations,
    verify_openai_hypotheses,
)
from app.ollama_client import OllamaClient
from app.ollama_investigation import (
    generate_ollama_investigation_with_tools,
    refine_ollama_investigation_recommendations,
)
from app.ollama_verification import (
    build_verification_input,
    verify_ollama_hypotheses,
)
from app.tool_executor import InvestigationToolExecutor
from app.ollama_verification import build_verification_input


class UnsupportedLLMProviderError(RuntimeError):
    """Raised when the configured LLM provider is not supported."""


HYPOTHESIS_VERIFICATION_FAILURE = (
    "Causal hypotheses were withheld because independent verification "
    "could not be completed."
)


def _withhold_unverified_hypotheses(
    result: AIInvestigationResult,
) -> AIInvestigationResult:
    """Remove causal hypotheses when independent verification fails."""

    unknowns = list(result.unknowns)

    if HYPOTHESIS_VERIFICATION_FAILURE not in unknowns:
        unknowns.append(HYPOTHESIS_VERIFICATION_FAILURE)

    return result.model_copy(
        update={
            "hypotheses": [],
            "unknowns": unknowns,
        }
    )


def run_ai_investigation(
    *,
    incident: Any,
    evidence: Sequence[Any],
    client: OpenAI | OllamaClient | None = None,
) -> AIInvestigationResult:
    """Run an evidence-grounded investigation using the configured LLM."""

    # Reject cross-incident evidence before creating context or tools.
    for item in evidence:
        if item.incident_id != incident.id:
            raise ValueError(
                f"Evidence items must belong to incident {incident.id}"
            )

    incident_context = build_incident_context(incident, evidence)

    # Only evidence included in the bounded initial context may be cited
    # unless additional evidence is returned by an approved search tool.
    context_data = json.loads(incident_context)
    valid_evidence_ids = {
        item["evidence_id"]
        for item in context_data["evidence"]
    }

    executor = InvestigationToolExecutor(
        incident_id=incident.id,
        evidence_items=evidence,
    )

    provider = get_llm_provider()

    if provider == "openai":
        result = generate_investigation_with_tools(
            incident_context=incident_context,
            executor=executor,
            client=client,
        )

    elif provider == "ollama":
        result = generate_ollama_investigation_with_tools(
            incident_context=incident_context,
            executor=executor,
            client=client,
        )

    else:
        raise UnsupportedLLMProviderError(
            f"Unsupported LLM provider: {provider}. "
            "Supported providers are 'openai' and 'ollama'."
        )

    # Add only evidence IDs actually returned by successful tool searches.
    valid_evidence_ids.update(executor.returned_evidence_ids)

    # Validate the original investigation before verification.
    validated_result = validate_evidence_references(
        result,
        valid_evidence_ids=valid_evidence_ids,
    )
    validated_result = validate_investigation_quality(validated_result)

    # There is nothing to verify when the investigator proposed no hypotheses.
    if not validated_result.hypotheses:
        return validated_result

    # Independently assess every proposed hypothesis against its cited
    # evidence. Any verifier or validation failure withholds all hypotheses.
    try:
        if provider == "openai":
            verification_input = build_verification_input(
                hypotheses=validated_result.hypotheses,
                evidence=evidence,
            )

            verification = verify_openai_hypotheses(
                verification_input=verification_input,
            )

        else:
            verification = verify_ollama_hypotheses(
                hypotheses=validated_result.hypotheses,
                evidence=evidence,
            )

        verified_result = validate_hypothesis_verification(
            result=validated_result,
            verification=verification,
            valid_evidence_ids=valid_evidence_ids,
        )

    except Exception:
        return _withhold_unverified_hypotheses(validated_result)

    # Recommendation refinement is allowed only after verification.
    # It runs only when at least one verified hypothesis remains and
    # the initial investigation did not provide recommended checks.
    has_verified_hypothesis = bool(verified_result.hypotheses)

    if (
        verified_result.recommended_checks
        or not has_verified_hypothesis
    ):
        return verified_result

    try:
        if provider == "openai":
            refined_result = refine_investigation_recommendations(
                incident_context=incident_context,
                draft_result=verified_result,
                client=client,
            )
        else:
            refined_result = refine_ollama_investigation_recommendations(
                incident_context=incident_context,
                draft_result=verified_result,
                client=client,
            )

        refined_result = validate_evidence_references(
            refined_result,
            valid_evidence_ids=valid_evidence_ids,
        )
        refined_result = validate_investigation_quality(refined_result)

        if refined_result.recommended_checks:
            # Preserve the independently verified findings. Only accept
            # the recommendation list from the refinement response.
            return verified_result.model_copy(
                update={
                    "recommended_checks": refined_result.recommended_checks
                }
            )

    except Exception:
        # Refinement is optional. Keep the verified investigation if it fails.
        pass

    return verified_result
