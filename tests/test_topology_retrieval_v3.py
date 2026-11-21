
import json
from types import SimpleNamespace

import pytest

from experiments.topology_retrieval_v3 import (
    directional_topology_relevant_evidence_ids,
    select_directional_topology_evidence,
)


TRACE_ID = "1" * 32


def make_trace(
    evidence_id,
    service_name,
    span_id,
    parent_span_id=None,
    trace_id=TRACE_ID,
):
    record = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "service_name": service_name,
        "span_name": f"{service_name}-operation",
        "span_kind": 1,
        "start_time_unix_nano": 1_000_000,
        "end_time_unix_nano": 2_000_000,
        "duration_ms": 1.0,
        "status_code": 0,
        "status_message": "",
        "attributes": {},
        "events": [],
    }

    return SimpleNamespace(
        id=evidence_id,
        source_type="trace",
        content=json.dumps(record),
    )


def make_log(evidence_id, content):
    return SimpleNamespace(
        id=evidence_id,
        source_type="log",
        content=content,
    )


def test_v3_selects_queried_service_evidence():
    evidence = [
        make_trace(
            1,
            "payment-service",
            "a" * 16,
        ),
        make_trace(
            2,
            "payment-service",
            "b" * 16,
            trace_id="2" * 32,
        ),
        make_trace(
            3,
            "frontend",
            "c" * 16,
            trace_id="3" * 32,
        ),
    ]

    result = select_directional_topology_evidence(
        "Investigate the payment service failure",
        evidence,
    )

    assert result.matched_services == {"payment-service"}
    assert result.direct_service_evidence_ids == {1, 2}
    assert result.downstream_evidence_ids == set()
    assert result.upstream_context_evidence_ids == set()


def test_v3_selects_downstream_child_not_upstream_parent():
    evidence = [
        # Gateway is the upstream parent of payment.
        make_trace(
            1,
            "gateway",
            "a" * 16,
        ),
        make_trace(
            2,
            "payment-service",
            "b" * 16,
            parent_span_id="a" * 16,
        ),
        # Database is downstream of payment.
        make_trace(
            3,
            "database",
            "c" * 16,
            parent_span_id="b" * 16,
        ),
        # Unconnected service.
        make_trace(
            4,
            "notification",
            "d" * 16,
            trace_id="2" * 32,
        ),
    ]

    result = select_directional_topology_evidence(
        "Investigate payment-service",
        evidence,
    )

    assert result.matched_services == {"payment-service"}

    assert result.direct_service_evidence_ids == {2}

    # Only the child span is selected for the downstream relationship.
    assert result.downstream_evidence_ids == {3}

    # The upstream gateway is context, not a boosted candidate.
    assert result.upstream_context_evidence_ids == {1}

    assert result.boosted_evidence_ids == {2, 3}


def test_v3_adapter_excludes_upstream_context():
    evidence = [
        make_trace(1, "gateway", "a" * 16),
        make_trace(
            2,
            "payment-service",
            "b" * 16,
            parent_span_id="a" * 16,
        ),
        make_trace(
            3,
            "database",
            "c" * 16,
            parent_span_id="b" * 16,
        ),
    ]

    result = directional_topology_relevant_evidence_ids(
        "payment-service",
        evidence,
    )

    assert result == {2, 3}
    assert 1 not in result


def test_v3_does_not_create_cross_trace_relationships():
    evidence = [
        make_trace(
            1,
            "payment-service",
            "a" * 16,
            trace_id="1" * 32,
        ),
        make_trace(
            2,
            "database",
            "b" * 16,
            parent_span_id="a" * 16,
            trace_id="2" * 32,
        ),
    ]

    result = select_directional_topology_evidence(
        "payment-service",
        evidence,
    )

    assert result.direct_service_evidence_ids == {1}
    assert result.downstream_evidence_ids == set()
    assert result.upstream_context_evidence_ids == set()


def test_v3_does_not_promote_unconnected_services():
    evidence = [
        make_trace(
            1,
            "payment-service",
            "a" * 16,
        ),
        make_trace(
            2,
            "database",
            "b" * 16,
            trace_id="2" * 32,
        ),
    ]

    result = select_directional_topology_evidence(
        "payment-service",
        evidence,
    )

    assert result.boosted_evidence_ids == {1}
    assert 2 not in result.boosted_evidence_ids


