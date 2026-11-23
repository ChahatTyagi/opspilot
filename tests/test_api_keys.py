
from datetime import datetime, timezone

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db_models, identity_models
from app.database import Base, get_db
from app.identity_models import (
    OrganizationMembership,
    Project,
    ProjectAPIKey,
    User,
)
from app.main import app
from app.security import hash_token
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from app.db_models import TelemetryRecord


@pytest.fixture
def api_key_client(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection,
        connection_record,
    ):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, TestSessionLocal

    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def registration_payload():
    return {
        "email": "developer@example.com",
        "display_name": "OpsPilot Developer",
        "password": "Correct-Horse-Battery-123!",
        "account_type": "personal",
        "project_name": "My First Project",
    }


def register_user(client):
    response = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert response.status_code == 201

    return response.json()


def csrf_headers(client):
    csrf_token = client.cookies.get("opspilot_csrf")

    assert csrf_token is not None

    return {"X-CSRF-Token": csrf_token}


def test_create_api_key_returns_raw_key_once_and_stores_only_hash(
    api_key_client,
):
    client, session_factory = api_key_client

    registration = register_user(client)
    project_id = registration["project_id"]

    response = client.post(
        f"/projects/{project_id}/api-keys",
        json={"name": "Production Collector"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["project_id"] == project_id
    assert response_data["name"] == "Production Collector"
    assert response_data["api_key"].startswith("opsp_live_")

    raw_key = response_data["api_key"]

    db = session_factory()
    try:
        api_key = db.scalar(
            select(ProjectAPIKey).where(
                ProjectAPIKey.id == response_data["id"]
            )
        )

        assert api_key is not None
        assert api_key.project_id == project_id
        assert api_key.name == "Production Collector"

        assert api_key.key_hash == hash_token(raw_key)
        assert api_key.key_hash != raw_key
        assert len(api_key.key_hash) == 64

    finally:
        db.close()


def test_list_api_keys_never_returns_raw_key_or_hash(
    api_key_client,
):
    client, session_factory = api_key_client

    registration = register_user(client)
    project_id = registration["project_id"]

    create_response = client.post(
        f"/projects/{project_id}/api-keys",
        json={"name": "Development Collector"},
        headers=csrf_headers(client),
    )

    assert create_response.status_code == 201

    raw_key = create_response.json()["api_key"]

    response = client.get(
        f"/projects/{project_id}/api-keys"
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["total"] == 1
    assert len(response_data["api_keys"]) == 1

    listed_key = response_data["api_keys"][0]

    assert listed_key["name"] == "Development Collector"
    assert listed_key["project_id"] == project_id

    assert "api_key" not in listed_key
    assert "key_hash" not in listed_key
    assert raw_key not in response.text

    db = session_factory()
    try:
        stored_key = db.scalar(
            select(ProjectAPIKey).where(
                ProjectAPIKey.id == listed_key["id"]
            )
        )

        assert stored_key is not None
        assert stored_key.key_hash != raw_key

    finally:
        db.close()


def test_revoke_api_key_and_repeat_revocation(
    api_key_client,
):
    client, session_factory = api_key_client

    registration = register_user(client)
    project_id = registration["project_id"]

    create_response = client.post(
        f"/projects/{project_id}/api-keys",
        json={"name": "Temporary Collector"},
        headers=csrf_headers(client),
    )

    assert create_response.status_code == 201

    key_id = create_response.json()["id"]

    delete_url = (
        f"/projects/{project_id}/api-keys/{key_id}"
    )

    first_response = client.delete(
        delete_url,
        headers=csrf_headers(client),
    )

    assert first_response.status_code == 204

    second_response = client.delete(
        delete_url,
        headers=csrf_headers(client),
    )

    assert second_response.status_code == 204

    db = session_factory()
    try:
        api_key = db.get(ProjectAPIKey, key_id)

        assert api_key is not None
        assert api_key.revoked_at is not None

    finally:
        db.close()


def test_api_key_cannot_be_revoked_through_another_project(
    api_key_client,
):
    client, session_factory = api_key_client

    registration = register_user(client)
    first_project_id = registration["project_id"]

    db = session_factory()
    try:
        first_project = db.get(Project, first_project_id)

        second_project = Project(
            organization_id=first_project.organization_id,
            name="Second Project",
            slug="second-project",
            description="Another project",
            created_by_user_id=first_project.created_by_user_id,
            is_active=True,
        )

        db.add(second_project)
        db.commit()
        db.refresh(second_project)

        second_project_id = second_project.id

    finally:
        db.close()

    create_response = client.post(
        f"/projects/{first_project_id}/api-keys",
        json={"name": "First Project Collector"},
        headers=csrf_headers(client),
    )

    assert create_response.status_code == 201

    key_id = create_response.json()["id"]

    response = client.delete(
        f"/projects/{second_project_id}/api-keys/{key_id}",
        headers=csrf_headers(client),
    )

    assert response.status_code == 404

    db = session_factory()
    try:
        api_key = db.get(ProjectAPIKey, key_id)

        assert api_key is not None
        assert api_key.project_id == first_project_id
        assert api_key.revoked_at is None

    finally:
        db.close()


def test_api_key_management_requires_authentication(
    api_key_client,
):
    client, _ = api_key_client

    response = client.get(
        "/projects/1/api-keys"
    )

    assert response.status_code == 401


def test_create_api_key_rejects_blank_name(
    api_key_client,
):
    client, registration = api_key_client
    project_id = register_user(client)["project_id"]

    response = client.post(
        f"/projects/{project_id}/api-keys",
        json={"name": "   "},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422



from app.api_key_service import authenticate_project_api_key


def test_authenticate_valid_api_key_returns_project_and_updates_last_used(
    api_key_client,
):
    client, session_factory = api_key_client

    registration = register_user(client)
    project_id = registration["project_id"]

    create_response = client.post(
        f"/projects/{project_id}/api-keys",
        json={"name": "Authentication Test Key"},
        headers=csrf_headers(client),
    )

    assert create_response.status_code == 201

    raw_key = create_response.json()["api_key"]

    db = session_factory()
    try:
        project = authenticate_project_api_key(db, raw_key)

        assert project is not None
        assert project.id == project_id

        api_key = db.scalar(
            select(ProjectAPIKey).where(
                ProjectAPIKey.key_hash == hash_token(raw_key)
            )
        )

        assert api_key is not None
        assert api_key.last_used_at is not None

    finally:
        db.close()


def test_authenticate_rejects_invalid_api_key(api_key_client):
    _, session_factory = api_key_client

    db = session_factory()
    try:
        result = authenticate_project_api_key(
            db,
            "opsp_live_invalid-key",
        )

        assert result is None

    finally:
        db.close()


def test_authenticate_rejects_missing_api_key(api_key_client):
    _, session_factory = api_key_client

    db = session_factory()
    try:
        assert authenticate_project_api_key(db, None) is None
        assert authenticate_project_api_key(db, "") is None

    finally:
        db.close()


def test_authenticate_rejects_revoked_api_key(api_key_client):
    client, session_factory = api_key_client

    registration = register_user(client)
    project_id = registration["project_id"]

    create_response = client.post(
        f"/projects/{project_id}/api-keys",
        json={"name": "Revocation Test Key"},
        headers=csrf_headers(client),
    )

    assert create_response.status_code == 201

    raw_key = create_response.json()["api_key"]
    key_id = create_response.json()["id"]

    revoke_response = client.delete(
        f"/projects/{project_id}/api-keys/{key_id}",
        headers=csrf_headers(client),
    )

    assert revoke_response.status_code == 204

    db = session_factory()
    try:
        result = authenticate_project_api_key(db, raw_key)

        assert result is None

    finally:
        db.close()



def build_otlp_trace_payload(
    trace_id_byte: int = 1,
    span_id_byte: int = 2,
    service_name: str = "checkout-service",
) -> bytes:
    request = ExportTraceServiceRequest()

    resource_spans = request.resource_spans.add()

    service_attribute = (
        resource_spans.resource.attributes.add()
    )
    service_attribute.key = "service.name"
    service_attribute.value.string_value = service_name

    scope_spans = resource_spans.scope_spans.add()

    span = scope_spans.spans.add()
    span.trace_id = bytes([trace_id_byte]) * 16
    span.span_id = bytes([span_id_byte]) * 8
    span.name = "POST /checkout"
    span.start_time_unix_nano = 1_700_000_000_000_000_000
    span.end_time_unix_nano = 1_700_000_001_000_000_000

    return request.SerializeToString()


def create_collector_key(client, name="Test Collector"):
    registration = register_user(client)

    response = client.post(
        f"/projects/{registration['project_id']}/api-keys",
        json={"name": name},
        headers=csrf_headers(client),
    )

    assert response.status_code == 201

    return registration, response.json()["api_key"]


def test_project_trace_ingestion_persists_telemetry(api_key_client):
    client, session_factory = api_key_client

    registration, api_key = create_collector_key(client)

    payload = build_otlp_trace_payload()

    response = client.post(
        "/v1/traces",
        content=payload,
        headers={
            "X-OTLP-API-Key": api_key,
            "Content-Type": "application/x-protobuf",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": registration["project_id"],
        "received_spans": 1,
        "accepted_spans": 1,
        "duplicate_spans": 0,
    }

    db = session_factory()

    try:
        telemetry = db.query(TelemetryRecord).one()

        assert telemetry.project_id == registration["project_id"]
        assert telemetry.signal_type == "trace"
        assert telemetry.service_name == "checkout-service"
        assert telemetry.trace_id == "01" * 16
        assert telemetry.span_id == "02" * 8
        assert telemetry.fingerprint is not None
        assert telemetry.payload["span_name"] == "POST /checkout"

    finally:
        db.close()


def test_project_trace_ingestion_rejects_missing_api_key(api_key_client):
    client, _ = api_key_client

    response = client.post(
        "/v1/traces",
        content=build_otlp_trace_payload(),
        headers={"Content-Type": "application/x-protobuf"},
    )

    assert response.status_code == 401


def test_project_trace_ingestion_rejects_invalid_api_key(api_key_client):
    client, _ = api_key_client

    response = client.post(
        "/v1/traces",
        content=build_otlp_trace_payload(),
        headers={
            "X-OTLP-API-Key": "opsp_live_invalid",
            "Content-Type": "application/x-protobuf",
        },
    )

    assert response.status_code == 401


def test_project_trace_ingestion_rejects_revoked_api_key(api_key_client):
    client, _ = api_key_client

    registration, api_key = create_collector_key(client)

    key_response = client.get(
        f"/projects/{registration['project_id']}/api-keys"
    )

    assert key_response.status_code == 200

    key_id = key_response.json()["api_keys"][0]["id"]

    revoke_response = client.delete(
        f"/projects/{registration['project_id']}/api-keys/{key_id}",
        headers=csrf_headers(client),
    )

    assert revoke_response.status_code == 204

    response = client.post(
        "/v1/traces",
        content=build_otlp_trace_payload(),
        headers={
            "X-OTLP-API-Key": api_key,
            "Content-Type": "application/x-protobuf",
        },
    )

    assert response.status_code == 401


def test_project_trace_ingestion_deduplicates_spans(api_key_client):
    client, session_factory = api_key_client

    _, api_key = create_collector_key(client)

    headers = {
        "X-OTLP-API-Key": api_key,
        "Content-Type": "application/x-protobuf",
    }

    payload = build_otlp_trace_payload()

    first_response = client.post(
        "/v1/traces",
        content=payload,
        headers=headers,
    )

    second_response = client.post(
        "/v1/traces",
        content=payload,
        headers=headers,
    )

    assert first_response.status_code == 200
    assert first_response.json()["accepted_spans"] == 1

    assert second_response.status_code == 200
    assert second_response.json()["accepted_spans"] == 0
    assert second_response.json()["duplicate_spans"] == 1

    db = session_factory()

    try:
        count = db.query(TelemetryRecord).count()
        assert count == 1

    finally:
        db.close()


def test_project_trace_ingestion_rejects_wrong_content_type(api_key_client):
    client, _ = api_key_client

    _, api_key = create_collector_key(client)

    response = client.post(
        "/v1/traces",
        content=build_otlp_trace_payload(),
        headers={
            "X-OTLP-API-Key": api_key,
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 415


def test_project_trace_ingestion_rejects_empty_payload(api_key_client):
    client, _ = api_key_client

    _, api_key = create_collector_key(client)

    response = client.post(
        "/v1/traces",
        content=b"",
        headers={
            "X-OTLP-API-Key": api_key,
            "Content-Type": "application/x-protobuf",
        },
    )

    assert response.status_code == 400
