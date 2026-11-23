
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity_models import Project, ProjectAPIKey
from app.security import generate_project_api_key, hash_token


def create_project_api_key(
    db: Session,
    project_id: int,
    name: str,
    created_by_user_id: int,
) -> tuple[ProjectAPIKey, str]:
    """
    Create a project API key.

    Only the SHA-256 hash is persisted.
    The raw key is returned once to the caller.
    """
    raw_key = generate_project_api_key()
    key_hash = hash_token(raw_key)

    api_key = ProjectAPIKey(
        project_id=project_id,
        name=name,
        key_hash=key_hash,
        created_by_user_id=created_by_user_id,
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return api_key, raw_key


def list_project_api_keys(
    db: Session,
    project_id: int,
) -> list[ProjectAPIKey]:
    """
    Return API-key metadata for a project.
    """
    statement = (
        select(ProjectAPIKey)
        .where(ProjectAPIKey.project_id == project_id)
        .order_by(
            ProjectAPIKey.created_at.desc(),
            ProjectAPIKey.id.desc(),
        )
    )

    return list(db.scalars(statement).all())


def revoke_project_api_key(
    db: Session,
    project_id: int,
    key_id: int,
) -> bool:
    """
    Revoke an API key belonging to the specified project.

    Returns False if the key does not belong to that project.
    Repeated revocation is harmless.
    """
    statement = select(ProjectAPIKey).where(
        ProjectAPIKey.id == key_id,
        ProjectAPIKey.project_id == project_id,
    )

    api_key = db.scalar(statement)

    if api_key is None:
        return False

    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        db.commit()

    return True


def authenticate_project_api_key(
    db: Session,
    raw_key: str | None,
) -> Project | None:
    """
    Authenticate a project API key.

    Returns the associated active project when the key is valid.
    Returns None for missing, invalid, revoked, or inactive-project keys.

    The raw key is never stored. Its SHA-256 hash is used for lookup.
    Successful authentication updates last_used_at.
    """
    if not raw_key or not raw_key.startswith("opsp_live_"):
        return None

    key_hash = hash_token(raw_key)

    statement = (
        select(ProjectAPIKey, Project)
        .join(
            Project,
            Project.id == ProjectAPIKey.project_id,
        )
        .where(
            ProjectAPIKey.key_hash == key_hash,
            ProjectAPIKey.revoked_at.is_(None),
            Project.is_active.is_(True),
        )
    )

    result = db.execute(statement).one_or_none()

    if result is None:
        return None

    api_key, project = result

    api_key.last_used_at = datetime.now(timezone.utc)

    db.commit()

    return project
