from types import SimpleNamespace

import pytest

from app.investigation_tools import search_incident_evidence


def make_evidence(
    evidence_id=10,
    incident_id=42,
    content="Database connection timeout occurred.",
    source_type="log",
):
    return SimpleNamespace(
        id=evidence_id,
        incident_id=incident_id,
        content=content,
        source_type=source_type,
    )


def test_search_returns_matching_evidence_from_current_incident():
    evidence = [
        make_evidence(
            evidence_id=10,
            content="Database connection timeout occurred.",
        ),
        make_evidence(
            evidence_id=11,
            content="Payment gateway returned HTTP 503.",
        ),
    ]

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=evidence,
    )

    assert len(results) == 1
    assert results[0]["evidence_id"] == 10
    assert results[0]["incident_id"] == 42
    assert "Database connection timeout" in results[0]["text"]

def test_search_ranks_evidence_by_matching_term_count():
    evidence = [
        make_evidence(
            evidence_id=10,
            content="Database connection is healthy.",
        ),
        make_evidence(
            evidence_id=11,
            content="Database connection timeout occurred.",
        ),
        make_evidence(
            evidence_id=12,
            content="Timeout while processing checkout.",
        ),
    ]

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=evidence,
    )

    assert [
        item["evidence_id"] for item in results
    ] == [11, 10, 12]


def test_search_does_not_return_evidence_from_another_incident():
    evidence = [
        make_evidence(
            evidence_id=10,
            incident_id=999,
            content="Database connection timeout occurred.",
        )
    ]

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=evidence,
    )

    assert results == []


@pytest.mark.parametrize(
    "query",
    ["", "   ", "x" * 501],
)
def test_search_rejects_invalid_query(query):
    with pytest.raises(ValueError):
        search_incident_evidence(
            query=query,
            incident_id=42,
            evidence_items=[make_evidence()],
        )


def test_search_limits_number_of_results():
    evidence = [
        make_evidence(
            evidence_id=index,
            content=f"Database timeout in service {index}.",
        )
        for index in range(1, 10)
    ]

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=evidence,
        max_results=3,
    )

    assert len(results) == 3


def test_search_truncates_returned_text():
    evidence = [
        make_evidence(content="Database timeout. " + "details " * 500)
    ]

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=evidence,
    )

    assert len(results) == 1
    assert len(results[0]["text"]) <= 1000

@pytest.mark.parametrize(
    "max_results",
    [0, -1, 11, 1.5, True],
)
def test_search_rejects_invalid_result_limit(max_results):
    with pytest.raises(ValueError):
        search_incident_evidence(
            query="database timeout",
            incident_id=42,
            evidence_items=[make_evidence()],
            max_results=max_results,
        )


def test_search_rejects_non_string_query():
    with pytest.raises(ValueError):
        search_incident_evidence(
            query=None,
            incident_id=42,
            evidence_items=[make_evidence()],
        )


def test_search_returns_only_public_result_fields():
    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=[make_evidence()],
    )

    assert set(results[0]) == {
        "incident_id",
        "evidence_id",
        "source_type",
        "text",
    }


def test_search_skips_evidence_with_missing_fields():
    malformed_evidence = SimpleNamespace(
        incident_id=42,
        content="Database timeout occurred.",
        source_type="log",
    )

    valid_evidence = make_evidence(
        evidence_id=11,
        content="Database timeout in checkout.",
    )

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=[malformed_evidence, valid_evidence],
    )

    assert len(results) == 1
    assert results[0]["evidence_id"] == 11


@pytest.mark.parametrize(
    "invalid_content",
    [123, ["Database timeout"], {"text": "Database timeout"}],
)
def test_search_skips_evidence_with_invalid_content_type(
    invalid_content,
):
    evidence = [
        make_evidence(
            evidence_id=10,
            content=invalid_content,
        ),
        make_evidence(
            evidence_id=11,
            content="Database timeout in checkout.",
        ),
    ]

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=evidence,
    )

    assert len(results) == 1
    assert results[0]["evidence_id"] == 11


def test_search_skips_evidence_with_invalid_id_or_source_type():
    evidence = [
        make_evidence(
            evidence_id="invalid-id",
            content="Database timeout.",
        ),
        make_evidence(
            evidence_id=11,
            content="Database timeout.",
            source_type=None,
        ),
        make_evidence(
            evidence_id=12,
            content="Database timeout in checkout.",
            source_type="log",
        ),
    ]

    results = search_incident_evidence(
        query="database timeout",
        incident_id=42,
        evidence_items=evidence,
    )

    assert len(results) == 1
    assert results[0]["evidence_id"] == 12
