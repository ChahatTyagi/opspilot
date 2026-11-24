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
    parse_otlp_logs,
    parse_otlp_metrics,
    parse_otlp_traces,
)

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
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

def test_topology_span_limit_does_not_count_non_trace_evidence():

    from app.telemetry import MAX_TOPOLOGY_SPANS

    non_trace_evidence = [

        make_evidence(

            index,

            {"message": "Database timeout"},

            source_type="log",

        )

        for index in range(MAX_TOPOLOGY_SPANS)

    ]

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

        non_trace_evidence

        + [

            make_evidence(MAX_TOPOLOGY_SPANS + 1, parent),

            make_evidence(MAX_TOPOLOGY_SPANS + 2, child),

        ]

    )

    assert len(result["nodes"]) == 2

    assert len(result["edges"]) == 1

    assert result["trace_count"] == 1

    assert result["edges"][0]["source"] == "checkout"

    assert result["edges"][0]["target"] == "payment"

def make_otlp_logs_payload():

    request = ExportLogsServiceRequest()

    resource_logs = request.resource_logs.add()

    service_attribute = resource_logs.resource.attributes.add()

    service_attribute.key = "service.name"

    service_attribute.value.string_value = "checkout-service"

    scope_logs = resource_logs.scope_logs.add()

    log_record = scope_logs.log_records.add()

    log_record.time_unix_nano = 1_700_000_000_000_000_000

    log_record.observed_time_unix_nano = 1_700_000_001_000_000_000

    log_record.severity_number = 17

    log_record.severity_text = "ERROR"

    log_record.body.string_value = "Database connection failed"

    log_record.trace_id = bytes.fromhex("1" * 32)

    log_record.span_id = bytes.fromhex("a" * 16)

    log_record.event_name = "database.error"

    attribute = log_record.attributes.add()

    attribute.key = "db.system"

    attribute.value.string_value = "postgresql"

    return request.SerializeToString()

def test_parse_otlp_log_payload():

    records = parse_otlp_logs(make_otlp_logs_payload())

    assert len(records) == 1

    record = records[0]

    assert record["schema_version"] == 1

    assert record["signal"] == "log"

    assert record["service_name"] == "checkout-service"

    assert record["severity_number"] == 17

    assert record["severity_text"] == "ERROR"

    assert record["body"] == "Database connection failed"

    assert record["trace_id"] == "1" * 32

    assert record["span_id"] == "a" * 16

    assert record["event_name"] == "database.error"

    assert record["attributes"]["db.system"] == "postgresql"

def test_parse_otlp_logs_rejects_empty_payload():

    with pytest.raises(TelemetryPayloadError):

        parse_otlp_logs(b"")

def test_parse_otlp_logs_rejects_invalid_protobuf():

    with pytest.raises(TelemetryPayloadError):

        parse_otlp_logs(b"\xff\xff\xff")

def test_parse_otlp_logs_rejects_request_without_log_records():

    request = ExportLogsServiceRequest()

    resource_logs = request.resource_logs.add()

    resource_logs.scope_logs.add()

    with pytest.raises(

        TelemetryPayloadError,

        match="did not contain any log records",

    ):

        parse_otlp_logs(request.SerializeToString())

def test_parse_otlp_logs_rejects_invalid_trace_identifier():

    request = ExportLogsServiceRequest()

    resource_logs = request.resource_logs.add()

    scope_logs = resource_logs.scope_logs.add()

    log_record = scope_logs.log_records.add()

    log_record.body.string_value = "Invalid trace identifier"

    log_record.trace_id = b"invalid"

    with pytest.raises(

        TelemetryPayloadError,

        match="Invalid trace identifier",

    ):

        parse_otlp_logs(request.SerializeToString())

def test_parse_otlp_logs_supports_records_without_trace_context():

    request = ExportLogsServiceRequest()

    resource_logs = request.resource_logs.add()

    scope_logs = resource_logs.scope_logs.add()

    log_record = scope_logs.log_records.add()

    log_record.body.string_value = "Application started"

    records = parse_otlp_logs(request.SerializeToString())

    assert len(records) == 1

    assert records[0]["body"] == "Application started"

    assert records[0]["trace_id"] is None

    assert records[0]["span_id"] is None

    assert records[0]["service_name"] == "unknown-service"

def test_parse_otlp_logs_rejects_oversized_batch():

    from app.telemetry import MAX_LOG_RECORDS_PER_BATCH

    request = ExportLogsServiceRequest()

    resource_logs = request.resource_logs.add()

    scope_logs = resource_logs.scope_logs.add()

    for _ in range(MAX_LOG_RECORDS_PER_BATCH + 1):

        log_record = scope_logs.log_records.add()

        log_record.body.string_value = "Test log"

    with pytest.raises(

        TelemetryPayloadError,

        match="cannot contain more than",

    ):

        parse_otlp_logs(request.SerializeToString())

# ============================================================
# OTLP METRICS
# ============================================================

def _metric_request():
    request = ExportMetricsServiceRequest()
    resource_metrics = request.resource_metrics.add()
    service_attribute = resource_metrics.resource.attributes.add()
    service_attribute.key = "service.name"
    service_attribute.value.string_value = "checkout-service"
    scope_metrics = resource_metrics.scope_metrics.add()
    return request, scope_metrics


def _add_number_point(container, value=12.5):
    point = container.data_points.add()
    point.time_unix_nano = 1_700_000_000_000_000_000
    point.start_time_unix_nano = 1_699_999_999_000_000_000
    point.as_double = value
    return point


