"""The booking form has a consent checkbox: the stored default wording said "by pressing the button".

Only the untouched default is replaced; a text the studio wrote itself stays.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19 10:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "Нажимая «Записаться», вы соглашаетесь с политикой обработки данных"
NEW = "Я согласен на обработку персональных данных в соответствии с политикой обработки данных"


def upgrade() -> None:
    op.execute(
        f"UPDATE site_sections SET content = jsonb_set(content, '{{consent_text}}', to_jsonb('{NEW}'::text)) "
        f"WHERE key = 'contacts' AND content ->> 'consent_text' = '{OLD}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE site_sections SET content = jsonb_set(content, '{{consent_text}}', to_jsonb('{OLD}'::text)) "
        f"WHERE key = 'contacts' AND content ->> 'consent_text' = '{NEW}'"
    )
