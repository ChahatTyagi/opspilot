
from unittest.mock import patch

import pytest

from experiments.evaluate_topology_retrieval_v3_3 import (
    BASELINE,
    BOOST_STRENGTHS,
    CANDIDATE,
    STRATEGY,
    retrieve_ids,
)


def test_boost_strengths_are_unique_and_non_negative():
    assert len(BOOST_STRENGTHS) == len(set(BOOST_STRENGTHS))
    assert all(boost >= 0 for boost in BOOST_STRENGTHS)


def test_boost_strengths_include_v3_2_best_tested_value():
    assert 0.20 in BOOST_STRENGTHS


def test_v3_3_tests_only_stronger_boosts():
    assert all(boost >= 0.20 for boost in BOOST_STRENGTHS)


def test_strategy_is_downstream_only():
    assert STRATEGY == "downstream_only"


def test_method_names_are_explicit():
    assert BASELINE == "semantic_only"
    assert CANDIDATE == "downstream_only"


def test_only_supported_methods_are_accepted():
    with pytest.raises(ValueError):
        retrieve_ids(
            None,
            "payment service",
            [],
            boost=0.25,
            method="topology_v3",
        )


def test_semantic_only_does_not_select_topology():
    with patch(
        "experiments.evaluate_topology_retrieval_v3_3.topology_ids_for_method"
    ) as selector:

        class FakeResult:
            class Chunk:
                evidence_id = 1

            chunk = Chunk()

        class FakeRetriever:
            def retrieve(self, **kwargs):
                return [FakeResult()]

        result = retrieve_ids(
            FakeRetriever(),
            "payment service",
            [],
            boost=0.25,
            method=BASELINE,
        )

    selector.assert_not_called()
    assert result == [1]
