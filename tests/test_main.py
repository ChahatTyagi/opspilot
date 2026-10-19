import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from app.database import Base, get_db
from app.db_models import IncidentEvidence, IncidentRecord
from app.main import app
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
@event.listens_for(test_engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

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



@pytest.fixture(scope="module", autouse=True)
def configure_test_database():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    yield

    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override



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

    fetched = client.get(f"/incidents/{incident_id}")

    assert fetched.status_code == 200
    assert fetched.json()["status"] == "investigating"

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


def test_global_exception_handler():
    test_app = FastAPI()

    from app.main import global_exception_handler, request_logging_middleware

    test_app.add_exception_handler(
        Exception,
        global_exception_handler,
    )
    test_app.middleware("http")(request_logging_middleware)

    @test_app.get("/test-unhandled-error")
    def trigger_unhandled_error():
        raise RuntimeError("sensitive internal details")

    with TestClient(
        test_app,
        raise_server_exceptions=False,
    ) as test_client:
        response = test_client.get("/test-unhandled-error")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected error occurred"
    }
    assert "sensitive internal details" not in response.text
    assert response.headers.get("X-Request-ID")



import re


def test_request_id_is_generated():
    response = client.get("/health")

    request_id = response.headers.get("X-Request-ID")

    assert request_id is not None
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        request_id,
    )


def test_valid_request_id_is_preserved():
    supplied_id = "opspilot-test-123"

    response = client.get(
        "/health",
        headers={"X-Request-ID": supplied_id},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == supplied_id


def test_invalid_request_id_is_replaced():
    supplied_id = "invalid request id!"

    response = client.get(
        "/health",
        headers={"X-Request-ID": supplied_id},
    )

    returned_id = response.headers["X-Request-ID"]

    assert response.status_code == 200
    assert returned_id != supplied_id
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        returned_id,
    )


from unittest.mock import patch

import pytest

from app.config import get_database_url


def test_missing_database_url_raises_error():
    with patch.dict("os.environ", {}, clear=True):
        with patch("app.config.load_dotenv"):
            with pytest.raises(
                RuntimeError,
                match="DATABASE_URL is missing from the environment",
            ):
                get_database_url()


def test_readiness_check_database_available():
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "available",
    }


def test_readiness_check_database_unavailable():
    with patch.object(
        Session,
        "execute",
        side_effect=SQLAlchemyError("Simulated connection failure"),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Database is unavailable"
    }

