"""App settings: background source (diffusers vs unsplash)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_background_source"
down_revision: Union[str, None] = "004_generation_retry_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "background_source",
            sa.String(length=32),
            nullable=False,
            server_default="diffusers",
        ),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "background_source")
