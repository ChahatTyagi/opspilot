import pytest
import scripts.evaluate_retrieval as retrieval_evaluation

from scripts.evaluate_retrieval import (
    compare_rankings,
    evaluate_case,
    lexical_overlap,
    mean_metric,
    reciprocal_rank,
    rerank_with_lexical_overlap,
    validate_case,
    validate_cases,
)


class FakeEmbedder:
    def __init__(self, vectors):
        self.vectors = vectors

    def embed_texts(self, texts):
        assert len(texts) == len(self.vectors)
        return self.vectors


# ---------------------------------------------------------
# Lexical overlap tests
# ---------------------------------------------------------

def test_lexical_overlap_measures_query_term_coverage():
    assert lexical_overlap(
        "payment service failure",
        "Payment service is failing",
    ) == pytest.approx(2 / 3)


def test_lexical_overlap_returns_zero_for_empty_query():
    assert lexical_overlap("", "payment service failure") == 0.0


# ---------------------------------------------------------
# Reranking tests
# ---------------------------------------------------------

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
def test_classify_outcome_detects_mixed_changes():
    deltas = {
        "recall_at_5": 0.1,
        "recall_at_3": -0.2,
        "mrr": 0.05,
    }

    assert retrieval_evaluation.classify_outcome(deltas) == "mixed"

# ---------------------------------------------------------
# Evaluation tests
# ---------------------------------------------------------

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

    ranked, recall_at_5, recall_at_3, rr = evaluate_case(
        embedder,
        case,
    )

    assert len(ranked) == 3
    assert recall_at_5 == pytest.approx(1.0)
    assert recall_at_3 == pytest.approx(1.0)
    assert rr == pytest.approx(1.0)


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

    ranked, recall_at_5, recall_at_3, rr = evaluate_case(
        embedder,
        case,
    )

    assert len(ranked) == 2
    assert recall_at_5 == 0.0
    assert recall_at_3 == 0.0
    assert rr == 0.0


def test_evaluate_case_handles_empty_candidates():
    case = {
        "query": "payment failure",
        "candidates": [],
    }

    embedder = FakeEmbedder([[1.0, 0.0]])

    ranked, recall_at_5, recall_at_3, rr = evaluate_case(
        embedder,
        case,
    )

    assert ranked == []
    assert recall_at_5 == 0.0
    assert recall_at_3 == 0.0
    assert rr == 0.0
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

    ranked, recall_at_5, recall_at_3, rr = evaluate_case(
        embedder,
        case,
    )

    assert len(ranked) == 2
    assert recall_at_5 == pytest.approx(1.0)
    assert recall_at_3 == pytest.approx(1.0)
    assert rr == pytest.approx(1.0)

@pytest.mark.parametrize(
    "returned_vectors",
    [
        [[1.0, 0.0]],  # Too few: query vector only
        [
            [1.0, 0.0],
            [0.9, 0.1],
            [0.1, 0.9],
            [0.5, 0.5],
        ],  # Too many: query + 3 vectors for 2 candidates
    ],
)
def test_evaluate_case_rejects_wrong_embedding_vector_count(
    returned_vectors,
):
    case = {
        "query": "payment failure",
        "candidates": [
            ("payment service timeout", True),
            ("unrelated frontend styling", False),
        ],
    }

    class MalformedEmbedder:
        def embed_texts(self, texts):
            return returned_vectors

    with pytest.raises(
        ValueError,
        match="embedder must return one vector per input text",
    ):
        evaluate_case(MalformedEmbedder(), case)

# ---------------------------------------------------------
# Mean metric tests
# ---------------------------------------------------------

def test_mean_metric_returns_case_weighted_mean():
    assert mean_metric([0.5, 1.0]) == 0.75


def test_mean_metric_returns_zero_for_empty_values():
    assert mean_metric([]) == 0.0


