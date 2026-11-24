from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.db_models import TelemetryRecord
from app.identity_models import ProjectAPIKey
from app.main import app
from app.security import hash_token
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)


# ============================================================
# TEST DATABASE AND APPLICATION FIXTURE
# ============================================================

@pytest.fixture
def metrics_api_client(monkeypatch):
    """Run API integration tests against an isolated SQLite database."""

    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
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

    try:
        with TestClient(app) as test_client:
            yield test_client, TestSessionLocal
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ============================================================
# AUTHENTICATION AND API-KEY HELPERS
# ============================================================

def registration_payload():
    return {
        "email": "metrics-developer@example.com",
        "display_name": "Metrics Test Developer",
        "password": "Correct-Horse-Battery-123!",
        "account_type": "personal",
        "project_name": "Metrics Integration Project",
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


def create_collector_key(client, name="Metrics Test Collector"):
    registration = register_user(client)
    response = client.post(
        f"/projects/{registration['project_id']}/api-keys",
        json={"name": name},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    return registration, response.json()["api_key"]


def metrics_headers(api_key):
    return {
        "X-OTLP-API-Key": api_key,
        "Content-Type": "application/x-protobuf",
    }


# ============================================================
# OTLP METRIC PAYLOAD BUILDER
# ============================================================

def build_otlp_metric_payload(
    *,
    service_name="checkout-service",
    metric_name="cpu.utilization",
    value=12.5,
    host="node-1",
):
    """Build one OTLP Gauge data point with resource and point attributes."""

    request = ExportMetricsServiceRequest()
    resource_metrics = request.resource_metrics.add()

    service_attribute = resource_metrics.resource.attributes.add()
    service_attribute.key = "service.name"
    service_attribute.value.string_value = service_name

    scope_metrics = resource_metrics.scope_metrics.add()
    metric = scope_metrics.metrics.add()
    metric.name = metric_name
    metric.description = "CPU utilization for the host"
    metric.unit = "1"

    point = metric.gauge.data_points.add()
    point.start_time_unix_nano = 1_699_999_999_000_000_000
    point.time_unix_nano = 1_700_000_000_000_000_000
    point.as_double = value

    host_attribute = point.attributes.add()
    host_attribute.key = "host"
    host_attribute.value.string_value = host

    return request.SerializeToString()


# ============================================================
# METRICS INGESTION INTEGRATION TESTS
# ============================================================

def test_project_metric_ingestion_persists_telemetry(metrics_api_client):
    client, session_factory = metrics_api_client
    registration, api_key = create_collector_key(client)

    response = client.post(
        "/v1/metrics",
        content=build_otlp_metric_payload(),
        headers=metrics_headers(api_key),
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": registration["project_id"],
        "received_data_points": 1,
        "accepted_data_points": 1,
    }

    db = session_factory()
    try:
        telemetry = db.query(TelemetryRecord).one()

        assert telemetry.project_id == registration["project_id"]
        assert telemetry.signal_type == "metric"
        assert telemetry.service_name == "checkout-service"
        assert telemetry.trace_id is None
        assert telemetry.span_id is None
        assert telemetry.fingerprint is not None

        payload = telemetry.payload
        assert payload["schema_version"] == 1
        assert payload["signal"] == "metric"
        assert payload["metric_name"] == "cpu.utilization"
        assert payload["description"] == "CPU utilization for the host"
        assert payload["unit"] == "1"
        assert payload["metric_type"] == "gauge"

        point = payload["data_point"]
        assert point["value"] == 12.5
        assert point["attributes"]["host"] == "node-1"
        assert point["time_unix_nano"] == 1_700_000_000_000_000_000

        assert telemetry.observed_at.replace(tzinfo=timezone.utc) == datetime(
            2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
        )
    finally:
        db.close()


def test_project_metric_ingestion_rejects_missing_api_key(metrics_api_client):
    client, _ = metrics_api_client
    response = client.post(
        "/v1/metrics",
        content=build_otlp_metric_payload(),
        headers={"Content-Type": "application/x-protobuf"},
    )
    assert response.status_code == 401


def test_project_metric_ingestion_rejects_invalid_api_key(metrics_api_client):
    client, _ = metrics_api_client
    response = client.post(
        "/v1/metrics",
        content=build_otlp_metric_payload(),
        headers=metrics_headers("opsp_live_invalid"),
    )
    assert response.status_code == 401


def test_project_metric_ingestion_rejects_revoked_api_key(metrics_api_client):
    client, _ = metrics_api_client
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
        "/v1/metrics",
        content=build_otlp_metric_payload(),
        headers=metrics_headers(api_key),
    )
    assert response.status_code == 401


def test_project_metric_ingestion_preserves_repeated_observations(
    metrics_api_client,
):
    client, session_factory = metrics_api_client
    _, api_key = create_collector_key(client)
    payload = build_otlp_metric_payload()
    headers = metrics_headers(api_key)

    first_response = client.post("/v1/metrics", content=payload, headers=headers)
    second_response = client.post("/v1/metrics", content=payload, headers=headers)

    assert first_response.status_code == 200
    assert first_response.json()["accepted_data_points"] == 1
    assert second_response.status_code == 200
    assert second_response.json()["accepted_data_points"] == 1

    db = session_factory()
    try:
        records = db.query(TelemetryRecord).order_by(TelemetryRecord.id).all()
        assert len(records) == 2
        assert all(record.signal_type == "metric" for record in records)
        assert records[0].fingerprint == records[1].fingerprint
        assert records[0].payload["data_point"]["value"] == 12.5
        assert records[1].payload["data_point"]["value"] == 12.5
    finally:
        db.close()


def test_project_metric_ingestion_groups_same_series_attributes(metrics_api_client):
    client, session_factory = metrics_api_client
    _, api_key = create_collector_key(client)
    headers = metrics_headers(api_key)

    responses = [
        client.post(
            "/v1/metrics",
            content=build_otlp_metric_payload(value=12.5, host="node-1"),
            headers=headers,
        ),
        client.post(
            "/v1/metrics",
            content=build_otlp_metric_payload(value=18.0, host="node-1"),
            headers=headers,
        ),
        client.post(
            "/v1/metrics",
            content=build_otlp_metric_payload(value=18.0, host="node-2"),
            headers=headers,
        ),
    ]
    assert all(response.status_code == 200 for response in responses)

    db = session_factory()
    try:
        records = db.query(TelemetryRecord).order_by(TelemetryRecord.id).all()
        assert len(records) == 3
        assert records[0].fingerprint == records[1].fingerprint
        assert records[1].fingerprint != records[2].fingerprint
    finally:
        db.close()


def test_project_metric_ingestion_rejects_wrong_content_type(metrics_api_client):
    client, _ = metrics_api_client
    _, api_key = create_collector_key(client)

    response = client.post(
        "/v1/metrics",
        content=build_otlp_metric_payload(),
        headers={
            "X-OTLP-API-Key": api_key,
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 415


def test_project_metric_ingestion_rejects_empty_payload(metrics_api_client):
    client, _ = metrics_api_client
    _, api_key = create_collector_key(client)

    response = client.post(
        "/v1/metrics",
        content=b"",
        headers=metrics_headers(api_key),
    )
    assert response.status_code == 400


def test_project_metric_ingestion_rejects_invalid_protobuf(metrics_api_client):
    client, _ = metrics_api_client
    _, api_key = create_collector_key(client)

    response = client.post(
        "/v1/metrics",
        content=b"\xff\xff\xff",
        headers=metrics_headers(api_key),
    )
    assert response.status_code == 400


def test_project_metric_ingestion_persists_multiple_data_points(
    metrics_api_client,
):
    client, session_factory = metrics_api_client
    registration, api_key = create_collector_key(client)

    request = ExportMetricsServiceRequest()
    resource_metrics = request.resource_metrics.add()
    service_attribute = resource_metrics.resource.attributes.add()
    service_attribute.key = "service.name"
    service_attribute.value.string_value = "checkout-service"

    scope_metrics = resource_metrics.scope_metrics.add()
    metric = scope_metrics.metrics.add()
    metric.name = "memory.usage"
    metric.unit = "By"

    for value, timestamp in (
        (1024, 1_700_000_000_000_000_000),
        (2048, 1_700_000_001_000_000_000),
    ):
        point = metric.gauge.data_points.add()
        point.as_int = value
        point.time_unix_nano = timestamp

    response = client.post(
        "/v1/metrics",
        content=request.SerializeToString(),
        headers=metrics_headers(api_key),
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": registration["project_id"],
        "received_data_points": 2,
        "accepted_data_points": 2,
    }

    db = session_factory()
    try:
        records = (
            db.query(TelemetryRecord)
            .filter(TelemetryRecord.signal_type == "metric")
            .order_by(TelemetryRecord.observed_at)
            .all()
        )
        assert len(records) == 2
        assert [record.payload["data_point"]["value"] for record in records] == [
            1024,
            2048,
        ]
    finally:
        db.close()


def test_project_metric_ingestion_updates_api_key_last_used(metrics_api_client):
    client, session_factory = metrics_api_client
    _, api_key = create_collector_key(client)

    response = client.post(
        "/v1/metrics",
        content=build_otlp_metric_payload(),
        headers=metrics_headers(api_key),
    )
    assert response.status_code == 200

    db = session_factory()
    try:
        stored_key = db.scalar(
            select(ProjectAPIKey).where(
                ProjectAPIKey.key_hash == hash_token(api_key)
            )
        )
        assert stored_key is not None
        assert stored_key.last_used_at is not None
    finally:
        db.close()
