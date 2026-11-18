
import json
from types import SimpleNamespace

from app.tool_executor import InvestigationToolExecutor
from app.topology_investigation import get_incident_service_topology


def make_span(
    evidence_id,
    *,
    incident_id=42,
    trace_id="1" * 32,
    span_id="a" * 16,
    parent_span_id=None,
    service="checkout",
    status_code=0,
):
    record = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "service_name": service,
        "status_code": status_code,
        "duration_ms": 2.0,
    }

    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        source_type="trace",
        content=json.dumps(record),
    )


def test_topology_tool_returns_service_dependency_graph():
    evidence = [
        make_span(10),
        make_span(
            11,
            span_id="b" * 16,
            parent_span_id="a" * 16,
            service="payment",
            status_code=2,
        ),
    ]

    executor = InvestigationToolExecutor(
        incident_id=42,
        evidence_items=evidence,
    )

    result = executor.execute(
        tool_name="get_incident_service_topology",
        arguments={},
    )

    assert result["ok"] is True

    topology = result["topology"]

    assert topology["trace_count"] == 1
    assert len(topology["nodes"]) == 2
    assert len(topology["edges"]) == 1

    edge = topology["edges"][0]

    assert edge["source"] == "checkout"
    assert edge["target"] == "payment"
    assert edge["call_count"] == 1
    assert edge["error_count"] == 1
    assert edge["evidence_ids"] == [10, 11]

    assert result["new_evidence_ids"] == [10, 11]
    assert executor.returned_evidence_ids == {10, 11}


def test_topology_tool_rejects_arguments():
    executor = InvestigationToolExecutor(
        incident_id=42,
        evidence_items=[],
    )

    result = executor.execute(
        tool_name="get_incident_service_topology",
        arguments={"incident_id": 99},
    )

    assert result["ok"] is False
    assert "does not accept arguments" in result["error"]
    assert executor.call_count == 0


def test_topology_tool_rejects_repeated_identical_call():
    executor = InvestigationToolExecutor(
        incident_id=42,
        evidence_items=[],
    )

    first = executor.execute(
        tool_name="get_incident_service_topology",
        arguments={},
    )

    second = executor.execute(
        tool_name="get_incident_service_topology",
        arguments={},
    )

    assert first["ok"] is True
    assert second["ok"] is False
    assert "Repeated" in second["error"]


def test_topology_tool_is_scoped_to_current_incident():
    evidence = [
        make_span(10, incident_id=42),
        make_span(
            99,
            incident_id=99,
            span_id="b" * 16,
            parent_span_id="a" * 16,
            service="foreign-service",
        ),
    ]

    result = get_incident_service_topology(
        incident_id=42,
        evidence_items=evidence,
    )

    assert len(result["topology"]["nodes"]) == 1
    assert result["topology"]["nodes"][0]["service"] == "checkout"
    assert result["evidence_ids"] == [10]


def test_topology_tool_returns_empty_graph_without_traces():
    evidence = [
        SimpleNamespace(
            id=10,
            incident_id=42,
            source_type="log",
            content="Database timeout",
        )
    ]

    result = get_incident_service_topology(
        incident_id=42,
        evidence_items=evidence,
    )

    assert result["topology"]["nodes"] == []
    assert result["topology"]["edges"] == []
    assert result["topology"]["trace_count"] == 0
    assert result["evidence_ids"] == []


def test_topology_tool_limits_number_of_nodes():
    evidence = [
        make_span(
            evidence_id=index,
            trace_id=f"{index:032x}",
            span_id=f"{index:016x}",
            service=f"service-{index}",
        )
        for index in range(1, 36)
    ]

    result = get_incident_service_topology(
        incident_id=42,
        evidence_items=evidence,
    )

    assert len(result["topology"]["nodes"]) == 30
    assert result["topology"]["total_nodes"] == 35
    assert result["topology"]["truncated"] is True


def test_topology_tool_tracks_only_new_evidence_ids():
    evidence = [
        make_span(10),
        make_span(
            11,
            span_id="b" * 16,
            parent_span_id="a" * 16,
            service="payment",
        ),
    ]

    executor = InvestigationToolExecutor(
        incident_id=42,
        evidence_items=evidence,
        max_calls=3,
    )

    topology_result = executor.execute(
        tool_name="get_incident_service_topology",
        arguments={},
    )

    assert topology_result["new_evidence_ids"] == [10, 11]
    assert executor.returned_evidence_ids == {10, 11}
