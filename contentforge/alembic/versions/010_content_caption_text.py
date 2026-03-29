"""content_items: caption_text for Instagram-style copy + hashtags."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_content_caption_text"
down_revision: Union[str, None] = "009_topic_background_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("caption_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "caption_text")
