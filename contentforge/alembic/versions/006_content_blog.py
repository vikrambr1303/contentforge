"""Content items: blog posts (kind, markdown, diagram asset list)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_content_blog"
down_revision: Union[str, None] = "005_background_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="social"),
    )
    op.add_column("content_items", sa.Column("blog_markdown", sa.Text(), nullable=True))
    op.add_column("content_items", sa.Column("blog_assets_json", sa.JSON(), nullable=True))
    op.create_index("ix_content_items_kind", "content_items", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_items_kind", table_name="content_items")
    op.drop_column("content_items", "blog_assets_json")
    op.drop_column("content_items", "blog_markdown")
    op.drop_column("content_items", "kind")
