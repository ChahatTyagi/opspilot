
import json

from pydantic import ValidationError

from app.ai_models import AIInvestigationResult
from app.investigation_prompts import INVESTIGATION_INSTRUCTIONS
from app.ollama_client import OllamaClient
from app.refinement_prompts import (
    RECOMMENDATION_REFINEMENT_INSTRUCTIONS,
)
from app.tool_executor import InvestigationToolExecutor


OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_incident_evidence",
            "description": (
                "Search evidence belonging to this incident using "
                "one short, focused keyword or phrase (maximum 120 "
                "characters). Search for one specific symptom, "
                "component, error, or technical concept at a time. "
                "Do not combine unrelated keywords or list possible "
                "failure modes. If a search returns no results, try "
                "a different short query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A short keyword or phrase to search for."
                        ),
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }
]


def refine_ollama_investigation_recommendations(
    *,
    incident_context: str,
    draft_result: AIInvestigationResult,
    client: OllamaClient | None = None,
) -> AIInvestigationResult:
    """Refine recommendations without repeating evidence searches."""

    if client is None:
        client = OllamaClient()

    refinement_input = {
        "original_incident_context": incident_context,
        "draft_investigation": draft_result.model_dump(mode="json"),
    }

    messages = [
        {
            "role": "system",
            "content": RECOMMENDATION_REFINEMENT_INSTRUCTIONS,
        },
        {
            "role": "user",
            "content": json.dumps(refinement_input),
        },
    ]

    response = client.chat(
        messages=messages,
        format=AIInvestigationResult.model_json_schema(),
    )

    content = response["message"].get("content")

    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "Ollama did not return a refined investigation result"
        )

    try:
        return AIInvestigationResult.model_validate_json(content)
    except (ValueError, ValidationError) as exc:
        raise ValueError(
            "Ollama returned an invalid refined investigation result"
        ) from exc


def generate_ollama_investigation_with_tools(
    *,
    incident_context: str,
    executor: InvestigationToolExecutor,
    client: OllamaClient | None = None,
) -> AIInvestigationResult:
    """Generate an evidence-grounded investigation using Ollama tools."""

    if client is None:
        client = OllamaClient()

    messages = [
        {
            "role": "system",
            "content": INVESTIGATION_INSTRUCTIONS,
        },
        {
            "role": "user",
            "content": incident_context,
        },
    ]

    tool_call_count = 0

    while True:
        response = client.chat(
            messages=list(messages),
            tools=OLLAMA_TOOLS,
        )

        message = response["message"]
        tool_calls = message.get("tool_calls", [])

        if not isinstance(tool_calls, list):
            raise ValueError(
                "Ollama returned malformed tool calls"
            )

        if not tool_calls:
            break

        messages.append(message)

        stop_searching = False

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                raise ValueError("Malformed Ollama tool call")

            function = tool_call.get("function")

            if not isinstance(function, dict):
                raise ValueError("Malformed Ollama tool function")

            tool_name = function.get("name")
            arguments = function.get("arguments")

            if (
                not isinstance(tool_name, str)
                or not tool_name
                or not isinstance(arguments, dict)
            ):
                raise ValueError("Malformed Ollama tool call")

            if stop_searching:
                messages.append({
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps({
                        "ok": False,
                        "error": (
                            "Search stopped because the previous search "
                            "returned no new evidence. No further searches "
                            "are permitted. Produce the final investigation "
                            "using the evidence already available."
                        ),
                    }),
                })
                continue

            if tool_call_count >= executor.max_calls:
                messages.append({
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps({
                        "ok": False,
                        "error": (
                            "Tool-call limit reached. No further searches "
                            "are permitted. Produce the final investigation "
                            "using the evidence already available."
                        ),
                    }),
                })
                continue

            tool_call_count += 1

            result = executor.execute(
                tool_name=tool_name,
                arguments=arguments,
            )

            messages.append({
                "role": "tool",
                "tool_name": tool_name,
                "content": json.dumps(result),
            })

            returned_results = result.get("results", [])
            new_evidence_ids = result.get("new_evidence_ids", [])

            if returned_results and not new_evidence_ids:
                stop_searching = True

        if stop_searching or tool_call_count >= executor.max_calls:
            break

    messages.append({
        "role": "user",
        "content": (
            "Now produce the final incident investigation. "
            "Use only the original incident evidence and the "
            "evidence returned by the tools. Do not treat previous "
            "assistant-generated text as evidence. Return only the "
            "structured investigation requested by the JSON schema."
        ),
    })

    final_response = client.chat(
        messages=list(messages),
        format=AIInvestigationResult.model_json_schema(),
    )

    content = final_response["message"].get("content")

    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "Ollama did not return a structured investigation result"
        )

    try:
        return AIInvestigationResult.model_validate_json(content)
    except (ValueError, ValidationError) as exc:
        raise ValueError(
            "Ollama returned an invalid structured investigation result"
        ) from exc
