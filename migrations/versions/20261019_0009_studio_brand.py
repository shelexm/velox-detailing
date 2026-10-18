"""Studio brand: logo word, tagline and an optional logo image from the media library.

Existing studios keep their current look: the VÉLOX word and its tagline.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("studios", sa.Column("brand_name", sa.String(length=24), nullable=True))
    op.add_column("studios", sa.Column("brand_tagline", sa.String(length=40), nullable=True))
    op.add_column("studios", sa.Column("logo_image_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_studios_logo_image_id_media_assets"),
        "studios",
        "media_assets",
        ["logo_image_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "UPDATE studios SET brand_name = 'VÉLOX', brand_tagline = 'DETAILING STUDIO' "
        "WHERE slug = 'velox' AND brand_name IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_studios_logo_image_id_media_assets"), "studios", type_="foreignkey")
    op.drop_column("studios", "logo_image_id")
    op.drop_column("studios", "brand_tagline")
    op.drop_column("studios", "brand_name")
