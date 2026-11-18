
import json
from types import SimpleNamespace

import pytest

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue

from app.telemetry import (
    TelemetryPayloadError,
    _attribute_value,
    build_service_topology,
    parse_otlp_traces,
)


def make_otlp_payload():
    request = ExportTraceServiceRequest()

    resource_spans = request.resource_spans.add()
    service_attribute = resource_spans.resource.attributes.add()
    service_attribute.key = "service.name"
    service_attribute.value.string_value = "checkout"

    scope_spans = resource_spans.scope_spans.add()

    parent = scope_spans.spans.add()
    parent.trace_id = bytes.fromhex("1" * 32)
    parent.span_id = bytes.fromhex("a" * 16)
    parent.name = "checkout-request"
    parent.start_time_unix_nano = 1_000_000
    parent.end_time_unix_nano = 5_000_000

    child = scope_spans.spans.add()
    child.trace_id = bytes.fromhex("1" * 32)
    child.span_id = bytes.fromhex("b" * 16)
    child.parent_span_id = bytes.fromhex("a" * 16)
    child.name = "database-query"
    child.start_time_unix_nano = 2_000_000
    child.end_time_unix_nano = 4_000_000
    child.status.code = 2

    return request.SerializeToString()


def make_evidence(
    evidence_id,
    record,
    source_type="trace",
):
    return SimpleNamespace(
        id=evidence_id,
        source_type=source_type,
        content=json.dumps(record),
    )


def test_parse_otlp_trace_payload():
    records = parse_otlp_traces(make_otlp_payload())

    assert len(records) == 2

    parent, child = records

    assert parent["service_name"] == "checkout"
    assert parent["span_name"] == "checkout-request"
    assert parent["parent_span_id"] is None

    assert child["service_name"] == "checkout"
    assert child["span_name"] == "database-query"
    assert child["parent_span_id"] == "a" * 16
    assert child["status_code"] == 2


def test_parse_otlp_rejects_empty_payload():
    with pytest.raises(TelemetryPayloadError):
        parse_otlp_traces(b"")


def test_parse_otlp_rejects_invalid_protobuf():
    with pytest.raises(TelemetryPayloadError):
        parse_otlp_traces(b"\xff\xff\xff")


def test_topology_derives_cross_service_dependency():
    parent = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": "1" * 32,
        "span_id": "a" * 16,
        "parent_span_id": None,
        "service_name": "checkout",
        "status_code": 0,
        "duration_ms": 4.0,
    }

    child = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": "1" * 32,
        "span_id": "b" * 16,
        "parent_span_id": "a" * 16,
        "service_name": "payment",
        "status_code": 2,
        "duration_ms": 2.0,
    }

    result = build_service_topology(
        [
            make_evidence(10, parent),
            make_evidence(11, child),
        ]
    )

    assert result["trace_count"] == 1
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1

    edge = result["edges"][0]

    assert edge["source"] == "checkout"
    assert edge["target"] == "payment"
    assert edge["call_count"] == 1
    assert edge["error_count"] == 1
    assert edge["average_duration_ms"] == 2.0


def test_topology_ignores_non_trace_evidence():
    result = build_service_topology(
        [
            make_evidence(
                10,
                {"message": "database error"},
                source_type="log",
            )
        ]
    )

    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["trace_count"] == 0


def test_topology_does_not_create_cross_trace_edges():
    parent = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": "1" * 32,
        "span_id": "a" * 16,
        "parent_span_id": None,
        "service_name": "checkout",
        "status_code": 0,
        "duration_ms": 1.0,
    }

    child = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": "2" * 32,
        "span_id": "b" * 16,
        "parent_span_id": "a" * 16,
        "service_name": "payment",
        "status_code": 0,
        "duration_ms": 1.0,
    }

    result = build_service_topology(
        [
            make_evidence(10, parent),
            make_evidence(11, child),
        ]
    )

    assert result["edges"] == []
    assert result["trace_count"] == 2


def test_topology_ignores_malformed_evidence():
    result = build_service_topology(
        [
            SimpleNamespace(
                id=10,
                source_type="trace",
                content="not-json",
            )
        ]
    )

    assert result["nodes"] == []
    assert result["edges"] == []


def test_nested_telemetry_attributes_are_depth_limited():
    root = AnyValue()
    current = root

    for _ in range(10):
        nested = current.kvlist_value.values.add()
        nested.key = "nested"
        current = nested.value

    current.string_value = "deep-value"

    result = _attribute_value(root)

    def contains_depth_marker(value):
        if value == "[MAX_DEPTH]":
            return True

        if isinstance(value, dict):
            return any(
                contains_depth_marker(item)
                for item in value.values()
            )

        if isinstance(value, list):
            return any(
                contains_depth_marker(item)
                for item in value
            )

        return False

    assert contains_depth_marker(result)


def test_topology_ignores_valid_json_that_is_not_an_object():
    evidence = SimpleNamespace(
        id=123,
        source_type="trace",
        content="[]",
    )

    result = build_service_topology([evidence])

    assert result == {
        "nodes": [],
        "edges": [],
        "trace_count": 0,
    }


def test_topology_does_not_count_duplicate_span_identity_twice():
    span = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": "1" * 32,
        "span_id": "a" * 16,
        "parent_span_id": None,
        "service_name": "checkout",
        "status_code": 0,
        "duration_ms": 1.0,
    }

    result = build_service_topology(
        [
            make_evidence(10, span),
            make_evidence(11, span),
        ]
    )

    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["span_count"] == 1
    assert result["nodes"][0]["error_count"] == 0
    assert result["nodes"][0]["evidence_ids"] == [10]
    assert result["trace_count"] == 1
