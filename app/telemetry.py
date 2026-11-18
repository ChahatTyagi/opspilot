
import json
import math
from collections import defaultdict
from typing import Any

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


MAX_SPANS_PER_BATCH = 1000
MAX_ATTRIBUTES = 40
MAX_ATTRIBUTE_VALUE_LENGTH = 500
MAX_EVENTS_PER_SPAN = 20
MAX_SPAN_NAME_LENGTH = 200

MAX_ATTRIBUTE_DEPTH = 5
MAX_TOTAL_ATTRIBUTE_VALUES = 200

MAX_TOPOLOGY_SPANS = 10000


class TelemetryPayloadError(ValueError):
    """Raised when an OTLP trace payload is invalid or exceeds limits."""


def _attribute_value(
    value: Any,
    *,
    depth: int = 0,
    budget: list[int] | None = None,
) -> Any:
    """Convert an OpenTelemetry AnyValue into a bounded JSON value."""

    if budget is None:
        budget = [0]

    if budget[0] >= MAX_TOTAL_ATTRIBUTE_VALUES:
        return "[TRUNCATED]"

    budget[0] += 1

    if depth > MAX_ATTRIBUTE_DEPTH:
        return "[MAX_DEPTH]"

    kind = value.WhichOneof("value")

    if kind == "string_value":
        return value.string_value[:MAX_ATTRIBUTE_VALUE_LENGTH]

    if kind == "bool_value":
        return bool(value.bool_value)

    if kind == "int_value":
        return int(value.int_value)

    if kind == "double_value":
        number = float(value.double_value)
        return number if math.isfinite(number) else None

    if kind == "bytes_value":
        return value.bytes_value[:100].hex()

    if kind == "array_value":
        result = []

        for item in value.array_value.values[:20]:
            if budget[0] >= MAX_TOTAL_ATTRIBUTE_VALUES:
                result.append("[TRUNCATED]")
                break

            result.append(
                _attribute_value(
                    item,
                    depth=depth + 1,
                    budget=budget,
                )
            )

        return result

    if kind == "kvlist_value":
        return _attributes(
            value.kvlist_value.values,
            depth=depth + 1,
            budget=budget,
        )

    return None


def _attributes(
    attributes: Any,
    *,
    depth: int = 0,
    budget: list[int] | None = None,
) -> Any:
    """Convert a bounded collection of OpenTelemetry attributes."""

    if budget is None:
        budget = [0]

    if depth > MAX_ATTRIBUTE_DEPTH:
        return "[MAX_DEPTH]"

    result = {}

    for item in list(attributes)[:MAX_ATTRIBUTES]:
        if budget[0] >= MAX_TOTAL_ATTRIBUTE_VALUES:
            result["_truncated"] = True
            break

        key = str(item.key)[:200]

        if not key:
            continue

        result[key] = _attribute_value(
            item.value,
            budget=budget,
            depth=depth,
        )

    return result


def _resource_attributes(resource: Any) -> dict[str, Any]:
    if resource is None:
        return {}

    result = _attributes(resource.attributes)

    return result if isinstance(result, dict) else {}


def _span_to_evidence(
    *,
    span: Any,
    resource_attributes: dict[str, Any],
) -> dict[str, Any]:
    trace_id_bytes = bytes(span.trace_id)
    span_id_bytes = bytes(span.span_id)
    parent_span_id_bytes = bytes(span.parent_span_id)

    if len(trace_id_bytes) != 16 or not any(trace_id_bytes):
        raise TelemetryPayloadError("Invalid trace identifier")

    if len(span_id_bytes) != 8 or not any(span_id_bytes):
        raise TelemetryPayloadError("Invalid span identifier")

    if len(parent_span_id_bytes) not in (0, 8):
        raise TelemetryPayloadError("Invalid parent span identifier")

    trace_id = trace_id_bytes.hex()
    span_id = span_id_bytes.hex()

    parent_span_id = (
        parent_span_id_bytes.hex()
        if parent_span_id_bytes and any(parent_span_id_bytes)
        else None
    )

    service_name = resource_attributes.get(
        "service.name",
        "unknown-service",
    )

    if not isinstance(service_name, str):
        service_name = "unknown-service"

    service_name = service_name.strip()[:200] or "unknown-service"

    attribute_budget = [0]

    attributes = _attributes(
        span.attributes,
        budget=attribute_budget,
    )

    events = []

    for event in list(span.events)[:MAX_EVENTS_PER_SPAN]:
        events.append(
            {
                "name": str(event.name)[:200],
                "time_unix_nano": int(event.time_unix_nano),
                "attributes": _attributes(
                    event.attributes,
                    budget=attribute_budget,
                ),
            }
        )

    start_ns = int(span.start_time_unix_nano)
    end_ns = int(span.end_time_unix_nano)

    duration_ms = (
        max(0, end_ns - start_ns) / 1_000_000
        if start_ns and end_ns >= start_ns
        else None
    )

    status_code = int(span.status.code)

    return {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "service_name": service_name,
        "span_name": str(span.name)[:MAX_SPAN_NAME_LENGTH],
        "span_kind": int(span.kind),
        "start_time_unix_nano": start_ns,
        "end_time_unix_nano": end_ns,
        "duration_ms": duration_ms,
        "status_code": status_code,
        "status_message": str(span.status.message)[:500],
        "attributes": attributes,
        "events": events,
    }


