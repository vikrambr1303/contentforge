"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ollama_model", sa.String(length=100), nullable=False),
        sa.Column("diffusers_model_path", sa.String(length=1024), nullable=False),
        sa.Column("default_image_style", sa.String(length=500), nullable=False),
        sa.Column("caption_cta", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.execute(
        text(
            "INSERT INTO app_settings (id, ollama_model, diffusers_model_path, default_image_style, caption_cta) "
            "VALUES (1, 'llama3.2', '/models/stable-diffusion', 'cinematic lighting, soft gradients', '')"
        )
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("style", sa.String(length=50), nullable=False),
        sa.Column("image_style", sa.String(length=500), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "platform_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "content_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=True),
        sa.Column("quote_author", sa.String(length=255), nullable=True),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column("video_path", sa.String(length=500), nullable=True),
        sa.Column("background_path", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("generation_model", sa.String(length=100), nullable=True),
        sa.Column("image_model", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_content_items_topic_id", "content_items", ["topic_id"])
    op.create_index("ix_content_items_status", "content_items", ["status"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=False),
        sa.Column("content_item_id", sa.BigInteger(), nullable=True),
        sa.Column("job_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_generation_jobs_topic_id", "generation_jobs", ["topic_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])

    op.create_table(
        "post_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("content_item_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_account_id", sa.BigInteger(), nullable=False),
        sa.Column("platform_post_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("post_history")
    op.drop_table("generation_jobs")
    op.drop_table("content_items")
    op.drop_table("platform_accounts")
    op.drop_table("topics")
    op.drop_table("app_settings")
