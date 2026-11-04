import json
from typing import Any, Sequence

from openai import OpenAI

from app.ai_models import AIInvestigationResult
from app.evidence_validation import validate_evidence_references
from app.incident_context import build_incident_context
from app.llm_client import generate_investigation


def run_ai_investigation(
    *,
    incident: Any,
    evidence: Sequence[Any],
    client: OpenAI | None = None,
) -> AIInvestigationResult:
    """Build bounded context, run the LLM, and validate its citations."""

    for item in evidence:
        if item.incident_id != incident.id:
            raise ValueError(
                f"Evidence items must belong to incident {incident.id}"
            )

    incident_context = build_incident_context(incident, evidence)
    # Only evidence included in the bounded context may be cited.
    context_data = json.loads(incident_context)
    valid_evidence_ids = {
        item["evidence_id"]
        for item in context_data["evidence"]
    }

    result = generate_investigation(
        incident_context=incident_context,
        client=client,
    )

    return validate_evidence_references(
        result,
        valid_evidence_ids=valid_evidence_ids,
    )