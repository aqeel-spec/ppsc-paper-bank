"""add paper series tables

Revision ID: 20260416_0001
Revises:
Create Date: 2026-04-16 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260416_0001"
down_revision = None
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("paper_series"):
        op.create_table(
            "paper_series",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("created_by", sa.String(length=36), nullable=False),
            sa.Column("mode", sa.String(length=20), nullable=False),
            sa.Column("years_json", sa.JSON(), nullable=False),
            sa.Column("chunk_size", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("total_papers", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing("ix_paper_series_created_by", "paper_series", ["created_by"])

    if not inspector.has_table("paper_series_day"):
        op.create_table(
            "paper_series_day",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("series_id", sa.String(length=36), nullable=False),
            sa.Column("day_no", sa.Integer(), nullable=False),
            sa.Column("scheduled_date", sa.Date(), nullable=False),
            sa.Column("phase", sa.String(length=20), nullable=False),
            sa.Column("syllabus_json", sa.JSON(), nullable=False),
            sa.Column("paper_id", sa.Integer(), nullable=True),
            sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing("ix_paper_series_day_series_id", "paper_series_day", ["series_id"])
    _create_index_if_missing("ix_paper_series_day_day_no", "paper_series_day", ["day_no"])
    _create_index_if_missing("ix_paper_series_day_scheduled_date", "paper_series_day", ["scheduled_date"])
    _create_index_if_missing("ix_paper_series_day_phase", "paper_series_day", ["phase"])
    _create_index_if_missing("ix_paper_series_day_paper_id", "paper_series_day", ["paper_id"])

    if not inspector.has_table("paper_series_attempt"):
        op.create_table(
            "paper_series_attempt",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("series_day_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("correct_answers", sa.Integer(), nullable=False),
            sa.Column("total_questions", sa.Integer(), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False),
            sa.Column("credit_cost", sa.Integer(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing("ix_paper_series_attempt_series_day_id", "paper_series_attempt", ["series_day_id"])
    _create_index_if_missing("ix_paper_series_attempt_user_id", "paper_series_attempt", ["user_id"])

    if not inspector.has_table("paper_series_reward_log"):
        op.create_table(
            "paper_series_reward_log",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("series_day_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("credits_awarded", sa.Integer(), nullable=False),
            sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing("ix_paper_series_reward_log_series_day_id", "paper_series_reward_log", ["series_day_id"])
    _create_index_if_missing("ix_paper_series_reward_log_user_id", "paper_series_reward_log", ["user_id"])
    _create_index_if_missing("ix_paper_series_reward_log_rank", "paper_series_reward_log", ["rank"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("paper_series_reward_log"):
        if _index_exists("paper_series_reward_log", "ix_paper_series_reward_log_rank"):
            op.drop_index("ix_paper_series_reward_log_rank", table_name="paper_series_reward_log")
        if _index_exists("paper_series_reward_log", "ix_paper_series_reward_log_user_id"):
            op.drop_index("ix_paper_series_reward_log_user_id", table_name="paper_series_reward_log")
        if _index_exists("paper_series_reward_log", "ix_paper_series_reward_log_series_day_id"):
            op.drop_index("ix_paper_series_reward_log_series_day_id", table_name="paper_series_reward_log")
        op.drop_table("paper_series_reward_log")

    if inspector.has_table("paper_series_attempt"):
        if _index_exists("paper_series_attempt", "ix_paper_series_attempt_user_id"):
            op.drop_index("ix_paper_series_attempt_user_id", table_name="paper_series_attempt")
        if _index_exists("paper_series_attempt", "ix_paper_series_attempt_series_day_id"):
            op.drop_index("ix_paper_series_attempt_series_day_id", table_name="paper_series_attempt")
        op.drop_table("paper_series_attempt")

    if inspector.has_table("paper_series_day"):
        if _index_exists("paper_series_day", "ix_paper_series_day_paper_id"):
            op.drop_index("ix_paper_series_day_paper_id", table_name="paper_series_day")
        if _index_exists("paper_series_day", "ix_paper_series_day_phase"):
            op.drop_index("ix_paper_series_day_phase", table_name="paper_series_day")
        if _index_exists("paper_series_day", "ix_paper_series_day_scheduled_date"):
            op.drop_index("ix_paper_series_day_scheduled_date", table_name="paper_series_day")
        if _index_exists("paper_series_day", "ix_paper_series_day_day_no"):
            op.drop_index("ix_paper_series_day_day_no", table_name="paper_series_day")
        if _index_exists("paper_series_day", "ix_paper_series_day_series_id"):
            op.drop_index("ix_paper_series_day_series_id", table_name="paper_series_day")
        op.drop_table("paper_series_day")

    if inspector.has_table("paper_series"):
        if _index_exists("paper_series", "ix_paper_series_created_by"):
            op.drop_index("ix_paper_series_created_by", table_name="paper_series")
        op.drop_table("paper_series")
