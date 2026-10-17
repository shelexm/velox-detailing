"""Master's phone (for the studio) and the year they joined.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18 12:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("staff", sa.Column("phone", sa.String(length=16), nullable=True))
    op.add_column("staff", sa.Column("since_year", sa.Integer(), nullable=True))
    op.create_check_constraint("since_year", "staff", "since_year IS NULL OR since_year BETWEEN 1980 AND 2100")


def downgrade() -> None:
    op.drop_constraint("since_year", "staff", type_="check")
    op.drop_column("staff", "since_year")
    op.drop_column("staff", "phone")
