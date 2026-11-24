import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

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
from app.identity_models import User
from app.telemetry import (
    MAX_TOPOLOGY_SPANS,
    TelemetryPayloadError,
    build_service_topology,
    parse_otlp_logs,
    parse_otlp_metrics,
    parse_otlp_traces,
)


logger = logging.getLogger(__name__)

router = APIRouter()

MAX_OTLP_BODY_BYTES = 2 * 1024 * 1024
OTLP_CONTENT_TYPE = "application/x-protobuf"


# ============================================================
# SHARED OTLP REQUEST VALIDATION
# ============================================================

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
    """Require the OTLP protobuf content type."""

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


# ============================================================
# TRACE HELPERS
# ============================================================

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


def _observed_at(record: dict[str, Any]) -> datetime:
    """Convert a span timestamp into a timezone-aware datetime."""

    timestamp_ns = record.get("start_time_unix_nano")

    if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool) or timestamp_ns <= 0:
        timestamp_ns = record.get("end_time_unix_nano")

    if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool) or timestamp_ns <= 0:
        return datetime.now(timezone.utc)

    try:
        return datetime.fromtimestamp(
            timestamp_ns / 1_000_000_000,
            tz=timezone.utc,
        )
    except (OverflowError, OSError, ValueError):
        return datetime.now(timezone.utc)


def _span_fingerprint(trace_id: str, span_id: str) -> str:
    """Create a stable fingerprint for a trace span."""

    identity = f"{trace_id}:{span_id}"

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


