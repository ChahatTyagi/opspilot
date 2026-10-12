
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from app.database import Base, get_db
from app.db_models import IncidentRecord
from app.main import app
from unittest.mock import patch
from sqlalchemy.exc import SQLAlchemyError
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


def test_create_incident_with_environment():
    response = client.post(
        "/incidents",
        json={
            "title": "Checkout latency spike",
            "description": "Checkout requests are taking longer than expected.",
            "service": "checkout",
            "environment": "production",
            "severity": "high",
        },
    )

    assert response.status_code == 201
    assert response.json()["environment"] == "production"


def test_create_incident_with_invalid_environment():
    response = client.post(
        "/incidents",
        json={
            "title": "Invalid environment test",
            "description": "Testing environment validation.",
            "service": "checkout",
            "environment": "testing",
            "severity": "high",
        },
    )

    assert response.status_code == 422


def test_update_incident_status():
    created = client.post(
        "/incidents",
        json={
            "title": "Payment service issue",
            "description": "Payment requests are returning errors.",
            "service": "payment",
            "severity": "high",
        },
    )

    incident_id = created.json()["id"]

    response = client.patch(
        f"/incidents/{incident_id}",
        json={"status": "investigating"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "investigating"
    assert response.json()["title"] == "Payment service issue"


def test_update_incident_invalid_status():
    created = client.post(
        "/incidents",
        json={
            "title": "Checkout service issue",
            "description": "Checkout requests are failing.",
            "service": "checkout",
        },
    )

    incident_id = created.json()["id"]

    response = client.patch(
        f"/incidents/{incident_id}",
        json={"status": "invalid"},
    )

    assert response.status_code == 422


def test_update_missing_incident():
    response = client.patch(
        "/incidents/999",
        json={"status": "resolved"},
    )

    assert response.status_code == 404


def test_filter_incidents_by_severity():
    client.post(
        "/incidents",
        json={
            "title": "Critical database outage",
            "description": "Database connections have failed.",
            "service": "database",
            "severity": "critical",
        },
    )
    client.post(
        "/incidents",
        json={
            "title": "Minor checkout issue",
            "description": "Checkout is responding slowly.",
            "service": "checkout",
            "severity": "low",
        },
    )

    response = client.get("/incidents?severity=critical")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["severity"] == "critical"


def test_filter_incidents_by_status():
    created = client.post(
        "/incidents",
        json={
            "title": "Payment service issue",
            "description": "Payment requests are failing.",
            "service": "payment",
        },
    )
    incident_id = created.json()["id"]

    client.patch(
        f"/incidents/{incident_id}",
        json={"status": "investigating"},
    )

    response = client.get("/incidents?status=investigating")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "investigating"


def test_filter_incidents_by_service():
    client.post(
        "/incidents",
        json={
            "title": "Payment service issue",
            "description": "Payment requests are failing.",
            "service": "payment",
        },
    )
    client.post(
        "/incidents",
        json={
            "title": "Checkout service issue",
            "description": "Checkout requests are failing.",
            "service": "checkout",
        },
    )

    response = client.get("/incidents?service=payment")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["service"] == "payment"


def test_incident_pagination():
    for number in range(3):
        client.post(
            "/incidents",
            json={
                "title": f"Incident number {number}",
                "description": "This is a pagination test incident.",
                "service": "checkout",
            },
        )

    response = client.get("/incidents?limit=2&offset=1")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["id"] < response.json()[1]["id"]


def test_incident_invalid_pagination():
    response = client.get("/incidents?limit=0")

    assert response.status_code == 422

def test_filter_incidents_by_environment():
    client.post(
        "/incidents",
        json={
            "title": "Production payment failure",
            "description": "Production payment requests are failing.",
            "service": "payment",
            "environment": "production",
            "severity": "critical",
        },
    )
    client.post(
        "/incidents",
        json={
            "title": "Staging payment issue",
            "description": "Staging payment requests are failing.",
            "service": "payment",
            "environment": "staging",
            "severity": "critical",
        },
    )

    response = client.get("/incidents?environment=production")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["environment"] == "production"


def test_combine_incident_filters():
    client.post(
        "/incidents",
        json={
            "title": "Production critical payment issue",
            "description": "Critical payment requests are failing.",
            "service": "payment",
            "environment": "production",
            "severity": "critical",
        },
    )
    client.post(
        "/incidents",
        json={
            "title": "Staging critical payment issue",
            "description": "Critical staging payment requests are failing.",
            "service": "payment",
            "environment": "staging",
            "severity": "critical",
        },
    )

    response = client.get(
        "/incidents?severity=critical&service=payment&environment=production"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["environment"] == "production"
    assert response.json()[0]["severity"] == "critical"
    assert response.json()[0]["service"] == "payment"




def test_create_incident_database_failure(caplog):
    with (
        patch.object(
            Session,
            "commit",
            side_effect=SQLAlchemyError("Simulated database failure"),
        ),
        patch.object(Session, "rollback") as mock_rollback,
        caplog.at_level("ERROR", logger="app.main"),
    ):
        response = client.post(
            "/incidents",
            json={
                "title": "Database failure test",
                "description": "Testing failed incident creation.",
                "service": "payment",
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Unable to create incident due to a database error"
    )
    mock_rollback.assert_called_once()
    assert "Database error while creating incident" in caplog.text



def test_list_incidents_returns_empty_list_when_no_matches():
    response = client.get("/incidents?service=nonexistent-service")

    assert response.status_code == 200
    assert response.json() == []
