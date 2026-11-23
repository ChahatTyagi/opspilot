
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
def session_test_environment(monkeypatch):
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

    try:
        yield TestSessionLocal
    finally:
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


def create_second_member_workspace(db, user_id):
    workspace = Organization(
        name="Acme Engineering",
        slug="acme-engineering",
        workspace_type="organization",
        created_by_user_id=user_id,
    )

    db.add(workspace)
    db.flush()

    membership = OrganizationMembership(
        organization_id=workspace.id,
        user_id=user_id,
        role="developer",
    )

    project = Project(
        organization_id=workspace.id,
        name="Payments Service",
        slug="payments-service",
        description="Payments project",
        created_by_user_id=user_id,
        is_active=True,
    )

    db.add_all([membership, project])
    db.commit()

    return workspace.id


def get_session_record(db, client):
    raw_token = client.cookies.get("opspilot_session")

    assert raw_token is not None

    return db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(raw_token)
        )
    )


def select_workspace(client, workspace_id):
    csrf_token = client.cookies.get("opspilot_csrf")

    assert csrf_token is not None

    return client.put(
        "/workspaces/current",
        json={"organization_id": workspace_id},
        headers={"X-CSRF-Token": csrf_token},
    )


def test_two_sessions_can_select_different_workspaces_and_login_restores_latest(
    session_test_environment,
):
    session_factory = session_test_environment

    # Browser session A registers the user.
    with TestClient(app) as client_a:
        registration = client_a.post(
            "/auth/register",
            json=registration_payload(),
        )

        assert registration.status_code == 201

        personal_workspace_id = registration.json()["workspace_id"]

        # Create a second workspace accessible to the same user.
        db = session_factory()
        try:
            user = db.scalar(
                select(User).where(
                    User.email == "developer@example.com"
                )
            )

            assert user is not None

            organization_workspace_id = create_second_member_workspace(
                db,
                user.id,
            )
        finally:
            db.close()

        # Browser session B logs in independently as the same user.
        with TestClient(app) as client_b:
            login_response = client_b.post(
                "/auth/login",
                json={
                    "email": "developer@example.com",
                    "password": "Correct-Horse-Battery-123!",
                },
            )

            assert login_response.status_code == 200

            # Initially, login restores the existing personal workspace.
            initial_b_workspace = client_b.get("/workspaces/current")

            assert initial_b_workspace.status_code == 200
            assert (
                initial_b_workspace.json()["workspace"]["id"]
                == personal_workspace_id
            )

            # Session B switches to the organization workspace.
            switch_b = select_workspace(
                client_b,
                organization_workspace_id,
            )

            assert switch_b.status_code == 200

            # Session A must remain on its personal workspace.
            current_a = client_a.get("/workspaces/current")

            assert current_a.status_code == 200
            assert (
                current_a.json()["workspace"]["id"]
                == personal_workspace_id
            )

            # Session B must remain on its organization workspace.
            current_b = client_b.get("/workspaces/current")

            assert current_b.status_code == 200
            assert (
                current_b.json()["workspace"]["id"]
                == organization_workspace_id
            )

            # Verify that each session stores its own selection.
            db = session_factory()
            try:
                session_a = get_session_record(db, client_a)
                session_b = get_session_record(db, client_b)

                assert session_a is not None
                assert session_b is not None

                assert (
                    session_a.current_organization_id
                    == personal_workspace_id
                )

                assert (
                    session_b.current_organization_id
                    == organization_workspace_id
                )

                assert session_a.workspace_selected_at is not None
                assert session_b.workspace_selected_at is not None

                assert (
                    session_b.workspace_selected_at
                    >= session_a.workspace_selected_at
                )
            finally:
                db.close()

            # A third independent login should restore the most
            # recently selected workspace: Acme Engineering.
            with TestClient(app) as client_c:
                third_login = client_c.post(
                    "/auth/login",
                    json={
                        "email": "developer@example.com",
                        "password": "Correct-Horse-Battery-123!",
                    },
                )

                assert third_login.status_code == 200

                current_c = client_c.get("/workspaces/current")

                assert current_c.status_code == 200
                assert (
                    current_c.json()["workspace"]["id"]
                    == organization_workspace_id
                )
