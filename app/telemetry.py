

import json

import math

from collections import defaultdict

from typing import Any



from google.protobuf.message import DecodeError



from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (

    ExportTraceServiceRequest,

)

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (

    ExportLogsServiceRequest,

)

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (

    ExportMetricsServiceRequest,

)





# ============================================================

# TELEMETRY LIMITS

# ============================================================



MAX_SPANS_PER_BATCH = 1000

MAX_LOG_RECORDS_PER_BATCH = 1000
MAX_METRIC_DATA_POINTS_PER_BATCH = 1000
MAX_METRIC_EXEMPLARS = 10
MAX_HISTOGRAM_BUCKETS = 160
MAX_SUMMARY_QUANTILES = 100



MAX_ATTRIBUTES = 40

MAX_ATTRIBUTE_VALUE_LENGTH = 500

MAX_EVENTS_PER_SPAN = 20

MAX_SPAN_NAME_LENGTH = 200

MAX_LOG_BODY_LENGTH = 4000



MAX_ATTRIBUTE_DEPTH = 5

MAX_TOTAL_ATTRIBUTE_VALUES = 200



MAX_TOPOLOGY_SPANS = 10000





# ============================================================

# EXCEPTIONS

# ============================================================



class TelemetryPayloadError(ValueError):

    """Raised when an OTLP telemetry payload is invalid or exceeds limits."""





# ============================================================

# SHARED ATTRIBUTE NORMALIZATION

# ============================================================



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

    """Extract normalized resource attributes."""



    if resource is None:

        return {}



    result = _attributes(resource.attributes)



    return result if isinstance(result, dict) else {}





# ============================================================

# TRACE NORMALIZATION

# ============================================================



def _span_to_evidence(

    *,

    span: Any,

    resource_attributes: dict[str, Any],

) -> dict[str, Any]:

    """Convert an OTLP span into a normalized record."""



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





# ============================================================

# LOG NORMALIZATION

# ============================================================



def _log_to_record(

    *,

    log_record: Any,

    resource_attributes: dict[str, Any],

) -> dict[str, Any]:

    """Convert an OTLP log record into a bounded normalized record."""



    service_name = resource_attributes.get(

        "service.name",

        "unknown-service",

    )



    if not isinstance(service_name, str):

        service_name = "unknown-service"



    service_name = service_name.strip()[:200] or "unknown-service"



    timestamp_ns = int(log_record.time_unix_nano)

    observed_timestamp_ns = int(log_record.observed_time_unix_nano)



    trace_id_bytes = bytes(log_record.trace_id)

    span_id_bytes = bytes(log_record.span_id)



    trace_id = None

    span_id = None



    if trace_id_bytes and any(trace_id_bytes):

        if len(trace_id_bytes) != 16:

            raise TelemetryPayloadError(

                "Invalid trace identifier in log record"

            )



        trace_id = trace_id_bytes.hex()



    if span_id_bytes and any(span_id_bytes):

        if len(span_id_bytes) != 8:

            raise TelemetryPayloadError(

                "Invalid span identifier in log record"

            )



        span_id = span_id_bytes.hex()



    attribute_budget = [0]



    body = _attribute_value(

        log_record.body,

        budget=attribute_budget,

    )



    if isinstance(body, str):

        body = body[:MAX_LOG_BODY_LENGTH]



    elif body is None:

        body = ""



    else:

        body = json.dumps(

            body,

            ensure_ascii=True,

            separators=(",", ":"),

        )[:MAX_LOG_BODY_LENGTH]



    attributes = _attributes(

        log_record.attributes,

        budget=attribute_budget,

    )



    return {

        "schema_version": 1,

        "signal": "log",

        "service_name": service_name,

        "timestamp_unix_nano": timestamp_ns,

        "observed_timestamp_unix_nano": observed_timestamp_ns,

        "severity_number": int(log_record.severity_number),

        "severity_text": str(log_record.severity_text)[:100],

        "body": body,

        "trace_id": trace_id,

        "span_id": span_id,

        "flags": int(log_record.flags),

        "event_name": str(log_record.event_name)[:200],

        "attributes": attributes,

    }





