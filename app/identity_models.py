
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    email_verified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Organization(Base):
    """
    A workspace and tenant boundary containing members and projects.
    """

    __tablename__ = "organizations"

    __table_args__ = (
        CheckConstraint(
            "workspace_type IN ('personal', 'organization')",
            name="ck_organizations_valid_workspace_type",
        ),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)

    workspace_type = Column(
        String(20),
        nullable=False,
        default="organization",
        server_default=text("'organization'"),
    )

    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_membership_organization_user",
        ),
        CheckConstraint(
            "role IN ('org_admin', 'developer', 'viewer')",
            name="ck_membership_valid_role",
        ),
        Index("ix_memberships_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True)

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    role = Column(String(20), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    __table_args__ = (
        CheckConstraint(
            "role IN ('org_admin', 'developer', 'viewer')",
            name="ck_invitation_valid_role",
        ),
        Index(
            "ix_invitations_organization_email",
            "organization_id",
            "email",
        ),
    )

    id = Column(Integer, primary_key=True)

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    email = Column(String(320), nullable=False)
    role = Column(String(20), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)

    invited_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Project(Base):
    __tablename__ = "projects"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_project_organization_slug",
        ),
    )

    id = Column(Integer, primary_key=True)

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    name = Column(String(150), nullable=False)
    slug = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)

    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProjectMembership(Base):
    """
    Grants a user access to one specific project.

    Primarily used for project-level collaboration in personal workspaces.
    Organization workspace permissions will continue to be governed by
    OrganizationMembership.
    """

    __tablename__ = "project_memberships"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_membership_project_user",
        ),
        CheckConstraint(
            "role IN ('project_admin', 'developer', 'viewer')",
            name="ck_project_membership_valid_role",
        ),
        Index(
            "ix_project_memberships_user_id",
            "user_id",
        ),
    )

    id = Column(Integer, primary_key=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    role = Column(String(20), nullable=False)

    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The workspace currently selected in this specific login session.
    # Nullable to support existing sessions and sessions without a selection.
    current_organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Records when this session last selected a workspace.
    workspace_selected_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    token_hash = Column(String(64), nullable=False, unique=True)
    csrf_token_hash = Column(String(64), nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String(500), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )



class ProjectAPIKey(Base):
    """
    A project-scoped credential used by external telemetry collectors.

    Only the SHA-256 hash of the raw API key is stored.
    Raw keys are generated and displayed once by the API.
    """

    __tablename__ = "project_api_keys"

    __table_args__ = (
        UniqueConstraint(
            "key_hash",
            name="uq_project_api_keys_key_hash",
        ),
        Index(
            "ix_project_api_keys_project_id",
            "project_id",
        ),
    )

    id = Column(Integer, primary_key=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    name = Column(
        String(100),
        nullable=False,
    )

    key_hash = Column(
        String(64),
        nullable=False,
    )

    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