def test_v3_does_not_match_partial_service_names():
    evidence = [
        make_trace(
            1,
            "pay",
            "a" * 16,
        ),
    ]

    result = select_directional_topology_evidence(
        "Investigate the payment service",
        evidence,
    )

    assert result.matched_services == set()
    assert result.boosted_evidence_ids == set()


def test_v3_matches_normalized_service_names():
    evidence = [
        make_trace(
            1,
            "Payment-Service",
            "a" * 16,
        ),
    ]

    result = select_directional_topology_evidence(
        "Investigate the payment service failure",
        evidence,
    )

    assert result.matched_services == {"Payment-Service"}
    assert result.direct_service_evidence_ids == {1}


def test_v3_ignores_non_trace_evidence():
    evidence = [
        make_log(1, "Payment service returned an error"),
    ]

    result = select_directional_topology_evidence(
        "payment service",
        evidence,
    )

    assert result.matched_services == set()
    assert result.boosted_evidence_ids == set()


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_v3_handles_invalid_queries(query):
    result = select_directional_topology_evidence(
        query,
        [],
    )

    assert result.matched_services == set()
    assert result.boosted_evidence_ids == set()


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "[]",
        "{}",
        json.dumps(
            {
                "schema_version": 2,
                "signal": "trace",
            }
        ),
        json.dumps(
            {
                "schema_version": 1,
                "signal": "metric",
            }
        ),
    ],
)
def test_v3_ignores_malformed_or_non_trace_records(content):
    evidence = [
        SimpleNamespace(
            id=1,
            source_type="trace",
            content=content,
        )
    ]

    result = select_directional_topology_evidence(
        "payment-service",
        evidence,
    )

    assert result.boosted_evidence_ids == set()


def test_v3_ignores_invalid_span_identifiers():
    record = {
        "schema_version": 1,
        "signal": "trace",
        "trace_id": "invalid",
        "span_id": "a" * 16,
        "parent_span_id": None,
        "service_name": "payment-service",
    }

    evidence = [
        SimpleNamespace(
            id=1,
            source_type="trace",
            content=json.dumps(record),
        )
    ]

    result = select_directional_topology_evidence(
        "payment-service",
        evidence,
    )

    assert result.boosted_evidence_ids == set()


def test_v3_ignores_boolean_evidence_ids():
    evidence = make_trace(
        True,
        "payment-service",
        "a" * 16,
    )

    result = select_directional_topology_evidence(
        "payment-service",
        [evidence],
    )

    assert result.boosted_evidence_ids == set()


def test_v3_ignores_duplicate_span_identity_after_first_record():
    evidence = [
        make_trace(
            1,
            "payment-service",
            "a" * 16,
        ),
        make_trace(
            2,
            "database",
            "a" * 16,
        ),
    ]

    result = select_directional_topology_evidence(
        "payment-service",
        evidence,
    )

    assert result.direct_service_evidence_ids == {1}
    assert result.boosted_evidence_ids == {1}


def test_v3_does_not_treat_same_service_parent_child_as_dependency():
    evidence = [
        make_trace(
            1,
            "payment-service",
            "a" * 16,
        ),
        make_trace(
            2,
            "payment-service",
            "b" * 16,
            parent_span_id="a" * 16,
        ),
    ]

    result = select_directional_topology_evidence(
        "payment-service",
        evidence,
    )

    assert result.direct_service_evidence_ids == {1, 2}
    assert result.downstream_evidence_ids == set()
    assert result.upstream_context_evidence_ids == set()


def test_v3_keeps_upstream_context_separate_from_boosted_evidence():
    evidence = [
        make_trace(
            1,
            "gateway",
            "a" * 16,
        ),
        make_trace(
            2,
            "payment-service",
            "b" * 16,
            parent_span_id="a" * 16,
        ),
    ]

    result = select_directional_topology_evidence(
        "payment-service",
        evidence,
    )

    assert result.upstream_context_evidence_ids == {1}
    assert result.boosted_evidence_ids == {2}
    assert result.upstream_context_evidence_ids.isdisjoint(
        result.boosted_evidence_ids
    )
