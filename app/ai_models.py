from enum import Enum

from pydantic import BaseModel, Field


class AIConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AIFact(BaseModel):
    statement: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[int] = Field(min_length=1)


class AIHypothesis(BaseModel):
    explanation: str = Field(min_length=1, max_length=1000)
    supporting_evidence_ids: list[int] = Field(default_factory=list)
    confidence: AIConfidence


class AIInvestigationResult(BaseModel):
    observed_facts: list[AIFact] = Field(default_factory=list)
    hypotheses: list[AIHypothesis] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
