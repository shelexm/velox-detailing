"""Released bot holds were stored as nameless cancelled bookings; they are expired holds.

They showed up in the panel calendar and list as cancelled bookings and inflated the cancellation count.
A completed booking always has a client, and an erased one has its hold owner cleared, so a cancelled row
without a client that still names a hold owner is a released hold.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-19 09:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE bookings SET status = 'expired', cancelled_at = NULL "
        "WHERE status = 'cancelled' AND client_id IS NULL AND hold_owner IS NOT NULL"
    )


def downgrade() -> None:
    # Data cleanup only: released holds cannot be told apart from expired ones afterwards.
    pass
