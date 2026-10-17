"""Short service group title for the mobile booking form.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18 09:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("service_groups", sa.Column("short_title", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("service_groups", "short_title")
