
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


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


class Incident(IncidentCreate):
    id: int
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )