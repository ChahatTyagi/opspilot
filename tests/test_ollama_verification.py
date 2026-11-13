
import json
from types import SimpleNamespace

import pytest

from app.ai_models import (
    AIConfidence,
    AIHypothesis,
    AIHypothesisAssessment,
    AIHypothesisVerificationResult,
    AIHypothesisVerdict,
)
from app.ollama_verification import (
    build_verification_input,
    _parse_verification_response,
    verify_ollama_hypotheses,
)


def make_hypothesis():
    return AIHypothesis(
        explanation="Connection saturation may have caused database errors.",
        supporting_evidence_ids=[11],
        confidence=AIConfidence.MEDIUM,
    )


def make_evidence(
    evidence_id=11,
    content="Database connection pool usage reached 100%.",
    source_type="log",
):
    return SimpleNamespace(
        id=evidence_id,
        source_type=source_type,
        content=content,
    )


def make_verification(
    evidence_id=11,
    hypothesis_index=0,
    verdict=AIHypothesisVerdict.SUPPORTED,
):
    return AIHypothesisVerificationResult(
        assessments=[
            AIHypothesisAssessment(
                hypothesis_index=hypothesis_index,
                verdict=verdict,
                evidence_ids=(
                    [evidence_id]
                    if verdict != AIHypothesisVerdict.INSUFFICIENT
                    else []
                ),
                rationale="The cited evidence supports this assessment.",
            )
        ]
    )


def make_response(result=None):
    if result is None:
        result = make_verification()

    return {
        "message": {
            "role": "assistant",
            "content": result.model_dump_json(),
        }
    }


class FakeOllamaClient:
    def __init__(self, response=None, responses=None):
        self.response = response or make_response()
        self.responses = list(responses) if responses is not None else None
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)

        if self.responses is not None:
            if not self.responses:
                raise AssertionError("Unexpected additional Ollama call.")

            return self.responses.pop(0)

        return self.response


def test_builds_input_with_actual_cited_evidence():
    hypothesis = make_hypothesis()

    evidence = [
        make_evidence(
            evidence_id=10,
            content="An unrelated application warning.",
        ),
        make_evidence(
            evidence_id=11,
            content="Database connection pool usage reached 100%.",
        ),
    ]

    payload = build_verification_input(
        hypotheses=[hypothesis],
        evidence=evidence,
    )

    cited_evidence = payload["hypotheses"][0]["cited_evidence"]

    assert len(cited_evidence) == 1
    assert cited_evidence[0]["evidence_id"] == 11
    assert cited_evidence[0]["source_type"] == "log"
    assert (
        cited_evidence[0]["content"]
        == "Database connection pool usage reached 100%."
    )


def test_builds_separate_indexes_for_multiple_hypotheses():
    hypotheses = [
        make_hypothesis(),
        AIHypothesis(
            explanation="A separate network issue may be involved.",
            supporting_evidence_ids=[12],
            confidence=AIConfidence.LOW,
        ),
    ]

    evidence = [
        make_evidence(evidence_id=11),
        make_evidence(
            evidence_id=12,
            content="Network packet loss was observed.",
        ),
    ]

    payload = build_verification_input(
        hypotheses=hypotheses,
        evidence=evidence,
    )

    assert [
        item["hypothesis_index"]
        for item in payload["hypotheses"]
    ] == [0, 1]

    assert (
        payload["hypotheses"][1]["cited_evidence"][0]["evidence_id"]
        == 12
    )


def test_rejects_missing_cited_evidence_content():
    with pytest.raises(ValueError, match="content is unavailable"):
        build_verification_input(
            hypotheses=[make_hypothesis()],
            evidence=[],
        )


def test_rejects_duplicate_evidence_records():
    with pytest.raises(ValueError, match="Duplicate evidence record"):
        build_verification_input(
            hypotheses=[make_hypothesis()],
            evidence=[
                make_evidence(),
                make_evidence(),
            ],
        )


def test_parses_structured_verification_response():
    result = _parse_verification_response(make_response())

    assert isinstance(result, AIHypothesisVerificationResult)
    assert len(result.assessments) == 1
    assert result.assessments[0].verdict == AIHypothesisVerdict.SUPPORTED


def test_rejects_malformed_verification_response():
    with pytest.raises(ValueError, match="malformed"):
        _parse_verification_response({})


def test_rejects_empty_response_content():
    response = {
        "message": {
            "content": "   ",
        }
    }

    with pytest.raises(ValueError, match="did not return"):
        _parse_verification_response(response)


def test_rejects_invalid_structured_verification_json():
    response = {
        "message": {
            "content": '{"assessments": "not-a-list"}',
        }
    }

    with pytest.raises(ValueError, match="invalid structured"):
        _parse_verification_response(response)


