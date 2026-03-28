"""App settings: generation retry limit."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_generation_retry_limit"
down_revision: Union[str, None] = "003_topic_style_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("generation_retry_limit", sa.Integer(), nullable=False, server_default="2"),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "generation_retry_limit")
