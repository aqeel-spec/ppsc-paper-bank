"""add vocab settings, themes, and daily progress tables

Revision ID: 20260818_0005
Revises: 20260818_0004
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0005"
down_revision = "20260818_0004"
branch_labels = None
depends_on = None


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _create_index_if_missing(inspector, index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("user_vocab_settings"):
        op.create_table(
            "user_vocab_settings",
            sa.Column("user_id", sa.String(length=36), primary_key=True),
            sa.Column("cards_per_day", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("selected_method", sa.String(length=80), nullable=False, server_default="american_flashcard"),
            sa.Column("selected_theme", sa.String(length=80), nullable=False, server_default="default_classic"),
            sa.Column("custom_card_fields", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not inspector.has_table("vocab_custom_themes"):
        op.create_table(
            "vocab_custom_themes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("theme_config", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not inspector.has_table("vocab_daily_progress"):
        op.create_table(
            "vocab_daily_progress",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("progress_date", sa.Date(), nullable=False),
            sa.Column("words_added", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reviews_done", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("correct_reviews", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("wrong_reviews", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("avg_recall_seconds", sa.Integer(), nullable=True),
            sa.Column("retention_rate", sa.Float(), nullable=True),
            sa.Column("pace_score", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("vocab_custom_themes"):
        _create_index_if_missing(inspector, "ix_vocab_custom_themes_user_id", "vocab_custom_themes", ["user_id"])

    if inspector.has_table("vocab_daily_progress"):
        _create_index_if_missing(inspector, "ix_vocab_daily_progress_user_id", "vocab_daily_progress", ["user_id"])
        _create_index_if_missing(inspector, "ix_vocab_daily_progress_progress_date", "vocab_daily_progress", ["progress_date"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("vocab_daily_progress"):
        if _index_exists(inspector, "vocab_daily_progress", "ix_vocab_daily_progress_progress_date"):
            op.drop_index("ix_vocab_daily_progress_progress_date", table_name="vocab_daily_progress")
        if _index_exists(inspector, "vocab_daily_progress", "ix_vocab_daily_progress_user_id"):
            op.drop_index("ix_vocab_daily_progress_user_id", table_name="vocab_daily_progress")
        op.drop_table("vocab_daily_progress")

    if inspector.has_table("vocab_custom_themes"):
        if _index_exists(inspector, "vocab_custom_themes", "ix_vocab_custom_themes_user_id"):
            op.drop_index("ix_vocab_custom_themes_user_id", table_name="vocab_custom_themes")
        op.drop_table("vocab_custom_themes")

    if inspector.has_table("user_vocab_settings"):
        op.drop_table("user_vocab_settings")
