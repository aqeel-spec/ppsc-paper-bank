"""add extra vocab fields

Revision ID: 20260818_0004
Revises: 20260818_0003
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0004"
down_revision = "20260818_0003"
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("words"):
        return

    if not _column_exists(inspector, "words", "relevant_meaning"):
        op.add_column("words", sa.Column("relevant_meaning", sa.Text(), nullable=True))

    if not _column_exists(inspector, "words", "synonyms"):
        op.add_column("words", sa.Column("synonyms", sa.Text(), nullable=True))

    if not _column_exists(inspector, "words", "antonyms"):
        op.add_column("words", sa.Column("antonyms", sa.Text(), nullable=True))

    if not _column_exists(inspector, "words", "tags"):
        op.add_column("words", sa.Column("tags", sa.Text(), nullable=True))

    # Refresh inspector after potential schema changes.
    inspector = sa.inspect(bind)
    if not _index_exists(inspector, "words", op.f("ix_words_tags")):
        op.create_index(op.f("ix_words_tags"), "words", ["tags"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("words"):
        return

    if _index_exists(inspector, "words", op.f("ix_words_tags")):
        op.drop_index(op.f("ix_words_tags"), table_name="words")

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "words", "tags"):
        op.drop_column("words", "tags")

    if _column_exists(inspector, "words", "antonyms"):
        op.drop_column("words", "antonyms")

    if _column_exists(inspector, "words", "synonyms"):
        op.drop_column("words", "synonyms")

    if _column_exists(inspector, "words", "relevant_meaning"):
        op.drop_column("words", "relevant_meaning")
