
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_incidents():
    main.incidents.clear()
    main.next_incident_id = 1
    yield


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
    assert data["id"] == 1
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