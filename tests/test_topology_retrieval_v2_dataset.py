
import json

import pytest

from app.telemetry import build_service_topology

from experiments.evaluate_final_retrieval_v2 import FINAL_TEST_CASES
from experiments.retrieval_v3_labels import EVIDENCE_LABELS

from experiments.topology_retrieval_v2_dataset import (
    TRACE_LABELS,
    build_dataset,
    get_relevant_ids,
    validate_dataset,
)


def test_dataset_validation_passes():
    assert validate_dataset() is True


def test_dataset_contains_20_scenarios():
    assert len(build_dataset()) == 20


def test_dataset_contains_260_evidence_records():
    cases = build_dataset()

    assert sum(len(case["evidence"]) for case in cases) == 260


def test_each_scenario_contains_five_trace_records():
    for case in build_dataset():
        traces = [
            item
            for item in case["evidence"]
            if item.source_type == "trace"
        ]

        assert len(traces) == 5


def test_all_evidence_ids_are_unique():
    evidence_ids = [
        item.id
        for case in build_dataset()
        for item in case["evidence"]
    ]

    assert len(evidence_ids) == len(set(evidence_ids))


def test_original_v3_evidence_and_labels_are_preserved():
    cases = build_dataset()

    original_records = {
        evidence_id
        for original_case in FINAL_TEST_CASES
        for evidence_id, _, _, _ in original_case["evidence"]
    }

    actual_records = {
        item.id
        for case in cases
        for item in case["evidence"]
    }

    assert original_records.issubset(actual_records)

    for case in cases:
        for evidence_id in original_records:
            if evidence_id in case["labels"]:
                assert case["labels"][evidence_id] == EVIDENCE_LABELS[evidence_id]


def test_synthetic_trace_labels_are_independent_of_topology():
    for case in build_dataset():
        trace_ids = case["trace_ids"]

        assert case["labels"][trace_ids["upstream"]] == "IRRELEVANT"
        assert case["labels"][trace_ids["target"]] == "CONTRIBUTING"
        assert case["labels"][trace_ids["dependency"]] == "DIRECT"

        for evidence_id in trace_ids["unrelated"]:
            assert case["labels"][evidence_id] == "IRRELEVANT"


def test_trace_records_follow_normalized_telemetry_schema():
    for case in build_dataset():
        for item in case["evidence"]:
            if item.source_type != "trace":
                continue

            record = json.loads(item.content)

            assert record["schema_version"] == 1
            assert record["signal"] == "trace"
            assert len(record["trace_id"]) == 32
            assert len(record["span_id"]) == 16
            assert record["service_name"]
            assert record["span_name"]


def test_connected_trace_spans_form_expected_service_chain():
    for case in build_dataset():
        traces = [
            item
            for item in case["evidence"]
            if item.source_type == "trace"
        ]

        topology = build_service_topology(traces)

        expected_edges = {
            (
                case["connected_services"][0],
                case["connected_services"][1],
            ),
            (
                case["connected_services"][1],
                case["connected_services"][2],
            ),
        }

        actual_edges = {
            (edge["source"], edge["target"])
            for edge in topology["edges"]
        }

        assert expected_edges.issubset(actual_edges)
        assert topology["trace_count"] == 3


def test_unrelated_services_do_not_create_cross_trace_edges():
    for case in build_dataset():
        traces = [
            item
            for item in case["evidence"]
            if item.source_type == "trace"
        ]

        topology = build_service_topology(traces)

        connected = set(case["connected_services"])
        unrelated = set(case["unrelated_services"])

        for edge in topology["edges"]:
            assert not (
                edge["source"] in unrelated
                or edge["target"] in unrelated
            )

        assert connected.isdisjoint(unrelated)


def test_service_anchored_query_mentions_target_service():
    for case in build_dataset():
        assert case["target_service"] in case["service_anchored_query"]


def test_symptom_query_is_preserved_from_original_v3():
    cases = build_dataset()

    for case, original_case in zip(cases, FINAL_TEST_CASES):
        assert case["symptom_query"] == original_case["query"]


def test_direct_relevance_contains_only_direct_labels():
    for case in build_dataset():
        relevant_ids = get_relevant_ids(case, "direct")

        assert relevant_ids
        assert all(
            case["labels"][evidence_id] == "DIRECT"
            for evidence_id in relevant_ids
        )


def test_diagnostic_relevance_excludes_only_irrelevant_labels():
    for case in build_dataset():
        relevant_ids = get_relevant_ids(case, "diagnostic")

        expected = {
            evidence_id
            for evidence_id, label in case["labels"].items()
            if label != "IRRELEVANT"
        }

        assert relevant_ids == expected


def test_invalid_relevance_perspective_is_rejected():
    case = build_dataset()[0]

    with pytest.raises(ValueError, match="perspective"):
        get_relevant_ids(case, "unknown")


def test_dataset_rejects_missing_scenario():
    cases = build_dataset()

    with pytest.raises(ValueError, match="20 scenarios"):
        validate_dataset(cases[:-1])


def test_dataset_rejects_duplicate_evidence_ids():
    cases = build_dataset()

    cases[0]["evidence"][0].id = cases[0]["evidence"][1].id

    with pytest.raises(ValueError, match="Duplicate evidence ID"):
        validate_dataset(cases)


def test_dataset_rejects_invalid_trace_labels():
    cases = build_dataset()

    trace_id = cases[0]["trace_ids"]["dependency"]
    cases[0]["labels"][trace_id] = "UNKNOWN"

    with pytest.raises(ValueError, match="Invalid relevance label"):
        validate_dataset(cases)
