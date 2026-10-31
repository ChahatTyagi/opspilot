
import pytest
from scripts.evaluate_retrieval import mean_metric
from scripts.evaluate_retrieval import (
    evaluate_case,
    lexical_overlap,
    rerank_with_lexical_overlap,
)


class FakeEmbedder:
    def __init__(self, vectors):
        self.vectors = vectors

    def embed_texts(self, texts):
        assert len(texts) == len(self.vectors)
        return self.vectors


def test_lexical_overlap_measures_query_term_coverage():
    assert lexical_overlap(
        "payment service failure",
        "Payment service is failing",
    ) == pytest.approx(2 / 3)


def test_lexical_overlap_returns_zero_for_empty_query():
    assert lexical_overlap("", "payment service failure") == 0.0


def test_reranker_preserves_candidates():
    ranked = [
        (0.9, "relevant evidence", True),
        (0.5, "irrelevant evidence", False),
    ]

    result = rerank_with_lexical_overlap("relevant evidence", ranked)

    assert len(result) == len(ranked)
    assert {item[1] for item in result} == {
        "relevant evidence",
        "irrelevant evidence",
    }


def test_evaluate_case_returns_perfect_metrics_when_relevant_items_rank_first():
    case = {
        "query": "payment failure",
        "candidates": [
            ("payment service failure", True),
            ("payment requests failing", True),
            ("unrelated frontend styling", False),
        ],
    }

    embedder = FakeEmbedder([
        [1.0, 0.0],
        [0.99, 0.01],
        [0.95, 0.05],
        [0.0, 1.0],
    ])

    ranked, recall_at_5, recall_at_3, reciprocal_rank = evaluate_case(
        embedder,
        case,
    )

    assert len(ranked) == 3
    assert recall_at_5 == pytest.approx(1.0)
    assert recall_at_3 == pytest.approx(1.0)
    assert reciprocal_rank == pytest.approx(1.0)


def test_evaluate_case_handles_no_relevant_candidates():
    case = {
        "query": "payment failure",
        "candidates": [
            ("frontend styling changed", False),
            ("documentation updated", False),
        ],
    }

    embedder = FakeEmbedder([
        [1.0, 0.0],
        [0.0, 1.0],
        [-1.0, 0.0],
    ])

    ranked, recall_at_5, recall_at_3, reciprocal_rank = evaluate_case(
        embedder,
        case,
    )

    assert len(ranked) == 2
    assert recall_at_5 == 0.0
    assert recall_at_3 == 0.0
    assert reciprocal_rank == 0.0

def test_evaluate_case_handles_empty_candidates():
    case = {
        "query": "payment failure",
        "candidates": [],
    }

    embedder = FakeEmbedder([[1.0, 0.0]])

    ranked, recall_at_5, recall_at_3, reciprocal_rank = evaluate_case(
        embedder,
        case,
    )

    assert ranked == []
    assert recall_at_5 == 0.0
    assert recall_at_3 == 0.0
    assert reciprocal_rank == 0.0


def test_evaluate_case_handles_k_larger_than_candidate_count():
    case = {
        "query": "payment failure",
        "candidates": [
            ("payment service failure", True),
            ("unrelated frontend styling", False),
        ],
    }

    embedder = FakeEmbedder([
        [1.0, 0.0],
        [0.99, 0.01],
        [0.0, 1.0],
    ])

    ranked, recall_at_5, recall_at_3, reciprocal_rank = evaluate_case(
        embedder,
        case,
    )

    assert len(ranked) == 2
    assert recall_at_5 == pytest.approx(1.0)
    assert recall_at_3 == pytest.approx(1.0)
    assert reciprocal_rank == pytest.approx(1.0)

def test_mean_metric_returns_case_weighted_mean():
    assert mean_metric([0.5, 1.0]) == 0.75


def test_mean_metric_returns_zero_for_empty_values():
    assert mean_metric([]) == 0.0