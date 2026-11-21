
from unittest.mock import patch

import pytest

from experiments.evaluate_topology_retrieval_v3_2 import (
    BOOST_STRENGTHS,
    retrieve_ids,
)


def test_boost_strengths_are_unique_and_non_negative():
    assert len(BOOST_STRENGTHS) == len(set(BOOST_STRENGTHS))
    assert all(boost >= 0 for boost in BOOST_STRENGTHS)


def test_boost_strengths_include_current_production_value():
    assert 0.10 in BOOST_STRENGTHS


def test_boost_strengths_include_semantic_baseline():
    assert 0.0 in BOOST_STRENGTHS


def test_only_supported_methods_are_accepted():
    with pytest.raises(ValueError):
        retrieve_ids(
            None,
            "payment service",
            [],
            boost=0.1,
            method="topology_v3",
        )


def test_semantic_only_does_not_select_topology():
    with patch(
        "experiments.evaluate_topology_retrieval_v3_2.topology_ids_for_method"
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
            boost=0.1,
            method="semantic_only",
        )

    selector.assert_not_called()
    assert result == [1]
