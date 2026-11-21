"""Tests for V3.1 directional topology ablation experiments."""

import pytest

from experiments.evaluate_topology_retrieval_v3_1 import (
    METHODS,
    V3_METHODS,
    topology_ids_for_method,
)

from experiments.topology_retrieval_v2_dataset import (
    build_dataset,
    validate_dataset,
)

from experiments.topology_retrieval_v3 import (
    select_directional_topology_evidence,
)


def test_experiment_defines_all_five_methods():
    assert METHODS == (
        "semantic_only",
        "topology_v2",
        "direct_only",
        "downstream_only",
        "topology_v3",
    )


def test_v3_ablation_methods_are_defined():
    assert V3_METHODS == (
        "direct_only",
        "downstream_only",
        "topology_v3",
    )


@pytest.mark.parametrize(
    "method",
    [
        "direct_only",
        "downstream_only",
        "topology_v3",
    ],
)
def test_topology_method_returns_a_set(method):
    case = build_dataset()[0]

    selected_ids = topology_ids_for_method(
        query=case["service_anchored_query"],
        evidence_items=case["evidence"],
        method=method,
    )

    assert isinstance(selected_ids, set)


def test_direct_and_downstream_evidence_are_disjoint():
    for case in build_dataset():
        selection = select_directional_topology_evidence(
            query=case["service_anchored_query"],
            evidence_items=case["evidence"],
        )

        assert (
            selection.direct_service_evidence_ids
            .isdisjoint(selection.downstream_evidence_ids)
        )


def test_full_v3_is_union_of_direct_and_downstream():
    for case in build_dataset():
        query = case["service_anchored_query"]
        evidence = case["evidence"]

        direct_ids = topology_ids_for_method(
            query,
            evidence,
            "direct_only",
        )

        downstream_ids = topology_ids_for_method(
            query,
            evidence,
            "downstream_only",
        )

        full_v3_ids = topology_ids_for_method(
            query,
            evidence,
            "topology_v3",
        )

        assert full_v3_ids == direct_ids | downstream_ids


def test_direct_only_excludes_downstream_evidence():
    for case in build_dataset():
        query = case["service_anchored_query"]
        evidence = case["evidence"]

        selection = select_directional_topology_evidence(
            query=query,
            evidence_items=evidence,
        )

        direct_ids = topology_ids_for_method(
            query,
            evidence,
            "direct_only",
        )

        assert direct_ids == set(
            selection.direct_service_evidence_ids
        )

        assert direct_ids.isdisjoint(
            selection.downstream_evidence_ids
        )


def test_downstream_only_excludes_direct_evidence():
    for case in build_dataset():
        query = case["service_anchored_query"]
        evidence = case["evidence"]

        selection = select_directional_topology_evidence(
            query=query,
            evidence_items=evidence,
        )

        downstream_ids = topology_ids_for_method(
            query,
            evidence,
            "downstream_only",
        )

        assert downstream_ids == set(
            selection.downstream_evidence_ids
        )

        assert downstream_ids.isdisjoint(
            selection.direct_service_evidence_ids
        )


def test_upstream_context_is_not_included_in_full_v3():
    for case in build_dataset():
        selection = select_directional_topology_evidence(
            query=case["service_anchored_query"],
            evidence_items=case["evidence"],
        )

        assert selection.upstream_context_evidence_ids.isdisjoint(
            selection.boosted_evidence_ids
        )


def test_selected_ids_belong_to_the_scenario():
    for case in build_dataset():
        scenario_ids = {
            item.id for item in case["evidence"]
        }

        for method in V3_METHODS:
            selected_ids = topology_ids_for_method(
                query=case["service_anchored_query"],
                evidence_items=case["evidence"],
                method=method,
            )

            assert selected_ids.issubset(scenario_ids)


def test_empty_query_does_not_select_topology_evidence():
    case = build_dataset()[0]

    for method in V3_METHODS:
        selected_ids = topology_ids_for_method(
            query="",
            evidence_items=case["evidence"],
            method=method,
        )

        assert selected_ids == set()


def test_invalid_method_is_rejected():
    case = build_dataset()[0]

    with pytest.raises(ValueError):
        topology_ids_for_method(
            query=case["service_anchored_query"],
            evidence_items=case["evidence"],
            method="invalid_method",
        )


def test_dataset_still_passes_validation():
    cases = build_dataset()

    validate_dataset(cases)

    assert len(cases) == 20