# ---------------------------------------------------------
# Case validation tests
# ---------------------------------------------------------
@pytest.mark.parametrize(
    "case",
    [
        {"query": "", "candidates": []},
        {"query": "   ", "candidates": []},
        {"query": "valid query"},
        {"query": "valid query", "candidates": "not a list"},
    ],
)
def test_validate_case_rejects_invalid_case_structure(case):
    with pytest.raises(ValueError):
        validate_case(case)

@pytest.mark.parametrize(
    "returned_vectors",
    [
        [[1.0, 0.0], [0.9]],  # Different dimensions
        [[1.0, 0.0], []],  # Empty candidate vector
        [[1.0, 0.0], [float("nan"), 0.1]],  # NaN
        [[1.0, 0.0], [float("inf"), 0.1]],  # Infinity
        [[1.0, 0.0], ["bad", 0.1]],  # Non-numeric value
    ],
)
def test_evaluate_case_rejects_malformed_embedding_vectors(
    returned_vectors,
):
    case = {
        "query": "payment failure",
        "candidates": [
            ("payment service timeout", True),
        ],
    }

    class MalformedEmbedder:
        def embed_texts(self, texts):
            return returned_vectors

    with pytest.raises(ValueError, match="invalid embedding vectors"):
        evaluate_case(MalformedEmbedder(), case)


@pytest.mark.parametrize(
    "candidate",
    [
        ("", True),
        ("   ", False),
        ("valid text", "yes"),
        ("valid text", 1),
        ("valid text", True, "extra"),
        "not a tuple",
    ],
)
def test_validate_case_rejects_invalid_candidates(candidate):
    case = {
        "query": "valid query",
        "candidates": [candidate],
    }

    with pytest.raises(ValueError):
        validate_case(case)


def test_validate_case_accepts_valid_case_and_empty_candidates():
    validate_case({
        "query": "valid query",
        "candidates": [
            ("relevant evidence", True),
            ("irrelevant evidence", False),
        ],
    })

    validate_case({
        "query": "valid query",
        "candidates": [],
    })


@pytest.mark.parametrize(
    "candidates",
    [
        [
            ("Database timeout", True),
            ("Database timeout", False),
        ],
        [
            ("Database timeout", True),
            (" database   timeout ", False),
        ],
    ],
)
def test_validate_case_rejects_duplicate_candidate_text(candidates):
    with pytest.raises(
        ValueError,
        match="duplicates earlier candidate",
    ):
        validate_case({
            "query": "database issue",
            "candidates": candidates,
        })


def test_validate_case_allows_same_text_in_different_cases():
    validate_case({
        "query": "database issue",
        "candidates": [("Database timeout", True)],
    })

    validate_case({
        "query": "authentication issue",
        "candidates": [("Database timeout", False)],
    })


# ---------------------------------------------------------
# Dataset validation tests
# ---------------------------------------------------------

def test_validate_cases_accepts_valid_dataset():
    cases = [
        {
            "query": "payment service failure",
            "candidates": [
                ("Payment service is failing", True),
                ("Database connection healthy", False),
            ],
        },
        {
            "query": "database timeout",
            "candidates": [
                ("Database request timed out", True),
            ],
        },
    ]

    validate_cases(cases)


def test_validate_cases_rejects_invalid_later_case():
    cases = [
        {
            "query": "valid query",
            "candidates": [("relevant evidence", True)],
        },
        {
            "query": "",
            "candidates": [("evidence", True)],
        },
    ]

    with pytest.raises(
        ValueError,
        match="Evaluation case query must be a non-empty string",
    ):
        validate_cases(cases)


def test_validate_cases_rejects_non_list_dataset():
    with pytest.raises(
        ValueError,
        match="Evaluation cases must be a list",
    ):
        validate_cases(None)


# ---------------------------------------------------------
# Main function validation and reporting tests
# ---------------------------------------------------------

