
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth_routes import get_current_session, get_current_user
from app.database import get_db
from app.identity_models import (
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
    User,
    UserSession,
)
from app.workspace_models import (
    CurrentWorkspaceResponse,
    WorkspaceListResponse,
    WorkspaceProjectResponse,
    WorkspaceResponse,
    WorkspaceSelectionRequest,
)


router = APIRouter(
    prefix="/workspaces",
    tags=["Workspaces"],
)


def _build_workspace_responses(
    db: Session,
    workspace_rows,
    user_id: int,
) -> list[WorkspaceResponse]:
    """
    Build workspace responses while enforcing project visibility.

    Organization workspaces:
        Every workspace member can see all projects.

    Personal workspaces:
        The workspace owner can see all projects.
        Other members can see only projects explicitly shared
        through ProjectMembership.

    Project visibility is checked here so every endpoint using
    this helper follows the same rules.
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

    if not projects:
        return [
            WorkspaceResponse(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                workspace_type=workspace.workspace_type,
                role=role,
                created_at=workspace.created_at,
                projects=[],
            )
            for workspace, role in workspace_rows
        ]

    project_ids = [project.id for project in projects]

    shared_project_ids = set(
        db.scalars(
            select(ProjectMembership.project_id).where(
                ProjectMembership.user_id == user_id,
                ProjectMembership.project_id.in_(project_ids),
            )
        ).all()
    )

    projects_by_workspace: dict[int, list[Project]] = {
        workspace_id: []
        for workspace_id in workspace_ids
    }

    for project in projects:
        projects_by_workspace[project.organization_id].append(project)

    responses = []

    for workspace, role in workspace_rows:
        workspace_projects = projects_by_workspace[workspace.id]

        if workspace.workspace_type == "personal":
            is_workspace_owner = workspace.created_by_user_id == user_id

            if not is_workspace_owner:
                workspace_projects = [
                    project
                    for project in workspace_projects
                    if project.id in shared_project_ids
                ]

        project_responses = [
            WorkspaceProjectResponse.model_validate(project)
            for project in workspace_projects
        ]

        responses.append(
            WorkspaceResponse(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                workspace_type=workspace.workspace_type,
                role=role,
                created_at=workspace.created_at,
                projects=project_responses,
            )
        )

    return responses


def _get_member_workspace_row(
    db: Session,
    user_id: int,
    workspace_id: int,
):
    """
    Return a workspace and the user's role only when membership exists.
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
            OrganizationMembership.user_id == user_id,
        )
    )

    return db.execute(statement).first()


@router.get(
    "/current",
    response_model=CurrentWorkspaceResponse,
)
def get_current_workspace(
    current_user: User = Depends(get_current_user),
    session_record: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    """
    Return the workspace selected in the current browser session.

    A missing selection or a selection without valid membership
    returns workspace=null.
    """

    workspace_id = session_record.current_organization_id

    if workspace_id is None:
        return CurrentWorkspaceResponse(workspace=None)

    workspace_row = _get_member_workspace_row(
        db,
        current_user.id,
        workspace_id,
    )

    if workspace_row is None:
        return CurrentWorkspaceResponse(workspace=None)

    workspace = _build_workspace_responses(
        db,
        [workspace_row],
        current_user.id,
    )[0]

    return CurrentWorkspaceResponse(workspace=workspace)


@router.put(
    "/current",
    response_model=CurrentWorkspaceResponse,
)
def select_current_workspace(
    payload: WorkspaceSelectionRequest,
    current_user: User = Depends(get_current_user),
    session_record: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    """
    Select a workspace for the current browser session.

    The user must have a membership in the requested workspace.
    The get_current_session dependency also enforces CSRF validation
    for this PUT request.

    The workspace selection timestamp is updated so that future
    logins can restore the most recently selected workspace.
    """

    workspace_row = _get_member_workspace_row(
        db,
        current_user.id,
        payload.organization_id,
    )

    if workspace_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    session_record.current_organization_id = payload.organization_id
    session_record.workspace_selected_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to switch workspace",
        )

    workspace = _build_workspace_responses(
        db,
        [workspace_row],
        current_user.id,
    )[0]

    return CurrentWorkspaceResponse(workspace=workspace)


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

    Project visibility is additionally restricted according to
    personal-workspace ownership or explicit project membership.
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
        current_user.id,
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

    workspace_row = _get_member_workspace_row(
        db,
        current_user.id,
        workspace_id,
    )

    if workspace_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    responses = _build_workspace_responses(
        db,
        [workspace_row],
        current_user.id,
    )

    return responses[0]