def parse_otlp_logs(payload: bytes) -> list[dict[str, Any]]:

    """Decode an OTLP ExportLogsServiceRequest into normalized log records."""



    if not isinstance(payload, bytes) or not payload:

        raise TelemetryPayloadError("Log payload cannot be empty")



    request = ExportLogsServiceRequest()



    try:

        request.ParseFromString(payload)

    except DecodeError as exc:

        raise TelemetryPayloadError(

            "Invalid OTLP protobuf log payload"

        ) from exc



    records = []



    for resource_logs in request.resource_logs:

        resource_attributes = _resource_attributes(

            resource_logs.resource

        )



        for scope_logs in resource_logs.scope_logs:

            for log_record in scope_logs.log_records:

                if len(records) >= MAX_LOG_RECORDS_PER_BATCH:

                    raise TelemetryPayloadError(

                        f"A batch cannot contain more than "

                        f"{MAX_LOG_RECORDS_PER_BATCH} log records"

                    )



                records.append(

                    _log_to_record(

                        log_record=log_record,

                        resource_attributes=resource_attributes,

                    )

                )



    if not records:

        raise TelemetryPayloadError(

            "The OTLP request did not contain any log records"

        )



    return records





# ============================================================

# SERVICE TOPOLOGY

# ============================================================



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

        if getattr(evidence, "source_type", None) != "trace":

            continue



        if processed >= MAX_TOPOLOGY_SPANS:

            break



        processed += 1



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



        if not isinstance(evidence_id, int) or isinstance(evidence_id, bool):

            continue



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





# ============================================================

# IDENTIFIER VALIDATION

# ============================================================



def _is_hex_identifier(value: str) -> bool:

    """Return whether a string contains only hexadecimal characters."""



    return bool(value) and all(

        character in "0123456789abcdefABCDEF"

        for character in value

    )


# ============================================================
# METRIC NORMALIZATION
# ============================================================


def _metric_number_value(point: Any) -> int | float | None:
    """Read an OTLP integer or floating-point value."""

    value_kind = point.WhichOneof("value")

    if value_kind == "as_int":
        return int(point.as_int)

    if value_kind == "as_double":
        number = float(point.as_double)
        return number if math.isfinite(number) else None

    return None


def _metric_optional_number(point: Any, field: str) -> float | None:
    """Read an optional numeric protobuf field when it is present."""

    if not point.HasField(field):
        return None

    number = float(getattr(point, field))
    return number if math.isfinite(number) else None


def _metric_exemplars(exemplars: Any) -> list[dict[str, Any]]:
    """Normalize a bounded collection of OTLP metric exemplars."""

    result = []

    for exemplar in list(exemplars)[:MAX_METRIC_EXEMPLARS]:
        trace_id_bytes = bytes(exemplar.trace_id)
        span_id_bytes = bytes(exemplar.span_id)

        if trace_id_bytes and (
            len(trace_id_bytes) != 16 or not any(trace_id_bytes)
        ):
            raise TelemetryPayloadError(
                "Invalid trace identifier in metric exemplar"
            )

        if span_id_bytes and (
            len(span_id_bytes) != 8 or not any(span_id_bytes)
        ):
            raise TelemetryPayloadError(
                "Invalid span identifier in metric exemplar"
            )

        result.append(
            {
                "time_unix_nano": int(exemplar.time_unix_nano),
                "value": _metric_number_value(exemplar),
                "trace_id": (
                    trace_id_bytes.hex() if trace_id_bytes else None
                ),
                "span_id": span_id_bytes.hex() if span_id_bytes else None,
                "filtered_attributes": _attributes(
                    exemplar.filtered_attributes
                ),
            }
        )

    return result