def test_parse_otlp_gauge_metric():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "cpu.utilization"
    metric.description = "CPU utilization"
    metric.unit = "1"
    point = _add_number_point(metric.gauge)
    attribute = point.attributes.add()
    attribute.key = "host"
    attribute.value.string_value = "node-1"

    records = parse_otlp_metrics(request.SerializeToString())

    assert len(records) == 1
    record = records[0]
    assert record["signal"] == "metric"
    assert record["service_name"] == "checkout-service"
    assert record["metric_name"] == "cpu.utilization"
    assert record["metric_type"] == "gauge"
    assert record["unit"] == "1"
    assert record["data_point"]["value"] == 12.5
    assert record["data_point"]["attributes"]["host"] == "node-1"


def test_parse_otlp_sum_metric_preserves_aggregation_metadata():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "http.server.request.count"
    metric.sum.aggregation_temporality = 2
    metric.sum.is_monotonic = True
    _add_number_point(metric.sum, 42)

    record = parse_otlp_metrics(request.SerializeToString())[0]

    assert record["metric_type"] == "sum"
    assert record["data_point"]["value"] == 42
    assert record["aggregation_temporality"] == 2
    assert record["is_monotonic"] is True


def test_parse_otlp_histogram_metric_preserves_buckets():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "http.server.request.duration"
    metric.histogram.aggregation_temporality = 2
    point = metric.histogram.data_points.add()
    point.count = 5
    point.sum = 12.5
    point.explicit_bounds.extend([1.0, 5.0])
    point.bucket_counts.extend([1, 3, 1])
    point.time_unix_nano = 1_700_000_000_000_000_000

    record = parse_otlp_metrics(request.SerializeToString())[0]

    assert record["metric_type"] == "histogram"
    assert record["data_point"]["count"] == 5
    assert record["data_point"]["sum"] == 12.5
    assert record["data_point"]["explicit_bounds"] == [1.0, 5.0]
    assert record["data_point"]["bucket_counts"] == [1, 3, 1]


def test_parse_otlp_exponential_histogram_metric():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "request.size"
    metric.exponential_histogram.aggregation_temporality = 1
    point = metric.exponential_histogram.data_points.add()
    point.count = 3
    point.sum = 30.0
    point.scale = 2
    point.zero_count = 1
    point.zero_threshold = 0.001
    point.positive.offset = 0
    point.positive.bucket_counts.extend([1, 1])
    point.negative.offset = 0
    point.time_unix_nano = 1_700_000_000_000_000_000

    record = parse_otlp_metrics(request.SerializeToString())[0]

    assert record["metric_type"] == "exponential_histogram"
    assert record["data_point"]["count"] == 3
    assert record["data_point"]["scale"] == 2
    assert record["data_point"]["zero_count"] == 1
    assert record["data_point"]["positive"]["bucket_counts"] == [1, 1]


def test_parse_otlp_summary_metric():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "http.server.request.duration.summary"
    point = metric.summary.data_points.add()
    point.count = 10
    point.sum = 25.0
    point.time_unix_nano = 1_700_000_000_000_000_000
    quantile = point.quantile_values.add()
    quantile.quantile = 0.5
    quantile.value = 2.0

    record = parse_otlp_metrics(request.SerializeToString())[0]

    assert record["metric_type"] == "summary"
    assert record["data_point"]["count"] == 10
    assert record["data_point"]["sum"] == 25.0
    assert record["data_point"]["quantile_values"] == [
        {"quantile": 0.5, "value": 2.0}
    ]


def test_parse_otlp_metrics_rejects_empty_payload():
    with pytest.raises(TelemetryPayloadError, match="cannot be empty"):
        parse_otlp_metrics(b"")


def test_parse_otlp_metrics_rejects_invalid_protobuf():
    with pytest.raises(TelemetryPayloadError, match="Invalid OTLP protobuf"):
        parse_otlp_metrics(b"\xff\xff\xff")


def test_parse_otlp_metrics_rejects_request_without_data_points():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "empty.metric"
    metric.gauge.SetInParent()

    with pytest.raises(
        TelemetryPayloadError,
        match="did not contain any metric data points",
    ):
        parse_otlp_metrics(request.SerializeToString())


def test_parse_otlp_metrics_rejects_inconsistent_histogram_buckets():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "invalid.histogram"
    point = metric.histogram.data_points.add()
    point.count = 2
    point.explicit_bounds.extend([1.0, 2.0])
    point.bucket_counts.extend([2, 1])

    with pytest.raises(
        TelemetryPayloadError,
        match="bucket counts and bounds are inconsistent",
    ):
        parse_otlp_metrics(request.SerializeToString())


def test_parse_otlp_metrics_rejects_non_finite_gauge_value():
    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "invalid.gauge"
    point = metric.gauge.data_points.add()
    point.as_double = float("nan")

    with pytest.raises(
        TelemetryPayloadError,
        match="missing a valid numeric value",
    ):
        parse_otlp_metrics(request.SerializeToString())


def test_parse_otlp_metrics_rejects_oversized_batch():
    from app.telemetry import MAX_METRIC_DATA_POINTS_PER_BATCH

    request, scope_metrics = _metric_request()
    metric = scope_metrics.metrics.add()
    metric.name = "many.points"

    for index in range(MAX_METRIC_DATA_POINTS_PER_BATCH + 1):
        point = metric.gauge.data_points.add()
        point.as_int = index

    with pytest.raises(
        TelemetryPayloadError,
        match="cannot contain more than",
    ):
        parse_otlp_metrics(request.SerializeToString())
