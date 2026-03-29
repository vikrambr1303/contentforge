"""Per-topic background source; remove from app_settings."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_topic_background_source"
down_revision: Union[str, None] = "008_drop_topic_target_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "topics",
        sa.Column(
            "background_source",
            sa.String(length=32),
            nullable=False,
            server_default="diffusers",
        ),
    )
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT background_source FROM app_settings WHERE id = 1 LIMIT 1")).fetchone()
    if row and row[0]:
        src = str(row[0]).strip().lower()
        if src not in ("diffusers", "unsplash"):
            src = "diffusers"
        bind.execute(sa.text("UPDATE topics SET background_source = :src"), {"src": src})
    op.alter_column("topics", "background_source", server_default=None)
    op.drop_column("app_settings", "background_source")


def downgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "background_source",
            sa.String(length=32),
            nullable=False,
            server_default="diffusers",
        ),
    )
    op.drop_column("topics", "background_source")
