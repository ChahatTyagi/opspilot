
import hmac
import json
import logging
import os

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

from app.database import get_db
from app.db_models import IncidentEvidence, IncidentRecord
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


def _load_existing_span_keys(
    db: Session,
    incident_id: int,
) -> set[tuple[str, str]]:
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
    _verify_otlp_api_key(x_otlp_api_key)

    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

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
    db: Session = Depends(get_db),
):
    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
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
