
import pytest

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import app.main to ensure all application models are registered
# with the shared SQLAlchemy Base metadata.
from app.main import app  # noqa: F401

from app.database import Base
from app.identity_models import (
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
    User,
)
from app.authorization import (
    get_project_access,
    require_project_access,
    require_project_permission,
)


@pytest.fixture
def authorization_db():
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

    Base.metadata.create_all(bind=engine)

    TestSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    db = TestSessionLocal()

    try:
        # ---------------------------------------------------------
        # Users
        # ---------------------------------------------------------

        owner = User(
            email="owner@example.com",
            display_name="Personal Workspace Owner",
            password_hash="test-hash",
        )

        collaborator = User(
            email="collaborator@example.com",
            display_name="Project Collaborator",
            password_hash="test-hash",
        )

        workspace_member = User(
            email="member@example.com",
            display_name="Workspace Member",
            password_hash="test-hash",
        )

        outsider = User(
            email="outsider@example.com",
            display_name="External User",
            password_hash="test-hash",
        )

        org_admin = User(
            email="admin@example.com",
            display_name="Organization Admin",
            password_hash="test-hash",
        )

        org_developer = User(
            email="developer@example.com",
            display_name="Organization Developer",
            password_hash="test-hash",
        )

        org_viewer = User(
            email="viewer@example.com",
            display_name="Organization Viewer",
            password_hash="test-hash",
        )

        db.add_all([
            owner,
            collaborator,
            workspace_member,
            outsider,
            org_admin,
            org_developer,
            org_viewer,
        ])
        db.flush()

        # ---------------------------------------------------------
        # Personal workspace
        # ---------------------------------------------------------

        personal_workspace = Organization(
            name="Owner Personal Workspace",
            slug="owner-personal-workspace",
            workspace_type="personal",
            created_by_user_id=owner.id,
        )

        db.add(personal_workspace)
        db.flush()

        db.add_all([
            OrganizationMembership(
                organization_id=personal_workspace.id,
                user_id=owner.id,
                role="org_admin",
            ),
            OrganizationMembership(
                organization_id=personal_workspace.id,
                user_id=collaborator.id,
                role="developer",
            ),
            OrganizationMembership(
                organization_id=personal_workspace.id,
                user_id=workspace_member.id,
                role="viewer",
            ),
        ])

        personal_project = Project(
            organization_id=personal_workspace.id,
            name="Personal Project",
            slug="personal-project",
            created_by_user_id=owner.id,
            is_active=True,
        )

        private_project = Project(
            organization_id=personal_workspace.id,
            name="Private Project",
            slug="private-project",
            created_by_user_id=owner.id,
            is_active=True,
        )

        inactive_project = Project(
            organization_id=personal_workspace.id,
            name="Inactive Project",
            slug="inactive-project",
            created_by_user_id=owner.id,
            is_active=False,
        )

        db.add_all([
            personal_project,
            private_project,
            inactive_project,
        ])
        db.flush()

        # The collaborator gets access to only one project.
        db.add(
            ProjectMembership(
                project_id=personal_project.id,
                user_id=collaborator.id,
                role="developer",
                created_by_user_id=owner.id,
            )
        )

        # The workspace member has no ProjectMembership.
        # They must not gain access to personal projects.

        # ---------------------------------------------------------
        # Organization workspace
        # ---------------------------------------------------------

        organization = Organization(
            name="Acme Engineering",
            slug="acme-engineering",
            workspace_type="organization",
            created_by_user_id=org_admin.id,
        )

        db.add(organization)
        db.flush()

        db.add_all([
            OrganizationMembership(
                organization_id=organization.id,
                user_id=org_admin.id,
                role="org_admin",
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=org_developer.id,
                role="developer",
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=org_viewer.id,
                role="viewer",
            ),
        ])

        organization_project = Project(
            organization_id=organization.id,
            name="Payments Service",
            slug="payments-service",
            created_by_user_id=org_admin.id,
            is_active=True,
        )

        db.add(organization_project)
        db.commit()

        yield {
            "db": db,
            "owner": owner,
            "collaborator": collaborator,
            "workspace_member": workspace_member,
            "outsider": outsider,
            "org_admin": org_admin,
            "org_developer": org_developer,
            "org_viewer": org_viewer,
            "personal_project": personal_project,
            "private_project": private_project,
            "inactive_project": inactive_project,
            "organization_project": organization_project,
        }

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# =============================================================
# Personal workspace authorization
# =============================================================


