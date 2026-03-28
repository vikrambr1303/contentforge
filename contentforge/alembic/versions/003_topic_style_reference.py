"""Topic style reference image (img2img) + strength."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_topic_style_reference"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "topics",
        sa.Column("style_reference_relpath", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "topics",
        sa.Column("reference_image_strength", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("topics", "reference_image_strength")
    op.drop_column("topics", "style_reference_relpath")
