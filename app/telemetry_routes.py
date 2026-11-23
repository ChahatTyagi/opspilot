
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api_key_service import authenticate_project_api_key
from app.auth_routes import get_current_user
from app.authorization import require_project_access
from app.database import get_db
from app.db_models import (
    IncidentEvidence,
    IncidentRecord,
    TelemetryRecord,
)
from app.identity_models import Project, User
from app.telemetry import (
    MAX_TOPOLOGY_SPANS,
    TelemetryPayloadError,
    build_service_topology,
    parse_otlp_traces,
)


logger = logging.getLogger(__name__)

router = APIRouter()

MAX_OTLP_BODY_BYTES = 2 * 1024 * 1024
OTLP_CONTENT_TYPE = "application/x-protobuf"


def _verify_otlp_api_key(provided_key: str | None) -> None:
    """
    Verify the legacy global OTLP API key.

    Kept temporarily for backward compatibility with the old
    incident-specific ingestion endpoint.
    """
    expected_key = os.getenv("OPSPILOT_OTLP_API_KEY", "")

    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telemetry ingestion is not configured",
        )

    if not provided_key or not hmac.compare_digest(
        provided_key,
        expected_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid telemetry API key",
        )


async def _read_limited_body(request: Request) -> bytes:
    """Read a request body without exceeding the configured size limit."""

    content_length = request.headers.get("content-length")

    if content_length:
        try:
            if int(content_length) > MAX_OTLP_BODY_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Telemetry payload exceeds the size limit",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header",
            )

    body = bytearray()

    async for chunk in request.stream():
        body.extend(chunk)

        if len(body) > MAX_OTLP_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Telemetry payload exceeds the size limit",
            )

    return bytes(body)


def _validate_otlp_content_type(request: Request) -> None:
    content_type = (
        request.headers.get("content-type", "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )

    if content_type != OTLP_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content-Type must be {OTLP_CONTENT_TYPE}",
        )


def _load_existing_span_keys(
    db: Session,
    incident_id: int,
) -> set[tuple[str, str]]:
    """Load trace/span identities already stored as incident evidence."""

    statement = select(IncidentEvidence).where(
        IncidentEvidence.incident_id == incident_id,
        IncidentEvidence.source_type == "trace",
    )

    existing: set[tuple[str, str]] = set()

    for evidence in db.scalars(statement):
        try:
            record = json.loads(evidence.content)
        except (TypeError, ValueError):
            continue

        if not isinstance(record, dict):
            continue

        trace_id = record.get("trace_id")
        span_id = record.get("span_id")

        if (
            isinstance(trace_id, str)
            and isinstance(span_id, str)
            and len(trace_id) == 32
            and len(span_id) == 16
        ):
            existing.add((trace_id, span_id))

    return existing


def _observed_at(record: dict) -> datetime:
    """Convert a span's start timestamp into a timezone-aware datetime."""

    timestamp_ns = record.get("start_time_unix_nano")

    if not isinstance(timestamp_ns, int) or timestamp_ns <= 0:
        timestamp_ns = record.get("end_time_unix_nano")

    if not isinstance(timestamp_ns, int) or timestamp_ns <= 0:
        return datetime.now(timezone.utc)

    return datetime.fromtimestamp(
        timestamp_ns / 1_000_000_000,
        tz=timezone.utc,
    )


def _span_fingerprint(trace_id: str, span_id: str) -> str:
    """Create a stable fingerprint for a trace span."""

    identity = f"{trace_id}:{span_id}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _persist_project_traces(
    db: Session,
    project_id: int,
    records: list[dict],
) -> tuple[int, int]:
    """
    Persist normalized trace spans for one authenticated project.

    Returns:
        accepted span count, duplicate span count
    """

    span_keys = {
        (record["trace_id"], record["span_id"])
        for record in records
    }

    existing_statement = select(
        TelemetryRecord.trace_id,
        TelemetryRecord.span_id,
    ).where(
        TelemetryRecord.project_id == project_id,
        TelemetryRecord.signal_type == "trace",
        TelemetryRecord.trace_id.is_not(None),
        TelemetryRecord.span_id.is_not(None),
    )

    existing_keys = set(db.execute(existing_statement).all())

    accepted = 0
    duplicates = 0
    seen_in_batch: set[tuple[str, str]] = set()

    for record in records:
        trace_id = record["trace_id"]
        span_id = record["span_id"]
        span_key = (trace_id, span_id)

        if span_key in existing_keys or span_key in seen_in_batch:
            duplicates += 1
            continue

        seen_in_batch.add(span_key)

        telemetry = TelemetryRecord(
            project_id=project_id,
            signal_type="trace",
            service_name=record["service_name"],
            observed_at=_observed_at(record),
            trace_id=trace_id,
            span_id=span_id,
            fingerprint=_span_fingerprint(trace_id, span_id),
            payload=record,
        )

        db.add(telemetry)
        accepted += 1

    return accepted, duplicates


