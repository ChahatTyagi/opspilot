
from types import SimpleNamespace

import pytest

from experiments.evaluate_final_retrieval_v3 import (
    evaluate_case,
    evaluate_dataset,
    macro_average,
    search_with_semantic_retrieval,
    search_with_semantic_lexical_rrf,
)


# ============================================================
# TEST DATA HELPERS
# ============================================================

def make_case():
    return {
        "name": "Test incident",
        "query": "database connection failure",
        "evidence": [
            (1, "log", "Database connection refused", False),
            (2, "log", "Connection pool exhausted", False),
            (3, "metric", "Database connection errors increased", False),
            (4, "log", "Database service unavailable", False),
            (5, "log", "Email delivery succeeded", False),
            (6, "metric", "CPU usage is normal", False),
        ],
    }


def make_search_function(retrieved_ids):
    def fake_search(
        query,
        incident_id,
        evidence_items,
        max_results=5,
    ):
        return [
            {"evidence_id": evidence_id}
            for evidence_id in retrieved_ids[:max_results]
        ]

    return fake_search


def make_semantic_result(
    incident_id,
    evidence_id,
    source_type,
    content,
    score,
):
    chunk = SimpleNamespace(
        incident_id=incident_id,
        evidence_id=evidence_id,
        source_type=source_type,
        text=content,
    )

    return SimpleNamespace(
        chunk=chunk,
        score=score,
    )


# ============================================================
# METRIC AND EVALUATION TESTS
# ============================================================

def test_relevance_is_restricted_to_current_scenario():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([1, 5, 3]),
        {1, 2, 999},
    )

    assert result["retrieved_relevant"] == [1]
    assert result["missed_ids"] == [2]
    assert result["irrelevant_ids"] == [5, 3]


def test_retrieved_and_missed_ids_are_correct():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([1, 5, 3, 6, 2]),
        {1, 2, 4},
    )

    assert result["retrieved_ids"] == [1, 5, 3, 6, 2]
    assert result["retrieved_relevant"] == [1, 2]
    assert result["missed_ids"] == [4]
    assert result["irrelevant_ids"] == [5, 3, 6]


def test_metrics_are_calculated_correctly():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([5, 6, 1, 2, 3]),
        {1, 2, 4},
    )

    assert result["recall_at_5"] == pytest.approx(2 / 3)
    assert result["precision_at_5"] == pytest.approx(2 / 5)
    assert result["precision_returned"] == pytest.approx(2 / 5)
    assert result["mrr"] == pytest.approx(1 / 3)


def test_direct_and_diagnostic_relevance_are_independent():
    case = make_case()

    search_function = make_search_function(
        [1, 5, 3, 6, 2]
    )

    direct_result = evaluate_case(
        case,
        "incident-1",
        search_function,
        {1, 2},
    )

    diagnostic_result = evaluate_case(
        case,
        "incident-1",
        search_function,
        {1, 2, 3, 4},
    )

    assert direct_result["retrieved_relevant"] == [1, 2]
    assert direct_result["missed_ids"] == []

    assert diagnostic_result["retrieved_relevant"] == [1, 3, 2]
    assert diagnostic_result["missed_ids"] == [4]

    assert direct_result["recall_at_5"] == pytest.approx(1.0)
    assert diagnostic_result["recall_at_5"] == pytest.approx(0.75)


def test_empty_search_results_are_handled():
    case = make_case()

    result = evaluate_case(
        case,
        "incident-1",
        make_search_function([]),
        {1, 2},
    )

    assert result["retrieved_ids"] == []
    assert result["retrieved_relevant"] == []
    assert result["missed_ids"] == [1, 2]
    assert result["irrelevant_ids"] == []

    assert result["recall_at_5"] == 0.0
    assert result["precision_at_5"] == 0.0
    assert result["precision_returned"] == 0.0
    assert result["mrr"] == 0.0


def test_evaluate_dataset_uses_separate_incident_ids():
    cases = [
        make_case(),
        make_case(),
    ]

    results = evaluate_dataset(
        cases,
        make_search_function([1]),
        {1, 2},
    )

    assert len(results) == 2
    assert results[0]["name"] == "Test incident"
    assert results[1]["name"] == "Test incident"


def test_macro_average_calculates_mean():
    results = [
        {"recall_at_5": 0.5},
        {"recall_at_5": 1.0},
        {"recall_at_5": 0.0},
    ]

    assert macro_average(
        results,
        "recall_at_5",
    ) == pytest.approx(0.5)


# ============================================================
# SEMANTIC RETRIEVAL ADAPTER TESTS
# ============================================================

class FakeSemanticRetriever:

    def __init__(self, results):
        self.results = results
        self.received_query = None
        self.received_evidence = None
        self.received_top_k = None

    def retrieve(self, query, evidence_items, top_k=5):
        self.received_query = query
        self.received_evidence = evidence_items
        self.received_top_k = top_k

        return self.results