def test_main_validates_cases_before_loading_embedder(monkeypatch):
    monkeypatch.setattr(
        retrieval_evaluation,
        "CASES",
        [
            {
                "query": "",
                "candidates": [("evidence", True)],
            }
        ],
    )

    def fail_if_embedder_loads():
        pytest.fail("Embedder should not load before dataset validation")

    monkeypatch.setattr(
        retrieval_evaluation,
        "LocalEmbedder",
        fail_if_embedder_loads,
    )

    with pytest.raises(
        ValueError,
        match="Evaluation case query must be a non-empty string",
    ):
        retrieval_evaluation.main()


@pytest.mark.parametrize(
    ("ranked", "expected"),
    [
        ([(0.9, "relevant evidence", True)], 1.0),
        (
            [
                (0.9, "irrelevant one", False),
                (0.8, "irrelevant two", False),
                (0.7, "relevant evidence", True),
            ],
            1 / 3,
        ),
        ([(0.9, "irrelevant evidence", False)], 0.0),
        ([], 0.0),
    ],
)
def test_reciprocal_rank_returns_expected_score(ranked, expected):
    assert reciprocal_rank(ranked) == pytest.approx(expected)


def test_main_reports_baseline_and_experimental_mrr(monkeypatch, capsys):
    cases = [
        {
            "query": "payment failure",
            "candidates": [
                ("relevant evidence", True),
                ("irrelevant evidence", False),
            ],
        }
    ]

    baseline_ranked = [
        (0.9, "irrelevant evidence", False),
        (0.8, "relevant evidence", True),
    ]

    experimental_ranked = [
        (0.9, "relevant evidence", True),
        (0.8, "irrelevant evidence", False),
    ]

    monkeypatch.setattr(
        retrieval_evaluation,
        "CASES",
        cases,
    )
    monkeypatch.setattr(
        retrieval_evaluation,
        "LocalEmbedder",
        lambda: object(),
    )
    monkeypatch.setattr(
        retrieval_evaluation,
        "evaluate_case",
        lambda embedder, case: (
            baseline_ranked,
            1.0,
            1.0,
            0.5,
        ),
    )
    monkeypatch.setattr(
        retrieval_evaluation,
        "rerank_with_lexical_overlap",
        lambda query, ranked: experimental_ranked,
    )

    retrieval_evaluation.main()

    output = capsys.readouterr().out

    assert "=== Baseline results ===" in output
    assert "=== Experimental results ===" in output
    assert "MRR: 0.500" in output
    assert output.count("MRR: 1.000") == 1
    assert "Recall@5: 1.000 -> 1.000 (+0.000)" in output
    assert "Recall@3: 1.000 -> 1.000 (+0.000)" in output
    assert "MRR: 0.500 -> 1.000 (+0.500)" in output
    assert "Overall outcome: improved" in output


# ---------------------------------------------------------
# Metric delta tests
# ---------------------------------------------------------

@pytest.mark.parametrize(
    ("baseline", "experimental", "expected"),
    [
        (0.5, 0.75, 0.25),
        (0.75, 0.5, -0.25),
        (0.5, 0.5, 0.0),
    ],
)
def test_metric_delta_returns_experimental_minus_baseline(
    baseline,
    experimental,
    expected,
):
    assert retrieval_evaluation.metric_delta(
        baseline,
        experimental,
    ) == pytest.approx(expected)


# ---------------------------------------------------------
# Ranking comparison tests
# compare_rankings expects (score, text, relevant) tuples.
# Its result uses nested "baseline", "experimental", "deltas".
# ---------------------------------------------------------

def test_compare_rankings_detects_improvement():
    baseline_ranked = [
        (0.9, "irrelevant-1", False),
        (0.8, "relevant-1", True),
        (0.7, "irrelevant-2", False),
        (0.6, "irrelevant-3", False),
        (0.5, "irrelevant-4", False),
        (0.4, "relevant-2", True),
    ]

    experimental_ranked = [
        (0.9, "relevant-1", True),
        (0.8, "irrelevant-1", False),
        (0.7, "irrelevant-2", False),
        (0.6, "irrelevant-3", False),
        (0.5, "irrelevant-4", False),
        (0.4, "relevant-2", True),
    ]

    result = compare_rankings(
        baseline_ranked,
        experimental_ranked,
    )

    assert result["outcome"] == "improved"
    assert result["deltas"]["mrr"] > 0