def test_calls_verifier_with_structured_output():
    client = FakeOllamaClient()

    result = verify_ollama_hypotheses(
        hypotheses=[make_hypothesis()],
        evidence=[make_evidence()],
        client=client,
    )

    assert result.assessments[0].verdict == AIHypothesisVerdict.SUPPORTED
    assert len(client.calls) == 1

    call = client.calls[0]

    assert len(call["messages"]) == 2

    assert "independent causal hypothesis verifier" in (
        call["messages"][0]["content"]
    )

    user_payload = json.loads(call["messages"][1]["content"])

    assert len(user_payload["hypotheses"]) == 1

    assert (
        user_payload["hypotheses"][0]["cited_evidence"][0]["content"]
        == "Database connection pool usage reached 100%."
    )

    assert call["format"] == (
        AIHypothesisVerificationResult.model_json_schema()
    )


def test_verifies_multiple_hypotheses_in_separate_requests():
    hypotheses = [
        make_hypothesis(),
        AIHypothesis(
            explanation="Network packet loss caused the failures.",
            supporting_evidence_ids=[12],
            confidence=AIConfidence.MEDIUM,
        ),
    ]

    evidence = [
        make_evidence(
            evidence_id=11,
            content="Database connection pool usage reached 100%.",
        ),
        make_evidence(
            evidence_id=12,
            content="Network packet loss reached 25%.",
        ),
        make_evidence(
            evidence_id=13,
            content="An unrelated warning.",
        ),
    ]

    client = FakeOllamaClient(
        responses=[
            make_response(
                make_verification(
                    evidence_id=11,
                    verdict=AIHypothesisVerdict.SUPPORTED,
                )
            ),
            make_response(
                make_verification(
                    evidence_id=12,
                    verdict=AIHypothesisVerdict.CONTRADICTED,
                )
            ),
        ]
    )

    result = verify_ollama_hypotheses(
        hypotheses=hypotheses,
        evidence=evidence,
        client=client,
    )

    assert len(client.calls) == 2
    assert len(result.assessments) == 2

    assert [
        assessment.hypothesis_index
        for assessment in result.assessments
    ] == [0, 1]

    assert result.assessments[0].verdict == AIHypothesisVerdict.SUPPORTED
    assert result.assessments[0].evidence_ids == [11]

    assert result.assessments[1].verdict == AIHypothesisVerdict.CONTRADICTED
    assert result.assessments[1].evidence_ids == [12]

    first_payload = json.loads(
        client.calls[0]["messages"][1]["content"]
    )

    second_payload = json.loads(
        client.calls[1]["messages"][1]["content"]
    )

    assert len(first_payload["hypotheses"]) == 1
    assert len(second_payload["hypotheses"]) == 1

    assert (
        first_payload["hypotheses"][0]["cited_evidence"][0]["evidence_id"]
        == 11
    )

    assert (
        second_payload["hypotheses"][0]["cited_evidence"][0]["evidence_id"]
        == 12
    )

    assert (
        first_payload["hypotheses"][0]["cited_evidence"][0]["content"]
        != second_payload["hypotheses"][0]["cited_evidence"][0]["content"]
    )


def test_rejects_multiple_assessments_for_one_hypothesis():
    invalid_result = AIHypothesisVerificationResult(
        assessments=[
            AIHypothesisAssessment(
                hypothesis_index=0,
                verdict=AIHypothesisVerdict.SUPPORTED,
                evidence_ids=[11],
                rationale="First assessment.",
            ),
            AIHypothesisAssessment(
                hypothesis_index=0,
                verdict=AIHypothesisVerdict.SUPPORTED,
                evidence_ids=[11],
                rationale="Duplicate assessment.",
            ),
        ]
    )

    client = FakeOllamaClient(
        response=make_response(invalid_result)
    )

    with pytest.raises(ValueError, match="exactly one assessment"):
        verify_ollama_hypotheses(
            hypotheses=[make_hypothesis()],
            evidence=[make_evidence()],
            client=client,
        )


def test_rejects_incorrect_local_hypothesis_index():
    invalid_result = make_verification(
        hypothesis_index=5
    )

    client = FakeOllamaClient(
        response=make_response(invalid_result)
    )

    with pytest.raises(ValueError, match="incorrect local hypothesis index"):
        verify_ollama_hypotheses(
            hypotheses=[make_hypothesis()],
            evidence=[make_evidence()],
            client=client,
        )


def test_does_not_call_model_when_there_are_no_hypotheses():
    client = FakeOllamaClient()

    result = verify_ollama_hypotheses(
        hypotheses=[],
        evidence=[],
        client=client,
    )

    assert result.assessments == []
    assert client.calls == []
