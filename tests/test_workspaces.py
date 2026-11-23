
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
def workspace_client(monkeypatch):
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


def create_other_user_workspace(db):
    """
    Create another user's workspace and a separate legacy workspace.

    Neither workspace should be visible to the authenticated test user.
    """

    other_user = User(
        email="other@example.com",
        display_name="Other Developer",
        password_hash="test-password-hash",
    )

    db.add(other_user)
    db.flush()

    other_workspace = Organization(
        name="Other Developer's Workspace",
        slug="other-developer-workspace",
        workspace_type="personal",
        created_by_user_id=other_user.id,
    )

    db.add(other_workspace)
    db.flush()

    other_membership = OrganizationMembership(
        organization_id=other_workspace.id,
        user_id=other_user.id,
        role="org_admin",
    )

    other_project = Project(
        organization_id=other_workspace.id,
        name="Other Developer Project",
        slug="other-developer-project",
        created_by_user_id=other_user.id,
    )

    legacy_workspace = Organization(
        name="Legacy Workspace",
        slug="legacy-workspace",
        workspace_type="organization",
    )

    db.add_all(
        [
            other_membership,
            other_project,
            legacy_workspace,
        ]
    )

    db.commit()

    return other_workspace.id, legacy_workspace.id


def create_second_member_workspace(db, user_id):
    """
    Create a second workspace that the given user is authorized to access.
    """

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


def test_list_workspaces_requires_authentication(workspace_client):
    client, _ = workspace_client

    response = client.get("/workspaces")

    assert response.status_code == 401


