"""
Centralized project-level authorization for OpsPilot.

Organization workspace:
    org_admin  -> read, write, manage project members
    developer  -> read and write
    viewer     -> read only

Personal workspace:
    Owner       -> access to all projects
    Collaborator -> access only to explicitly shared projects

Inactive projects are never accessible.

Unauthorized and nonexistent projects both return 404 through
require_project_access(), preventing project ID enumeration.
"""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.identity_models import (
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
)


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    organization: Organization
    role: str
    organization_role: str | None
    is_workspace_owner: bool


PERMISSION_ROLES = {
    "read": {
        "org_admin",
        "project_admin",
        "developer",
        "viewer",
    },
    "write": {
        "org_admin",
        "project_admin",
        "developer",
    },
    "manage_members": {
        "org_admin",
        "project_admin",
    },
}


def get_project_access(
    db: Session,
    user_id: int,
    project_id: int,
) -> ProjectAccess | None:
    """
    Return the user's access to a project.

    Returns None when:
    - The project does not exist.
    - The project is inactive.
    - The user is not a member of its workspace.
    - The user has not been explicitly added to a personal project.
    """

    statement = (
        select(
            Project,
            Organization,
            OrganizationMembership.role,
            ProjectMembership.role,
        )
        .join(
            Organization,
            Organization.id == Project.organization_id,
        )
        .outerjoin(
            OrganizationMembership,
            and_(
                OrganizationMembership.organization_id
                == Organization.id,
                OrganizationMembership.user_id == user_id,
            ),
        )
        .outerjoin(
            ProjectMembership,
            and_(
                ProjectMembership.project_id == Project.id,
                ProjectMembership.user_id == user_id,
            ),
        )
        .where(
            Project.id == project_id,
            Project.is_active.is_(True),
        )
    )

    result = db.execute(statement).first()

    if result is None:
        return None

    project, organization, organization_role, project_role = result

    # A user must first belong to the workspace.
    if organization_role is None:
        return None

    if organization.workspace_type == "organization":
        if organization_role not in {
            "org_admin",
            "developer",
            "viewer",
        }:
            return None

        return ProjectAccess(
            project=project,
            organization=organization,
            role=organization_role,
            organization_role=organization_role,
            is_workspace_owner=False,
        )

    if organization.workspace_type == "personal":
        # The personal workspace owner can access every project
        # inside their own workspace.
        if organization.created_by_user_id == user_id:
            return ProjectAccess(
                project=project,
                organization=organization,
                role="project_admin",
                organization_role=organization_role,
                is_workspace_owner=True,
            )

        # Other workspace members need explicit project membership.
        if project_role not in {
            "project_admin",
            "developer",
            "viewer",
        }:
            return None

        return ProjectAccess(
            project=project,
            organization=organization,
            role=project_role,
            organization_role=organization_role,
            is_workspace_owner=False,
        )

    return None


def require_project_access(
    db: Session,
    user_id: int,
    project_id: int,
) -> ProjectAccess:
    """
    Require the user to have access to a project.

    Returns 404 for both missing and inaccessible projects.
    """

    access = get_project_access(
        db=db,
        user_id=user_id,
        project_id=project_id,
    )

    if access is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return access


def require_project_permission(
    db: Session,
    user_id: int,
    project_id: int,
    permission: str,
) -> ProjectAccess:
    """
    Require a specific permission on a project.

    Supported permissions:
        read
        write
        manage_members
    """

    allowed_roles = PERMISSION_ROLES.get(permission)

    if allowed_roles is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported project permission",
        )

    access = require_project_access(
        db=db,
        user_id=user_id,
        project_id=project_id,
    )

    if access.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient project permissions",
        )

    return access


def get_accessible_project_ids(
    db: Session,
    user_id: int,
) -> list[int]:
    """
    Return all active project IDs accessible to a user.

    Organization workspace:
        Every project in a workspace where the user is a member.

    Personal workspace:
        All projects for the owner.
        Only explicitly shared projects for collaborators.
    """

    statement = (
        select(Project.id)
        .join(
            Organization,
            Organization.id == Project.organization_id,
        )
        .outerjoin(
            OrganizationMembership,
            and_(
                OrganizationMembership.organization_id
                == Organization.id,
                OrganizationMembership.user_id == user_id,
            ),
        )
        .outerjoin(
            ProjectMembership,
            and_(
                ProjectMembership.project_id == Project.id,
                ProjectMembership.user_id == user_id,
            ),
        )
        .where(
            Project.is_active.is_(True),
            OrganizationMembership.user_id == user_id,
            or_(
                Organization.workspace_type == "organization",
                and_(
                    Organization.workspace_type == "personal",
                    or_(
                        Organization.created_by_user_id == user_id,
                        ProjectMembership.user_id == user_id,
                    ),
                ),
            ),
        )
        .distinct()
        .order_by(Project.id)
    )

    return list(db.scalars(statement).all())