def test_semantic_adapter_converts_retrieval_results():
    incident_id = "incident-1"

    evidence_items = [
        SimpleNamespace(
            id=1,
            incident_id=incident_id,
            source_type="log",
            content="Database connection refused",
        ),
        SimpleNamespace(
            id=2,
            incident_id=incident_id,
            source_type="metric",
            content="Connection errors increased",
        ),
    ]

    fake_results = [
        make_semantic_result(
            incident_id,
            2,
            "metric",
            "Connection errors increased",
            0.91,
        ),
        make_semantic_result(
            incident_id,
            1,
            "log",
            "Database connection refused",
            0.84,
        ),
    ]

    retriever = FakeSemanticRetriever(fake_results)

    results = search_with_semantic_retrieval(
        "database connection failure",
        incident_id,
        evidence_items,
        max_results=2,
        retriever=retriever,
    )

    assert [item["evidence_id"] for item in results] == [2, 1]

    assert results[0]["score"] == pytest.approx(0.91)
    assert results[1]["score"] == pytest.approx(0.84)

    assert results[0]["source_type"] == "metric"
    assert results[1]["source_type"] == "log"

    assert retriever.received_query == "database connection failure"
    assert retriever.received_top_k == 2
    assert retriever.received_evidence == evidence_items


def test_semantic_adapter_restricts_evidence_to_current_incident():
    incident_id = "incident-1"

    current_evidence = SimpleNamespace(
        id=1,
        incident_id=incident_id,
        source_type="log",
        content="Database connection refused",
    )

    other_evidence = SimpleNamespace(
        id=2,
        incident_id="incident-2",
        source_type="log",
        content="Unrelated incident evidence",
    )

    retriever = FakeSemanticRetriever([])

    search_with_semantic_retrieval(
        "database connection failure",
        incident_id,
        [current_evidence, other_evidence],
        retriever=retriever,
    )

    assert retriever.received_evidence == [current_evidence]

    assert all(
        item.incident_id == incident_id
        for item in retriever.received_evidence
    )


def test_semantic_adapter_returns_empty_for_no_matching_incident_evidence():
    retriever = FakeSemanticRetriever([])

    results = search_with_semantic_retrieval(
        "database connection failure",
        "incident-1",
        [
            SimpleNamespace(
                id=2,
                incident_id="incident-2",
                source_type="log",
                content="Other incident evidence",
            )
        ],
        retriever=retriever,
    )

    assert results == []
    assert retriever.received_evidence is None


def test_semantic_adapter_requires_retriever():
    with pytest.raises(
        ValueError,
        match="shared EvidenceRetriever",
    ):
        search_with_semantic_retrieval(
            "database connection failure",
            "incident-1",
            [],
        )


def test_semantic_adapter_rejects_invalid_top_k():
    retriever = FakeSemanticRetriever([])

    with pytest.raises(
        ValueError,
        match="max_results must be positive",
    ):
        search_with_semantic_retrieval(
            "database connection failure",
            "incident-1",
            [],
            max_results=0,
            retriever=retriever,
        )


# ============================================================
# EVALUATION VALIDATION TESTS
# ============================================================

def test_evaluate_case_rejects_duplicate_evidence_ids():
    case = make_case()

    def duplicate_search(
        query,
        incident_id,
        evidence_items,
        max_results=5,
    ):
        return [
            {"evidence_id": 1},
            {"evidence_id": 1},
        ]

    with pytest.raises(
        ValueError,
        match="duplicate evidence IDs",
    ):
        evaluate_case(
            case,
            "incident-1",
            duplicate_search,
            {1, 2},
        )


def test_evaluate_case_rejects_evidence_from_another_scenario():
    case = make_case()

    def cross_incident_search(
        query,
        incident_id,
        evidence_items,
        max_results=5,
    ):
        return [{"evidence_id": 9999}]

    with pytest.raises(
        ValueError,
        match="outside scenario",
    ):
        evaluate_case(
            case,
            "incident-1",
            cross_incident_search,
            {1, 2},
        )


# ============================================================
# SEMANTIC + LEXICAL RRF TEST HELPERS
# ============================================================

def make_rrf_evidence(incident_id="incident-1"):
    return [
        SimpleNamespace(
            id=1,
            incident_id=incident_id,
            source_type="log",
            content="Database connection refused",
        ),
        SimpleNamespace(
            id=2,
            incident_id=incident_id,
            source_type="metric",
            content="Connection pool exhausted",
        ),
        SimpleNamespace(
            id=3,
            incident_id=incident_id,
            source_type="deployment",
            content="Database service restarted",
        ),
    ]


def make_rrf_semantic_results(incident_id, ranking):
    return [
        make_semantic_result(
            incident_id,
            evidence_id,
            "log",
            f"Evidence {evidence_id}",
            0.9 - rank * 0.1,
        )
        for rank, evidence_id in enumerate(ranking)
    ]


# ============================================================
# SEMANTIC + LEXICAL RRF TESTS
# ============================================================

