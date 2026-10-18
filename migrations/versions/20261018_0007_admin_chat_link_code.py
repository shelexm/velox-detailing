"""One-time code for linking the admins' Telegram chat.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18 18:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("studios", sa.Column("telegram_link_code_hash", sa.String(length=64), nullable=True))
    op.add_column("studios", sa.Column("telegram_link_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("studios", "telegram_link_expires_at")
    op.drop_column("studios", "telegram_link_code_hash")
