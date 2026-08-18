"""add vocab ai explanations and quiz results tables

Revision ID: 20260818_0007
Revises: 20260818_0006
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0007"
down_revision = "20260818_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("vocab_ai_explanations"):
        op.create_table(
            "vocab_ai_explanations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("card_id", sa.String(length=100), nullable=True),
            sa.Column("word", sa.String(length=100), nullable=False),
            sa.Column("user_prompt", sa.Text(), nullable=False),
            sa.Column("ai_response", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_vocab_ai_explanations_id", "vocab_ai_explanations", ["id"])
        op.create_index("ix_vocab_ai_explanations_user_id", "vocab_ai_explanations", ["user_id"])
        op.create_index("ix_vocab_ai_explanations_card_id", "vocab_ai_explanations", ["card_id"])
        op.create_index("ix_vocab_ai_explanations_word", "vocab_ai_explanations", ["word"])

    if not inspector.has_table("vocab_quiz_results"):
        op.create_table(
            "vocab_quiz_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=100), nullable=False),
            sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accuracy", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("voice_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_vocab_quiz_results_id", "vocab_quiz_results", ["id"])
        op.create_index("ix_vocab_quiz_results_user_id", "vocab_quiz_results", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("vocab_quiz_results"):
        op.drop_table("vocab_quiz_results")

    if inspector.has_table("vocab_ai_explanations"):
        op.drop_table("vocab_ai_explanations")
