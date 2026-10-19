
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"

class IncidentEnvironment(str, Enum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=5, max_length=2000)
    service: str = Field(min_length=2, max_length=100)
    environment: IncidentEnvironment | None = None
    severity: IncidentSeverity = IncidentSeverity.MEDIUM


class IncidentUpdate(BaseModel):
    status: IncidentStatus


class Incident(IncidentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class EvidenceSourceType(str, Enum):
    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"
    DEPLOYMENT = "deployment"
    NOTE = "note"


class IncidentEvidenceCreate(BaseModel):
    source_type: EvidenceSourceType
    content: str = Field(min_length=1, max_length=20000)


class IncidentEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    source_type: EvidenceSourceType
    content: str
    created_at: datetime

class EvidenceCounts(BaseModel):
    log: int = 0
    metric: int = 0
    trace: int = 0
    deployment: int = 0
    note: int = 0


class InvestigationContext(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    incident: Incident
    evidence_count: int
    evidence_counts: EvidenceCounts
    evidence: list[IncidentEvidenceResponse]