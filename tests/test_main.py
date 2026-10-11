
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.db_models import IncidentRecord
from app.main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
)

Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_incidents():
    with test_engine.begin() as connection:
        connection.execute(IncidentRecord.__table__.delete())


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_incident():
    response = client.post(
        "/incidents",
        json={
            "title": "Payment service unavailable",
            "description": "Payment requests return HTTP 500 errors.",
            "service": "payment",
            "severity": "high",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["severity"] == "high"
    assert data["status"] == "open"


def test_list_incidents():
    client.post(
        "/incidents",
        json={
            "title": "Checkout is slow",
            "description": "Checkout requests are taking too long.",
            "service": "checkout",
            "severity": "medium",
        },
    )

    response = client.get("/incidents")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["service"] == "checkout"


def test_get_incident():
    created = client.post(
        "/incidents",
        json={
            "title": "Database unavailable",
            "description": "The application cannot connect to the database.",
            "service": "database",
            "severity": "critical",
        },
    )

    incident_id = created.json()["id"]
    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["title"] == "Database unavailable"


def test_get_missing_incident():
    response = client.get("/incidents/999")

    assert response.status_code == 404