def test_personal_workspace_owner_can_access_project(authorization_db):
    data = authorization_db

    access = require_project_access(
        data["db"],
        data["owner"].id,
        data["personal_project"].id,
    )

    assert access.role == "project_admin"
    assert access.is_workspace_owner is True
    assert access.organization_role == "org_admin"


def test_personal_project_collaborator_can_access_assigned_project(
    authorization_db,
):
    data = authorization_db

    access = require_project_access(
        data["db"],
        data["collaborator"].id,
        data["personal_project"].id,
    )

    assert access.role == "developer"
    assert access.is_workspace_owner is False


def test_personal_workspace_member_without_project_membership_is_denied(
    authorization_db,
):
    data = authorization_db

    access = get_project_access(
        data["db"],
        data["workspace_member"].id,
        data["personal_project"].id,
    )

    assert access is None


def test_personal_collaborator_cannot_access_unassigned_project(
    authorization_db,
):
    data = authorization_db

    access = get_project_access(
        data["db"],
        data["collaborator"].id,
        data["private_project"].id,
    )

    assert access is None


def test_personal_workspace_owner_can_manage_project_members(
    authorization_db,
):
    data = authorization_db

    access = require_project_permission(
        data["db"],
        data["owner"].id,
        data["personal_project"].id,
        "manage_members",
    )

    assert access.role == "project_admin"


def test_personal_project_developer_cannot_manage_members(
    authorization_db,
):
    data = authorization_db

    with pytest.raises(HTTPException) as exc_info:
        require_project_permission(
            data["db"],
            data["collaborator"].id,
            data["personal_project"].id,
            "manage_members",
        )

    assert exc_info.value.status_code == 403


# =============================================================
# Organization workspace authorization
# =============================================================


def test_organization_admin_can_read_and_write_project(authorization_db):
    data = authorization_db

    access = require_project_permission(
        data["db"],
        data["org_admin"].id,
        data["organization_project"].id,
        "write",
    )

    assert access.role == "org_admin"


def test_organization_developer_can_write_project(authorization_db):
    data = authorization_db

    access = require_project_permission(
        data["db"],
        data["org_developer"].id,
        data["organization_project"].id,
        "write",
    )

    assert access.role == "developer"


def test_organization_viewer_can_read_project(authorization_db):
    data = authorization_db

    access = require_project_permission(
        data["db"],
        data["org_viewer"].id,
        data["organization_project"].id,
        "read",
    )

    assert access.role == "viewer"


def test_organization_viewer_cannot_write_project(authorization_db):
    data = authorization_db

    with pytest.raises(HTTPException) as exc_info:
        require_project_permission(
            data["db"],
            data["org_viewer"].id,
            data["organization_project"].id,
            "write",
        )

    assert exc_info.value.status_code == 403


def test_organization_viewer_cannot_manage_members(authorization_db):
    data = authorization_db

    with pytest.raises(HTTPException) as exc_info:
        require_project_permission(
            data["db"],
            data["org_viewer"].id,
            data["organization_project"].id,
            "manage_members",
        )

    assert exc_info.value.status_code == 403


# =============================================================
# Tenant isolation and project status
# =============================================================


def test_user_from_another_workspace_cannot_access_project(
    authorization_db,
):
    data = authorization_db

    access = get_project_access(
        data["db"],
        data["outsider"].id,
        data["personal_project"].id,
    )

    assert access is None


def test_nonexistent_project_returns_404(authorization_db):
    data = authorization_db

    with pytest.raises(HTTPException) as exc_info:
        require_project_access(
            data["db"],
            data["owner"].id,
            999999,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Project not found"


def test_inactive_project_is_not_accessible(authorization_db):
    data = authorization_db

    access = get_project_access(
        data["db"],
        data["owner"].id,
        data["inactive_project"].id,
    )

    assert access is None


def test_inactive_project_returns_404(authorization_db):
    data = authorization_db

    with pytest.raises(HTTPException) as exc_info:
        require_project_access(
            data["db"],
            data["owner"].id,
            data["inactive_project"].id,
        )

    assert exc_info.value.status_code == 404


def test_unsupported_permission_returns_400(authorization_db):
    data = authorization_db

    with pytest.raises(HTTPException) as exc_info:
        require_project_permission(
            data["db"],
            data["owner"].id,
            data["personal_project"].id,
            "delete_everything",
        )

    assert exc_info.value.status_code == 400
