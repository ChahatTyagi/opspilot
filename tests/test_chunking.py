
from types import SimpleNamespace

import pytest

from app.chunking import chunk_evidence, chunk_text


def test_chunk_text_returns_empty_for_blank_input():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_returns_single_chunk_for_short_text():
    assert chunk_text("database connection failed") == [
        "database connection failed"
    ]


def test_chunk_text_splits_long_text_with_overlap():
    words = [f"word{i}" for i in range(11)]
    text = " ".join(words)

    chunks = chunk_text(
        text,
        chunk_size=5,
        overlap=2,
    )

    assert chunks == [
        "word0 word1 word2 word3 word4",
        "word3 word4 word5 word6 word7",
        "word6 word7 word8 word9 word10",
    ]


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [
        (0, 0),
        (-1, 0),
        (5, -1),
        (5, 5),
        (5, 6),
    ],
)
def test_chunk_text_rejects_invalid_configuration(
    chunk_size,
    overlap,
):
    with pytest.raises(ValueError):
        chunk_text(
            "some evidence",
            chunk_size=chunk_size,
            overlap=overlap,
        )


def test_chunk_evidence_preserves_metadata():
    evidence = SimpleNamespace(
        id=42,
        incident_id=7,
        source_type="log",
        content="database connection failed",
    )

    chunks = chunk_evidence(evidence)

    assert len(chunks) == 1
    assert chunks[0].incident_id == 7
    assert chunks[0].evidence_id == 42
    assert chunks[0].source_type == "log"
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "database connection failed"


def test_chunk_evidence_assigns_sequential_indexes():
    evidence = SimpleNamespace(
        id=50,
        incident_id=8,
        source_type="log",
        content="one two three four five six seven eight",
    )

    chunks = chunk_evidence(
        evidence,
        chunk_size=3,
        overlap=1,
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    assert [chunk.text for chunk in chunks] == [
        "one two three",
        "three four five",
        "five six seven",
        "seven eight",
    ]
