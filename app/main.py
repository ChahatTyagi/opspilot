import logging
import re
import time
import uuid
from sqlalchemy.exc import SQLAlchemyError

from fastapi import Depends, FastAPI, HTTPException, Query, status

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import IncidentEvidence, IncidentRecord

from app.models import (
    Incident,
    IncidentCreate,
    IncidentEnvironment,
    IncidentSeverity,
    IncidentStatus,
    IncidentUpdate,
    IncidentEvidenceCreate,
    IncidentEvidenceResponse,
)
from fastapi import Request
from fastapi.responses import JSONResponse
logger = logging.getLogger(__name__)
app = FastAPI(
    title="OpsPilot",
    description="Evidence-driven AI incident investigation",
    version="0.2.0",
)
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    incoming_id = request.headers.get("X-Request-ID", "")

    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", incoming_id):
        request_id = incoming_id
    else:
        request_id = str(uuid.uuid4())

    request.state.request_id = request_id
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "Request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )

    return response

@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)

    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"request_id": request_id},
    )

    response = JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"},
    )

    if request_id:
        response.headers["X-Request-ID"] = request_id

    return response



@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "opspilot-api",
        "version": "0.2.0",
    }


@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )

    return {
        "status": "ready",
        "database": "available",
    }



@app.post("/incidents", response_model=Incident, status_code=status.HTTP_201_CREATED)
def create_incident(incident_data: IncidentCreate, db: Session = Depends(get_db)):
    incident = IncidentRecord(
        title=incident_data.title,
        description=incident_data.description,
        service=incident_data.service,
        environment=(
            incident_data.environment.value
            if incident_data.environment is not None
            else None
        ),
        severity=incident_data.severity.value,
    )

    try:
        db.add(incident)
        db.commit()
        db.refresh(incident)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating incident")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create incident due to a database error",
        )

    return incident




@app.get("/incidents", response_model=list[Incident])
def list_incidents(
    severity: IncidentSeverity | None = None,
    status_filter: IncidentStatus | None = None,
    service: str | None = None,
    environment: IncidentEnvironment | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    statement = select(IncidentRecord)

    if severity is not None:
        statement = statement.where(
            IncidentRecord.severity == severity.value
        )

    if status_filter is not None:
        statement = statement.where(
            IncidentRecord.status == status_filter.value
        )

    if service is not None:
        statement = statement.where(
            IncidentRecord.service == service
        )

    if environment is not None:
        statement = statement.where(
            IncidentRecord.environment == environment.value
        )

    statement = (
        statement
        .order_by(IncidentRecord.id)
        .limit(limit)
        .offset(offset)
    )

    return db.scalars(statement).all()



@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
):
    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident


@app.patch("/incidents/{incident_id}", response_model=Incident)
def update_incident(
    incident_id: int,
    incident_data: IncidentUpdate,
    db: Session = Depends(get_db),
):
    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    incident.status = incident_data.status.value

    try:
        db.commit()
        db.refresh(incident)
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "Database error while updating incident %s",
            incident_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update incident due to a database error",
        )

    return incident

@app.post(
    "/incidents/{incident_id}/evidence",
    response_model=IncidentEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incident_evidence(
    incident_id: int,
    evidence_data: IncidentEvidenceCreate,
    db: Session = Depends(get_db),
):
    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )

    evidence = IncidentEvidence(
        incident_id=incident_id,
        source_type=evidence_data.source_type.value,
        content=evidence_data.content,
    )

    try:
        db.add(evidence)
        db.commit()
        db.refresh(evidence)
        return evidence
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "Failed to create incident evidence for incident %s",
            incident_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save incident evidence",
        ) from exc


@app.get(
    "/incidents/{incident_id}/evidence",
    response_model=list[IncidentEvidenceResponse],
)
def list_incident_evidence(
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
        .where(IncidentEvidence.incident_id == incident_id)
        .order_by(IncidentEvidence.created_at, IncidentEvidence.id)
    )

    return list(db.scalars(statement).all())
