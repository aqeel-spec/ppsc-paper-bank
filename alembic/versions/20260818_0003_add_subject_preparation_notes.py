"""add subject preparation notes tables

Revision ID: 20260818_0003
Revises: 20260818_0002
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0003"
down_revision = "20260818_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("subject_preparation_notes"):
        op.create_table(
            "subject_preparation_notes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=False),
            sa.Column("format", sa.String(length=20), nullable=False, server_default="md"),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("file_url", sa.String(length=500), nullable=True),
            sa.Column("content_markdown", sa.Text(), nullable=True),
            sa.Column("content_text", sa.Text(), nullable=True),
            sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_by", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    op.create_index(op.f("ix_subject_preparation_notes_title"), "subject_preparation_notes", ["title"], unique=False)
    op.create_index(op.f("ix_subject_preparation_notes_subject"), "subject_preparation_notes", ["subject"], unique=False)
    op.create_index(op.f("ix_subject_preparation_notes_format"), "subject_preparation_notes", ["format"], unique=False)
    op.create_index(op.f("ix_subject_preparation_notes_is_visible"), "subject_preparation_notes", ["is_visible"], unique=False)
    op.create_index(op.f("ix_subject_preparation_notes_created_by"), "subject_preparation_notes", ["created_by"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("subject_preparation_notes"):
        op.drop_index(op.f("ix_subject_preparation_notes_created_by"), table_name="subject_preparation_notes")
        op.drop_index(op.f("ix_subject_preparation_notes_is_visible"), table_name="subject_preparation_notes")
        op.drop_index(op.f("ix_subject_preparation_notes_format"), table_name="subject_preparation_notes")
        op.drop_index(op.f("ix_subject_preparation_notes_subject"), table_name="subject_preparation_notes")
        op.drop_index(op.f("ix_subject_preparation_notes_title"), table_name="subject_preparation_notes")
        op.drop_table("subject_preparation_notes")
