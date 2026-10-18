"""Past bookings may lose their client when the client's personal data is erased.

Only active bookings (new, confirmed) still require a client.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18 21:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_bookings_client_required"), "bookings", type_="check")
    op.create_check_constraint(
        op.f("ck_bookings_client_required"), "bookings", "client_id IS NOT NULL OR status NOT IN ('new', 'confirmed')"
    )


def downgrade() -> None:
    # Fails if anonymous past visits exist: their client is gone for good.
    op.drop_constraint(op.f("ck_bookings_client_required"), "bookings", type_="check")
    op.create_check_constraint(
        op.f("ck_bookings_client_required"),
        "bookings",
        "client_id IS NOT NULL OR status IN ('hold', 'expired', 'cancelled')",
    )
