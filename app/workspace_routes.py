
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_routes import get_current_user
from app.database import get_db
from app.identity_models import (
    Organization,
    OrganizationMembership,
    Project,
    User,
)
from app.workspace_models import (
    WorkspaceListResponse,
    WorkspaceProjectResponse,
    WorkspaceResponse,
)


router = APIRouter(
    prefix="/workspaces",
    tags=["Workspaces"],
)


def _build_workspace_responses(
    db: Session,
    workspace_rows,
) -> list[WorkspaceResponse]:
    """
    Convert authorized workspace and membership rows into API responses.

    Projects are fetched in one query for all returned workspaces,
    avoiding a separate database query for every workspace.
    """

    if not workspace_rows:
        return []

    workspace_ids = [
        workspace.id
        for workspace, role in workspace_rows
    ]

    projects = db.scalars(
        select(Project)
        .where(Project.organization_id.in_(workspace_ids))
        .order_by(Project.created_at, Project.id)
    ).all()

    projects_by_workspace: dict[int, list[Project]] = {
        workspace_id: []
        for workspace_id in workspace_ids
    }

    for project in projects:
        projects_by_workspace[project.organization_id].append(project)

    responses = []

    for workspace, role in workspace_rows:
        workspace_projects = [
            WorkspaceProjectResponse.model_validate(project)
            for project in projects_by_workspace[workspace.id]
        ]

        responses.append(
            WorkspaceResponse(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                workspace_type=workspace.workspace_type,
                role=role,
                created_at=workspace.created_at,
                projects=workspace_projects,
            )
        )

    return responses


@router.get(
    "",
    response_model=WorkspaceListResponse,
)
def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return only workspaces where the authenticated user is a member.
    """

    statement = (
        select(
            Organization,
            OrganizationMembership.role,
        )
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.user_id == current_user.id,
        )
        .order_by(
            Organization.created_at,
            Organization.id,
        )
    )

    workspace_rows = db.execute(statement).all()

    workspaces = _build_workspace_responses(
        db,
        workspace_rows,
    )

    return WorkspaceListResponse(
        workspaces=workspaces,
        total=len(workspaces),
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
)
def get_workspace(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return one workspace only if the authenticated user is a member.

    Nonexistent and unauthorized workspaces both return 404 so that
    the API does not reveal whether another user's workspace exists.
    """

    statement = (
        select(
            Organization,
            OrganizationMembership.role,
        )
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            Organization.id == workspace_id,
            OrganizationMembership.user_id == current_user.id,
        )
    )

    workspace_row = db.execute(statement).first()

    if workspace_row is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    responses = _build_workspace_responses(
        db,
        [workspace_row],
    )

    return responses[0]
