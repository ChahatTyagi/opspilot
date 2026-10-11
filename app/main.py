
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import IncidentRecord
from app.models import Incident, IncidentCreate

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


@app.post(
    "/incidents",
    response_model=Incident,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(
    incident_data: IncidentCreate,
    db: Session = Depends(get_db),
):
    incident = IncidentRecord(
        title=incident_data.title,
        description=incident_data.description,
        service=incident_data.service,
        severity=incident_data.severity.value,
    )

    db.add(incident)
    db.commit()
    db.refresh(incident)

    return incident


@app.get("/incidents", response_model=list[Incident])
def list_incidents(db: Session = Depends(get_db)):
    statement = select(IncidentRecord).order_by(IncidentRecord.id)
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