def test_update_incident_rolls_back_on_commit_failure(monkeypatch):
    created = client.post(
        "/incidents",
        json={
            "title": "Rollback test",
            "description": "Testing a simulated database failure.",
            "service": "payment",
            "severity": "high",
        },
    )
    incident_id = created.json()["id"]

    rollback_called = False
    original_rollback = Session.rollback

    def fail_commit(self):
        raise SQLAlchemyError("Simulated commit failure")

    def track_rollback(self):
        nonlocal rollback_called
        rollback_called = True
        return original_rollback(self)

    monkeypatch.setattr(Session, "commit", fail_commit)
    monkeypatch.setattr(Session, "rollback", track_rollback)

    response = client.patch(
        f"/incidents/{incident_id}",
        json={"status": "investigating"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Unable to update incident due to a database error"
    )
    assert rollback_called is True

    fetched = client.get(f"/incidents/{incident_id}")

    assert fetched.status_code == 200
    assert fetched.json()["status"] == "open"

    
def test_get_db_closes_session():
    db_generator = get_db()
    db = next(db_generator)

    with patch.object(Session, "close", autospec=True) as mock_close:
        db_generator.close()

    mock_close.assert_called_once_with(db)

def test_incident_evidence_is_persisted():
    with TestSessionLocal() as db:
        incident = IncidentRecord(
            title="Payment service unavailable",
            description="Payment requests are failing.",
            service="payment",
            environment="test",
            severity="high",
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)

        evidence = IncidentEvidence(
            incident_id=incident.id,
            source_type="log",
            content="Database connection timeout observed.",
        )
        db.add(evidence)
        db.commit()
        db.refresh(evidence)

        saved_evidence = db.get(IncidentEvidence, evidence.id)

        assert saved_evidence is not None
        assert saved_evidence.incident_id == incident.id
        assert saved_evidence.source_type == "log"
        assert saved_evidence.content == (
            "Database connection timeout observed."
        )

def test_deleting_incident_deletes_its_evidence():
    with TestSessionLocal() as db:
        incident = IncidentRecord(
            title="Payment service unavailable",
            description="Payment requests are failing.",
            service="payment",
            environment="test",
            severity="high",
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)

        evidence = IncidentEvidence(
            incident_id=incident.id,
            source_type="log",
            content="Database connection timeout observed.",
        )
        db.add(evidence)
        db.commit()
        evidence_id = evidence.id

        db.delete(incident)
        db.commit()

        saved_evidence = db.get(IncidentEvidence, evidence_id)

        assert saved_evidence is None


def test_create_incident_evidence():
    incident_response = client.post(
        "/incidents",
        json={
            "title": "Payment outage",
            "description": "Payment requests are failing.",
            "service": "payment",
            "severity": "high",
        },
    )
    assert incident_response.status_code == 201
    incident_id = incident_response.json()["id"]

    response = client.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "source_type": "log",
            "content": "Database connection timeout observed.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["incident_id"] == incident_id
    assert body["source_type"] == "log"
    assert body["content"] == (
        "Database connection timeout observed."
    )
    assert body["id"] > 0


def test_list_incident_evidence():
    incident_response = client.post(
        "/incidents",
        json={
            "title": "Payment outage",
            "description": "Payment requests are failing.",
            "service": "payment",
            "severity": "high",
        },
    )
    incident_id = incident_response.json()["id"]

    client.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "source_type": "log",
            "content": "Connection timeout.",
        },
    )
    client.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "source_type": "metric",
            "content": "Error rate increased to 40%.",
        },
    )

    response = client.get(
        f"/incidents/{incident_id}/evidence"
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {item["source_type"] for item in body} == {
        "log",
        "metric",
    }


def test_create_evidence_for_missing_incident():
    response = client.post(
        "/incidents/999999/evidence",
        json={
            "source_type": "log",
            "content": "Connection timeout.",
        },
    )

    assert response.status_code == 404


def test_list_evidence_for_missing_incident():
    response = client.get(
        "/incidents/999999/evidence"
    )

    assert response.status_code == 404


def test_create_evidence_rejects_invalid_source_type():
    incident_response = client.post(
        "/incidents",
        json={
            "title": "Payment outage",
            "description": "Payment requests are failing.",
            "service": "payment",
            "severity": "high",
        },
    )
    incident_id = incident_response.json()["id"]

    response = client.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "source_type": "random",
            "content": "Some evidence.",
        },
    )

    assert response.status_code == 422


def test_create_evidence_rejects_empty_content():
    incident_response = client.post(
        "/incidents",
        json={
            "title": "Payment outage",
            "description": "Payment requests are failing.",
            "service": "payment",
            "severity": "high",
        },
    )
    incident_id = incident_response.json()["id"]

    response = client.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "source_type": "log",
            "content": "",
        },
    )

    assert response.status_code == 422


def test_filter_incident_evidence_by_source_type():
    incident_response = client.post(
        "/incidents",
        json={
            "title": "Payment outage",
            "description": "Payment requests are failing.",
            "service": "payment",
            "severity": "high",
        },
    )
    incident_id = incident_response.json()["id"]

    for source_type, content in [
        ("log", "Connection timeout."),
        ("metric", "Error rate reached 40%."),
        ("log", "Database retry failed."),
    ]:
        response = client.post(
            f"/incidents/{incident_id}/evidence",
            json={
                "source_type": source_type,
                "content": content,
            },
        )
        assert response.status_code == 201

    response = client.get(
        f"/incidents/{incident_id}/evidence",
        params={"source_type": "log"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(item["source_type"] == "log" for item in body)


def test_incident_evidence_pagination():
    incident_response = client.post(
        "/incidents",
        json={
            "title": "Payment outage",
            "description": "Payment requests are failing.",
            "service": "payment",
            "severity": "high",
        },
    )
    incident_id = incident_response.json()["id"]

    for index in range(3):
        response = client.post(
            f"/incidents/{incident_id}/evidence",
            json={
                "source_type": "log",
                "content": f"Log entry number {index}.",
            },
        )
        assert response.status_code == 201

    first_page = client.get(
        f"/incidents/{incident_id}/evidence",
        params={"limit": 2, "offset": 0},
    )
    second_page = client.get(
        f"/incidents/{incident_id}/evidence",
        params={"limit": 2, "offset": 2},
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 1
    assert (
        first_page.json()[0]["id"]
        != second_page.json()[0]["id"]
    )


def test_incident_evidence_rejects_invalid_pagination():
    incident_response = client.post(
        "/incidents",
        json={
            "title": "Payment outage",
            "description": "Payment requests are failing.",
            "service": "payment",
            "severity": "high",
        },
    )
    incident_id = incident_response.json()["id"]

    response = client.get(
        f"/incidents/{incident_id}/evidence",
        params={"limit": 101},
    )

    assert response.status_code == 422
