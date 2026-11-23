
from datetime import datetime, timedelta, timezone

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth_routes, db_models, identity_models
from app.database import Base, get_db
from app.identity_models import (
    Organization,
    OrganizationMembership,
    Project,
    User,
    UserSession,
)
from app.main import app
from app.security import hash_token


@pytest.fixture
def auth_client(monkeypatch):
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


def test_register_creates_personal_workspace_project_and_session(
    auth_client,
):
    client, session_factory = auth_client

    response = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["email"] == "developer@example.com"
    assert response_data["display_name"] == "OpsPilot Developer"
    assert response_data["workspace_type"] == "personal"
    assert response_data["workspace_name"] == "OpsPilot Developer's Workspace"
    assert response_data["membership_role"] == "org_admin"
    assert response_data["project_name"] == "My First Project"
    assert response_data["project_slug"].startswith("my-first-project-")

    assert client.cookies.get("opspilot_session")
    assert client.cookies.get("opspilot_csrf")

    db = session_factory()
    try:
        user = db.scalar(
            select(User).where(
                User.email == "developer@example.com"
            )
        )

        assert user is not None
        assert user.password_hash != registration_payload()["password"]
        assert user.password_hash.startswith("$argon2id$")

        workspace = db.get(
            Organization,
            response_data["workspace_id"],
        )

        assert workspace is not None
        assert workspace.workspace_type == "personal"

        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == workspace.id,
                OrganizationMembership.user_id == user.id,
            )
        )

        assert membership is not None
        assert membership.role == "org_admin"

        project = db.get(
            Project,
            response_data["project_id"],
        )

        assert project is not None
        assert project.organization_id == workspace.id
        assert project.created_by_user_id == user.id

        session_record = db.scalar(
            select(UserSession).where(
                UserSession.user_id == user.id
            )
        )

        assert session_record is not None
        assert session_record.current_organization_id == workspace.id

        raw_session_token = client.cookies.get("opspilot_session")

        assert session_record.token_hash == hash_token(
            raw_session_token
        )
        assert session_record.token_hash != raw_session_token

    finally:
        db.close()


def test_register_creates_organization_workspace(auth_client):
    client, session_factory = auth_client

    payload = registration_payload()
    payload.update(
        {
            "account_type": "organization",
            "organization_name": "Acme Engineering",
            "project_name": "Payments Service",
        }
    )

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["workspace_type"] == "organization"
    assert response_data["workspace_name"] == "Acme Engineering"
    assert response_data["project_name"] == "Payments Service"
    assert response_data["project_slug"].startswith("payments-service-")

    db = session_factory()
    try:
        workspace = db.get(
            Organization,
            response_data["workspace_id"],
        )

        assert workspace is not None
        assert workspace.workspace_type == "organization"
        assert workspace.name == "Acme Engineering"

        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == workspace.id
            )
        )

        assert membership is not None
        assert membership.role == "org_admin"

        project = db.get(
            Project,
            response_data["project_id"],
        )

        assert project is not None
        assert project.name == "Payments Service"
        assert project.organization_id == workspace.id

        session_record = db.scalar(
            select(UserSession).where(
                UserSession.user_id == membership.user_id
            )
        )

        assert session_record is not None
        assert session_record.current_organization_id == workspace.id

    finally:
        db.close()


def test_register_requires_organization_name_for_organization_account(
    auth_client,
):
    client, _ = auth_client

    payload = registration_payload()
    payload["account_type"] = "organization"

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_register_rejects_organization_name_for_personal_account(
    auth_client,
):
    client, _ = auth_client

    payload = registration_payload()
    payload["organization_name"] = "Unexpected Organization"

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_register_rejects_invalid_account_type(auth_client):
    client, _ = auth_client

    payload = registration_payload()
    payload["account_type"] = "team"

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_register_rejects_empty_project_name(auth_client):
    client, _ = auth_client

    payload = registration_payload()
    payload["project_name"] = "   "

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_registration_rolls_back_all_records_if_session_creation_fails(
    auth_client,
    monkeypatch,
):
    client, session_factory = auth_client

    def fail_session_creation(
        db,
        user,
        request,
        current_organization_id=None,
    ):
        raise SQLAlchemyError("Simulated session creation failure")

    monkeypatch.setattr(
        auth_routes,
        "_create_session",
        fail_session_creation,
    )

    response = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert response.status_code == 500

    db = session_factory()
    try:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert (
            db.scalar(select(func.count()).select_from(Organization)) == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(OrganizationMembership)
            )
            == 0
        )
        assert db.scalar(select(func.count()).select_from(Project)) == 0
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0

    finally:
        db.close()


