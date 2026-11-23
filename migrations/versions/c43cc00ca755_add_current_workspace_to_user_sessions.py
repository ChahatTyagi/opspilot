
"""add current workspace to user sessions

Revision ID: c43cc00ca755
Revises: e91f6c2a7b40
Create Date: 2026-11-23 22:18:38.932592

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers.
revision: str = "c43cc00ca755"
down_revision: Union[str, Sequence[str], None] = "e91f6c2a7b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the current workspace reference to user sessions."""

    op.add_column(
        "user_sessions",
        sa.Column(
            "current_organization_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_user_sessions_current_organization_id_organizations",
        "user_sessions",
        "organizations",
        ["current_organization_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove the current workspace reference from user sessions."""

    op.drop_constraint(
        "fk_user_sessions_current_organization_id_organizations",
        "user_sessions",
        type_="foreignkey",
    )

    op.drop_column(
        "user_sessions",
        "current_organization_id",
    )
