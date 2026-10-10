
from fastapi import FastAPI, HTTPException, status

from app.models import Incident, IncidentCreate

app = FastAPI(
    title="OpsPilot",
    description="Evidence-driven AI incident investigation",
    version="0.2.0",
)

# Temporary storage; replaced with PostgreSQL later.
incidents: dict[int, Incident] = {}
next_incident_id = 1


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
def create_incident(incident_data: IncidentCreate):
    global next_incident_id

    incident = Incident(
        id=next_incident_id,
        **incident_data.model_dump(),
    )

    incidents[next_incident_id] = incident
    next_incident_id += 1

    return incident


@app.get("/incidents", response_model=list[Incident])
def list_incidents():
    return list(incidents.values())


@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: int):
    incident = incidents.get(incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    return incident