
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import app.investigation_service as service
from app.tool_executor import InvestigationToolExecutor


class LoggingExecutor(InvestigationToolExecutor):
    total_calls = 0
    calls_without_new_evidence = 0

    def execute(self, *, tool_name, arguments):
        print("\n========== TOOL CALL ==========")
        print("Tool:", tool_name)
        print("Arguments:", arguments)

        result = super().execute(
            tool_name=tool_name,
            arguments=arguments,
        )

        type(self).total_calls += 1

        print("Search successful:", result.get("ok"))

        returned_ids = [
            item["evidence_id"]
            for item in result.get("results", [])
        ]

        new_ids = result.get("new_evidence_ids", [])

        previously_returned_ids = sorted(
            set(returned_ids) - set(new_ids)
        )

        print("Returned evidence IDs:", returned_ids)
        print("New evidence IDs:", new_ids)
        print("Previously discovered IDs:", previously_returned_ids)

        if not new_ids:
            type(self).calls_without_new_evidence += 1
            print("Result: NO NEW EVIDENCE")

        print("================================\n")

        return result


# Temporarily replace the executor used by the investigation service.
service.InvestigationToolExecutor = LoggingExecutor


incident = SimpleNamespace(
    id=9002,
    title="Checkout errors",
    description="Checkout requests are intermittently failing.",
    service="checkout",
    environment="production",
    severity="high",
    status="open",
    created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
)


evidence = []

# Add 18 large, mostly uninformative evidence items.
for evidence_id in range(901, 919):
    evidence.append(
        SimpleNamespace(
            id=evidence_id,
            incident_id=9002,
            source_type="log",
            content=(
                "Routine application heartbeat completed successfully. "
                "No actionable diagnostic details were recorded. "
            ) * 30,
            created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        )
    )


# This important evidence should be outside the initial context.
evidence.append(
    SimpleNamespace(
        id=919,
        incident_id=9002,
        source_type="log",
        content=(
            "CRITICAL DATABASE INCIDENT: PostgreSQL connection pool "
            "exhausted. All 50 connections are active. Connection "
            "acquisition failures increased sharply after deployment "
            "version checkout-api-2.8.1. Connection acquisition timeout "
            "is 30 seconds. Investigate possible connection leak."
        ),
        created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )
)


print("Starting real Ollama investigation...")
print("Total evidence items:", len(evidence))

context = service.build_incident_context(incident, evidence)

context_data = json.loads(context)

initial_ids = [
    item["evidence_id"]
    for item in context_data["evidence"]
]

print("Initial context evidence IDs:", initial_ids)
print("Evidence 919 initially included:", 919 in initial_ids)


result = service.run_ai_investigation(
    incident=incident,
    evidence=evidence,
)


print("\n========== FINAL INVESTIGATION ==========")
print(result.model_dump_json(indent=2))
print("=========================================")


# Print aggregate search statistics once, after the investigation.
print("\n========== SEARCH SUMMARY ==========")
print("Total tool calls:", LoggingExecutor.total_calls)
print(
    "Calls without new evidence:",
    LoggingExecutor.calls_without_new_evidence,
)
print("====================================")