def parse_otlp_traces(payload: bytes) -> list[dict[str, Any]]:
    """Decode an OTLP ExportTraceServiceRequest into normalized spans."""

    if not isinstance(payload, bytes) or not payload:
        raise TelemetryPayloadError("Trace payload cannot be empty")

    request = ExportTraceServiceRequest()

    try:
        request.ParseFromString(payload)
    except DecodeError as exc:
        raise TelemetryPayloadError(
            "Invalid OTLP protobuf trace payload"
        ) from exc

    records = []

    for resource_spans in request.resource_spans:
        resource_attributes = _resource_attributes(
            resource_spans.resource
        )

        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                if len(records) >= MAX_SPANS_PER_BATCH:
                    raise TelemetryPayloadError(
                        f"A batch cannot contain more than "
                        f"{MAX_SPANS_PER_BATCH} spans"
                    )

                records.append(
                    _span_to_evidence(
                        span=span,
                        resource_attributes=resource_attributes,
                    )
                )

    if not records:
        raise TelemetryPayloadError(
            "The OTLP request did not contain any spans"
        )

    return records


def build_service_topology(
    evidence_items: list[Any],
) -> dict[str, Any]:
    """Derive service dependencies from stored parent-child trace spans."""

    spans_by_trace: dict[
        str, dict[str, dict[str, Any]]
    ] = defaultdict(dict)

    nodes: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "service": "",
            "span_count": 0,
            "error_count": 0,
            "evidence_ids": set(),
        }
    )

    trace_ids = set()
    processed = 0

    for evidence in evidence_items:
        if processed >= MAX_TOPOLOGY_SPANS:
            break

        processed += 1

        if getattr(evidence, "source_type", None) != "trace":
            continue

        content = getattr(evidence, "content", None)

        if not isinstance(content, str):
            continue

        try:
            record = json.loads(content)
        except (TypeError, ValueError):
            continue

        if (
            not isinstance(record, dict)
            or record.get("schema_version") != 1
            or record.get("signal") != "trace"
        ):
            continue

        trace_id = record.get("trace_id")
        span_id = record.get("span_id")
        service = record.get("service_name")

        if not all(
            isinstance(value, str) and value
            for value in (trace_id, span_id, service)
        ):
            continue

        if (
            len(trace_id) != 32
            or len(span_id) != 16
            or not _is_hex_identifier(trace_id)
            or not _is_hex_identifier(span_id)
        ):
            continue

        service = service.strip()[:200]

        if not service:
            continue

        evidence_id = getattr(evidence, "id", None)

        if not isinstance(evidence_id, int):
            continue

        # Ignore duplicate span identities before updating statistics.
        existing_span = spans_by_trace[trace_id].get(span_id)

        if existing_span is not None:
            continue

        trace_ids.add(trace_id)

        spans_by_trace[trace_id][span_id] = {
            **record,
            "service_name": service,
            "evidence_id": evidence_id,
        }

        node = nodes[service]
        node["service"] = service
        node["span_count"] += 1

        if record.get("status_code") == 2:
            node["error_count"] += 1

        node["evidence_ids"].add(evidence_id)

    edges: dict[tuple[str, str], dict[str, Any]] = {}

    for trace_id, spans in spans_by_trace.items():
        for child in spans.values():
            parent_id = child.get("parent_span_id")

            if (
                not isinstance(parent_id, str)
                or len(parent_id) != 16
                or not _is_hex_identifier(parent_id)
            ):
                continue

            parent = spans.get(parent_id)

            if parent is None:
                continue

            source = parent["service_name"]
            target = child["service_name"]

            if source == target:
                continue

            edge = edges.setdefault(
                (source, target),
                {
                    "source": source,
                    "target": target,
                    "call_count": 0,
                    "error_count": 0,
                    "durations": [],
                    "evidence_ids": set(),
                    "_seen": set(),
                },
            )

            relationship = (
                trace_id,
                parent_id,
                child["span_id"],
            )

            if relationship in edge["_seen"]:
                continue

            edge["_seen"].add(relationship)
            edge["call_count"] += 1

            if child.get("status_code") == 2:
                edge["error_count"] += 1

            duration = child.get("duration_ms")

            if (
                isinstance(duration, (int, float))
                and math.isfinite(duration)
                and duration >= 0
            ):
                edge["durations"].append(float(duration))

            edge["evidence_ids"].update(
                [
                    parent["evidence_id"],
                    child["evidence_id"],
                ]
            )

    serialized_edges = []

    for edge in edges.values():
        durations = edge.pop("durations")
        edge.pop("_seen", None)

        edge["average_duration_ms"] = (
            round(sum(durations) / len(durations), 2)
            if durations
            else None
        )

        edge["evidence_ids"] = sorted(edge["evidence_ids"])
        serialized_edges.append(edge)

    serialized_nodes = []

    for node in nodes.values():
        node["evidence_ids"] = sorted(node["evidence_ids"])
        serialized_nodes.append(node)

    serialized_nodes.sort(key=lambda item: item["service"])
    serialized_edges.sort(
        key=lambda item: (item["source"], item["target"])
    )

    return {
        "nodes": serialized_nodes,
        "edges": serialized_edges,
        "trace_count": len(trace_ids),
    }


def _is_hex_identifier(value: str) -> bool:
    """Return whether a string contains only hexadecimal characters."""

    return bool(value) and all(
        character in "0123456789abcdefABCDEF"
        for character in value
    )
