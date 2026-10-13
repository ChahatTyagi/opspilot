
"""Remove redundant incident ID index."""

from alembic import op

# Revision identifiers
revision = "4eb8d503912b"
down_revision = "e32d9d45a4d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_incidents_id", table_name="incidents")


def downgrade() -> None:
    op.create_index("ix_incidents_id", "incidents", ["id"], unique=False)
