
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api_key_models import (
    ProjectAPIKeyCreateRequest,
    ProjectAPIKeyCreateResponse,
    ProjectAPIKeyListResponse,
)
from app.api_key_service import (
    create_project_api_key,
    list_project_api_keys,
    revoke_project_api_key,
)
from app.auth_routes import get_current_user
from app.authorization import require_project_permission
from app.database import get_db
from app.identity_models import User


router = APIRouter(tags=["Project API Keys"])


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=ProjectAPIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(
    project_id: int,
    request: ProjectAPIKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_project_permission(
        db,
        current_user.id,
        project_id,
        "manage_members",
    )

    api_key, raw_key = create_project_api_key(
        db=db,
        project_id=project_id,
        name=request.name,
        created_by_user_id=current_user.id,
    )

    return ProjectAPIKeyCreateResponse(
        id=api_key.id,
        project_id=api_key.project_id,
        name=api_key.name,
        api_key=raw_key,
        created_at=api_key.created_at,
    )


@router.get(
    "/projects/{project_id}/api-keys",
    response_model=ProjectAPIKeyListResponse,
)
def get_api_keys(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_project_permission(
        db,
        current_user.id,
        project_id,
        "manage_members",
    )

    api_keys = list_project_api_keys(
        db=db,
        project_id=project_id,
    )

    return ProjectAPIKeyListResponse(
        api_keys=api_keys,
        total=len(api_keys),
    )


@router.delete(
    "/projects/{project_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_api_key(
    project_id: int,
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_project_permission(
        db,
        current_user.id,
        project_id,
        "manage_members",
    )

    revoked = revoke_project_api_key(
        db=db,
        project_id=project_id,
        key_id=key_id,
    )

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
