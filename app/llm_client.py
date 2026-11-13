
import json
from typing import Any

from openai import OpenAI

from app.ai_models import AIInvestigationResult
from app.config import get_openai_api_key, get_openai_model
from app.investigation_prompts import INVESTIGATION_INSTRUCTIONS
from app.refinement_prompts import (
    RECOMMENDATION_REFINEMENT_INSTRUCTIONS,
)
from app.tool_executor import InvestigationToolExecutor


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM provider is not configured."""


def create_openai_client() -> OpenAI:
    api_key = get_openai_api_key()

    if not api_key:
        raise LLMConfigurationError(
            "OPENAI_API_KEY is not configured"
        )

    return OpenAI(api_key=api_key)


def generate_investigation(
    *,
    incident_context: str,
    client: OpenAI | None = None,
) -> AIInvestigationResult:
    """Generate a structured investigation from supplied evidence."""

    if client is None:
        client = create_openai_client()

    response = client.responses.parse(
        model=get_openai_model(),
        instructions=INVESTIGATION_INSTRUCTIONS,
        input=incident_context,
        text_format=AIInvestigationResult,
        max_output_tokens=1200,
    )

    result = response.output_parsed

    if result is None:
        raise ValueError(
            "The LLM did not return a structured investigation result"
        )

    return result


def refine_investigation_recommendations(
    *,
    incident_context: str,
    draft_result: AIInvestigationResult,
    client: OpenAI | None = None,
) -> AIInvestigationResult:
    """Refine recommendations without repeating evidence searches."""

    if client is None:
        client = create_openai_client()

    refinement_input = {
        "original_incident_context": incident_context,
        "draft_investigation": draft_result.model_dump(mode="json"),
    }

    response = client.responses.parse(
        model=get_openai_model(),
        instructions=RECOMMENDATION_REFINEMENT_INSTRUCTIONS,
        input=json.dumps(refinement_input),
        text_format=AIInvestigationResult,
        max_output_tokens=1200,
    )

    result = response.output_parsed

    if result is None:
        raise ValueError(
            "The LLM did not return a refined investigation result"
        )

    return result


def generate_investigation_with_tools(
    *,
    incident_context: str,
    executor: InvestigationToolExecutor,
    client: OpenAI | None = None,
) -> AIInvestigationResult:
    """Generate an investigation while allowing bounded evidence-search calls."""

    if client is None:
        client = create_openai_client()

    instructions = (
        INVESTIGATION_INSTRUCTIONS
        + "\nYou may use search_incident_evidence to find relevant evidence."
    )

    tools = [
        {
            "type": "function",
            "name": "search_incident_evidence",
            "description": (
                "Search evidence belonging to this incident for a relevant "
                "keyword or phrase."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A short keyword or phrase to search for.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]

    response = client.responses.parse(
        model=get_openai_model(),
        instructions=instructions,
        input=incident_context,
        tools=tools,
        tool_choice="auto",
        max_output_tokens=1200,
        max_tool_calls=5,
        text_format=AIInvestigationResult,
    )

    tool_call_count = 0

    while True:
        tool_calls = [
            item
            for item in response.output
            if getattr(item, "type", None) == "function_call"
        ]

        if not tool_calls:
            break

        tool_outputs = []

        for tool_call in tool_calls:
            if tool_call_count >= executor.max_calls:
                raise ValueError(
                    "LLM exceeded the investigation tool-call limit"
                )

            tool_call_count += 1

            tool_name = getattr(tool_call, "name", None)
            raw_arguments = getattr(tool_call, "arguments", None)
            call_id = getattr(tool_call, "call_id", None)

            if (
                not isinstance(tool_name, str)
                or not tool_name
                or not isinstance(raw_arguments, str)
                or not isinstance(call_id, str)
                or not call_id
            ):
                raise ValueError("Malformed tool call returned by the LLM")

            try:
                arguments = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    "Invalid tool arguments returned by the LLM"
                ) from exc

            tool_result = executor.execute(
                tool_name=tool_name,
                arguments=arguments,
            )

            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(tool_result),
                }
            )

        response = client.responses.parse(
            model=get_openai_model(),
            instructions=instructions,
            input=tool_outputs,
            tools=tools,
            tool_choice="auto",
            max_output_tokens=1200,
            max_tool_calls=5,
            previous_response_id=response.id,
            text_format=AIInvestigationResult,
        )

    result = getattr(response, "output_parsed", None)

    if result is None:
        raise ValueError(
            "The LLM did not return a structured investigation result"
        )

    return result