def test_compare_rankings_detects_regression():
    baseline_ranked = [
        (0.9, "relevant-1", True),
        (0.8, "irrelevant-1", False),
        (0.7, "irrelevant-2", False),
        (0.6, "irrelevant-3", False),
        (0.5, "irrelevant-4", False),
        (0.4, "relevant-2", True),
    ]

    experimental_ranked = [
        (0.9, "irrelevant-1", False),
        (0.8, "relevant-1", True),
        (0.7, "irrelevant-2", False),
        (0.6, "irrelevant-3", False),
        (0.5, "irrelevant-4", False),
        (0.4, "relevant-2", True),
    ]

    result = compare_rankings(
        baseline_ranked,
        experimental_ranked,
    )

    assert result["outcome"] == "regressed"
    assert result["deltas"]["mrr"] < 0


def test_compare_rankings_detects_recall_at_3_regression():
    baseline_ranked = [
        (0.9, "relevant-1", True),
        (0.8, "irrelevant-1", False),
        (0.7, "irrelevant-2", False),
        (0.6, "irrelevant-3", False),
        (0.5, "irrelevant-4", False),
        (0.4, "relevant-2", True),
    ]

    experimental_ranked = [
        (0.9, "irrelevant-1", False),
        (0.8, "irrelevant-2", False),
        (0.7, "irrelevant-3", False),
        (0.6, "relevant-1", True),
        (0.5, "irrelevant-4", False),
        (0.4, "relevant-2", True),
    ]

    result = compare_rankings(
        baseline_ranked,
        experimental_ranked,
    )

    assert result["deltas"]["recall_at_3"] < 0
    assert result["deltas"]["recall_at_5"] == pytest.approx(0.0)
    assert result["deltas"]["mrr"] < 0
    assert result["outcome"] == "regressed"


def test_compare_rankings_handles_unchanged_metrics():
    ranked = [
        (0.9, "relevant-1", True),
        (0.8, "irrelevant-1", False),
        (0.7, "relevant-2", True),
        (0.6, "irrelevant-2", False),
    ]

    result = compare_rankings(ranked, ranked)

    assert result["outcome"] == "unchanged"
    assert result["deltas"]["mrr"] == 0.0


def test_compare_rankings_handles_no_relevant_candidates():
    ranked = [
        (0.9, "irrelevant-1", False),
        (0.8, "irrelevant-2", False),
    ]

    result = compare_rankings(ranked, ranked)

    assert result["outcome"] == "unchanged"
    assert result["deltas"]["mrr"] == 0.0

def test_compare_rankings_handles_empty_rankings():
    result = compare_rankings([], [])

    assert result["baseline"] == {
        "recall_at_5": 0.0,
        "recall_at_3": 0.0,
        "mrr": 0.0,
    }
    assert result["experimental"] == {
        "recall_at_5": 0.0,
        "recall_at_3": 0.0,
        "mrr": 0.0,
    }
    assert result["deltas"] == {
        "recall_at_5": 0.0,
        "recall_at_3": 0.0,
        "mrr": 0.0,
    }
    assert result["outcome"] == "unchanged"


def test_compare_rankings_detects_improvement_from_empty_baseline():
    experimental_ranked = [
        (0.9, "relevant evidence", True),
        (0.8, "irrelevant evidence", False),
    ]

    result = compare_rankings([], experimental_ranked)

    assert result["baseline"]["recall_at_5"] == 0.0
    assert result["baseline"]["recall_at_3"] == 0.0
    assert result["baseline"]["mrr"] == 0.0

    assert result["experimental"]["recall_at_5"] == pytest.approx(1.0)
    assert result["experimental"]["recall_at_3"] == pytest.approx(1.0)
    assert result["experimental"]["mrr"] == pytest.approx(1.0)

    assert result["outcome"] == "improved"