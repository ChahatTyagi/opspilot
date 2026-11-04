
import json
from typing import Any, Sequence

from app.investigation_tools import search_incident_evidence


MAX_TOOL_CALLS = 5
MAX_ARGUMENTS_LENGTH = 1000
MAX_ERROR_LENGTH = 200


class InvestigationToolExecutor:
    """Execute only explicitly registered, bounded investigation tools."""

    def __init__(
        self,
        *,
        incident_id: int,
        evidence_items: Sequence[Any],
        max_calls: int = MAX_TOOL_CALLS,
    ):
        if not isinstance(max_calls, int) or isinstance(max_calls, bool):
            raise ValueError("max_calls must be an integer.")

        if not 1 <= max_calls <= MAX_TOOL_CALLS:
            raise ValueError(
                f"max_calls must be between 1 and {MAX_TOOL_CALLS}."
            )

        self.incident_id = incident_id
        self.evidence_items = evidence_items
        self.max_calls = max_calls
        self.call_count = 0
        self.seen_calls = set()

        # Track only evidence IDs actually returned by successful searches.
        self.returned_evidence_ids: set[int] = set()

        # Explicit allowlist: no dynamic imports, eval, shell, or arbitrary code.
        self._tools = {
            "search_incident_evidence": self._search_incident_evidence,
        }

    def execute(
        self,
        *,
        tool_name: str,
        arguments: Any,
    ) -> dict:
        """Execute one validated tool request and return a safe result."""

        if not isinstance(tool_name, str) or tool_name not in self._tools:
            return {
                "ok": False,
                "error": "Unknown tool requested.",
            }

        if not isinstance(arguments, dict):
            return {
                "ok": False,
                "error": "Tool arguments must be an object.",
            }

        try:
            serialized_arguments = json.dumps(
                arguments,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            return {
                "ok": False,
                "error": "Tool arguments must contain JSON-compatible values.",
            }

        if len(serialized_arguments) > MAX_ARGUMENTS_LENGTH:
            return {
                "ok": False,
                "error": "Tool arguments exceed the size limit.",
            }

        if tool_name == "search_incident_evidence":
            if set(arguments) != {"query"}:
                return {
                    "ok": False,
                    "error": "Invalid arguments for search_incident_evidence.",
                }

            if not isinstance(arguments["query"], str):
                return {
                    "ok": False,
                    "error": "Tool argument 'query' must be a string.",
                }

        call_signature = (tool_name, serialized_arguments)

        if call_signature in self.seen_calls:
            return {
                "ok": False,
                "error": "Repeated identical tool call rejected.",
            }

        if self.call_count >= self.max_calls:
            return {
                "ok": False,
                "error": "Tool call limit reached.",
            }

        self.seen_calls.add(call_signature)
        self.call_count += 1

        try:
            result = self._tools[tool_name](arguments)
        except (ValueError, TypeError, AttributeError):
            return {
                "ok": False,
                "error": "Tool request could not be processed.",
            }
        except Exception:
            # Do not expose internal exception details to the model.
            return {
                "ok": False,
                "error": "Tool execution failed.",
            }

        return {
            "ok": True,
            **result,
        }

    def _search_incident_evidence(self, arguments: dict) -> dict:
        """Search evidence for this incident and track returned evidence IDs."""

        results = search_incident_evidence(
            query=arguments["query"],
            incident_id=self.incident_id,
            evidence_items=self.evidence_items,
        )

        self.returned_evidence_ids.update(
            item["evidence_id"]
            for item in results
        )

        return {"results": results}