def test_list_workspaces_returns_only_user_workspaces_and_projects(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    registration_data = registration.json()

    db = session_factory()
    try:
        other_workspace_id, legacy_workspace_id = (
            create_other_user_workspace(db)
        )
    finally:
        db.close()

    response = client.get("/workspaces")

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["total"] == 1
    assert len(response_data["workspaces"]) == 1

    workspace = response_data["workspaces"][0]

    assert workspace["id"] == registration_data["workspace_id"]
    assert workspace["name"] == "OpsPilot Developer's Workspace"
    assert workspace["workspace_type"] == "personal"
    assert workspace["role"] == "org_admin"

    assert len(workspace["projects"]) == 1

    project = workspace["projects"][0]

    assert project["id"] == registration_data["project_id"]
    assert project["name"] == "My First Project"
    assert project["slug"].startswith("my-first-project-")

    visible_workspace_ids = {
        item["id"]
        for item in response_data["workspaces"]
    }

    assert other_workspace_id not in visible_workspace_ids
    assert legacy_workspace_id not in visible_workspace_ids


def test_get_workspace_returns_workspace_for_its_member(
    workspace_client,
):
    client, _ = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    workspace_id = registration.json()["workspace_id"]

    response = client.get(f"/workspaces/{workspace_id}")

    assert response.status_code == 200

    workspace = response.json()

    assert workspace["id"] == workspace_id
    assert workspace["name"] == "OpsPilot Developer's Workspace"
    assert workspace["workspace_type"] == "personal"
    assert workspace["role"] == "org_admin"

    assert len(workspace["projects"]) == 1
    assert workspace["projects"][0]["name"] == "My First Project"


def test_get_workspace_rejects_another_users_workspace(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    db = session_factory()
    try:
        other_workspace_id, _ = create_other_user_workspace(db)
    finally:
        db.close()

    response = client.get(
        f"/workspaces/{other_workspace_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found"


def test_get_workspace_rejects_workspace_without_membership(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    db = session_factory()
    try:
        _, legacy_workspace_id = create_other_user_workspace(db)
    finally:
        db.close()

    response = client.get(
        f"/workspaces/{legacy_workspace_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found"


def test_get_nonexistent_workspace_returns_404(workspace_client):
    client, _ = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    response = client.get("/workspaces/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found"


def test_get_current_workspace_requires_authentication(workspace_client):
    client, _ = workspace_client

    response = client.get("/workspaces/current")

    assert response.status_code == 401


def test_get_current_workspace_returns_registration_workspace(
    workspace_client,
):
    client, _ = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    expected_workspace_id = registration.json()["workspace_id"]

    response = client.get("/workspaces/current")

    assert response.status_code == 200

    workspace = response.json()["workspace"]

    assert workspace is not None
    assert workspace["id"] == expected_workspace_id
    assert workspace["role"] == "org_admin"
    assert workspace["projects"][0]["name"] == "My First Project"


def test_get_current_workspace_returns_null_for_unselected_session(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    db = session_factory()
    try:
        session_record = get_session_record(db, client)

        assert session_record is not None

        session_record.current_organization_id = None
        db.commit()
    finally:
        db.close()

    response = client.get("/workspaces/current")

    assert response.status_code == 200
    assert response.json() == {"workspace": None}


def test_select_current_workspace_requires_authentication(
    workspace_client,
):
    client, _ = workspace_client

    response = client.put(
        "/workspaces/current",
        json={"organization_id": 1},
    )

    assert response.status_code == 401


def test_select_current_workspace_requires_csrf_token(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    workspace_id = registration.json()["workspace_id"]

    db = session_factory()
    try:
        session_record = get_session_record(db, client)

        assert session_record is not None
        original_workspace_id = session_record.current_organization_id
    finally:
        db.close()

    response = client.put(
        "/workspaces/current",
        json={"organization_id": workspace_id},
    )

    assert response.status_code == 403

    db = session_factory()
    try:
        session_record = get_session_record(db, client)

        assert session_record is not None
        assert session_record.current_organization_id == original_workspace_id
    finally:
        db.close()


def test_select_current_workspace_switches_to_another_member_workspace(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    db = session_factory()
    try:
        user = db.scalar(select(User))
        assert user is not None

        second_workspace_id = create_second_member_workspace(
            db,
            user.id,
        )
    finally:
        db.close()

    csrf_token = client.cookies.get("opspilot_csrf")

    response = client.put(
        "/workspaces/current",
        json={"organization_id": second_workspace_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200

    response_workspace = response.json()["workspace"]

    assert response_workspace is not None
    assert response_workspace["id"] == second_workspace_id
    assert response_workspace["name"] == "Acme Engineering"
    assert response_workspace["role"] == "developer"
    assert response_workspace["projects"][0]["name"] == "Payments Service"

    current_response = client.get("/workspaces/current")

    assert current_response.status_code == 200
    assert (
        current_response.json()["workspace"]["id"]
        == second_workspace_id
    )

    db = session_factory()
    try:
        session_record = get_session_record(db, client)

        assert session_record is not None
        assert session_record.current_organization_id == second_workspace_id
    finally:
        db.close()


def test_select_current_workspace_rejects_another_users_workspace(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    db = session_factory()
    try:
        other_workspace_id, _ = create_other_user_workspace(db)
    finally:
        db.close()

    csrf_token = client.cookies.get("opspilot_csrf")

    response = client.put(
        "/workspaces/current",
        json={"organization_id": other_workspace_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found"

    current_response = client.get("/workspaces/current")

    assert current_response.status_code == 200
    assert (
        current_response.json()["workspace"]["id"]
        == registration.json()["workspace_id"]
    )


def test_select_current_workspace_rejects_legacy_workspace(
    workspace_client,
):
    client, session_factory = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    db = session_factory()
    try:
        _, legacy_workspace_id = create_other_user_workspace(db)
    finally:
        db.close()

    csrf_token = client.cookies.get("opspilot_csrf")

    response = client.put(
        "/workspaces/current",
        json={"organization_id": legacy_workspace_id},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 404


def test_select_current_workspace_rejects_nonexistent_workspace(
    workspace_client,
):
    client, _ = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    csrf_token = client.cookies.get("opspilot_csrf")

    response = client.put(
        "/workspaces/current",
        json={"organization_id": 999999},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 404


def test_select_current_workspace_rejects_invalid_workspace_id(
    workspace_client,
):
    client, _ = workspace_client

    registration = client.post(
        "/auth/register",
        json=registration_payload(),
    )

    assert registration.status_code == 201

    csrf_token = client.cookies.get("opspilot_csrf")

    response = client.put(
        "/workspaces/current",
        json={"organization_id": -1},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422
