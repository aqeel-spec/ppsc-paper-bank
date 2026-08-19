"""add news and current affairs tables

Revision ID: 20260819_0008
Revises: 20260818_0007
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0008"
down_revision = "20260818_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("news_articles"):
        op.create_table(
            "news_articles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("section", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("image_url", sa.String(length=1000), nullable=True),
            sa.Column("audio_url", sa.String(length=1000), nullable=True),
            sa.Column("audio_cues_json", sa.Text(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("author", sa.String(length=255), nullable=True),
            sa.Column("body_text", sa.Text(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="fresh"),
            sa.Column("is_current_affairs", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_news_articles_id", "news_articles", ["id"])
        op.create_index("ix_news_articles_source", "news_articles", ["source"])
        op.create_index("ix_news_articles_section", "news_articles", ["section"])
        op.create_index("ix_news_articles_title", "news_articles", ["title"])
        op.create_index("ix_news_articles_url", "news_articles", ["url"], unique=True)
        op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"])
        op.create_index("ix_news_articles_is_current_affairs", "news_articles", ["is_current_affairs"])

    if not inspector.has_table("news_mcqs"):
        op.create_table(
            "news_mcqs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("article_id", sa.String(length=36), nullable=True),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("option_1", sa.String(length=500), nullable=False),
            sa.Column("option_2", sa.String(length=500), nullable=False),
            sa.Column("option_3", sa.String(length=500), nullable=False),
            sa.Column("option_4", sa.String(length=500), nullable=False),
            sa.Column("correct_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("correct_answer", sa.String(length=500), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=100), nullable=False, server_default="Current Affairs"),
            sa.Column("difficulty", sa.String(length=50), nullable=False, server_default="medium"),
            sa.Column("target_date", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_news_mcqs_id", "news_mcqs", ["id"])
        op.create_index("ix_news_mcqs_article_id", "news_mcqs", ["article_id"])
        op.create_index("ix_news_mcqs_category", "news_mcqs", ["category"])
        op.create_index("ix_news_mcqs_target_date", "news_mcqs", ["target_date"])

    if not inspector.has_table("news_vocabs"):
        op.create_table(
            "news_vocabs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("article_id", sa.String(length=36), nullable=True),
            sa.Column("word", sa.String(length=100), nullable=False),
            sa.Column("phonetic", sa.String(length=100), nullable=True),
            sa.Column("part_of_speech", sa.String(length=50), nullable=True),
            sa.Column("css_meaning", sa.Text(), nullable=False),
            sa.Column("synonyms", sa.Text(), nullable=True),
            sa.Column("antonyms", sa.Text(), nullable=True),
            sa.Column("context_in_article", sa.Text(), nullable=True),
            sa.Column("css_usage_example", sa.Text(), nullable=True),
            sa.Column("target_date", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_news_vocabs_id", "news_vocabs", ["id"])
        op.create_index("ix_news_vocabs_article_id", "news_vocabs", ["article_id"])
        op.create_index("ix_news_vocabs_word", "news_vocabs", ["word"])
        op.create_index("ix_news_vocabs_target_date", "news_vocabs", ["target_date"])

    if not inspector.has_table("news_pov_analyses"):
        op.create_table(
            "news_pov_analyses",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("article_id", sa.String(length=36), nullable=False),
            sa.Column("article_title", sa.String(length=500), nullable=False),
            sa.Column("author", sa.String(length=255), nullable=True),
            sa.Column("theme", sa.String(length=255), nullable=False),
            sa.Column("relevant_papers_json", sa.Text(), nullable=True),
            sa.Column("central_thesis", sa.Text(), nullable=False),
            sa.Column("key_arguments_json", sa.Text(), nullable=True),
            sa.Column("policy_recommendations_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_news_pov_analyses_id", "news_pov_analyses", ["id"])
        op.create_index("ix_news_pov_analyses_article_id", "news_pov_analyses", ["article_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("news_pov_analyses"):
        op.drop_table("news_pov_analyses")

    if inspector.has_table("news_vocabs"):
        op.drop_table("news_vocabs")

    if inspector.has_table("news_mcqs"):
        op.drop_table("news_mcqs")

    if inspector.has_table("news_articles"):
        op.drop_table("news_articles")
