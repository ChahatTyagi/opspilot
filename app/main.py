from sqlalchemy.exc import SQLAlchemyError

from fastapi import Depends, FastAPI, HTTPException, Query, status

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import IncidentRecord

from app.models import (
    Incident,
    IncidentCreate,
    IncidentEnvironment,
    IncidentSeverity,
    IncidentStatus,
    IncidentUpdate,
)

app = FastAPI(
    title="OpsPilot",
    description="Evidence-driven AI incident investigation",
    version="0.2.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "opspilot-api",
        "version": "0.2.0",
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

    db.commit()
    db.refresh(incident)

    return incident
