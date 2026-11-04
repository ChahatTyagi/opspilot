
import json
from typing import Any, Sequence

from openai import OpenAI

from app.ai_models import AIInvestigationResult
from app.evidence_validation import validate_evidence_references
from app.incident_context import build_incident_context
from app.llm_client import generate_investigation_with_tools
from app.tool_executor import InvestigationToolExecutor


def run_ai_investigation(
    *,
    incident: Any,
    evidence: Sequence[Any],
    client: OpenAI | None = None,
) -> AIInvestigationResult:
    """Build bounded context, run tool-assisted investigation, and validate citations."""

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

    result = generate_investigation_with_tools(
        incident_context=incident_context,
        executor=executor,
        client=client,
    )

    # Add only evidence IDs actually returned by successful tool searches.
    valid_evidence_ids.update(executor.returned_evidence_ids)

    return validate_evidence_references(
        result,
        valid_evidence_ids=valid_evidence_ids,
    )
