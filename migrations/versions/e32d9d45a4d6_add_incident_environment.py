"""add incident environment

Revision ID: e32d9d45a4d6
Revises: d620a1ef9cd6
Create Date: 2026-10-12 21:27:34.489995

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e32d9d45a4d6'
down_revision: Union[str, Sequence[str], None] = 'd620a1ef9cd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("environment", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "environment")
