"""generation job progress and stage

Revision ID: 002
Revises: 001
Create Date: 2026-03-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs",
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("generation_jobs", sa.Column("stage", sa.String(length=128), nullable=True))
    op.execute(sa.text("UPDATE generation_jobs SET progress_percent = 100 WHERE status IN ('done', 'failed')"))
    op.alter_column(
        "generation_jobs",
        "progress_percent",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("generation_jobs", "stage")
    op.drop_column("generation_jobs", "progress_percent")