def test_rrf_combines_semantic_and_lexical_rankings(monkeypatch):
    incident_id = "incident-1"
    evidence_items = make_rrf_evidence(incident_id)

    semantic_results = make_rrf_semantic_results(
        incident_id,
        [1, 2, 3],
    )

    retriever = FakeSemanticRetriever(semantic_results)

    lexical_ranking = [2, 3, 1]

    def fake_lexical_search(
        query,
        incident_id,
        evidence_items,
        max_results=5,
    ):
        return [
            {
                "incident_id": incident_id,
                "evidence_id": evidence_id,
                "source_type": "log",
                "text": f"Evidence {evidence_id}",
            }
            for evidence_id in lexical_ranking[:max_results]
        ]

    monkeypatch.setattr(
        "experiments.evaluate_final_retrieval_v3.search_with_hybrid_retrieval",
        fake_lexical_search,
    )

    results = search_with_semantic_lexical_rrf(
        "database connection failure",
        incident_id,
        evidence_items,
        max_results=3,
        retriever=retriever,
        rrf_k=60,
    )

    retrieved_ids = [
        result["evidence_id"]
        for result in results
    ]

    assert retrieved_ids == [2, 1, 3]

    assert results[0]["rrf_score"] == pytest.approx(
        (1 / 62) + (1 / 61)
    )

    assert results[1]["rrf_score"] == pytest.approx(
        (1 / 61) + (1 / 63)
    )

    assert results[2]["rrf_score"] == pytest.approx(
        (1 / 63) + (1 / 62)
    )


def test_rrf_restricts_candidates_to_current_incident(monkeypatch):
    incident_id = "incident-1"

    current_evidence = make_rrf_evidence(incident_id)

    other_evidence = SimpleNamespace(
        id=999,
        incident_id="incident-2",
        source_type="log",
        content="Unrelated incident evidence",
    )

    retriever = FakeSemanticRetriever(
        make_rrf_semantic_results(
            incident_id,
            [1, 2, 3],
        )
    )

    received_lexical_evidence = []

    def fake_lexical_search(
        query,
        incident_id,
        evidence_items,
        max_results=5,
    ):
        received_lexical_evidence.extend(evidence_items)
        return []

    monkeypatch.setattr(
        "experiments.evaluate_final_retrieval_v3.search_with_hybrid_retrieval",
        fake_lexical_search,
    )

    search_with_semantic_lexical_rrf(
        "database connection failure",
        incident_id,
        current_evidence + [other_evidence],
        retriever=retriever,
    )

    assert len(retriever.received_evidence) == 3

    assert all(
        item.incident_id == incident_id
        for item in retriever.received_evidence
    )

    assert all(
        item.incident_id == incident_id
        for item in received_lexical_evidence
    )


def test_rrf_handles_empty_lexical_ranking(monkeypatch):
    incident_id = "incident-1"
    evidence_items = make_rrf_evidence(incident_id)

    semantic_results = make_rrf_semantic_results(
        incident_id,
        [2, 1, 3],
    )

    retriever = FakeSemanticRetriever(semantic_results)

    def empty_lexical_search(
        query,
        incident_id,
        evidence_items,
        max_results=5,
    ):
        return []

    monkeypatch.setattr(
        "experiments.evaluate_final_retrieval_v3.search_with_hybrid_retrieval",
        empty_lexical_search,
    )

    results = search_with_semantic_lexical_rrf(
        "database connection failure",
        incident_id,
        evidence_items,
        max_results=3,
        retriever=retriever,
    )

    assert [
        result["evidence_id"]
        for result in results
    ] == [2, 1, 3]

    assert results[0]["rrf_score"] == pytest.approx(1 / 61)


def test_rrf_returns_empty_when_incident_has_no_evidence():
    retriever = FakeSemanticRetriever([])

    results = search_with_semantic_lexical_rrf(
        "database connection failure",
        "incident-1",
        make_rrf_evidence("incident-2"),
        retriever=retriever,
    )

    assert results == []
    assert retriever.received_evidence is None


def test_rrf_requires_semantic_retriever():
    with pytest.raises(
        ValueError,
        match="semantic retriever",
    ):
        search_with_semantic_lexical_rrf(
            "database connection failure",
            "incident-1",
            make_rrf_evidence(),
        )


@pytest.mark.parametrize(
    "max_results",
    [0, -1, 1.5, True],
)
def test_rrf_rejects_invalid_max_results(max_results):
    retriever = FakeSemanticRetriever([])

    with pytest.raises(
        ValueError,
        match="max_results must be a positive integer",
    ):
        search_with_semantic_lexical_rrf(
            "database connection failure",
            "incident-1",
            make_rrf_evidence(),
            max_results=max_results,
            retriever=retriever,
        )


@pytest.mark.parametrize(
    "rrf_k",
    [0, -1, 1.5, True],
)
def test_rrf_rejects_invalid_rrf_constant(rrf_k):
    retriever = FakeSemanticRetriever([])

    with pytest.raises(
        ValueError,
        match="rrf_k must be a positive integer",
    ):
        search_with_semantic_lexical_rrf(
            "database connection failure",
            "incident-1",
            make_rrf_evidence(),
            retriever=retriever,
            rrf_k=rrf_k,
        )