@router.post("/v1/traces")
async def ingest_project_otlp_traces(
    request: Request,
    x_otlp_api_key: str | None = Header(
        default=None,
        alias="X-OTLP-API-Key",
    ),
    db: Session = Depends(get_db),
):
    """
    Ingest OTLP traces into the project identified by its API key.

    No incident ID is required. Telemetry belongs to the project,
    and incident detection will be handled by a separate pipeline.
    """

    project = authenticate_project_api_key(db, x_otlp_api_key)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid telemetry API key",
        )

    _validate_otlp_content_type(request)

    body = await _read_limited_body(request)

    try:
        records = parse_otlp_traces(body)
    except TelemetryPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        accepted, duplicates = _persist_project_traces(
            db=db,
            project_id=project.id,
            records=records,
        )

        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()

        logger.exception(
            "Failed to persist project telemetry for project %s",
            project.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist telemetry",
        ) from exc

    return {
        "project_id": project.id,
        "received_spans": len(records),
        "accepted_spans": accepted,
        "duplicate_spans": duplicates,
    }


@router.post("/incidents/{incident_id}/telemetry/v1/traces")
async def ingest_otlp_traces(
    incident_id: int,
    request: Request,
    x_otlp_api_key: str | None = Header(
        default=None,
        alias="X-OTLP-API-Key",
    ),
    db: Session = Depends(get_db),
):
    """Legacy incident-specific ingestion endpoint."""

    _verify_otlp_api_key(x_otlp_api_key)

    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    _validate_otlp_content_type(request)

    body = await _read_limited_body(request)

    try:
        records = parse_otlp_traces(body)
    except TelemetryPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    existing_keys = _load_existing_span_keys(db, incident_id)

    accepted = 0
    duplicates = 0

    try:
        for record in records:
            span_key = (
                record["trace_id"],
                record["span_id"],
            )

            if span_key in existing_keys:
                duplicates += 1
                continue

            evidence = IncidentEvidence(
                incident_id=incident_id,
                source_type="trace",
                content=json.dumps(
                    record,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ),
            )

            db.add(evidence)
            existing_keys.add(span_key)
            accepted += 1

        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()

        logger.exception(
            "Failed to persist telemetry for incident %s",
            incident_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist telemetry",
        ) from exc

    return {
        "incident_id": incident_id,
        "received_spans": len(records),
        "accepted_spans": accepted,
        "duplicate_spans": duplicates,
    }


@router.get("/incidents/{incident_id}/service-topology")
def get_service_topology(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return topology only to users authorized to read the incident's project."""

    incident = db.get(IncidentRecord, incident_id)

    if incident is None or incident.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    require_project_access(
        db,
        current_user.id,
        incident.project_id,
    )

    statement = (
        select(IncidentEvidence)
        .where(
            IncidentEvidence.incident_id == incident_id,
            IncidentEvidence.source_type == "trace",
        )
        .order_by(
            IncidentEvidence.created_at,
            IncidentEvidence.id,
        )
        .limit(MAX_TOPOLOGY_SPANS)
    )

    evidence = list(db.scalars(statement).all())

    return {
        "incident_id": incident_id,
        **build_service_topology(evidence),
    }
