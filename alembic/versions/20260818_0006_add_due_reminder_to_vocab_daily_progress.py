"""add due reminder timestamp to vocab daily progress

Revision ID: 20260818_0006
Revises: 20260818_0005
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0006"
down_revision = "20260818_0005"
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("vocab_daily_progress") and not _column_exists(inspector, "vocab_daily_progress", "due_reminder_sent_at"):
        op.add_column(
            "vocab_daily_progress",
            sa.Column("due_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("vocab_daily_progress") and _column_exists(inspector, "vocab_daily_progress", "due_reminder_sent_at"):
        op.drop_column("vocab_daily_progress", "due_reminder_sent_at")