def test_registration_sets_http_only_session_cookie(auth_client):
    client, _ = auth_client

    response = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert response.status_code == 201

    set_cookie_headers = response.headers.get_list("set-cookie")

    session_cookie = next(
        value
        for value in set_cookie_headers
        if value.startswith("opspilot_session=")
    )

    csrf_cookie = next(
        value
        for value in set_cookie_headers
        if value.startswith("opspilot_csrf=")
    )

    assert "httponly" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()


def test_register_rejects_duplicate_email(auth_client):
    client, _ = auth_client

    first = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    second = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_register_rejects_invalid_email(auth_client):
    client, _ = auth_client

    payload = registration_payload()
    payload["email"] = "not-an-email"

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_register_rejects_short_password(auth_client):
    client, _ = auth_client

    payload = registration_payload()
    payload["password"] = "short"

    response = client.post(
        "/auth/register",
        json=payload,
    )

    assert response.status_code == 422


def test_login_accepts_correct_credentials(auth_client):
    client, session_factory = auth_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    workspace_id = registration.json()["workspace_id"]

    client.cookies.clear()

    response = client.post(
        "/auth/login",
        json={
            "email": "developer@example.com",
            "password": "Correct-Horse-Battery-123!",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "developer@example.com"
    assert client.cookies.get("opspilot_session")
    assert client.cookies.get("opspilot_csrf")

    db = session_factory()
    try:
        raw_token = client.cookies.get("opspilot_session")

        login_session = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_token(raw_token)
            )
        )

        assert login_session is not None
        assert login_session.current_organization_id == workspace_id

    finally:
        db.close()


def test_login_rejects_wrong_password(auth_client):
    client, _ = auth_client

    client.post(
        "/auth/register",
        json=registration_payload(),
    )

    client.cookies.clear()

    response = client.post(
        "/auth/login",
        json={
            "email": "developer@example.com",
            "password": "Wrong-Password-123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_unknown_email(auth_client):
    client, _ = auth_client

    response = client.post(
        "/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "Correct-Horse-Battery-123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_current_user_requires_authentication(auth_client):
    client, _ = auth_client

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_current_user_returns_authenticated_user(auth_client):
    client, _ = auth_client

    client.post(
        "/auth/register",
        json=registration_payload(),
    )

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "developer@example.com"


def test_logout_requires_csrf_token(auth_client):
    client, _ = auth_client

    client.post(
        "/auth/register",
        json=registration_payload(),
    )

    response = client.post("/auth/logout")

    assert response.status_code == 403

    still_authenticated = client.get("/auth/me")
    assert still_authenticated.status_code == 200


def test_logout_revokes_session(auth_client):
    client, session_factory = auth_client

    client.post(
        "/auth/register",
        json=registration_payload(),
    )

    csrf_token = client.cookies.get("opspilot_csrf")

    response = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 204

    current_user = client.get("/auth/me")
    assert current_user.status_code == 401

    db = session_factory()
    try:
        session_record = db.scalar(
            select(UserSession)
        )

        assert session_record is not None
        assert session_record.revoked_at is not None
    finally:
        db.close()


def test_logout_rejects_wrong_csrf_token(auth_client):
    client, _ = auth_client

    client.post(
        "/auth/register",
        json=registration_payload(),
    )

    response = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": "incorrect-csrf-token"},
    )

    assert response.status_code == 403

    current_user = client.get("/auth/me")
    assert current_user.status_code == 200


def test_expired_session_is_rejected(auth_client):
    client, session_factory = auth_client

    client.post(
        "/auth/register",
        json=registration_payload(),
    )

    raw_token = client.cookies.get("opspilot_session")

    db = session_factory()
    try:
        session_record = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_token(raw_token)
            )
        )

        assert session_record is not None

        session_record.expires_at = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        db.commit()
    finally:
        db.close()

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_inactive_user_cannot_use_session(auth_client):
    client, session_factory = auth_client

    client.post(
        "/auth/register",
        json=registration_payload(),
    )

    db = session_factory()
    try:
        user = db.scalar(select(User))
        assert user is not None

        user.is_active = False
        db.commit()
    finally:
        db.close()

    response = client.get("/auth/me")

    assert response.status_code == 401