def _metric_point_payload(
    point: Any,
    metric_type: str,
) -> dict[str, Any]:
    """Normalize one OTLP metric data point while preserving its structure."""

    attribute_budget = [0]

    result: dict[str, Any] = {
        "attributes": _attributes(
            point.attributes,
            budget=attribute_budget,
        ),
        "start_time_unix_nano": int(point.start_time_unix_nano),
        "time_unix_nano": int(point.time_unix_nano),
        "flags": int(point.flags),
    }

    if metric_type in ("gauge", "sum"):
        value = _metric_number_value(point)

        if value is None:
            raise TelemetryPayloadError(
                "Metric data point is missing a valid numeric value"
            )

        result["value"] = value
        result["exemplars"] = _metric_exemplars(point.exemplars)

    elif metric_type == "histogram":
        bucket_counts = [int(value) for value in point.bucket_counts]
        explicit_bounds = [float(value) for value in point.explicit_bounds]

        if len(bucket_counts) > MAX_HISTOGRAM_BUCKETS:
            raise TelemetryPayloadError(
                "Histogram contains too many buckets"
            )

        if len(explicit_bounds) > MAX_HISTOGRAM_BUCKETS:
            raise TelemetryPayloadError(
                "Histogram contains too many explicit bounds"
            )

        if len(bucket_counts) != len(explicit_bounds) + 1:
            raise TelemetryPayloadError(
                "Histogram bucket counts and bounds are inconsistent"
            )

        if any(value < 0 for value in bucket_counts):
            raise TelemetryPayloadError(
                "Histogram bucket counts cannot be negative"
            )

        if any(
            not math.isfinite(value)
            for value in explicit_bounds
        ):
            raise TelemetryPayloadError(
                "Histogram contains a non-finite bucket bound"
            )

        if any(
            explicit_bounds[index] >= explicit_bounds[index + 1]
            for index in range(len(explicit_bounds) - 1)
        ):
            raise TelemetryPayloadError(
                "Histogram bucket bounds must be strictly increasing"
            )

        count = int(point.count)
        if count < 0 or sum(bucket_counts) != count:
            raise TelemetryPayloadError(
                "Histogram count does not match its bucket counts"
            )

        result.update(
            {
                "count": count,
                "sum": _metric_optional_number(point, "sum"),
                "bucket_counts": bucket_counts,
                "explicit_bounds": explicit_bounds,
                "min": _metric_optional_number(point, "min"),
                "max": _metric_optional_number(point, "max"),
                "exemplars": _metric_exemplars(point.exemplars),
            }
        )

    elif metric_type == "exponential_histogram":
        def normalize_buckets(buckets: Any) -> dict[str, Any]:
            counts = [int(value) for value in buckets.bucket_counts]

            if len(counts) > MAX_HISTOGRAM_BUCKETS:
                raise TelemetryPayloadError(
                    "Exponential histogram contains too many buckets"
                )

            if any(value < 0 for value in counts):
                raise TelemetryPayloadError(
                    "Exponential histogram bucket counts cannot be negative"
                )

            return {
                "offset": int(buckets.offset),
                "bucket_counts": counts,
            }

        count = int(point.count)
        zero_count = int(point.zero_count)
        zero_threshold = float(point.zero_threshold)

        if count < 0 or zero_count < 0:
            raise TelemetryPayloadError(
                "Exponential histogram counts cannot be negative"
            )

        if not math.isfinite(zero_threshold) or zero_threshold < 0:
            raise TelemetryPayloadError(
                "Exponential histogram has an invalid zero threshold"
            )

        positive = normalize_buckets(point.positive)
        negative = normalize_buckets(point.negative)

        represented_count = (
            zero_count
            + sum(positive["bucket_counts"])
            + sum(negative["bucket_counts"])
        )

        if represented_count != count:
            raise TelemetryPayloadError(
                "Exponential histogram count does not match its buckets"
            )

        result.update(
            {
                "count": count,
                "sum": _metric_optional_number(point, "sum"),
                "scale": int(point.scale),
                "zero_count": zero_count,
                "zero_threshold": zero_threshold,
                "positive": positive,
                "negative": negative,
                "min": _metric_optional_number(point, "min"),
                "max": _metric_optional_number(point, "max"),
                "exemplars": _metric_exemplars(point.exemplars),
            }
        )

    elif metric_type == "summary":
        quantiles = list(point.quantile_values)

        if len(quantiles) > MAX_SUMMARY_QUANTILES:
            raise TelemetryPayloadError(
                "Summary contains too many quantile values"
            )

        normalized_quantiles = []

        for item in quantiles:
            quantile = float(item.quantile)
            value = float(item.value)

            if (
                not math.isfinite(quantile)
                or not 0.0 <= quantile <= 1.0
                or not math.isfinite(value)
            ):
                raise TelemetryPayloadError(
                    "Summary contains an invalid quantile value"
                )

            normalized_quantiles.append(
                {
                    "quantile": quantile,
                    "value": value,
                }
            )

        count = int(point.count)
        total = float(point.sum)

        if count < 0 or not math.isfinite(total):
            raise TelemetryPayloadError(
                "Summary contains invalid count or sum"
            )

        result.update(
            {
                "count": count,
                "sum": total,
                "quantile_values": normalized_quantiles,
            }
        )

    else:
        raise TelemetryPayloadError(
            f"Unsupported OTLP metric type: {metric_type}"
        )

    return result