def _persist_project_traces(
    db: Session,
    project_id: int,
    records: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    Persist normalized trace spans for one authenticated project.

    Returns:
        accepted span count, duplicate span count
    """

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


# ============================================================
# LOG HELPERS
# ============================================================

def _log_observed_at(record: dict[str, Any]) -> datetime:
    """
    Determine the event timestamp for an OTLP log record.

    Prefer the event timestamp. If it is unavailable, use the
    collector's observed timestamp. Fall back to current UTC time.
    """

    timestamp_ns = record.get("timestamp_unix_nano")

    if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool) or timestamp_ns <= 0:
        timestamp_ns = record.get("observed_timestamp_unix_nano")

    if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool) or timestamp_ns <= 0:
        return datetime.now(timezone.utc)

    try:
        return datetime.fromtimestamp(
            timestamp_ns / 1_000_000_000,
            tz=timezone.utc,
        )
    except (OverflowError, OSError, ValueError):
        return datetime.now(timezone.utc)


def _log_fingerprint(record: dict[str, Any]) -> str:
    """
    Create a stable grouping fingerprint for similar log events.

    This fingerprint does NOT deduplicate log records.
    Every received log event is persisted.
    """

    identity = json.dumps(
        [
            record.get("service_name", ""),
            record.get("severity_number", 0),
            record.get("severity_text", ""),
            record.get("body", ""),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


def _persist_project_logs(
    db: Session,
    project_id: int,
    records: list[dict[str, Any]],
) -> int:
    """
    Persist normalized log records for one authenticated project.

    Logs are intentionally not deduplicated. Two identical messages
    can represent two distinct events at different times.
    """

    for record in records:
        telemetry = TelemetryRecord(
            project_id=project_id,
            signal_type="log",
            service_name=record["service_name"],
            observed_at=_log_observed_at(record),
            trace_id=record.get("trace_id"),
            span_id=record.get("span_id"),
            fingerprint=_log_fingerprint(record),
            payload=record,
        )

        db.add(telemetry)

    return len(records)


# ============================================================
# METRIC HELPERS
# ============================================================

def _metric_observed_at(record: dict[str, Any]) -> datetime:
    """
    Determine the observation timestamp for an OTLP metric data point.

    Prefer the point timestamp, then its start timestamp.
    Fall back to current UTC time if neither is available.
    """

    data_point = record.get("data_point")

    if not isinstance(data_point, dict):
        data_point = {}

    timestamp_ns = data_point.get("time_unix_nano")

    if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool) or timestamp_ns <= 0:
        timestamp_ns = data_point.get("start_time_unix_nano")

    if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool) or timestamp_ns <= 0:
        return datetime.now(timezone.utc)

    try:
        return datetime.fromtimestamp(
            timestamp_ns / 1_000_000_000,
            tz=timezone.utc,
        )
    except (OverflowError, OSError, ValueError):
        return datetime.now(timezone.utc)


def _metric_fingerprint(record: dict[str, Any]) -> str:
    """
    Create a stable grouping fingerprint for a metric time series.

    Points belonging to the same service, metric, type, unit, and
    attribute set share a fingerprint. Individual observations are
    never deduplicated.
    """

    data_point = record.get("data_point")

    if not isinstance(data_point, dict):
        data_point = {}

    identity = json.dumps(
        [
            record.get("service_name", ""),
            record.get("metric_name", ""),
            record.get("metric_type", ""),
            record.get("unit", ""),
            data_point.get("attributes", {}),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


def _persist_project_metrics(
    db: Session,
    project_id: int,
    records: list[dict[str, Any]],
) -> int:
    """
    Persist normalized metric data points for one authenticated project.

    Every received data point is persisted. Repeated observations
    are not deduplicated.
    """

    for record in records:
        telemetry = TelemetryRecord(
            project_id=project_id,
            signal_type="metric",
            service_name=record["service_name"],
            observed_at=_metric_observed_at(record),
            trace_id=None,
            span_id=None,
            fingerprint=_metric_fingerprint(record),
            payload=record,
        )

        db.add(telemetry)

    return len(records)


# ============================================================
# PROJECT-LEVEL OTLP TRACE INGESTION
# ============================================================

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
            "Failed to persist project traces for project %s",
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


# ============================================================
# PROJECT-LEVEL OTLP LOG INGESTION
# ============================================================

@router.post("/v1/logs")
async def ingest_project_otlp_logs(
    request: Request,
    x_otlp_api_key: str | None = Header(
        default=None,
        alias="X-OTLP-API-Key",
    ),
    db: Session = Depends(get_db),
):
    """
    Ingest OTLP logs into the project identified by its API key.

    Every log event is persisted, including repeated messages.
    No incident ID is required.
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
        records = parse_otlp_logs(body)
    except TelemetryPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        accepted = _persist_project_logs(
            db=db,
            project_id=project.id,
            records=records,
        )

        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()

        logger.exception(
            "Failed to persist project logs for project %s",
            project.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist telemetry",
        ) from exc

    return {
        "project_id": project.id,
        "received_logs": len(records),
        "accepted_logs": accepted,
    }


# ============================================================
# PROJECT-LEVEL OTLP METRIC INGESTION
# ============================================================

@router.post("/v1/metrics")
async def ingest_project_otlp_metrics(
    request: Request,
    x_otlp_api_key: str | None = Header(
        default=None,
        alias="X-OTLP-API-Key",
    ),
    db: Session = Depends(get_db),
):
    """
    Ingest OTLP metrics into the project identified by its API key.

    Each normalized metric data point is persisted separately.
    Metric metadata and the complete data-point structure are
    retained in the TelemetryRecord payload.
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
        records = parse_otlp_metrics(body)
    except TelemetryPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        accepted = _persist_project_metrics(
            db=db,
            project_id=project.id,
            records=records,
        )

        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()

        logger.exception(
            "Failed to persist project metrics for project %s",
            project.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist telemetry",
        ) from exc

    return {
        "project_id": project.id,
        "received_data_points": len(records),
        "accepted_data_points": accepted,
    }


# ============================================================
# LEGACY INCIDENT-LEVEL TRACE INGESTION
# ============================================================

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


# ============================================================
# SERVICE TOPOLOGY
# ============================================================

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
