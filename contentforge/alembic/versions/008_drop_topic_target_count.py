"""Drop topics.target_count."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_drop_topic_target_count"
down_revision: Union[str, None] = "007_generation_job_payload"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("topics", "target_count")


def downgrade() -> None:
    op.add_column(
        "topics",
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="10"),
    )
    op.alter_column("topics", "target_count", server_default=None)
