
"""Assign existing incidents to a dedicated legacy project.

Revision ID: c84a9f21d6b3
Revises: baa417791e78
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# Alembic revision identifiers.
revision: str = "c84a9f21d6b3"
down_revision: Union[str, Sequence[str], None] = "baa417791e78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_ORGANIZATION_NAME = "Legacy Workspace"
LEGACY_ORGANIZATION_SLUG = "legacy-workspace"

LEGACY_PROJECT_NAME = "Legacy Project"
LEGACY_PROJECT_SLUG = "legacy-project"


def upgrade() -> None:
    """Create a legacy workspace and assign all existing incidents to it."""

    # 1. Add the project reference as nullable first.
    # Existing incident rows do not have a project ID yet.
    op.add_column(
        "incidents",
        sa.Column("project_id", sa.Integer(), nullable=True),
    )

    connection = op.get_bind()

    # 2. Create a dedicated organization for pre-existing data.
    organization_id = connection.execute(
        sa.text(
            """
            INSERT INTO organizations (
                name,
                slug,
                created_by_user_id
            )
            VALUES (
                :name,
                :slug,
                NULL
            )
            RETURNING id
            """
        ),
        {
            "name": LEGACY_ORGANIZATION_NAME,
            "slug": LEGACY_ORGANIZATION_SLUG,
        },
    ).scalar_one()

    # 3. Create the legacy project inside that organization.
    project_id = connection.execute(
        sa.text(
            """
            INSERT INTO projects (
                organization_id,
                name,
                slug,
                description,
                created_by_user_id,
                is_active
            )
            VALUES (
                :organization_id,
                :name,
                :slug,
                :description,
                NULL,
                TRUE
            )
            RETURNING id
            """
        ),
        {
            "organization_id": organization_id,
            "name": LEGACY_PROJECT_NAME,
            "slug": LEGACY_PROJECT_SLUG,
            "description": (
                "Workspace for incidents created before "
                "project-based ownership was introduced."
            ),
        },
    ).scalar_one()

    # 4. Assign every existing incident to the legacy project.
    connection.execute(
        sa.text(
            """
            UPDATE incidents
            SET project_id = :project_id
            WHERE project_id IS NULL
            """
        ),
        {"project_id": project_id},
    )

    # 5. Refuse to continue if any incident was left unassigned.
    unassigned_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM incidents
            WHERE project_id IS NULL
            """
        )
    ).scalar_one()

    if unassigned_count != 0:
        raise RuntimeError(
            f"Legacy project assignment incomplete: "
            f"{unassigned_count} incidents remain unassigned."
        )

    # 6. Enforce referential integrity and add a lookup index.
    op.create_foreign_key(
        "fk_incidents_project_id_projects",
        "incidents",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_incidents_project_id",
        "incidents",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the legacy project assignment and its ownership records."""

    # Remove the index and foreign key before removing the column.
    op.drop_index(
        "ix_incidents_project_id",
        table_name="incidents",
    )

    op.drop_constraint(
        "fk_incidents_project_id_projects",
        "incidents",
        type_="foreignkey",
    )

    op.drop_column("incidents", "project_id")

    # Remove only the organization and project created by this migration.
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            DELETE FROM projects
            WHERE slug = :project_slug
              AND organization_id = (
                  SELECT id
                  FROM organizations
                  WHERE slug = :organization_slug
              )
            """
        ),
        {
            "project_slug": LEGACY_PROJECT_SLUG,
            "organization_slug": LEGACY_ORGANIZATION_SLUG,
        },
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM organizations
            WHERE slug = :organization_slug
            """
        ),
        {"organization_slug": LEGACY_ORGANIZATION_SLUG},
    )
