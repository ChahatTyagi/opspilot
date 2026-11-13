
import json
from typing import Any, Sequence

from openai import OpenAI

from app.ai_models import AIInvestigationResult
from app.config import get_llm_provider
from app.evidence_validation import (
    validate_evidence_references,
    validate_investigation_quality,
)
from app.incident_context import build_incident_context
from app.llm_client import (
    generate_investigation_with_tools,
    refine_investigation_recommendations,
)
from app.ollama_client import OllamaClient
from app.ollama_investigation import (
    generate_ollama_investigation_with_tools,
    refine_ollama_investigation_recommendations,
)
from app.tool_executor import InvestigationToolExecutor


class UnsupportedLLMProviderError(RuntimeError):
    """Raised when the configured LLM provider is not supported."""


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

    # Select the configured LLM provider.
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

    # Validate the original investigation before considering refinement.
    validated_result = validate_evidence_references(
        result,
        valid_evidence_ids=valid_evidence_ids,
    )
    validated_result = validate_investigation_quality(validated_result)

    # Refine only when there is a supported hypothesis but no checks.
    has_supported_hypothesis = any(
        hypothesis.supporting_evidence_ids
        for hypothesis in validated_result.hypotheses
    )

    if validated_result.recommended_checks or not has_supported_hypothesis:
        return validated_result

    try:
        # This is a separate model call. It does not repeat evidence searches.
        if provider == "openai":
            refined_result = refine_investigation_recommendations(
                incident_context=incident_context,
                draft_result=validated_result,
                client=client,
            )
        else:
            refined_result = refine_ollama_investigation_recommendations(
                incident_context=incident_context,
                draft_result=validated_result,
                client=client,
            )

        # Validate the refinement before accepting any of its output.
        refined_result = validate_evidence_references(
            refined_result,
            valid_evidence_ids=valid_evidence_ids,
        )
        refined_result = validate_investigation_quality(refined_result)

        # Keep the original findings and accept only non-empty recommendations.
        if refined_result.recommended_checks:
            return validated_result.model_copy(
                update={
                    "recommended_checks": refined_result.recommended_checks
                }
            )

    except Exception:
        # Refinement is optional. A failed second call must not discard
        # an otherwise valid initial investigation.
        pass

    return validated_result
