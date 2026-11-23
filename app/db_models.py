
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app import identity_models  # noqa: F401


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    service: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    environment: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class IncidentInvestigation(Base):
    __tablename__ = "incident_investigations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TelemetryRecord(Base):
    """
    Project-level telemetry received from external collectors.

    Telemetry is stored independently of incidents so that OpsPilot
    can detect incidents from incoming signals in a later processing step.
    """

    __tablename__ = "telemetry_records"

    __table_args__ = (
        CheckConstraint(
            "signal_type IN ('trace', 'log', 'metric')",
            name="ck_telemetry_records_signal_type",
        ),
        Index(
            "ix_telemetry_records_project_signal_observed",
            "project_id",
            "signal_type",
            "observed_at",
        ),
        Index(
            "ix_telemetry_records_project_trace_id",
            "project_id",
            "trace_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    signal_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    service_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    trace_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    span_id: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
