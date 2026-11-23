
"""Add workspace type to organizations.

Revision ID: e91f6c2a7b40
Revises: c84a9f21d6b3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e91f6c2a7b40"
down_revision: Union[str, Sequence[str], None] = "c84a9f21d6b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Classify existing workspaces and support personal workspaces."""

    op.add_column(
        "organizations",
        sa.Column(
            "workspace_type",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'organization'"),
        ),
    )

    op.create_check_constraint(
        "ck_organizations_valid_workspace_type",
        "organizations",
        "workspace_type IN ('personal', 'organization')",
    )


def downgrade() -> None:
    """Remove workspace type classification."""

    op.drop_constraint(
        "ck_organizations_valid_workspace_type",
        "organizations",
        type_="check",
    )

    op.drop_column(
        "organizations",
        "workspace_type",
    )