def parse_otlp_metrics(payload: bytes) -> list[dict[str, Any]]:
    """Decode an OTLP ExportMetricsServiceRequest into normalized records.

    One returned record represents one metric data point. Metric metadata,
    resource identity, aggregation temporality, and original point structure
    are retained in JSON-compatible form.
    """

    if not isinstance(payload, bytes) or not payload:
        raise TelemetryPayloadError("Metric payload cannot be empty")

    request = ExportMetricsServiceRequest()

    try:
        request.ParseFromString(payload)
    except DecodeError as exc:
        raise TelemetryPayloadError(
            "Invalid OTLP protobuf metric payload"
        ) from exc

    records: list[dict[str, Any]] = []

    for resource_metrics in request.resource_metrics:
        resource_attributes = _resource_attributes(
            resource_metrics.resource
        )

        service_name = resource_attributes.get(
            "service.name",
            "unknown-service",
        )

        if not isinstance(service_name, str):
            service_name = "unknown-service"

        service_name = service_name.strip()[:200] or "unknown-service"

        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                metric_type = metric.WhichOneof("data")

                if metric_type is None:
                    continue

                metric_name = str(metric.name).strip()[:200]

                if not metric_name:
                    raise TelemetryPayloadError(
                        "Metric name cannot be empty"
                    )

                metric_data = getattr(metric, metric_type)

                for point in metric_data.data_points:
                    if len(records) >= MAX_METRIC_DATA_POINTS_PER_BATCH:
                        raise TelemetryPayloadError(
                            "A batch cannot contain more than "
                            f"{MAX_METRIC_DATA_POINTS_PER_BATCH} "
                            "metric data points"
                        )

                    record: dict[str, Any] = {
                        "schema_version": 1,
                        "signal": "metric",
                        "service_name": service_name,
                        "metric_name": metric_name,
                        "description": str(metric.description)[:500],
                        "unit": str(metric.unit)[:100],
                        "metric_type": metric_type,
                        "data_point": _metric_point_payload(
                            point,
                            metric_type,
                        ),
                    }

                    if metric_type == "sum":
                        record["aggregation_temporality"] = int(
                            metric_data.aggregation_temporality
                        )
                        record["is_monotonic"] = bool(
                            metric_data.is_monotonic
                        )

                    elif metric_type in (
                        "histogram",
                        "exponential_histogram",
                    ):
                        record["aggregation_temporality"] = int(
                            metric_data.aggregation_temporality
                        )

                    records.append(record)

    if not records:
        raise TelemetryPayloadError(
            "The OTLP request did not contain any metric data points"
        )

    return records
