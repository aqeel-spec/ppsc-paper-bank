"""add vocab tables

Revision ID: 20260818_0002
Revises: 20260416_0001
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0002"
down_revision = "20260416_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("words"):
        op.create_table(
            "words",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("word", sa.String(length=255), nullable=False),
            sa.Column("meaning", sa.Text(), nullable=False),
            sa.Column("sentence", sa.Text(), nullable=True),
            sa.Column("hook", sa.Text(), nullable=True),
            sa.Column("box", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("next_review", sa.DateTime(timezone=True), nullable=False),
            sa.Column("scheduled_date", sa.Date(), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("revision_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    op.create_index(op.f("ix_words_word"), "words", ["word"], unique=False)
    op.create_index(op.f("ix_words_next_review"), "words", ["next_review"], unique=False)
    op.create_index(op.f("ix_words_scheduled_date"), "words", ["scheduled_date"], unique=False)

    if not inspector.has_table("day_plans"):
        op.create_table(
            "day_plans",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("date", sa.Date(), nullable=False, unique=True),
            sa.Column("target_count", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("due_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    op.create_index(op.f("ix_day_plans_date"), "day_plans", ["date"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("day_plans"):
        op.drop_index(op.f("ix_day_plans_date"), table_name="day_plans")
        op.drop_table("day_plans")

    if inspector.has_table("words"):
        op.drop_index(op.f("ix_words_scheduled_date"), table_name="words")
        op.drop_index(op.f("ix_words_next_review"), table_name="words")
        op.drop_index(op.f("ix_words_word"), table_name="words")
        op.drop_table("words")
